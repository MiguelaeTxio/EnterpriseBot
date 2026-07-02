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
from decimal import Decimal, InvalidOperation
from typing import Optional

from django.utils.timezone import now
from google.genai import types
from pydantic import BaseModel, Field

from ai_services.gemini_client import (
    DEFAULT_MODEL,
    get_gemini_client,
    get_request_config,
)
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
    machine_code_raw: Optional[str] = Field(
        default=None,
        description='Código de máquina o de almacén anotado a mano '
                     'junto a esta línea, tal cual aparece escrito '
                     '(sin normalizar). Null si no hay anotación.',
    )


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
    delivery_number: Optional[str] = Field(
        default=None,
        description='Número de albarán. Null si no es legible.',
    )
    delivery_date: Optional[str] = Field(
        default=None,
        description='Fecha del albarán en formato YYYY-MM-DD. Null '
                     'si no es legible o no figura.',
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

1. Datos del proveedor: nombre comercial, NIF/CIF si aparece, \
dirección si aparece.
2. Número de albarán y fecha (formato YYYY-MM-DD).
3. Cada línea de artículo del albarán, en orden, con: número de \
línea, referencia (si tiene), descripción, cantidad, precio \
unitario, precio total.
4. Para cada línea, si hay una anotación manuscrita junto al \
artículo indicando a qué máquina o almacén va destinado (por \
ejemplo un código como "B14", "A-054", "ALM", "ALMACEN"), \
transcríbela tal cual está escrita en el campo machine_code_raw. \
Si no hay anotación, deja ese campo en null.

No inventes datos que no sean legibles en el documento — usa null \
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
# Line assignment resolution / Resolución de asignación de línea
# (Annex H10, section 3.1, step 4-5)
# ---------------------------------------------------------------------------

_WAREHOUSE_CODE_ALIASES = {'ALM', 'AL', 'ALMACEN', 'ALMACÉN', 'WAREHOUSE'}


def resolve_line_assignment(raw_code: Optional[str], company):
    """
    Resolves a raw machine/warehouse code annotated on a delivery
    note line into an assignment_type + MachineAsset, reusing the
    same normaliser validated in work_order_processor (Hito 8) per
    the DRY directive.

    Returns a tuple (assignment_type, machine) where assignment_type
    is one of 'WAREHOUSE', 'MACHINE', 'UNASSIGNED' and machine is the
    resolved MachineAsset or None.

    ---

    Resuelve un código bruto de máquina/almacén anotado en una línea
    de albarán a un assignment_type + MachineAsset, reutilizando el
    mismo normalizador validado en work_order_processor (Hito 8)
    según la directriz DRY.

    Devuelve una tupla (assignment_type, machine) donde
    assignment_type es 'WAREHOUSE', 'MACHINE' o 'UNASSIGNED', y
    machine es el MachineAsset resuelto o None.
    """
    if not raw_code or not raw_code.strip():
        return 'UNASSIGNED', None

    stripped_upper = raw_code.strip().upper()
    if stripped_upper in _WAREHOUSE_CODE_ALIASES:
        return 'WAREHOUSE', None

    normalised = _normalise_machine_code(raw_code)
    machine = _resolve_machine_asset(normalised, company=company)
    if machine is not None:
        return 'MACHINE', machine

    return 'UNASSIGNED', None


def confirm_delivery_note(delivery_note, company_user):
    """
    Executes the delivery note assignment circuit described in annex
    H10, section 3.1, step 5, for every line of delivery_note whose
    assignment_type is WAREHOUSE or MACHINE. Lines left UNASSIGNED
    are skipped and reported back for manual review.

    WAREHOUSE lines: creates or updates (matched by company +
    reference when reference is set) a SparePartEntry with
    status=WAREHOUSE, sums stock_quantity, and records a
    StockMovement IN.

    MACHINE lines: looks up an open BreakdownTicket (OPEN /
    IN_PROGRESS) for the target machine; creates a SparePartEntry
    with status=PRE_ASSIGNED (limbo), attached to the ticket if one
    is open or directly to the machine otherwise, and records a
    StockMovement IN.

    All entries created here are countable (is_uncountable=False) —
    supplier delivery notes always state a quantity; uncountable
    stock levels are only set manually by mechanics at consumption
    time (annex H10, section 3.5, Caso C).

    Sets delivery_note.status = 'ASSIGNED' on completion.

    Returns a dict with counts: warehouse, pre_assigned, unassigned.

    ---

    Ejecuta el circuito de asignación de albarán descrito en el
    anexo H10, sección 3.1, paso 5, para cada línea de delivery_note
    cuyo assignment_type sea WAREHOUSE o MACHINE. Las líneas que
    queden UNASSIGNED se omiten y se reportan para revisión manual.

    Líneas WAREHOUSE: crea o actualiza (emparejado por empresa +
    referencia cuando hay referencia) un SparePartEntry con
    status=WAREHOUSE, suma stock_quantity, y registra un
    StockMovement IN.

    Líneas MACHINE: busca un BreakdownTicket abierto (OPEN /
    IN_PROGRESS) para la máquina destino; crea un SparePartEntry con
    status=PRE_ASSIGNED (limbo), vinculado al ticket si hay uno
    abierto o directamente a la máquina en caso contrario, y
    registra un StockMovement IN.

    Todas las entradas creadas aquí son contables
    (is_uncountable=False) — los albaranes de proveedor siempre
    indican una cantidad; los niveles incontables solo los establece
    manualmente el mecánico en el momento del consumo (anexo H10,
    sección 3.5, Caso C).

    Al finalizar establece delivery_note.status = 'ASSIGNED'.

    Devuelve un diccionario con los contadores: warehouse,
    pre_assigned, unassigned.
    """
    from chat.models import BreakdownTicket

    from .models import SparePartEntry, StockMovement

    company = delivery_note.company
    counts = {'warehouse': 0, 'pre_assigned': 0, 'unassigned': 0}

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
                entry = SparePartEntry.objects.create(
                    company=company,
                    reference=line.reference,
                    description=line.description,
                    is_uncountable=False,
                    status=SparePartEntry.STATUS_WAREHOUSE,
                    origin_type=SparePartEntry.ORIGIN_SUPPLIER,
                    supplier_name=delivery_note.supplier_name,
                    supplier_tax_id=delivery_note.supplier_tax_id,
                    purchase_unit_price=line.unit_price,
                    purchase_total_price=line.total_price,
                    source_delivery_note_line=line,
                )
            entry.stock_quantity = (
                entry.stock_quantity or Decimal('0')
            ) + quantity
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
                description=line.description,
                is_uncountable=False,
                status=SparePartEntry.STATUS_PRE_ASSIGNED,
                machine=None if ticket else line.machine,
                breakdown_ticket=ticket,
                pre_assigned_at=now(),
                origin_type=SparePartEntry.ORIGIN_SUPPLIER,
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
    delivery_note.save(update_fields=['status', 'processed_by'])

    return counts


