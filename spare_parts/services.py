# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/spare_parts/services.py
"""
Business logic services for the spare parts and delivery note
module.
Contains GeminiVisionExtractionService: extracts structured supplier
delivery note data (supplier, delivery number/date, line items)
from a photo or PDF using Gemini Vision via the shared
ai_services.gemini_client helper.

---

Servicios de lógica de negocio para el módulo de albaranes y
repuestos.
Contiene GeminiVisionExtractionService: extrae datos estructurados
de un albarán de proveedor (proveedor, número/fecha de albarán,
líneas de artículo) a partir de una foto o PDF usando Gemini Vision
a través del helper compartido ai_services.gemini_client.
"""
import logging
import pathlib
import re
import unicodedata
from decimal import Decimal, InvalidOperation
from typing import Optional

from django.db import transaction
from django.utils.timezone import now
from google.genai import types
from pydantic import BaseModel, Field

from ai_services.gemini_client import (
    DEFAULT_MODEL,
    get_gemini_client,
    get_request_config,
)
from fleet.models import MachineAsset

# Reuses the machine-code normaliser already validated in
# work_order_processor (Hito 8) for the historic PDF work-order
# reader, per the DRY directive (annex H10, section 3.1, step 4).
# ---
# Reutiliza el normalizador de código de máquina ya validado en
# work_order_processor (Hito 8) para el lector de PDF histórico de
# partes de trabajo, según la directriz DRY (anexo H10, sección 3.1,
# paso 4).
from work_order_processor.services import (
    _normalise_machine_code,
    _resolve_machine_asset,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Structured extraction schema (Pydantic) / Schema de extracción (Pydantic)
# ---------------------------------------------------------------------------

class DeliveryNoteLineExtraction(BaseModel):
    """
    Single line item extracted from a delivery note.
    ---
    Línea individual de artículo extraída de un albarán.
    """

    line_number: int = Field(
        description='Número de orden de la línea dentro del albarán, '
                     'empezando en 1.'
    )
    reference: Optional[str] = Field(
        default=None,
        description='Referencia o código del artículo, si figura en '
                     'el albarán. Null si no aparece.',
    )
    description: str = Field(
        description='Descripción del artículo tal como figura en el '
                     'albarán.'
    )
    quantity: Optional[str] = Field(
        default=None,
        description='Cantidad del artículo como texto numérico '
                     '(ej. "3", "1.5"). Null si el artículo es '
                     'incontable o la cantidad no es legible.',
    )
    unit_price: Optional[str] = Field(
        default=None,
        description='Precio unitario como texto numérico (ej. '
                     '"12.50"). Null si no figura en el albarán.',
    )
    total_price: Optional[str] = Field(
        default=None,
        description='Precio total de la línea como texto numérico. '
                     'Null si no figura en el albarán.',
    )
    # Sin machine_code_raw por línea desde S015 (H10, primer punto de
    # la hoja de ruta): confirmado por Miguel Ángel, la asignación es
    # SIEMPRE completa por albarán -- un único centro de gasto para
    # todas las líneas, nunca uno distinto por línea. Ver
    # DeliveryNoteExtraction.document_machine_code_raw más abajo.
    # ---
    # No per-line machine_code_raw since S015 (H10, first roadmap
    # point): confirmed by Miguel Ángel, assignment is ALWAYS whole-
    # document -- a single cost centre for every line, never a
    # different one per line. See
    # DeliveryNoteExtraction.document_machine_code_raw below.


class DeliveryNoteExtraction(BaseModel):
    """
    Full structured extraction result for a supplier delivery note.
    ---
    Resultado completo de extracción estructurada de un albarán de
    proveedor.
    """

    supplier_name: Optional[str] = Field(
        default=None,
        description='Nombre comercial del proveedor. Null si no es '
                     'legible.',
    )
    supplier_tax_id: Optional[str] = Field(
        default=None,
        description='NIF/CIF del proveedor, si figura en el '
                     'albarán. Null si no aparece.',
    )
    supplier_address: Optional[str] = Field(
        default=None,
        description='Dirección del proveedor, si figura en el '
                     'albarán. Null si no aparece.',
    )
    recipient_name: Optional[str] = Field(
        default=None,
        description='Razón social de la empresa DESTINATARIA del '
                     'albarán (a quién va dirigido, no el proveedor '
                     'que lo emite). Suele figurar en un bloque '
                     '"Cliente"/"Destino"/"Entregar a". Null si no es '
                     'legible.',
    )
    recipient_tax_id: Optional[str] = Field(
        default=None,
        description='NIF/CIF de la empresa destinataria del albarán. '
                     'Null si no aparece o no es legible.',
    )
    delivery_number: Optional[str] = Field(
        default=None,
        description='Número de albarán. Null si no es legible.',
    )
    delivery_date: Optional[str] = Field(
        default=None,
        description='Fecha del albarán en formato YYYY-MM-DD. Null '
                     'si no es legible o no figura.',
    )
    general_machine_code_raw: Optional[str] = Field(
        default=None,
        description='Código de máquina o centro de gasto (o nombre '
                     'de dependencia: "Almacén", "Taller Mecánico", '
                     '"Administración", etc.) al que va destinado TODO '
                     'el albarán. Búscalo en DOS sitios posibles, por '
                     'este orden de preferencia: '
                     '1) El campo impreso "Observaciones" o "Notas" de '
                     'la cabecera o el pie del documento. '
                     '2) Si el campo Observaciones/Notas está vacío o '
                     'no lo usa este proveedor, un código encerrado '
                     'entre almohadillas, asteriscos o comillas (ej. '
                     '"#B14#", "*B14*", "\\"B14\\"") dentro de la '
                     'descripción de una línea de artículo -- el '
                     'mismo carácter debe aparecer antes Y después del '
                     'código. Transcribe tal cual está escrito, sin '
                     'normalizar ni corregir, y sin los caracteres '
                     'delimitadores (ej. "#B14#" -> "B14"). Null si no '
                     'encuentras un código reconocible en ninguno de '
                     'los dos sitios.',
    )
    document_code_found_as_line_item: bool = Field(
        default=False,
        description='True si ves un fragmento que PARECE un código de '
                     'máquina/centro de gasto metido como si fuera una '
                     'línea de artículo o suelto en el documento, pero '
                     'SIN los delimitadores exigidos (almohadilla, '
                     'asterisco o comillas antes Y después) -- p. ej. '
                     'un código suelto sin marcar, o una fila con '
                     'categoría/familia "TEXTO"/"NOTA" que menciona '
                     'una máquina sin usar el patrón delimitado. En '
                     'ese caso, general_machine_code_raw debe quedar '
                     'en null (fuente ambigua, no válida) y este campo '
                     'debe ir en true, para que el sistema rechace el '
                     'albarán con un motivo preciso. False en '
                     'cualquier otro caso, incluido cuando el código '
                     'SÍ está correctamente delimitado (eso es un '
                     'general_machine_code_raw válido, no esto).',
    )
    general_warehouse_keyword_found: bool = Field(
        default=False,
        description='True si, y solo si, general_machine_code_raw ha '
                     'quedado en null (no hay código de máquina ni en '
                     'Observaciones ni delimitado en ninguna línea) '
                     'PERO el propio texto del albarán (cabecera, '
                     'Observaciones, o la descripción de alguna línea) '
                     'contiene la palabra "repuesto", "stock" o '
                     '"almacén" (o variantes con tilde/mayúsculas) '
                     'indicando que el envío completo va a almacén en '
                     'vez de a una máquina concreta. False si ya hay '
                     'general_machine_code_raw, o si no aparece '
                     'ninguna de esas palabras.',
    )
    handwritten_annotation_raw: Optional[str] = Field(
        default=None,
        description='SOLO informativo, NUNCA usado para asignación '
                     'automática (S025): cualquier anotación escrita '
                     'A MANO (bolígrafo, lápiz, rotulador -- nunca '
                     'texto impreso por el proveedor) que parezca '
                     'referirse a una máquina, matrícula o '
                     'departamento, aunque no cumpla ningún requisito '
                     'de validez (ej. "P14", "P21", "a67" escritos a '
                     'mano en un margen o círculo). Transcribe tal '
                     'cual está escrito. Si hay varias anotaciones a '
                     'mano distintas, sepáralas por coma. Null si no '
                     'hay ninguna anotación a mano visible en el '
                     'documento. Este campo existe para que un '
                     'operario humano pueda resolver la asignación a '
                     'mano con contexto, nunca para que el sistema '
                     'decida solo.',
    )
    lines: list[DeliveryNoteLineExtraction] = Field(
        default_factory=list,
        description='Líneas de artículo extraídas del albarán, en '
                     'el orden en que aparecen.',
    )


# ---------------------------------------------------------------------------
# Extraction prompt / Prompt de extracción
# ---------------------------------------------------------------------------
_EXTRACTION_PROMPT = """\
Eres un asistente experto en lectura de albaranes de proveedor de \
repuestos para maquinaria pesada y vehículos industriales (grúas, \
plataformas, carretillas, remolques).

Analiza la imagen o documento del albarán adjunto y extrae:

1. Datos del proveedor (quién EMITE el albarán): nombre comercial, \
NIF/CIF si aparece, dirección si aparece.
2. Datos del destinatario (a quién va dirigido el albarán, suele \
figurar en un bloque "Cliente" / "Destino" / "Entregar a" / \
"Facturar a"): razón social y NIF/CIF. Es una empresa distinta del \
proveedor -- no confundir ambos bloques.
3. Número de albarán y fecha (formato YYYY-MM-DD).
4. Cada línea de artículo REAL del albarán, en orden, con: número de \
línea, referencia (si tiene), descripción, cantidad, precio \
unitario, precio total. IMPORTANTE: algunos proveedores insertan \
líneas que NO son artículos reales -- p. ej. una fila con \
categoría/familia "TEXTO", "NOTA" u similar, precio 0 y sin \
descripción de producto -- para escribir una anotación en vez de \
vender algo. NO incluyas esas filas en la lista de líneas de \
artículo -- ver el punto 5 para qué hacer con su contenido.
5. El código de máquina o centro de gasto/dependencia al que va \
destinado TODO el albarán (norma vigente desde S015: un albarán \
completo va SIEMPRE a un único destino, nunca uno distinto por \
línea). Búscalo en los siguientes sitios posibles, por este orden de \
preferencia: \
  a) El campo impreso "Observaciones" o "Notas" de la cabecera o el \
pie del documento. Puede ser: \
  - Un código de máquina o matrícula (ej. "B14", "A-054", "G12"). \
  - El nombre de una dependencia o centro de gasto general de la \
empresa, escrito tal cual (ej. "ALMACEN", "TALLER MECANICO", \
"ADMINISTRACION", "DEPENDENCIAS", "ALMACEN HUELVA", "LOGISTICA", \
"TALLER ELEVACION", "ALMACEN ELEVACION"). \
Puede venir encerrada entre almohadillas (ej. "#B14#", \
"#TALLER MECANICO#") -- si ves ese patrón, transcribe únicamente el \
texto entre las almohadillas, sin ellas. \
  b) (AMPLIADO S025) Cualquier OTRO campo impreso ESTRUCTURADO del \
propio albarán, en la cabecera o el pie, con una etiqueta clara \
seguida de un valor -- ej. "Matrícula: A-67", "Máquina: B14", \
"Vehículo: G12", "Equipo: A-054", "Centro de coste: TALLER \
MECANICO". Estos campos son tan válidos como Observaciones/Notas -- \
mismo criterio: SOLO si está IMPRESO por el proveedor, con su propia \
etiqueta y valor, nunca una anotación suelta sin etiquetar. \
Transcribe únicamente el valor, sin la etiqueta. \
  c) Si ninguno de los campos estructurados de arriba (a, b) está \
presente o vacío, busca en la descripción de las líneas de artículo \
un código encerrado entre almohadillas, asteriscos o comillas -- el \
MISMO carácter debe aparecer antes Y después del código (ej. \
"#B14#", "*B14*", "\"B14\""). Transcribe únicamente el código, sin \
los caracteres delimitadores. \
Transcribe la anotación tal cual está escrita en el campo \
general_machine_code_raw, sin normalizar ni corregir. Reglas \
estrictas, sin excepción: \
  - SOLO cuenta si está IMPRESO/ESCRITO POR EL PROVEEDOR (en \
Observaciones/Notas, en un campo estructurado como en b, o \
delimitado en una línea como en c). Una anotación a mano \
(bolígrafo/lápiz/rotulador) sobre la foto, hecha por otra persona \
tras recibir el albarán, NUNCA es válida para este campo -- \
ignórala por completo aquí, no la transcribas ni la uses como \
general_machine_code_raw (ver el punto 7 más abajo para qué hacer \
con ella). \
  - Si ves un fragmento que PARECE un código pero NO está ni en \
Observaciones/Notas, ni en un campo estructurado etiquetado, ni \
correctamente delimitado (almohadilla, asterisco o comillas antes Y \
después) en una línea -- p. ej. un código suelto sin marcar, o una \
fila con categoría/familia "TEXTO"/"NOTA" que lo menciona sin \
delimitarlo -- general_machine_code_raw debe quedar en null y \
document_code_found_as_line_item debe ir en true -- no lo aceptes \
como válido bajo ningún concepto, solo se reporta para que el \
sistema explique el motivo del rechazo. \
Si no encuentras ningún código reconocible en ninguno de los sitios \
de arriba, deja general_machine_code_raw en null y \
document_code_found_as_line_item en false.
6. SOLO si general_machine_code_raw ha quedado en null (no hay \
código de máquina en Observaciones ni delimitado en ninguna línea): \
comprueba si el propio texto del albarán (cabecera, Observaciones, o \
la descripción de alguna línea) contiene la palabra "repuesto", \
"stock" o "almacén" (con o sin tilde, en cualquier mayúscula/ \
minúscula) indicando que el envío completo va a almacén general en \
vez de a una máquina concreta. Si es así, general_warehouse_keyword_found \
debe ir en true. Si ya hay general_machine_code_raw, o si no aparece \
ninguna de esas palabras, general_warehouse_keyword_found debe ir en \
false.
7. (AMPLIADO S025) handwritten_annotation_raw: revisa TODO el \
documento en busca de cualquier anotación escrita A MANO (bolígrafo, \
lápiz, rotulador -- nunca texto impreso por el proveedor) que \
parezca referirse a una máquina, matrícula o departamento, aunque no \
cumpla ningún requisito de validez del punto 5 (ej. un código suelto \
en un margen, dentro de un círculo, subrayado, etc.). Transcribe tal \
cual está escrito -- SOLO para que un operario humano la use como \
pista al asignar la máquina a mano, NUNCA para asignación \
automática. Si hay varias anotaciones a mano distintas o dudosas, \
transcribe todas separadas por coma. Null si no ves ninguna \
anotación a mano en el documento. Esto es independiente e \
INCLUSO SI general_machine_code_raw ya tiene un valor válido -- \
repórtalo igualmente si lo ves, para que quede constancia por si el \
operario lo necesita.

No inventes datos que no sean legibles en el documento -- usa null \
en los campos opcionales cuando no puedas leerlos con certeza. Los \
precios y cantidades devuélvelos como texto numérico simple (sin \
símbolo de moneda, usando punto como separador decimal).
"""


class GeminiVisionExtractionService:
    """
    Extracts structured data from a supplier delivery note (photo or
    PDF) using Gemini Vision via the shared ai_services.gemini_client
    helper. Uses gemini-3.5-flash (Directriz 4.1, mandatory for new
    code as of S001-H10 — see doc-master-enterprisebot section 4.1.1
    for the gemini-2.5-flash migration debt this avoids incurring).

    ---

    Extrae datos estructurados de un albarán de proveedor (foto o
    PDF) usando Gemini Vision a través del helper compartido
    ai_services.gemini_client. Usa gemini-3.5-flash (Directriz 4.1,
    obligatorio para código nuevo desde S001-H10 — ver
    doc-master-enterprisebot sección 4.1.1 para la deuda de
    migración de gemini-2.5-flash que esto evita incurrir).
    """

    # MIME types accepted for delivery note ingestion.
    # Tipos MIME aceptados para la ingesta de albaranes.
    _MIME_TYPES = {
        '.pdf': 'application/pdf',
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.png': 'image/png',
        '.webp': 'image/webp',
    }

    def __init__(self, model: str = DEFAULT_MODEL):
        """
        Args:
            model: Gemini model ID to use for extraction. Defaults
                to ai_services.gemini_client.DEFAULT_MODEL
                (gemini-3.5-flash).
        ---
        Args:
            model: ID del modelo Gemini a usar para la extracción.
                Por defecto ai_services.gemini_client.DEFAULT_MODEL
                (gemini-3.5-flash).
        """
        self._model = model

    def extract(self, file_path: str) -> DeliveryNoteExtraction:
        """
        Sends the delivery note file at file_path to Gemini Vision
        and returns the structured extraction result.

        Args:
            file_path: Absolute path to the photo or PDF file on
                disk (already saved, e.g. via Django's FileField
                .path).

        Raises:
            ValueError: if the file extension is not a supported
                MIME type.

        ---

        Envía el archivo de albarán en file_path a Gemini Vision y
        devuelve el resultado de extracción estructurado.

        Args:
            file_path: Ruta absoluta al archivo de foto o PDF en
                disco (ya guardado, p. ej. vía .path de un
                FileField de Django).

        Raises:
            ValueError: si la extensión del archivo no es un tipo
                MIME soportado.
        """
        path = pathlib.Path(file_path)
        mime_type = self._MIME_TYPES.get(path.suffix.lower())
        if mime_type is None:
            raise ValueError(
                f'Extensión no soportada para extracción de '
                f'albarán: {path.suffix!r}. Tipos válidos: '
                f'{sorted(self._MIME_TYPES)}.'
            )

        client = get_gemini_client()
        request_config = get_request_config()

        file_part = types.Part.from_bytes(
            data=path.read_bytes(),
            mime_type=mime_type,
        )

        generation_config = types.GenerateContentConfig(
            http_options=request_config.http_options,
            response_mime_type='application/json',
            response_schema=DeliveryNoteExtraction,
        )

        logger.info(
            '# Enviando albarán a Gemini Vision (modelo=%s, '
            'archivo=%s).',
            self._model, path.name,
        )

        response = client.models.generate_content(
            model=self._model,
            contents=[file_part, _EXTRACTION_PROMPT],
            config=generation_config,
        )

        extraction = DeliveryNoteExtraction.model_validate_json(
            response.text
        )

        logger.info(
            '# Extracción de albarán completada: proveedor=%s, '
            '%d línea(s).',
            extraction.supplier_name, len(extraction.lines),
        )

        return extraction


def parse_decimal(value: Optional[str]) -> Optional[Decimal]:
    """
    Safely parses a numeric string extracted by Gemini into a
    Decimal, returning None if the value is missing or not
    parseable. Used when populating DeliveryNoteLine / SparePartEntry
    numeric fields from a DeliveryNoteLineExtraction.

    ---

    Parsea de forma segura un texto numérico extraído por Gemini a
    Decimal, devolviendo None si el valor falta o no es parseable.
    Se usa al poblar los campos numéricos de DeliveryNoteLine /
    SparePartEntry desde una DeliveryNoteLineExtraction.
    """
    if not value:
        return None
    try:
        return Decimal(value)
    except (InvalidOperation, ValueError):
        logger.warning(
            '# Valor numérico no parseable en extracción de '
            'albarán: %r.',
            value,
        )
        return None


# ---------------------------------------------------------------------------
# Recipient company resolution / Resolución de empresa destinataria
# (Annex H10, TAREA INMEDIATA punto 1, S004)
# ---------------------------------------------------------------------------

# Confirmed by Miguel Ángel in S004: only these three group companies
# receive supplier delivery notes today. Keyed by tax ID (the only stable
# identifier -- the same company appears in fleet.MachineAsset under
# several free-text name variants). New entries are added here as new
# recipient companies are encountered, same organic-growth philosophy as
# the MachineAsset company_code catalogue.
# ---
# Confirmado por Miguel Ángel en S004: solo estas tres empresas del grupo
# reciben albaranes de proveedor hoy. Indexado por CIF (el único
# identificador estable -- la misma empresa aparece en fleet.MachineAsset
# bajo varias variantes de texto libre). Se añaden entradas nuevas aquí a
# medida que aparezcan nuevas empresas destinatarias, misma filosofía de
# crecimiento orgánico que el catálogo company_code de MachineAsset.
_RECIPIENT_TAX_ID_TO_COMPANY_CODE = {
    'B29405040': 'GRA',  # Gruas Adolfo Alvarez, S.L.
    'B92493022': 'TRA',  # Transgrual, S.L.
    'B93261824': 'GRG',  # Asistencia y Gruas Granada, S.L.
}


def _normalise_tax_id(raw: Optional[str]) -> str:
    """
    Uppercases and strips spaces/dashes from a tax ID for lookup.
    ---
    Pasa a mayúsculas y elimina espacios/guiones de un CIF para su
    búsqueda.
    """
    if not raw:
        return ''
    return re.sub(r'[\s\-.]', '', raw.strip().upper())


def _normalise_description(raw: Optional[str]) -> str:
    """
    Lowercases and collapses whitespace in a spare-part description,
    for case-insensitive comparison between an ad-hoc warehouse entry
    (registered by a mechanic without knowing the supplier's exact
    wording) and a delivery-note line's description. Confirmed by
    Miguel Ángel (2026-07-07): normalise to lowercase for these
    comparisons.

    Does not strip accents (unlike _normalise_alias_text, used for
    cost-centre aliases) -- a spare-part description is free text
    written by a human each time, and over-aggressive normalisation
    risks matching two genuinely different parts. Kept intentionally
    conservative; can be revisited if real-world data shows accent
    variants causing missed matches.

    ---

    Pasa a minúsculas y colapsa espacios en una descripción de
    repuesto, para comparar sin distinguir mayúsculas entre una
    entrada de almacén ad-hoc (dada de alta por un mecánico sin
    conocer la redacción exacta del proveedor) y la descripción de
    una línea de albarán. Confirmado por Miguel Ángel (2026-07-07):
    normalizar a minúsculas para estas comparaciones.

    No elimina acentos (a diferencia de _normalise_alias_text, usado
    para alias de centro de gasto) -- la descripción de un repuesto es
    texto libre escrito por una persona cada vez, y una normalización
    demasiado agresiva arriesga emparejar dos piezas realmente
    distintas. Mantenido intencionadamente conservador; revisable si
    los datos reales muestran variantes de acentuación que provocan
    emparejamientos perdidos.
    """
    if not raw:
        return ''
    return re.sub(r'\s+', ' ', raw.strip().lower())


def resolve_recipient_company_code(raw_tax_id: Optional[str]) -> str:
    """
    Resolves the raw recipient tax ID extracted from a delivery note
    into the short company_code used by fleet.MachineAsset. Returns
    '' when the tax ID is missing or not yet in the catalogue -- the
    line stays for manual review rather than guessing.

    ---

    Resuelve el CIF destinatario extraído del albarán al
    company_code corto usado por fleet.MachineAsset. Devuelve '' si
    el CIF falta o todavía no está en el catálogo -- se deja para
    revisión manual en vez de adivinar.
    """
    return _RECIPIENT_TAX_ID_TO_COMPANY_CODE.get(
        _normalise_tax_id(raw_tax_id), ''
    )


def resolve_or_create_supplier(company, raw_tax_id: Optional[str], name: str = ''):
    """
    Resuelve un Supplier de tipo EXTERNAL para `company` a partir del
    CIF del albarán -- confirmado por Miguel Ángel (2026-07-07):
    siempre por CIF, nunca por nombre, mismo principio ya aplicado en
    resolve_recipient_company_code() para la empresa destinataria.
    Si no hay ningún Supplier con ese CIF (normalizado, sin espacios/
    guiones -- ver _normalise_tax_id) para la empresa, se crea uno
    nuevo automáticamente.

    Sin CIF (raw_tax_id vacío o no extraído) no se resuelve ni se
    crea nada -- devuelve None, y la línea/entrada queda con
    supplier=None, igual que hasta ahora (los campos de texto libre
    supplier_name/supplier_tax_id siguen siendo el único rastro en
    ese caso). Evita crear proveedores duplicados o mal identificados
    a partir de una coincidencia de nombre poco fiable.

    No aplicado retroactivamente a SparePartEntry ya existentes --
    confirmado por Miguel Ángel: no hace falta, los datos de prueba
    actuales se borrarán al final de las pruebas.

    ---

    Resolves an EXTERNAL-type Supplier for `company` from the
    delivery note's tax ID -- confirmed by Miguel Ángel (2026-07-07):
    always by tax ID, never by name, same principle already applied
    in resolve_recipient_company_code() for the recipient company. If
    no Supplier with that tax ID (normalised, no spaces/dashes -- see
    _normalise_tax_id) exists for the company, a new one is created
    automatically.

    Without a tax ID (raw_tax_id empty or not extracted) nothing is
    resolved or created -- returns None, and the line/entry stays
    with supplier=None, same as before (the supplier_name/
    supplier_tax_id free-text fields remain the only trace in that
    case). Avoids creating duplicate or misidentified suppliers from
    an unreliable name match.

    Not applied retroactively to existing SparePartEntry records --
    confirmed by Miguel Ángel: not needed, current test data will be
    deleted at the end of testing.
    """
    from .models import Supplier

    normalised = _normalise_tax_id(raw_tax_id)
    if not normalised:
        return None

    for candidate in Supplier.objects.filter(
        company=company,
        supplier_type=Supplier.TYPE_EXTERNAL,
    ).exclude(tax_id=''):
        if _normalise_tax_id(candidate.tax_id) == normalised:
            return candidate

    return Supplier.objects.create(
        company=company,
        supplier_type=Supplier.TYPE_EXTERNAL,
        name=(name or raw_tax_id or 'Proveedor sin nombre').strip(),
        tax_id=(raw_tax_id or '').strip(),
    )


# ---------------------------------------------------------------------------
# General cost-centre resolution / Resolución de centro de gasto general
# (Annex H10, TAREA INMEDIATA punto 2, S004)
# ---------------------------------------------------------------------------

# Prefix shared by every MachineAsset that represents an aggregate company
# cost centre (warehouse, workshop, logistics...) rather than an
# individual physical machine -- e.g. EMPRESA_TALLER_MECANICO,
# EMPRESA_ALMACEN_HUELVA. Confirmed empirically against the real catalogue
# in S004 (panel filtrado por "EMP").
# ---
# Prefijo compartido por todo MachineAsset que representa un centro de
# gasto agregado de empresa (almacén, taller, logística...) en vez de una
# máquina física individual -- ej. EMPRESA_TALLER_MECANICO,
# EMPRESA_ALMACEN_HUELVA. Confirmado empíricamente contra el catálogo real
# en S004 (panel filtrado por "EMP").
_COMPANY_COST_CENTER_PREFIX = 'EMPRESA_'


def _normalise_alias_text(raw: str) -> str:
    """
    Uppercases, strips accents and collapses whitespace, for
    accent/case-insensitive comparison of free-text cost-centre
    names (e.g. "Almacén Huelva" == "ALMACEN HUELVA").
    ---
    Pasa a mayúsculas, elimina acentos y colapsa espacios, para
    comparar sin distinguir acentos/mayúsculas nombres de centro de
    gasto en texto libre (ej. "Almacén Huelva" == "ALMACEN HUELVA").
    """
    text = unicodedata.normalize('NFD', raw.strip().upper())
    text = ''.join(c for c in text if unicodedata.category(c) != 'Mn')
    return re.sub(r'\s+', ' ', text).strip()


def _resolve_company_cost_center(
    raw_code: str, company,
) -> Optional[MachineAsset]:
    """
    Resolves a general (non-machine) cost-centre annotation -- e.g.
    "TALLER MECANICO", "Almacén Huelva" -- against the MachineAsset
    rows that represent aggregate company cost centres (code prefix
    EMPRESA_). Comparison is accent- and case-insensitive on both
    sides, since the annotation is handwritten free text and the
    catalogue code may itself carry accents (ej. EMPRESA_LOGÍSTICA).

    ---

    Resuelve una anotación de centro de gasto general (no una
    máquina) -- ej. "TALLER MECANICO", "Almacén Huelva" -- contra
    las filas de MachineAsset que representan centros de gasto
    agregados de empresa (prefijo de código EMPRESA_). La
    comparación no distingue acentos ni mayúsculas en ninguno de los
    dos lados, ya que la anotación es texto libre manuscrito y el
    propio código del catálogo puede llevar acentos (ej.
    EMPRESA_LOGÍSTICA).
    """
    target = _normalise_alias_text(raw_code)
    if not target:
        return None

    qs = MachineAsset.objects.filter(
        code__startswith=_COMPANY_COST_CENTER_PREFIX,
    )
    if company is not None:
        qs = qs.filter(company=company)

    for asset in qs:
        candidate = _normalise_alias_text(
            asset.code[len(_COMPANY_COST_CENTER_PREFIX):].replace('_', ' ')
        )
        if candidate == target:
            return asset

    return None


# ---------------------------------------------------------------------------
# Line assignment resolution / Resolución de asignación de línea
# (Annex H10, section 3.1, step 4-5)
# ---------------------------------------------------------------------------

_WAREHOUSE_CODE_ALIASES = {'ALM', 'AL', 'ALMACEN', 'ALMACÉN', 'WAREHOUSE'}


def resolve_line_assignment(raw_code: Optional[str], company):
    """
    Resolves a raw machine/warehouse code annotated on a delivery
    note line into an assignment_type + MachineAsset. Tries, in
    order: the WAREHOUSE alias list, a general company cost centre
    (EMPRESA_* MachineAsset rows, S004 TAREA INMEDIATA punto 2), and
    finally the individual-machine normaliser/resolver already
    validated in work_order_processor (Hito 8) per the DRY
    directive.

    Returns a tuple (assignment_type, machine) where assignment_type
    is one of 'WAREHOUSE', 'MACHINE', 'UNASSIGNED' and machine is the
    resolved MachineAsset or None.

    ---

    Resuelve un código bruto de máquina/almacén anotado en una línea
    de albarán a un assignment_type + MachineAsset. Prueba, en
    orden: la lista de alias WAREHOUSE, un centro de gasto general
    de empresa (filas MachineAsset EMPRESA_*, S004 TAREA INMEDIATA
    punto 2), y por último el normalizador/resolver de máquina
    individual ya validado en work_order_processor (Hito 8) según la
    directriz DRY.

    Devuelve una tupla (assignment_type, machine) donde
    assignment_type es 'WAREHOUSE', 'MACHINE' o 'UNASSIGNED', y
    machine es el MachineAsset resuelto o None.
    """
    if not raw_code or not raw_code.strip():
        return 'UNASSIGNED', None

    stripped_upper = raw_code.strip().upper()
    if stripped_upper in _WAREHOUSE_CODE_ALIASES:
        return 'WAREHOUSE', None

    cost_center = _resolve_company_cost_center(raw_code, company)
    if cost_center is not None:
        return 'MACHINE', cost_center

    normalised = _normalise_machine_code(raw_code)
    machine = _resolve_machine_asset(normalised, company=company)
    if machine is not None:
        return 'MACHINE', machine

    return 'UNASSIGNED', None


def resolve_document_assignment(raw_code, warehouse_keyword_found, company):
    """
    Resolves the single whole-document destination (S015: always one
    per document, never one per line) combining, in priority order:
    (1) an explicit machine/cost-centre code (raw_code, resolved via
    resolve_line_assignment -- from Observaciones or a delimited line
    per S020), and (2) the S020 keyword fallback: if no code was
    found at all, but the delivery note's own wording ("repuesto",
    "stock", "almacén") signals a warehouse destination, assigns
    WAREHOUSE undifferentiated -- confirmed by Miguel Ángel
    (2026-07-15): for now everything the supplier marks this way goes
    to the single WAREHOUSE bucket, with no distinction by workshop/
    family (Mecánico/Elevación/Huelva); that differentiation is
    deliberately deferred to a future session.

    Returns (assignment_type, machine), same contract as
    resolve_line_assignment.
    ---
    Resuelve el destino único de todo el albarán (S015: siempre uno
    por documento, nunca uno distinto por línea) combinando, por este
    orden de prioridad: (1) un código explícito de máquina/centro de
    gasto (raw_code, resuelto vía resolve_line_assignment -- desde
    Observaciones o delimitado en línea según S020), y (2) el
    fallback de palabra clave de S020: si no se encontró ningún
    código, pero el propio texto del albarán ("repuesto", "stock",
    "almacén") señala un destino de almacén, asigna WAREHOUSE sin
    diferenciar -- confirmado por Miguel Ángel (2026-07-15): de
    momento todo lo que el proveedor marque así va al mismo cajón
    WAREHOUSE, sin distinguir por taller/familia (Mecánico/Elevación/
    Huelva); esa diferenciación queda deliberadamente pospuesta a una
    sesión futura.

    Devuelve (assignment_type, machine), mismo contrato que
    resolve_line_assignment.
    """
    if raw_code and raw_code.strip():
        assignment_type, machine = resolve_line_assignment(raw_code, company)
        if assignment_type != 'UNASSIGNED':
            return assignment_type, machine

    if warehouse_keyword_found:
        return 'WAREHOUSE', None

    return 'UNASSIGNED', None


def validate_document_assignment(delivery_note, company):
    """
    Validates the mandatory whole-document assignment rule (annex
    H10, S015 roadmap point 1): every delivery note must carry
    exactly one machine/cost-centre code -- printed by the supplier
    in the document's own "Observaciones"/"Notas" field, OR (S020)
    delimited by #, * or " within an article line -- OR, absent any
    code, flagged as a warehouse destination via the "repuesto"/
    "stock"/"almacén" keyword fallback. No manual correction is
    allowed -- if the extraction doesn't meet this rule, the operator
    must re-upload a clearer photo instead of editing the data
    (confirmed by Miguel Ángel, S015).

    Returns a tuple (is_valid, reason, assignment_type, machine).
    reason is a human-readable Spanish string explaining the specific
    rejection cause, or None if is_valid is True. assignment_type/
    machine are the resolved target when is_valid, else
    ('UNASSIGNED', None).

    ---

    Valida la norma obligatoria de asignación completa por albarán
    (anexo H10, primer punto de la hoja de ruta de S015): todo
    albarán debe llevar exactamente un código de máquina/centro de
    gasto -- impreso por el proveedor en el propio campo
    "Observaciones"/"Notas" del documento, O (S020) delimitado con #,
    * o " dentro de una línea de artículo -- O, en ausencia de
    código, marcado como destino de almacén vía el fallback de
    palabra clave "repuesto"/"stock"/"almacén". No se admite
    corrección manual -- si la extracción no cumple esta norma, el
    operario debe volver a subir una foto más clara en vez de
    corregir el dato (confirmado por Miguel Ángel, S015).

    Devuelve una tupla (is_valid, reason, assignment_type, machine).
    reason es un texto en castellano legible explicando el motivo
    concreto de rechazo, o None si is_valid es True. assignment_type/
    machine son el destino resuelto cuando is_valid, si no
    ('UNASSIGNED', None).
    """
    extraction_raw = delivery_note.extraction_raw or {}

    if extraction_raw.get('document_code_found_as_line_item'):
        return (
            False,
            'El código de máquina/departamento aparece como si fuera '
            'un artículo del albarán, sin delimitar correctamente '
            '(almohadilla, asterisco o comillas antes y después) ni '
            'estar en el campo Observaciones. El proveedor debe '
            'anotarlo en Observaciones, o delimitarlo con #, * o " '
            'en la línea, antes de volver a fotografiarlo.',
            'UNASSIGNED', None,
        )

    raw_code = (delivery_note.general_machine_code_raw or '').strip()
    warehouse_keyword_found = bool(
        extraction_raw.get('general_warehouse_keyword_found')
    )

    if not raw_code and not warehouse_keyword_found:
        return (
            False,
            'Falta el código de máquina o departamento (en '
            'Observaciones o delimitado con #, * o " en una línea) y '
            'no se detecta ninguna palabra clave de almacén '
            '(repuesto/stock/almacén) en el albarán. El proveedor '
            'debe anotarlo antes de volver a fotografiarlo.',
            'UNASSIGNED', None,
        )

    assignment_type, machine = resolve_document_assignment(
        raw_code or None, warehouse_keyword_found, company,
    )
    if assignment_type == 'UNASSIGNED':
        return (
            False,
            f'El código «{raw_code}» leído en el albarán no se '
            f'reconoce como ninguna máquina ni departamento de la '
            f'empresa. Revisa que esté escrito correctamente en el '
            f'albarán físico y vuelve a fotografiarlo.',
            'UNASSIGNED', None,
        )

    return (True, None, assignment_type, machine)


def generate_internal_reference(company):
    """
    Generates the next sequential internal reference for a company,
    format 'REP-000001'. Internal reference is company-owned and
    stable across supplier changes -- confirmed by Miguel Ángel
    (2026-07-06): the supplier's own reference for the same physical
    part can change if the company switches suppliers, so the
    catalog must be identified by something the company controls,
    never by the supplier's nomenclature.

    Not fully race-safe under concurrent creation (single low-
    concurrency admin environment) -- if that becomes a real issue,
    replace with a per-company sequence table or
    select_for_update() on a counter row.

    ---

    Genera la siguiente referencia interna secuencial de una empresa,
    formato 'REP-000001'. La referencia interna es propiedad de la
    empresa y estable frente a cambios de proveedor -- confirmado por
    Miguel Ángel (2026-07-06): la referencia propia del proveedor
    para la misma pieza física puede cambiar si la empresa cambia de
    proveedor, así que el catálogo debe identificarse por algo que
    controla la empresa, nunca por la nomenclatura del proveedor.

    No es totalmente segura frente a concurrencia (entorno de un solo
    administrador, baja concurrencia) -- si eso llega a ser un
    problema real, sustituir por una tabla de secuencia por empresa o
    un select_for_update() sobre una fila contador.
    """
    from .models import SparePartEntry

    last = (
        SparePartEntry.objects
        .filter(company=company, internal_reference__startswith='REP-')
        .exclude(internal_reference='')
        .order_by('-internal_reference')
        .first()
    )
    if last and last.internal_reference[4:].isdigit():
        next_number = int(last.internal_reference[4:]) + 1
    else:
        next_number = 1
    return f'REP-{next_number:06d}'


def confirm_delivery_note(delivery_note, company_user):
    """
    Executes the delivery note assignment circuit described in annex
    H10, section 3.1, step 5, for every line of delivery_note whose
    assignment_type is WAREHOUSE or MACHINE. Lines left UNASSIGNED
    are skipped and reported back for manual review.

    WAREHOUSE lines: creates or updates (matched by company +
    reference when reference is set; falls back to matching an
    ad-hoc, supplier-less warehouse entry by normalised description --
    2026-07-07, see _normalise_description) a SparePartEntry with
    status=WAREHOUSE, sums stock_quantity, and records a
    StockMovement IN.

    MACHINE lines: looks up an open BreakdownTicket (OPEN /
    IN_PROGRESS) for the target machine; creates a SparePartEntry
    with status=PRE_ASSIGNED (limbo), attached to the ticket if one
    is open or directly to the machine otherwise, and records a
    StockMovement IN.

    Resolves (or creates, if none matches) a real Supplier record for
    the whole delivery note via resolve_or_create_supplier(), always
    by tax ID (2026-07-07, confirmed by Miguel Ángel) -- assigns it to
    every SparePartEntry.supplier created/updated here, alongside the
    existing supplier_name/supplier_tax_id free-text fields (kept
    untouched for historical trace). Not applied retroactively to
    entries from earlier sessions.

    All entries created here are countable (is_uncountable=False) —
    supplier delivery notes always state a quantity; uncountable
    stock levels are only set manually by mechanics at consumption
    time (annex H10, section 3.5, Caso C).

    Sets delivery_note.status = 'ASSIGNED' and delivery_note.supplier
    (2026-07-08, gap fix) on completion.

    Returns a dict with counts: warehouse, pre_assigned, unassigned.

    ---

    Ejecuta el circuito de asignación de albarán descrito en el
    anexo H10, sección 3.1, paso 5, para cada línea de delivery_note
    cuyo assignment_type sea WAREHOUSE o MACHINE. Las líneas que
    queden UNASSIGNED se omiten y se reportan para revisión manual.

    Líneas WAREHOUSE: crea o actualiza (emparejado por empresa +
    referencia cuando hay referencia; si no hay coincidencia, se
    intenta emparejar con una entrada ad-hoc de almacén sin proveedor
    conocido por descripción normalizada -- 2026-07-07, ver
    _normalise_description) un SparePartEntry con status=WAREHOUSE,
    suma stock_quantity, y registra un StockMovement IN.

    Líneas MACHINE: busca un BreakdownTicket abierto (OPEN /
    IN_PROGRESS) para la máquina destino; crea un SparePartEntry con
    status=PRE_ASSIGNED (limbo), vinculado al ticket si hay uno
    abierto o directamente a la máquina en caso contrario, y
    registra un StockMovement IN.

    Resuelve (o crea, si no coincide ninguno) un registro Supplier
    real para todo el albarán vía resolve_or_create_supplier(),
    siempre por CIF (2026-07-07, confirmado por Miguel Ángel) --
    lo asigna a cada SparePartEntry.supplier creado/actualizado aquí,
    junto a los campos de texto libre supplier_name/supplier_tax_id
    ya existentes (intactos, para rastro histórico). No se aplica
    retroactivamente a entradas de sesiones anteriores.

    Todas las entradas creadas aquí son contables
    (is_uncountable=False) — los albaranes de proveedor siempre
    indican una cantidad; los niveles incontables solo los establece
    manualmente el mecánico en el momento del consumo (anexo H10,
    sección 3.5, Caso C).

    Al finalizar establece delivery_note.status = 'ASSIGNED' y
    delivery_note.supplier (2026-07-08, fix del gap).

    Devuelve un diccionario con los contadores: warehouse,
    pre_assigned, unassigned.
    """
    from chat.models import BreakdownTicket

    from .models import SparePartEntry, StockMovement

    company = delivery_note.company
    counts = {'warehouse': 0, 'pre_assigned': 0, 'unassigned': 0}

    # Resolucion/alta del Supplier real, siempre por CIF -- confirmado
    # por Miguel Angel (2026-07-07). Una sola vez por albaran, no por
    # linea (el proveedor es el mismo para todas las lineas del mismo
    # albaran). None si no hay CIF extraido -- las lineas quedan solo
    # con los campos de texto libre, igual que hasta ahora.
    resolved_supplier = resolve_or_create_supplier(
        company, delivery_note.supplier_tax_id, delivery_note.supplier_name,
    )

    for line in delivery_note.lines.all():
        quantity = line.quantity or Decimal('0')

        if line.assignment_type == 'WAREHOUSE':
            entry = None
            if line.reference:
                entry = SparePartEntry.objects.filter(
                    company=company,
                    reference=line.reference,
                    status=SparePartEntry.STATUS_WAREHOUSE,
                ).first()
            if entry is None:
                # Segundo intento: repuestos dados de alta rapidamente
                # por los propios mecanicos desde el Almacen, sin
                # proveedor conocido todavia (reference='',
                # supplier=None) -- se emparejan por descripcion
                # normalizada (minusculas, espacios colapsados) con la
                # linea del primer albaran que documente el mismo
                # articulo. Confirmado por Miguel Angel (2026-07-07).
                normalised_desc = _normalise_description(line.description)
                if normalised_desc:
                    for candidate in SparePartEntry.objects.filter(
                        company=company,
                        status=SparePartEntry.STATUS_WAREHOUSE,
                        reference='',
                        supplier__isnull=True,
                    ):
                        if _normalise_description(candidate.description) == normalised_desc:
                            entry = candidate
                            break
            if entry is None:
                entry = SparePartEntry.objects.create(
                    company=company,
                    reference=line.reference,
                    internal_reference=generate_internal_reference(company),
                    description=line.description,
                    is_uncountable=False,
                    status=SparePartEntry.STATUS_WAREHOUSE,
                    origin_type=SparePartEntry.ORIGIN_SUPPLIER,
                    supplier=resolved_supplier,
                    supplier_name=delivery_note.supplier_name,
                    supplier_tax_id=delivery_note.supplier_tax_id,
                    purchase_unit_price=line.unit_price,
                    purchase_total_price=line.total_price,
                    source_delivery_note_line=line,
                )
            elif not entry.reference and line.reference:
                # Emparejado por descripcion (ad-hoc) -- aprende la
                # referencia real del proveedor para acelerar el
                # emparejamiento directo en futuros albaranes.
                entry.reference = line.reference
            entry.stock_quantity = (
                entry.stock_quantity or Decimal('0')
            ) + quantity
            entry.supplier = resolved_supplier
            entry.purchase_unit_price = line.unit_price
            entry.purchase_total_price = line.total_price
            entry.save()

            StockMovement.objects.create(
                spare_part_entry=entry,
                movement_type=StockMovement.MOVEMENT_IN,
                quantity=quantity,
                delivery_note_line=line,
                created_by=company_user,
                notes=(
                    f'Entrada por albarán '
                    f'{delivery_note.delivery_number or delivery_note.pk}.'
                ),
            )

            line.spare_part_entry = entry
            line.save(update_fields=['spare_part_entry'])
            counts['warehouse'] += 1

        elif line.assignment_type == 'MACHINE' and line.machine is not None:
            ticket = BreakdownTicket.objects.filter(
                machine=line.machine,
                status__in=['OPEN', 'IN_PROGRESS'],
            ).first()

            entry = SparePartEntry.objects.create(
                company=company,
                reference=line.reference,
                internal_reference=generate_internal_reference(company),
                description=line.description,
                is_uncountable=False,
                status=SparePartEntry.STATUS_PRE_ASSIGNED,
                machine=None if ticket else line.machine,
                breakdown_ticket=ticket,
                pre_assigned_at=now(),
                origin_type=SparePartEntry.ORIGIN_SUPPLIER,
                supplier=resolved_supplier,
                supplier_name=delivery_note.supplier_name,
                supplier_tax_id=delivery_note.supplier_tax_id,
                purchase_unit_price=line.unit_price,
                purchase_total_price=line.total_price,
                source_delivery_note_line=line,
            )

            StockMovement.objects.create(
                spare_part_entry=entry,
                movement_type=StockMovement.MOVEMENT_IN,
                quantity=quantity,
                machine=line.machine,
                breakdown_ticket=ticket,
                delivery_note_line=line,
                created_by=company_user,
                notes=(
                    f'Entrada por albarán '
                    f'{delivery_note.delivery_number or delivery_note.pk}.'
                ),
            )

            line.spare_part_entry = entry
            line.save(update_fields=['spare_part_entry'])
            counts['pre_assigned'] += 1

        else:
            counts['unassigned'] += 1

    delivery_note.status = 'ASSIGNED'
    delivery_note.processed_by = company_user
    delivery_note.supplier = resolved_supplier
    delivery_note.save(update_fields=['status', 'processed_by', 'supplier'])

    return counts


@transaction.atomic
def register_salvaged_entry(
    company, created_by, description, origin_machine,
    destination, is_uncountable=False, stock_quantity=None,
    stock_level=None, origin_work_order_entry_line=None,
    destination_machine=None, reference='',
):
    """
    H10 Paso 7 -- alta manual de una SparePartEntry recuperada por
    canibalización de otra máquina de la propia flota (anexo H10,
    seccion 3.6). Siempre iniciada desde spare_parts (responsable de
    almacen/logistica), nunca disparada automaticamente desde el
    parte de trabajo -- principio rector de separacion total entre
    parte y almacen, seccion 3.6.

    destination='WAREHOUSE': la entrada queda en almacen general
    (status=WAREHOUSE, sin machine/breakdown_ticket), lista para
    rectificar/reutilizar mas adelante.

    destination='PRE_ASSIGNED': ya se sabe que va para
    destination_machine (obligatorio en este caso). Reutiliza
    literalmente la misma resolucion de ticket que confirm_delivery_note()
    para las lineas MACHINE (busca un BreakdownTicket OPEN/IN_PROGRESS
    para destination_machine; si existe se engancha ahi, si no se
    pre-asigna directamente a la maquina) -- no la maquinaria mas
    elaborada de resolucion CHOOSE/ASK_REOPEN de chat.ticket_resolution,
    que es especifica del flujo de tareas del parte de trabajo
    (Paso 4-bis) y no aplica aqui (aqui no hay "tarea" que este
    generando el ticket, es un alta de almacen).

    origin_work_order_entry_line es opcional -- queda null para
    piezas ya retiradas de antiguo sin parte asociado en el sistema
    (seccion 3.6, punto 3).

    Genera un StockMovement SALVAGE. origin_type se fija a SALVAGED.

    ---

    H10 Paso 7 -- manual creation of a SparePartEntry recovered via
    cannibalisation of another machine in the company's own fleet
    (annex H10, section 3.6). Always initiated from spare_parts
    (warehouse/logistics responsible), never automatically triggered
    from the work order -- guiding principle of total separation
    between the work order and warehouse management, section 3.6.

    destination='WAREHOUSE': the entry stays in the general warehouse
    (status=WAREHOUSE, no machine/breakdown_ticket), ready to be
    rectified/reused later.

    destination='PRE_ASSIGNED': it is already known it will go to
    destination_machine (required in this case). Literally reuses the
    same ticket resolution as confirm_delivery_note() for MACHINE
    lines (looks up an open BreakdownTicket OPEN/IN_PROGRESS for
    destination_machine; if one exists it attaches there, otherwise
    it pre-assigns directly to the machine) -- not the more elaborate
    CHOOSE/ASK_REOPEN resolution machinery in chat.ticket_resolution,
    which is specific to the work-order task flow (Paso 4-bis) and
    does not apply here (there is no "task" generating the ticket,
    this is a warehouse intake).

    origin_work_order_entry_line is optional -- left null for parts
    already removed long ago with no associated part record in the
    system (section 3.6, point 3).

    Generates a StockMovement SALVAGE. origin_type is set to
    SALVAGED.
    """
    from chat.models import BreakdownTicket

    from .models import SparePartEntry, StockMovement

    if not description or not description.strip():
        raise ValueError('description es obligatorio.')

    if destination not in (
        SparePartEntry.STATUS_WAREHOUSE, SparePartEntry.STATUS_PRE_ASSIGNED,
    ):
        raise ValueError(
            "destination debe ser 'WAREHOUSE' o 'PRE_ASSIGNED'."
        )

    if destination == SparePartEntry.STATUS_PRE_ASSIGNED and destination_machine is None:
        raise ValueError(
            'destination_machine es obligatorio cuando destination=PRE_ASSIGNED.'
        )

    if is_uncountable:
        if stock_level not in StockAssignmentService.LEVEL_CHOICES:
            raise ValueError(
                'stock_level debe ser uno de FULL/MEDIUM/LOW/EMPTY '
                'para un repuesto incontable.'
            )
        entry_stock_quantity = Decimal('0')
        entry_stock_level = stock_level
    else:
        if stock_quantity is None or stock_quantity < 0:
            raise ValueError(
                'stock_quantity debe ser un numero >= 0 para un '
                'repuesto contable.'
            )
        entry_stock_quantity = Decimal(str(stock_quantity))
        entry_stock_level = ''

    machine = None
    ticket = None
    pre_assigned_at = None
    if destination == SparePartEntry.STATUS_PRE_ASSIGNED:
        ticket = BreakdownTicket.objects.filter(
            machine=destination_machine,
            status__in=['OPEN', 'IN_PROGRESS'],
        ).first()
        machine = None if ticket else destination_machine
        pre_assigned_at = now()

    entry = SparePartEntry.objects.create(
        company=company,
        reference=reference or '',
        internal_reference=generate_internal_reference(company),
        description=description.strip(),
        is_uncountable=is_uncountable,
        stock_quantity=entry_stock_quantity,
        stock_level=entry_stock_level,
        status=destination,
        machine=machine,
        breakdown_ticket=ticket,
        pre_assigned_at=pre_assigned_at,
        origin_type=SparePartEntry.ORIGIN_SALVAGED,
        origin_machine=origin_machine,
        origin_work_order_entry_line=origin_work_order_entry_line,
    )

    StockMovement.objects.create(
        spare_part_entry=entry,
        movement_type=StockMovement.MOVEMENT_SALVAGE,
        quantity=entry_stock_quantity,
        level_after=entry_stock_level,
        machine=machine,
        breakdown_ticket=ticket,
        created_by=created_by,
        notes=(
            f'Entrada por canibalización de la máquina '
            f'{origin_machine.code}.'
        ),
    )

    return entry


@transaction.atomic
def register_uninventoried_warehouse_stock(
    company, created_by, description, is_uncountable=False,
    stock_quantity=None, stock_level=None,
):
    """
    Alta rápida en el almacén digital de un repuesto que un mecánico
    acaba de coger del almacén físico y que todavía no estaba
    inventoriado -- gap señalado por Miguel Ángel (2026-07-07):
    "faltaba dar de alta repuestos por los mecánicos cuando van
    cogiendo del almacén y aún no se han inventariado". No requiere
    ni referencia de proveedor ni CIF -- se dejan intencionadamente
    sin resolver (reference='', supplier=None): en cuanto llegue un
    albarán que documente el mismo artículo, confirm_delivery_note()
    lo empareja automáticamente por descripción normalizada
    (_normalise_description) y rellena entonces el proveedor real y
    la referencia.

    Siempre status=WAREHOUSE -- a diferencia del Caso C
    (register_new_and_consume), esto no consume nada en el momento;
    es una digitalización orgánica pura del almacén físico (anexo
    H10, sección 1, principio 1), sin ninguna tarea de parte de
    trabajo asociada.

    Genera un StockMovement ADJUST (mismo patrón que el alta manual
    de catálogo, SparePartEntryCreateView) con nota explícita de que
    el origen es "alta rápida sin proveedor conocido".

    ---

    Quick digital-warehouse intake of a spare part a mechanic just
    took off the physical shelf and that was not inventoried yet --
    gap flagged by Miguel Ángel (2026-07-07): "mechanics need a way to
    register spare parts when they pick them up from the warehouse
    and they haven't been inventoried yet". Requires neither a
    supplier reference nor a tax ID -- both are intentionally left
    unresolved (reference='', supplier=None): as soon as a delivery
    note documenting the same article arrives, confirm_delivery_note()
    automatically matches it by normalised description
    (_normalise_description) and fills in the real supplier and
    reference then.

    Always status=WAREHOUSE -- unlike Caso C
    (register_new_and_consume), this does not consume anything at
    intake time; it is a pure organic digitisation of the physical
    warehouse (annex H10, section 1, principle 1), with no work-order
    task attached.

    Generates a StockMovement ADJUST (same pattern as the manual
    catalog intake, SparePartEntryCreateView) with an explicit note
    that the origin is "quick intake, supplier unknown".
    """
    from .models import SparePartEntry, StockMovement

    if not description or not description.strip():
        raise ValueError('description es obligatorio.')

    if is_uncountable:
        if stock_level not in StockAssignmentService.LEVEL_CHOICES:
            raise ValueError(
                'stock_level debe ser uno de FULL/MEDIUM/LOW/EMPTY '
                'para un repuesto incontable.'
            )
        entry_stock_quantity = Decimal('0')
        entry_stock_level = stock_level
    else:
        if stock_quantity is None or stock_quantity <= 0:
            raise ValueError(
                'stock_quantity debe ser un numero > 0 para un '
                'repuesto contable.'
            )
        entry_stock_quantity = Decimal(str(stock_quantity))
        entry_stock_level = ''

    entry = SparePartEntry.objects.create(
        company=company,
        reference='',
        internal_reference=generate_internal_reference(company),
        description=description.strip(),
        is_uncountable=is_uncountable,
        stock_quantity=entry_stock_quantity,
        stock_level=entry_stock_level,
        status=SparePartEntry.STATUS_WAREHOUSE,
        origin_type=SparePartEntry.ORIGIN_SUPPLIER,
        supplier=None,
    )

    StockMovement.objects.create(
        spare_part_entry=entry,
        movement_type=StockMovement.MOVEMENT_ADJUST,
        quantity=entry_stock_quantity,
        level_after=entry_stock_level,
        created_by=created_by,
        notes=(
            'Alta rápida en almacén por mecánico -- repuesto tomado '
            'del almacén físico sin inventariar todavía, sin proveedor '
            'conocido (se resolverá automáticamente cuando llegue un '
            'albarán del mismo artículo).'
        ),
    )

    return entry


# =============================================================================
# StockAssignmentService -- Paso 4 de H10 (seccion 3.3, 3.4, 3.5 del anexo)
# =============================================================================

class StockAssignmentService:
    """
    Encapsulates spare-part usage in a digital work order: the
    pre-assigned listing helper (annex H10, section 3.3), the three
    consumption cases (section 3.5, A/B/C), and the shared
    materialisation into SparePartLine + StockMovement OUT at closing
    time (section 3.4).

    NOTA DE INTERPRETACION (aclarar con Miguel Angel): la seccion 3.4
    punto 4 dice que en Caso A el descuento de stock_quantity ocurre
    "al anadir la linea, no en el cierre" -- pero la seccion 3.5 Caso A
    dice literalmente que el status pasa a CONSUMED en ese mismo
    momento. Aplicado sin matices a la SparePartEntry de almacen
    compartida, eso la haria desaparecer del almacen aunque le quede
    stock. Esta implementacion resuelve la contradiccion asi: la
    entrada de almacen permanece en WAREHOUSE mientras le quede stock
    tras el descuento, y solo pasa a CONSUMED cuando llega
    exactamente a cero (contables) o siempre que se registre un uso
    (incontables, que no tienen "cantidad restante" numerica sino
    nivel). Pendiente de confirmacion de Miguel Angel.
    """

    LEVEL_CHOICES = ('FULL', 'MEDIUM', 'LOW', 'EMPTY')

    @staticmethod
    def list_pre_assigned(machine=None, breakdown_ticket=None):
        """Seccion 3.3 -- listado automatico de pre-asignados."""
        from .models import SparePartEntry

        qs = SparePartEntry.objects.filter(
            status=SparePartEntry.STATUS_PRE_ASSIGNED,
        )
        if breakdown_ticket is not None:
            return qs.filter(
                breakdown_ticket=breakdown_ticket,
            ).order_by('pre_assigned_at')
        if machine is not None:
            return qs.filter(
                machine=machine,
                breakdown_ticket__isnull=True,
            ).order_by('pre_assigned_at')
        return SparePartEntry.objects.none()

    @staticmethod
    def search_warehouse(company, query, limit=20):
        """Paso 1 de 3.5 -- busqueda en almacen digital."""
        from django.db.models import Q

        from .models import SparePartEntry

        query = (query or '').strip()
        if not query:
            return SparePartEntry.objects.none()

        return SparePartEntry.objects.filter(
            company=company,
            status=SparePartEntry.STATUS_WAREHOUSE,
        ).filter(
            Q(internal_reference__icontains=query)
            | Q(reference__icontains=query)
            | Q(description__icontains=query)
        )[:limit]

    @staticmethod
    def search_global(company, query='', limit=50):
        """
        Busqueda global "Añadir repuesto" (2026-07-23, a peticion de
        Miguel Angel): combina WAREHOUSE (sin maquina) y PRE_ASSIGNED
        (reservado a una maquina, "en el limbo") de TODA la empresa --
        a diferencia de search_warehouse() (solo WAREHOUSE) y
        list_pre_assigned() (solo de una maquina/ticket concreto).
        Nunca incluye CONSUMED. Sin query, devuelve el listado
        completo ordenado alfabeticamente por descripcion (autocarga
        al abrir el modal, igual que list_pre_assigned). Con query,
        filtra ademas por referencia/descripcion.
        """
        from django.db.models import Q

        from .models import SparePartEntry

        qs = SparePartEntry.objects.filter(
            company=company,
            status__in=[
                SparePartEntry.STATUS_WAREHOUSE,
                SparePartEntry.STATUS_PRE_ASSIGNED,
            ],
        ).select_related('machine')

        query = (query or '').strip()
        if query:
            qs = qs.filter(
                Q(internal_reference__icontains=query)
                | Q(reference__icontains=query)
                | Q(description__icontains=query)
            )

        return qs.order_by('description')[:limit]

    @staticmethod
    def _next_line_number(entry_line):
        """Siguiente line_number libre para una SparePartLine nueva."""
        from work_order_processor.models import SparePartLine

        last = (
            SparePartLine.objects
            .filter(entry_line=entry_line)
            .order_by('-line_number')
            .first()
        )
        return (last.line_number + 1) if last else 1

    @staticmethod
    def _materialize_consumption(
        entry, entry_line, machine, breakdown_ticket, created_by,
        quantity_out=None, level_before='', level_after='', notes='',
    ):
        """
        Seccion 3.4 -- comun a los tres casos. Crea la SparePartLine
        vinculada a entry via spare_part_entry (ya migrada, ver
        work_order_processor/migrations/0027_sparepartline_spare_part_entry.py)
        y el StockMovement OUT correspondiente.
        """
        from work_order_processor.models import SparePartLine

        from .models import SparePartEntry, StockMovement

        if quantity_out is None:
            quantity_out = Decimal('0')

        is_supplier = entry.origin_type == SparePartEntry.ORIGIN_SUPPLIER
        spare_part_line = SparePartLine.objects.create(
            entry_line=entry_line,
            line_number=StockAssignmentService._next_line_number(entry_line),
            reference=entry.reference,
            material=entry.description,
            vehicle=machine,
            quantity=quantity_out if not entry.is_uncountable else None,
            unit_price=entry.purchase_unit_price if is_supplier else None,
            source=(
                SparePartLine.Source.SUPPLIER
                if is_supplier else SparePartLine.Source.WAREHOUSE
            ),
            spare_part_entry=entry,
        )

        StockMovement.objects.create(
            spare_part_entry=entry,
            movement_type=StockMovement.MOVEMENT_OUT,
            quantity=quantity_out,
            level_before=level_before,
            level_after=level_after,
            machine=machine,
            breakdown_ticket=breakdown_ticket,
            work_order_entry_line=entry_line,
            spare_part_line=spare_part_line,
            created_by=created_by,
            notes=notes,
        )
        return spare_part_line

    @staticmethod
    @transaction.atomic
    def consume_from_warehouse(
        entry, entry_line, machine, breakdown_ticket, created_by,
        quantity_used=None, new_level=None, notes='',
    ):
        """
        Caso A (anexo H10, seccion 3.5). entry debe estar en
        status=WAREHOUSE. Contable: descuenta quantity_used de
        stock_quantity (ValueError si el stock es insuficiente); la
        entrada permanece en WAREHOUSE si queda stock, o pasa a
        CONSUMED si llega exactamente a cero (ver nota de
        interpretacion en el docstring de la clase). Incontable:
        new_level debe ser uno de LEVEL_CHOICES; la entrada permanece
        en WAREHOUSE con el nuevo nivel.
        """
        from .models import SparePartEntry

        if entry.status != SparePartEntry.STATUS_WAREHOUSE:
            raise ValueError(
                f'SparePartEntry #{entry.pk} no esta en almacen '
                f'(status={entry.status}).'
            )

        if entry.is_uncountable:
            if new_level not in StockAssignmentService.LEVEL_CHOICES:
                raise ValueError(
                    'new_level debe ser uno de FULL/MEDIUM/LOW/EMPTY '
                    'para un repuesto incontable.'
                )
            level_before = entry.stock_level
            entry.stock_level = new_level
            entry.save(update_fields=['stock_level'])
            return StockAssignmentService._materialize_consumption(
                entry, entry_line, machine, breakdown_ticket, created_by,
                quantity_out=Decimal('0'),
                level_before=level_before,
                level_after=new_level,
                notes=notes,
            )

        if quantity_used is None or quantity_used <= 0:
            raise ValueError(
                'quantity_used debe ser un numero positivo para un '
                'repuesto contable.'
            )
        current = entry.stock_quantity or Decimal('0')
        if quantity_used > current:
            raise ValueError(
                f'Stock insuficiente en SparePartEntry #{entry.pk}: '
                f'quedan {current}, se solicitan {quantity_used}.'
            )
        entry.stock_quantity = current - quantity_used
        if entry.stock_quantity == 0:
            entry.status = SparePartEntry.STATUS_CONSUMED
            entry.consumed_at = now()
            entry.save(update_fields=['stock_quantity', 'status', 'consumed_at'])
        else:
            entry.save(update_fields=['stock_quantity'])
        return StockAssignmentService._materialize_consumption(
            entry, entry_line, machine, breakdown_ticket, created_by,
            quantity_out=quantity_used, notes=notes,
        )

    @staticmethod
    @transaction.atomic
    def consume_pre_assigned(entry, entry_line, created_by, notes=''):
        """
        Caso B (anexo H10, seccion 3.5 / 3.3). entry debe estar en
        status=PRE_ASSIGNED. Se consume de golpe toda la cantidad/
        nivel reservado. entry.status pasa a CONSUMED sin condicion,
        consistente con la seccion 3.4 punto 1.
        """
        from .models import SparePartEntry

        if entry.status != SparePartEntry.STATUS_PRE_ASSIGNED:
            raise ValueError(
                f'SparePartEntry #{entry.pk} no esta pre-asignado '
                f'(status={entry.status}).'
            )

        machine = entry.machine
        if machine is None and entry.breakdown_ticket is not None:
            machine = entry.breakdown_ticket.machine

        quantity_out = (
            Decimal('0') if entry.is_uncountable
            else (entry.stock_quantity or Decimal('0'))
        )

        entry.status = SparePartEntry.STATUS_CONSUMED
        entry.consumed_at = now()
        entry.save(update_fields=['status', 'consumed_at'])

        return StockAssignmentService._materialize_consumption(
            entry, entry_line, machine, entry.breakdown_ticket, created_by,
            quantity_out=quantity_out, notes=notes,
        )

    @staticmethod
    @transaction.atomic
    def register_new_and_consume(
        company, entry_line, machine, breakdown_ticket, created_by,
        description, reference='', is_uncountable=False,
        stock_quantity_remaining=None, stock_level_remaining=None,
        quantity_used=None, notes='',
    ):
        """
        Caso C (anexo H10, seccion 3.5). Crea una SparePartEntry
        nueva directamente en status=CONSUMED (digitalizacion
        organica retroactiva, seccion 1 principio 1) y materializa el
        consumo en el mismo paso.

        stock_quantity_remaining/stock_level_remaining: lo que queda
        en el almacen fisico TRAS este uso (segun redaccion literal
        del anexo) -- se convierte en el stock_quantity/stock_level
        de la entrada. quantity_used (por defecto 1) es lo que se
        registra como consumido esta vez -- el anexo no lo especifica
        explicitamente, solo pregunta "cuantos quedan".

        origin_type se fija a SUPPLIER con supplier_* vacios -- el
        modelo solo distingue SUPPLIER/SALVAGED y esta alta ad-hoc no
        tiene ni albaran escaneado ni maquina donante. Senalado para
        que Miguel Angel confirme o proponga mejor convencion.
        """
        from .models import SparePartEntry

        if not description or not description.strip():
            raise ValueError('description es obligatorio en el Caso C.')

        if is_uncountable:
            if stock_level_remaining not in StockAssignmentService.LEVEL_CHOICES:
                raise ValueError(
                    'stock_level_remaining debe ser uno de '
                    'FULL/MEDIUM/LOW/EMPTY para un repuesto incontable.'
                )
        else:
            if stock_quantity_remaining is None or stock_quantity_remaining < 0:
                raise ValueError(
                    'stock_quantity_remaining debe ser un numero >= 0 '
                    'para un repuesto contable.'
                )

        if quantity_used is None:
            quantity_used = Decimal('1')

        entry = SparePartEntry.objects.create(
            company=company,
            reference=reference or '',
            internal_reference=generate_internal_reference(company),
            description=description.strip(),
            is_uncountable=is_uncountable,
            stock_quantity=(
                Decimal('0') if is_uncountable
                else Decimal(str(stock_quantity_remaining))
            ),
            stock_level=stock_level_remaining or '',
            status=SparePartEntry.STATUS_CONSUMED,
            machine=machine,
            breakdown_ticket=breakdown_ticket,
            consumed_at=now(),
            origin_type=SparePartEntry.ORIGIN_SUPPLIER,
        )

        return StockAssignmentService._materialize_consumption(
            entry, entry_line, machine, breakdown_ticket, created_by,
            quantity_out=(Decimal('0') if is_uncountable else quantity_used),
            level_after=(stock_level_remaining or '') if is_uncountable else '',
            notes=notes,
        )


