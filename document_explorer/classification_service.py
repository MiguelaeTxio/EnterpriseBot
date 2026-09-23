# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/classification_service.py
"""
First real Gemini call for H29 classification (S040, testing phase --
Miguel Angel: "generar ya el prompt para empezar a hacer las pruebas
de clasificación de la carpeta de cuarentena").

Reuses the shared, already-validated Gemini plumbing from `ai_services`
(client construction, rate limiting, 429 retry, JSON response_schema
pattern) instead of duplicating it -- same client used by the voice
bridge, WhatsApp, and spare_parts vision (transversal infra, DRY
principle per doc-master-enterprisebot section 4.1.1). Does NOT import
anything from `document_ingestion`/`entity_matching_service`/
`machine_documents`/`personal_documents` -- H29 stays isolated from
H17-H25 per Miguel Angel's explicit S040 decision (H29 annex, 3.15,
"Regla derivada").

Gemini's job stops at *suggesting* a `DocumentTypeCatalog.code` and a
handful of hint fields -- see `naming_service` for why the actual
filename is never built from Gemini's own wording.

**Testing phase, not yet wired to any batch/production classification
flow.** Callers get the raw suggestion back and decide what to do with
it (this session: a "Clasificar" button on the explorer that shows the
suggestion via Django messages, nothing auto-applied).

---

Primera llamada real a Gemini para la clasificación de H29 (S040, fase
de pruebas -- Miguel Ángel: "generar ya el prompt para empezar a hacer
las pruebas de clasificación de la carpeta de cuarentena").

Reutiliza el mecanismo de Gemini ya compartido y validado de
`ai_services` (construcción de cliente, límite de tasa, reintento ante
429, patrón de `response_schema` JSON) en vez de duplicarlo -- el mismo
cliente que usan el puente de voz, WhatsApp y la visión de
`spare_parts` (infraestructura transversal, principio DRY, ver
doc-master-enterprisebot sección 4.1.1). No importa nada de
`document_ingestion`/`entity_matching_service`/`machine_documents`/
`personal_documents` -- H29 queda aislado de H17-H25 según la decisión
explícita de Miguel Ángel en S040 (anexo H29, 3.15, "Regla derivada").

El trabajo de Gemini termina en *sugerir* un `DocumentTypeCatalog.code`
y un puñado de campos de pista -- ver `naming_service` para el porqué
de que el nombre de archivo final nunca se construya con la redacción
propia de Gemini.

**Fase de pruebas, todavía sin conectar a ningún flujo de
clasificación por lote/producción.** Quien llama recibe la sugerencia
en crudo y decide qué hacer con ella (en esta sesión: un botón
"Clasificar" en el explorador que muestra la sugerencia vía mensajes
de Django, sin aplicar nada automáticamente).
**Extended S040 (misma sesión): ya aplica de verdad, pero 100%
virtual.** Miguel Ángel, verbatim: *"En realidad no vamos a tocar
CGS, lo vamos a hacer todo a nivel de datos (...) Al clasificarla le
damos el nombre nuevo en base de datos."* Aplicar una clasificación
escribe únicamente `DocumentIndexEntry.name` (el nombre VIRTUAL) --
`blob_name` (la ruta real en el cubo) nunca se toca, exactamente el
mismo principio que `move_service` (v2, puntero puro, S039). Ver
`apply_classification()`.
"""
import datetime
import logging
import os
import re
import subprocess
import tempfile
import time

import fitz  # PyMuPDF -- ya en requirements (ver cabecera del módulo)

from django.db.models import Q
from django.utils import timezone
from google.genai.types import GenerateContentConfig, HttpOptions, Part

from ai_services.gemini_client import DEFAULT_MODEL, get_gemini_client
from ai_services.gemini_rate_limiter import acquire_gemini_slot
from fleet.models import MachineAsset
from spare_parts.gcs_service import download_bytes

from . import archive_service, naming_service
from .buckets import (
    MANUAL_USO_FOLDER, NO_CONFORMES_PREFIX, QUARANTINE_PREFIX,
    quarantine_scope_q,
)
from .heuristic_type_service import resolve_document_type_heuristic
from .move_service import _virtual_location_taken, move_entry

from .models import DocumentIndexEntry, DocumentTypeCatalog, PersonIdentity

logger = logging.getLogger(__name__)

_MAX_GEMINI_ATTEMPTS = 3
_RETRY_DELAY_SECONDS = 60

# Verificado online el 2026-07-31 contra la documentación real de
# Document understanding de Gemini (ai.google.dev/gemini-api/docs/
# document-processing): "You can also pass non-PDF documents in the
# same way but Gemini will see them as normal text" -- es decir, un
# .docx con su mimeType real de Office (OpenXML) NO se acepta
# directamente; requeriría convertirlo a PDF/texto plano antes.
# Confirmado también con el error real de producción de esta misma
# sesión (S040): 400 INVALID_ARGUMENT sobre
# application/vnd.openxmlformats-officedocument.wordprocessingml.document.
_SUPPORTED_MIME_TYPES = {
    "application/pdf",
    "image/png",
    "image/jpeg",
    "image/webp",
    "image/heic",
    "image/heif",
    "text/plain",
}

# Extensiones que LibreOffice headless sabe convertir a PDF -- S040,
# tras el hallazgo real de un .docx rechazado por Gemini. Solo Office
# clásico de documento/hoja/presentación; deliberadamente no incluye
# nada que ya esté en _SUPPORTED_MIME_TYPES (PDF, imágenes, texto
# plano ya se aceptan directamente, sin pasar por LibreOffice).
_LIBREOFFICE_CONVERTIBLE_EXTENSIONS = {
    "docx", "doc", "odt", "rtf",
    "xlsx", "xls", "ods",
    "pptx", "ppt", "odp",
}
_SOFFICE_TIMEOUT_SECONDS = 90

# XPS/OpenXPS -- deliberadamente FUERA de
# _LIBREOFFICE_CONVERTIBLE_EXTENSIONS. S042, Miguel Ángel: un tríptico
# real de una minigrúa cayó en NO CONFORMES por esto exacto --
# comprobado empíricamente contra ese mismo archivo antes de escribir
# una sola línea de este arreglo (método empírico, nunca bola de
# cristal): `soffice --convert-to pdf` sobre él responde "Error:
# source file could not be loaded" (LibreOffice 6.4.7.2 del servidor
# no trae el filtro de importación XPS). `fitz` (PyMuPDF, ya
# dependencia del proyecto -- MuPDF es literalmente "a lightweight
# PDF **and XPS** viewer") sí lo abre y convierte sin problema, mismo
# archivo, mismo comando de verificación: `fitz.open(stream=...,
# filetype="xps").convert_to_pdf()`. Ver `_convert_xps_to_pdf()`.
_XPS_EXTENSIONS = {"xps", "oxps"}

# S042 -- el límite real de 52428800 bytes (50 MiB) de Vertex AI para
# PDF (S040, confirmado por la propia API en producción) ya no se
# comprueba por separado: desde que el número de páginas se cuenta
# SIEMPRE para cualquier PDF (regla general de Miguel Ángel, ver
# _pdf_page_count()), un archivo de más de 4 páginas se recorta antes
# de llegar a Gemini sea cual sea su peso -- en la práctica ningún PDF
# de 4 páginas o menos pesa lo bastante como para chocar con ese
# límite, así que la comprobación de tamaño quedó redundante.

# S042 -- sustituye a _PDF_CLASSIFICATION_MAX_PAGES=3 (solo primeras
# páginas). Ver el docstring de _extract_pdf_edges() para los datos
# reales que motivaron el cambio a "principio + final" en vez de
# "más páginas seguidas desde el principio".
_PDF_EXCERPT_FIRST_PAGES = 2
_PDF_EXCERPT_LAST_PAGES = 2


_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "domain": {
            "type": "string",
            "enum": ["MACHINE", "PERSONAL", "DESCONOCIDO"],
        },
        "document_type_code": {"type": "string"},
        "confidence": {"type": "string", "enum": ["ALTA", "MEDIA", "BAJA"]},
        "reasoning": {"type": "string"},
        "machine_code_hint": {"type": "string"},
        "brand_model_hint": {"type": "string"},
        "first_surname_hint": {"type": "string"},
        "second_surname_hint": {"type": "string"},
        "given_name_hint": {"type": "string"},
        "dni_hint": {"type": "string"},
        "date_hint": {"type": "string"},
        "is_dossier": {"type": "boolean"},
        "is_photo": {"type": "boolean"},
    },
    "required": [
        "domain", "document_type_code", "confidence", "reasoning",
        "machine_code_hint", "brand_model_hint",
        "first_surname_hint", "second_surname_hint",
        "given_name_hint", "dni_hint", "date_hint", "is_dossier",
        "is_photo",
    ],
}

_PROMPT_TEMPLATE = """Eres un clasificador de documentación \
administrativa de una empresa \
española de grúas y maquinaria pesada. Se te da UN documento (PDF), y debes \
identificar su tipo dentro de una lista CERRADA de tipos posibles -- nunca \
inventes un tipo fuera de esta lista, ni renombres uno existente con tus \
propias palabras.
{curator_note_section}
{excerpt_notice}
{domain_instruction}

TIPOS DE DOCUMENTO POSIBLES (código -- descripción):
{catalog_lines}

Si el documento no encaja claramente en ninguno de los tipos anteriores, \
usa el código "DESCONOCIDO" y explica por qué en "reasoning".

REVERSOS Y CARAS SUELTAS de un documento de doble cara (DNI, permiso de \
conducción, tarjeta ITV con reverso, etc.): el reverso es EL MISMO \
documento que el anverso, nunca un tipo distinto ni "DESCONOCIDO" solo \
por faltarle la cara con la foto/datos principales. Si reconoces de qué \
tipo de documento es el reverso (por el formato, los campos que sí se \
ven, el propio membrete), usa exactamente el mismo código que usarías \
para el anverso completo -- un reverso sin nombre visible pero \
identificable por su formato como "reverso de DNI" sigue siendo ese \
mismo tipo de documento, con confianza más baja si hace falta, nunca \
DESCONOCIDO por el mero hecho de ser la cara de atrás.

is_dossier: SOLO true cuando tengas la CERTEZA de que el archivo es la \
unión de DOS O MÁS documentos catalogados DISTINTOS, cada uno \
identificable por separado -- por ejemplo: una tarjeta ITV + un permiso \
de circulación; un DNI + un certificado de un curso; un DNI + un permiso \
de conducción. El número de páginas no importa (un dossier puede tener \
tres páginas o quince). NUNCA marques is_dossier=true solo porque el \
documento no encaje en ningún tipo de la lista y por eso uses \
"DESCONOCIDO" -- eso es un documento único que no reconoces, no un \
dossier, y es un caso completamente distinto. Si tienes cualquier duda \
real sobre si es un único documento o varios, usa is_dossier=false -- \
la certeza es obligatoria, la sospecha no basta. Cuando is_dossier=true, \
explica en "reasoning" qué documentos distintos identificaste dentro \
del archivo. Si el propio extracto que te doy avisa de que le faltan \
páginas intermedias, un cambio claro de membrete, formato o tipo de \
documento entre el bloque inicial y el final es motivo suficiente para \
marcar is_dossier=true con certeza -- no hace falta ver las páginas de \
en medio para saber que hay dos documentos distintos cosidos juntos.

is_photo: true SOLO cuando el archivo es, en esencia, una FOTOGRAFÍA (de una \
máquina, un vehículo, una escena de trabajo, un daño, etc.) y no un \
documento administrativo o técnico escaneado/generado -- p. ej. una foto \
tomada con el móvil y guardada como PDF/imagen sigue siendo is_photo=true, \
aunque el formato del archivo sea PDF. false para cualquier documento con \
texto administrativo real (facturas, permisos, certificados, DNI...), \
aunque contenga alguna imagen o logo. Si is_photo=true, usa \
document_type_code="DESCONOCIDO" y explica en "reasoning" que es una \
fotografía, no un documento -- nunca inventes un tipo de la lista para \
encajarla a la fuerza.

Además del tipo, extrae estas pistas SI aparecen de forma clara en el propio \
documento (deja la cadena vacía "" si no aparecen -- nunca inventes un valor):
- machine_code_hint: el código interno de flota o la matrícula de la \
máquina/vehículo (solo si el dominio es de máquina) -- casi siempre con \
forma "LETRA-NÚMERO" (p. ej. "A-29") y/o una matrícula española \
("E-0356-BBZ", "1532-DVF"). NUNCA el "Tipo"/modelo/denominación \
comercial que dé el FABRICANTE (p. ej. "AT-35/32" en una Declaración \
CE es el modelo del fabricante, no el código de flota -- ignóralo para \
este campo aunque sea el dato más visible del documento). Si el \
documento no deja claro cuál es el código de flota/matrícula real, \
deja el campo vacío en vez de usar el modelo del fabricante.
- brand_model_hint: la MARCA y el MODELO del fabricante que diga el propio \
documento (solo si el dominio es de máquina) -- p. ej. "LUNA AT-35/32", \
"LIEBHERR LTM 1055". Aquí SÍ interesa exactamente el dato que se ignora \
para machine_code_hint -- sirve para comprobar después, por otra vía, que \
el documento corresponde de verdad a la máquina de la carpeta donde está \
archivado.
- first_surname_hint, second_surname_hint, given_name_hint, dni_hint: \
primer apellido, segundo apellido, nombre de pila y DNI/NIE de la persona a \
la que se refiere el documento (solo si el dominio es de personal). Si el \
documento es un DNI o un informe de la Seguridad Social, estos son \
exactamente los campos que aparecen impresos en él. El DNI es el dato más \
fiable de los cuatro para identificar a la persona sin ambigüedad -- \
extráelo siempre que aparezca, aunque también extraigas el nombre. \
EXCEPCIÓN a "deja la cadena vacía si no aparece": si la NOTA DEL \
SUPERVISOR de arriba incluye un DNI/NIE explícito, usa ese valor como \
dni_hint aunque el propio documento no lo mencione en ningún sitio -- la \
nota es la fuente más fiable de todas, por delante incluso del propio \
documento, y muchos documentos personales reales (partes de vacaciones, \
notas internas) nunca llevan DNI impreso. Si el documento menciona a \
VARIAS personas distintas por igual (un listado, una declaración con \
varios trabajadores...), extrae los datos de la persona más prominente y \
dilo explícitamente en "reasoning" -- eso indica que el archivo podría \
contener a más de una persona.
- date_hint: la fecha más relevante del documento para decidir cuándo se \
emitió o cuándo caduca (formato AAAA-MM-DD), si se puede leer con claridad.

Responde ÚNICAMENTE el JSON solicitado, sin texto adicional."""

_DOMAIN_LABELS = {
    "MACHINE": "MÁQUINA / VEHÍCULO",
    "PERSONAL": "PERSONAL / TRABAJADOR",
}


def _build_prompt(
    domain: str | None, curator_note: str = "",
    is_partial_excerpt: bool = False,
) -> str:
    """
    Builds the classification prompt. If the domain is already known
    (file living under DOC. MAQUINAS or DOC. PERSONAL), the catalog is
    narrowed to that domain's own codes plus BOTH, and "domain" is
    given as a fact. If the domain is unknown (a quarantine file,
    which is exactly the real use case -- nobody has sorted it yet),
    the full active catalog is listed and Gemini is asked to decide
    the domain too.

    `curator_note` (H29, S042, decision 3.14 extended -- Miguel
    Ángel's own example: "DNI 74633524I -> 74633524L") is optional,
    free text a supervisor left on the row while it sat in "NO
    CONFORMES" after a failed first pass -- e.g. correcting a
    misread DNI so the next attempt resolves the right
    `PersonIdentity`. When present it is rendered as a short,
    explicitly prioritised block ahead of the domain instruction, so
    Gemini reads it before anything else.

    `is_partial_excerpt` (S042, `_extract_pdf_edges()`'s companion --
    see that function's docstring for the real dossier-detection data
    behind this) flags that the PDF Part isn't the whole document:
    only its first and last few pages, with a gap in between. Without
    this notice Gemini has no way to know the content "jumps" and
    could read an abrupt change in letterhead/format between the two
    blocks as odd formatting rather than the dossier signal it
    actually is.

    ---

    Construye el prompt de clasificación. Si el dominio ya se conoce
    (archivo que vive bajo DOC. MAQUINAS o DOC. PERSONAL), el catálogo
    se acota a los códigos propios de ese dominio más BOTH, y "domain"
    se da como un hecho. Si el dominio se desconoce (un archivo de
    cuarentena, que es exactamente el caso de uso real -- todavía
    nadie lo ha clasificado), se lista el catálogo activo completo y
    se le pide a Gemini que decida también el dominio.

    `curator_note` (H29, S042, decisión 3.14 ampliada -- ejemplo del
    propio Miguel Ángel: "DNI 74633524I -> 74633524L") es texto libre
    opcional que un supervisor dejó en la fila mientras estaba en "NO
    CONFORMES" tras fallar una primera pasada -- p. ej. corrigiendo un
    DNI mal leído para que el siguiente intento resuelva la
    `PersonIdentity` correcta. Cuando existe se renderiza como un
    bloque corto y explícitamente prioritario, por delante de la
    instrucción de dominio, para que Gemini lo lea antes que nada.

    `is_partial_excerpt` (S042, compañero de `_extract_pdf_edges()` --
    ver el docstring de esa función para los datos reales de
    detección de dosieres detrás de esto) avisa de que el Part de PDF
    no es el documento completo: solo sus primeras y últimas páginas,
    con un hueco en medio. Sin este aviso Gemini no tiene forma de
    saber que el contenido "salta", y podría leer un cambio brusco de
    membrete/formato entre los dos bloques como un formateo raro en
    vez de la señal de dosier que de verdad es.
    """
    curator_note = (curator_note or "").strip()
    curator_note_section = (
        (
            "NOTA DEL SUPERVISOR -- PRIORITARIA sobre lo que leas en "
            "el propio documento, corrige un fallo real de una pasada "
            "anterior: %s\n" % curator_note
        )
        if curator_note else ""
    )
    excerpt_notice = (
        "AVISO: este PDF NO está completo -- son solo las primeras y "
        "las últimas páginas del documento real, con páginas "
        "intermedias que no ves. Un cambio claro de membrete, formato "
        "o tipo de documento entre el bloque inicial y el final es "
        "una señal fuerte de que hay más de un documento cosido junto "
        "(ver is_dossier más abajo).\n"
        if is_partial_excerpt else ""
    )
    if domain:
        catalog_entries = (
            DocumentTypeCatalog.objects
            .filter(is_active=True)
            .filter(domain__in=[domain, DocumentTypeCatalog.DOMAIN_BOTH])
            .order_by("code")
        )
        domain_instruction = (
            "DOMINIO (ya conocido, no lo cambies): %s"
            % _DOMAIN_LABELS.get(domain, domain)
        )
    else:
        catalog_entries = (
            DocumentTypeCatalog.objects.filter(is_active=True).order_by("code")
        )
        domain_instruction = (
            "DOMINIO: desconocido -- decide tú si el documento es de "
            "MÁQUINA/VEHÍCULO o de PERSONAL/TRABAJADOR y ponlo en el campo "
            "\"domain\" (\"MACHINE\" o \"PERSONAL\"; \"DESCONOCIDO\" solo si "
            "de verdad no se puede determinar)."
        )
    catalog_lines = "\n".join(
        "- %s -- %s" % (entry.code, entry.label) for entry in catalog_entries
    )
    return _PROMPT_TEMPLATE.format(
        curator_note_section=curator_note_section,
        excerpt_notice=excerpt_notice,
        domain_instruction=domain_instruction, catalog_lines=catalog_lines,
    )


def _generate_content_with_retry(client, **kwargs):
    """
    Same retry pattern already validated in
    `ai_services.document_vision_service._generate_content_with_retry`
    (proactive rate-limit slot + up to 3 attempts on a Vertex AI 429),
    kept local to this app instead of importing that module's private
    helper across app boundaries.

    **Extended S042, real incident**: 504 DEADLINE_EXCEEDED gave zero
    retries -- confirmed against 24h of real production data, 25 of
    359 `SENT_NO_CONFORMES` entries were a bare timeout, permanently
    exiling a file to NO CONFORMES for a purely transient network/API
    hiccup, exactly as if its content were genuinely unclassifiable.
    A timeout deserves the same backoff-and-retry treatment as a 429 --
    it says nothing about the document itself.

    ---

    Mismo patrón de reintento ya validado en
    `ai_services.document_vision_service._generate_content_with_retry`
    (slot de límite de tasa proactivo + hasta 3 intentos ante un 429 de
    Vertex AI), mantenido local a esta app en vez de importar el
    auxiliar privado de ese módulo cruzando el límite entre apps.

    **Ampliado en S042, incidente real**: 504 DEADLINE_EXCEEDED no
    tenía ningún reintento -- confirmado contra 24h de datos reales de
    producción, 25 de 359 entradas `SENT_NO_CONFORMES` eran un simple
    timeout, desterrando el archivo a NO CONFORMES para siempre por un
    problema de red/API puramente transitorio, exactamente igual que
    si su contenido fuera genuinamente inclasificable. Un timeout
    merece el mismo tratamiento de espera-y-reintento que un 429 -- no
    dice nada sobre el documento en sí.
    """
    last_exc = None
    for attempt in range(1, _MAX_GEMINI_ATTEMPTS + 1):
        acquire_gemini_slot()
        try:
            return client.models.generate_content(**kwargs)
        except Exception as exc:
            last_exc = exc
            exc_str = str(exc)
            is_retryable = (
                "429" in exc_str or "RESOURCE_EXHAUSTED" in exc_str
                or "504" in exc_str or "DEADLINE_EXCEEDED" in exc_str
                or "503" in exc_str or "UNAVAILABLE" in exc_str
            )
            if not is_retryable or attempt == _MAX_GEMINI_ATTEMPTS:
                raise
            logger.warning(
                "# [classification_service] Error transitorio de "
                "Vertex AI (intento %d/%d): %s. Reintentando en %ds.",
                attempt, _MAX_GEMINI_ATTEMPTS, exc_str[:200],
                _RETRY_DELAY_SECONDS,
            )
            time.sleep(_RETRY_DELAY_SECONDS)
    raise last_exc  # pragma: no cover -- inalcanzable


def domain_for_entry(entry) -> str | None:
    """
    Best-effort domain guess from the entry's own folder, for files
    that already live under a known root (DOC. MAQUINAS/DOC.
    PERSONAL). Returns None for anything else (quarantine, other
    buckets) -- callers pass that straight through to `classify_entry`,
    which then asks Gemini to determine the domain too.

    ---

    Estimación del dominio a partir de la propia carpeta de la
    entrada, para archivos que ya viven bajo una raíz conocida (DOC.
    MAQUINAS/DOC. PERSONAL). Devuelve None para cualquier otro caso
    (cuarentena, otros cubos) -- quien llama lo pasa tal cual a
    `classify_entry`, que entonces le pide a Gemini que determine
    también el dominio.
    """
    if entry.blob_name.startswith("DOC. MAQUINAS/"):
        return DocumentTypeCatalog.DOMAIN_MACHINE
    if entry.blob_name.startswith("DOC. PERSONAL/"):
        return DocumentTypeCatalog.DOMAIN_PERSONAL
    return None


# Un TOKEN (palabra) de un segmento de carpeta es un código de flota si
# empieza por letra(s) + guion opcional + dígitos, tal como usa
# fleet.MachineAsset.code (S040: "A54, Z45, B27"). Ancla en el propio
# token, no en el segmento completo -- corrección real S041: algunas
# carpetas escriben el código primero ("A-29 E-0356-BBZ (GR)"), pero
# otras (carretillas/dumpers) escriben antes una palabra descriptiva
# ("CARRETILLA T13 - E-1364-BFL", "DUMPER T27 E-9982-BHD") -- con el
# ancla en el segmento completo esos casos nunca llegaban a probar el
# código real, y el archivo se quedaba sin reubicar aunque el tipo
# documental sí se hubiera identificado con certeza (hallazgo real:
# manuales de despiece correctamente tipificados MANUAL_DESPIECE que
# nunca salían de cuarentena).
_FOLDER_MACHINE_CODE_RE = re.compile(r"^([A-Z]+-?\d+)")


def resolve_machine_asset(entry) -> MachineAsset | None:
    """
    Best-effort lookup of the real `fleet.MachineAsset` a MACHINE-domain
    file's folder belongs to, by scanning every word of every
    `parent_path` segment for something matching a fleet code and
    querying `MachineAsset.code` (dashes stripped, case-insensitive --
    folders write "A-29", the fleet catalogue writes "A29"). Read-only,
    `fleet` (H12) is live production infrastructure, not H17-H25 --
    safe to query per the H29 annex 3.15 isolation rule, which only
    excludes document_ingestion/entity_matching_service/
    machine_documents/personal_documents.

    Word-by-word, not segment-by-segment (S041 fix) -- a segment can
    carry a descriptive word before the real code ("CARRETILLA T13 -
    E-1364-BFL"), and the code is never guaranteed to be the first
    word. A token that merely looks like a code (e.g. a plate,
    "E-1364") but matches no real `MachineAsset` is harmless --
    querying it just returns nothing and scanning continues; only a
    real match short-circuits the search.

    Returns None if nothing in the path matches any real machine --
    callers must treat that as "can't check", never as "no mismatch".

    ---

    Búsqueda de mejor esfuerzo del `fleet.MachineAsset` real al que
    pertenece la carpeta de un archivo de dominio MÁQUINA, recorriendo
    cada palabra de cada segmento de `parent_path` en busca de algo con
    forma de código de flota y consultando `MachineAsset.code` (sin
    guiones, sin distinguir mayúsculas -- las carpetas escriben "A-29",
    el catálogo de flota escribe "A29"). Solo lectura, `fleet` (H12) es
    infraestructura viva en producción, no H17-H25 -- consultarlo es
    seguro según la regla de aislamiento 3.15 del anexo H29, que solo
    excluye document_ingestion/entity_matching_service/
    machine_documents/personal_documents.

    Palabra a palabra, no segmento a segmento (corrección S041) -- un
    segmento puede llevar una palabra descriptiva antes del código real
    ("CARRETILLA T13 - E-1364-BFL"), y el código no siempre es la
    primera palabra. Un token que simplemente parece un código (p. ej.
    una matrícula, "E-1364") pero no coincide con ningún
    `MachineAsset` real es inofensivo -- consultarlo solo devuelve
    nada y la búsqueda continúa; solo una coincidencia real corta la
    búsqueda.

    Devuelve None si nada en la ruta coincide con ninguna máquina real
    -- quien llama debe tratarlo como "no se puede comprobar", nunca
    como "no hay discrepancia".
    """
    for segment in entry.parent_path.split("/"):
        asset = _machine_from_text(segment)
        if asset:
            return asset
    return None


# S117 (H30, Fase 2) -- matrícula española en texto libre: 4 dígitos y 3
# letras, con o sin separador ("3968HWN", "0230 KWB", "9843-KBZ").
_TEXT_PLATE_RE = re.compile(r"(?<![0-9A-Z])(\d{4})[\s-]?([A-Z]{3})(?![A-Z])")


def _machine_from_text(text):
    """
    S117. Finds the real MachineAsset named in a piece of text (a folder
    segment or a file name): fleet codes word by word (punctuation
    around the word stripped -- "(X-01)" is X01) and Spanish plates,
    compared against BOTH MachineAsset.code and MachineAsset.plate
    without dashes/spaces (plate-coded cars carry the plate as code:
    "0230KWB"). Returns None when nothing matches a real machine.
    ---
    S117. Busca la MachineAsset real nombrada en un texto (un segmento
    de carpeta o un nombre de archivo): códigos de flota palabra a
    palabra (quitando la puntuación que rodea la palabra -- "(X-01)" es
    X01) y matrículas españolas, contra MachineAsset.code Y
    MachineAsset.plate sin guiones ni espacios (los turismos llevan la
    matrícula como código: "0230KWB"). Devuelve None si nada coincide
    con una máquina real.
    """
    from django.db.models import Value
    from django.db.models.functions import Replace, Upper

    upper = (text or "").upper()
    for word in upper.split():
        word = word.strip("()[]{}.,;:_")
        match = _FOLDER_MACHINE_CODE_RE.match(word)
        if not match:
            continue
        candidate_code = match.group(1).replace("-", "")
        asset = MachineAsset.objects.filter(code__iexact=candidate_code).first()
        if asset:
            return asset
    for match in _TEXT_PLATE_RE.finditer(upper):
        plate = match.group(1) + match.group(2)
        asset = (
            MachineAsset.objects
            .annotate(
                norm_code=Upper(Replace(Replace("code", Value("-"), Value("")), Value(" "), Value(""))),
                norm_plate=Upper(Replace(Replace("plate", Value("-"), Value("")), Value(" "), Value(""))),
            )
            .filter(Q(norm_code=plate) | Q(norm_plate=plate))
            .first()
        )
        if asset:
            return asset
    return None


def resolve_machine_asset_with_filename(entry):
    """
    S117 (H30, Fase 2). Same as resolve_machine_asset(), and, when the
    folder names no real machine (generic folders: GESTORIA VEHICULOS,
    a family's OBSOLETO...), the file name itself.
    ---
    S117 (H30, Fase 2). Igual que resolve_machine_asset() y, si la
    carpeta no nombra ninguna máquina real (carpetas genéricas:
    GESTORIA VEHICULOS, OBSOLETO de una familia...), el propio nombre
    del archivo.
    """
    return resolve_machine_asset(entry) or _machine_from_text(entry.name)


# S042, Miguel Ángel, verbatim tras confirmar que el `company` de
# MachineAsset apunta a `ivr_config.Company` -- un único inquilino de
# plataforma ("Grupo Álvarez", nunca ambiguo) y NO la empresa/sección
# interna real (GRA/TRA/GRH viven en los campos de texto company_code/
# company_name): "había pensado precisamente directamente a Grúas
# Adolfo, es GRA". Cajón por defecto para una máquina recién creada
# hasta que alguien confirme su empresa/sección interna real -- nunca
# un valor inventado, siempre los datos reales de una máquina GRA ya
# existente en el catálogo.
_DEFAULT_MACHINE_COMPANY_CODE = "GRA"


# Vehículos de empresa nuevos sin ningún código de flota clásico
# (S043): la carpeta los nombra por su matrícula española en formato
# actual (4 dígitos + 3 consonantes, con o sin espacio -- "2119 NGV",
# "2119NGV"), nunca con forma letra(s)+dígitos como una máquina de la
# flota. Caso real que lo motivó: "VEHICULOS DE EMPRESA/DOCUMENT NUEVO
# ADOLFO BMW 2119 NGV" -- una proforma y un justificante de depósito
# de compra (ambos con fecha real 2026-07-31, sin MachineAsset todavía)
# se clasificaban correctamente por Gemini (dominio MACHINE, tipo
# PROFORMA/confianza ALTA) pero terminaban en NO CONFORMES igual,
# porque ningún segmento de la carpeta tenía forma de código de flota
# -- _FOLDER_MACHINE_CODE_RE nunca podía encontrar nada de lo que
# partir. Miguel Ángel, verbatim (S043), confirmando el diseño antes
# de tocar código: "Las matrículas, como norma general, están
# correctamente en BBDD." Confirmado con datos reales de producción:
# varios MachineAsset ya usan la propia matrícula en formato actual
# como `code` cuando no hay código de flota clásico que asignar
# (4542KGD, 6788DMV, 3072MDV) -- mismo patrón que este bloque replica,
# nunca uno nuevo inventado.
_FOLDER_PLATE_RE = re.compile(r"(\d{4})[\s-]?([A-Z]{3})\b")


def resolve_or_create_machine_asset(
    entry, result: dict, allow_create: bool = True,
) -> MachineAsset | None:
    """
    Same lookup as `resolve_machine_asset()`, extended to create a
    real new `MachineAsset` when the folder clearly names a fleet
    code that matches no existing machine -- S042, Miguel Ángel,
    verbatim: "¿Qué debemos de hacer? [con una máquina nueva] Debemos
    de juntar toda la documentación que tenemos de esa máquina y
    sacar su ficha (...) Crear la máquina en fleet.MachineAsset
    automáticamente, igual que ya hace con trabajadores nuevos" --
    same real incident that motivated this: `A-69`/`506` (minigrúa)
    had real, correctly-classified documentation sitting in a
    correctly-named folder, but no `MachineAsset` row at all, so
    `resolve_machine_asset()` could never relocate anything for them,
    however many documents piled up.

    Real constraint `resolve_or_create_person_identity` doesn't share:
    `MachineAsset.company` is a required FK to `ivr_config.Company` --
    a genuinely different, cross-app, production-critical field (each
    machine is a real cost centre, work-order hours and delivery
    notes get imputed against it). Confirmed with real data before
    writing this (never guessed): there is exactly ONE `Company` row
    in the whole platform ("Grupo Álvarez", the platform tenant
    itself) -- so `company` is never actually ambiguous. The real
    ambiguity Miguel Ángel flagged (GRA/TRA/GRH -- Grúas, Asistencia,
    Plataformas... "una sección dentro de la empresa") lives entirely
    in the free-text `company_code`/`company_name` fields, not in
    `company` -- his own explicit default for those, verbatim: "Grúas
    Adolfo, es GRA" (`_DEFAULT_MACHINE_COMPANY_CODE`). Real values
    copied from an existing GRA-coded `MachineAsset`, never
    hand-typed -- if the exact `company_name` string in the catalogue
    ever changes, this keeps matching it instead of drifting stale.

    `result["machine_asset_note"]` announces the creation so it lands
    in the file's own audit trail (`DataOperationLogEntry.detail`) --
    the closest equivalent this session's scope can safely build to
    Miguel Ángel's "alerta visual" ask without touching `fleet`'s own
    schema (no `pending_review`/nullable-`company` field exists there
    today; adding one is a `fleet`-focused decision of its own, not a
    side effect of a `document_explorer` session).

    Returns None when no plausible fleet-code-shaped folder segment
    exists at all (nothing to create from) or when no reference GRA
    machine exists to copy real company fields from (never invents
    one) -- callers must treat this exactly like `resolve_machine_
    asset()` returning None: "can't resolve," stays flagged, never a
    guess.

    ---

    Misma búsqueda que `resolve_machine_asset()`, ampliada para crear
    un `MachineAsset` real cuando la carpeta nombra con claridad un
    código de flota que no coincide con ninguna máquina existente --
    S042, Miguel Ángel, verbatim: "¿Qué debemos de hacer? [con una
    máquina nueva] Debemos de juntar toda la documentación que
    tenemos de esa máquina y sacar su ficha (...) Crear la máquina en
    fleet.MachineAsset automáticamente, igual que ya hace con
    trabajadores nuevos" -- mismo incidente real que lo motivó:
    `A-69`/`506` (minigrúa) tenían documentación real ya bien
    clasificada en una carpeta con el nombre correcto, pero ninguna
    fila `MachineAsset` -- así que `resolve_machine_asset()` nunca
    podía reubicar nada para ellas, por muchos documentos que se
    acumularan.

    Restricción real que `resolve_or_create_person_identity` no
    comparte: `MachineAsset.company` es una FK obligatoria a
    `ivr_config.Company` -- un campo genuinamente distinto, entre
    apps, crítico en producción (cada máquina es un centro de coste
    real, horas de partes de trabajo y albaranes de terceros se
    imputan contra ella). Confirmado con datos reales antes de
    escribir esto (nunca supuesto): existe exactamente UNA fila
    `Company` en toda la plataforma ("Grupo Álvarez", el propio
    inquilino de la plataforma) -- así que `company` nunca es
    realmente ambiguo. La ambigüedad real que señaló Miguel Ángel
    (GRA/TRA/GRH -- Grúas, Asistencia, Plataformas... "una sección
    dentro de la empresa") vive por completo en los campos de texto
    `company_code`/`company_name`, no en `company` -- su propio valor
    por defecto explícito para esos, verbatim: "Grúas Adolfo, es GRA"
    (`_DEFAULT_MACHINE_COMPANY_CODE`). Valores reales copiados de un
    `MachineAsset` GRA ya existente, nunca escritos a mano -- si la
    cadena exacta de `company_name` cambia algún día en el catálogo,
    esto sigue coincidiendo con ella en vez de quedarse obsoleto.

    `result["machine_asset_note"]` anuncia la creación para que quede
    en el propio rastro de auditoría del archivo
    (`DataOperationLogEntry.detail`) -- lo más parecido que el alcance
    de esta sesión puede construir con seguridad a la "alerta visual"
    que pidió Miguel Ángel, sin tocar el propio esquema de `fleet`
    (hoy no existe ningún campo `pending_review`/`company` anulable
    ahí; añadir uno es una decisión propia centrada en `fleet`, no un
    efecto secundario de una sesión de `document_explorer`).

    Devuelve None cuando no hay ningún segmento de carpeta con forma
    de código de flota (nada de lo que partir) o cuando no existe
    ninguna máquina GRA de referencia de la que copiar los campos
    reales de empresa (nunca se inventa una) -- quien llama debe
    tratarlo exactamente igual que un None de `resolve_machine_
    asset()`: "no se puede resolver", se queda marcado, nunca una
    suposición.
    """
    asset = resolve_machine_asset(entry)
    if asset:
        return asset

    candidate_code = None
    for segment in entry.parent_path.split("/"):
        for word in segment.strip().split():
            match = _FOLDER_MACHINE_CODE_RE.match(word)
            if match:
                candidate_code = match.group(1).replace("-", "").upper()
                break
        if candidate_code:
            break

    candidate_plate = None
    if not candidate_code:
        # Respaldo por matrícula (S043) -- ver _FOLDER_PLATE_RE. Sobre
        # el segmento completo, no palabra a palabra: la matrícula
        # puede llegar partida en dos tokens por el espacio real de la
        # carpeta ("2119 NGV" -> "2119" y "NGV" por separado).
        for segment in entry.parent_path.split("/"):
            match = _FOLDER_PLATE_RE.search(segment.strip().upper())
            if match:
                candidate_plate = match.group(1) + match.group(2)
                break

    if not candidate_code and not candidate_plate:
        # Respaldo por machine_code_hint (H30, S046) -- incidente real:
        # un archivo reencolado desde NO CONFORMES vivía en la RAÍZ del
        # cubo (sin ninguna subcarpeta de máquina), con curator_note
        # explícito ("Pertenece al centro de gasto P-26") y con Gemini
        # extrayendo correctamente machine_code_hint="P-26" del propio
        # contenido del documento -- pero nunca se resolvía, porque
        # tanto resolve_machine_asset() como el bloque de arriba solo
        # miran entry.parent_path, y sin subcarpeta no hay nada que
        # escanear. machine_code_hint es exactamente la misma pista
        # que la carpeta le da a la búsqueda de arriba (un código de
        # flota o una matrícula, según lo que el propio prompt le pide
        # a Gemini extraer), así que se prueba con el mismo criterio:
        # primero como código de flota (_FOLDER_MACHINE_CODE_RE),
        # después como matrícula (_FOLDER_PLATE_RE) -- nunca se crea
        # una máquina nueva solo a partir de esta pista (podría ser un
        # error de lectura de Gemini sin la verificación adicional que
        # sí tiene una carpeta ya nombrada por un humano); si no
        # resuelve contra un MachineAsset YA EXISTENTE, se sigue
        # devolviendo None, igual que cualquier otro caso sin resolver.
        #
        # Backup via machine_code_hint (H30, S046) -- real incident: a
        # file requeued from NO CONFORMES lived at the bucket ROOT (no
        # machine subfolder), with an explicit curator_note ("Pertenece
        # al centro de gasto P-26") and Gemini correctly extracting
        # machine_code_hint="P-26" from the document's own content --
        # yet it never resolved, because both resolve_machine_asset()
        # and the block above only look at entry.parent_path, and
        # without a subfolder there is nothing to scan. machine_code_
        # hint carries the exact same kind of clue the folder gives the
        # search above, so it is tried with the same criteria: first as
        # a fleet code, then as a plate -- never creates a new machine
        # from this hint alone (it could be a Gemini misread without
        # the extra verification a human-named folder already gives);
        # if it does not resolve against an EXISTING MachineAsset, this
        # still returns None, same as any other unresolved case.
        hint = (result.get("machine_code_hint") or "").strip().upper()
        if hint:
            code_match = _FOLDER_MACHINE_CODE_RE.match(hint)
            if code_match:
                hint_code = code_match.group(1).replace("-", "")
                asset = MachineAsset.objects.filter(
                    code__iexact=hint_code,
                ).first()
                if asset:
                    return asset
            plate_match = _FOLDER_PLATE_RE.search(hint)
            if plate_match:
                hint_plate = plate_match.group(1) + plate_match.group(2)
                asset = MachineAsset.objects.filter(
                    Q(code__iexact=hint_plate)
                    | Q(plate__iexact=hint_plate),
                ).first()
                if asset:
                    return asset
        return None

    if candidate_plate:
        asset = MachineAsset.objects.filter(
            Q(code__iexact=candidate_plate)
            | Q(plate__iexact=candidate_plate),
        ).first()
        if asset:
            return asset

    # S117 -- fallo real: los tres comandos de barrido (run_fase_a_
    # sweep, run_fase_a_sweep_scoped, run_fase_b1_ocr_classify)
    # llamaban a esta función también en DRY-RUN, así que una
    # "simulación" daba de alta máquinas nuevas de verdad en
    # fleet.MachineAsset. Con allow_create=False (lo que pasan ahora
    # en dry-run) nunca se crea nada: se anota en
    # result["would_create_machine"] qué código/matrícula se crearía y
    # se devuelve None. El pipeline real de ingesta sigue igual
    # (allow_create=True por defecto).
    if not allow_create:
        result["would_create_machine"] = candidate_plate or candidate_code
        return None

    reference = (
        MachineAsset.objects
        .filter(company_code=_DEFAULT_MACHINE_COMPANY_CODE)
        .select_related("company")
        .first()
    )
    if not reference:
        return None

    brand_model = (result.get("brand_model_hint") or "").strip()

    if candidate_plate:
        asset = MachineAsset.objects.create(
            company=reference.company,
            company_code=reference.company_code,
            company_name=reference.company_name,
            code=candidate_plate,
            plate=candidate_plate,
            brand_model=brand_model,
        )
        result["machine_asset_note"] = (
            "Vehículo de empresa nuevo creado automáticamente en la "
            "flota por matrícula (sin código de flota clásico en la "
            "carpeta): código/matrícula %s%s -- empresa/sección por "
            "defecto (%s, %s), pendiente de confirmar la real y de "
            "completar el resto de su ficha."
            % (
                candidate_plate,
                " (%s)" % brand_model if brand_model else "",
                reference.company_code, reference.company_name,
            )
        )
        return asset

    asset = MachineAsset.objects.create(
        company=reference.company,
        company_code=reference.company_code,
        company_name=reference.company_name,
        code=candidate_code,
        brand_model=brand_model,
    )
    result["machine_asset_note"] = (
        "Máquina nueva creada automáticamente en la flota: código "
        "%s%s -- empresa/sección por defecto (%s, %s), pendiente de "
        "confirmar la real y de completar el resto de su ficha."
        % (
            candidate_code,
            " (%s)" % brand_model if brand_model else "",
            reference.company_code, reference.company_name,
        )
    )
    return asset


# Extensiones que nunca son documentación real, confirmadas una a una
# contra un caso real antes de añadirlas -- nunca una lista genérica
# de "extensiones raras". `.log` (S043): un archivo real de cuarentena
# resultó ser un log de spooler de impresión de Windows
# (`Pipe:\\.\pipe\PMtoDistiller_ID_42:...`, "La operación se completó
# correctamente"), capturado sin querer junto a la documentación real
# -- mismo patrón exacto que los temporales de OneDrive ya filtrados
# en el agente H28 (ver anexo, "Temporales de OneDrive tratados como
# documentación"), pero del lado servidor: `classify_entry()` ya
# rechazaba `.log` por tipo MIME no soportado y sin conversión
# conocida, así que nunca llegaba a gastar una llamada real a Gemini
# -- pero se quedaba parado en NO CONFORMES para siempre en vez de
# eliminarse solo, con el mismo coste de revisión humana que un
# archivo genuinamente ambiguo. Miguel Ángel, verbatim (S043),
# confirmando que es basura real, no un caso a revisar: "No debería de
# enviarse a Gemini, hay que borrarlo."
_JUNK_EXTENSIONS = {"log"}


def is_known_junk_extension(entry) -> bool:
    """
    True when `entry`'s extension is in `_JUNK_EXTENSIONS` -- real
    junk confirmed one extension at a time (see that set's own
    comment for the real `.log` incident, S043), never a generic
    "looks unsupported" heuristic. Deliberately narrower than "Gemini
    can't read this type" (`_SUPPORTED_MIME_TYPES`/
    `_LIBREOFFICE_CONVERTIBLE_EXTENSIONS`/`_XPS_EXTENSIONS`): plenty
    of unsupported types are real content waiting on a future
    converter, not junk -- this only ever matches extensions
    confirmed junk by a real incident, added to the set one at a
    time, never inferred from "classify_entry() already rejects it."

    Runs before any Gemini call, same reasoning and same directive as
    `is_empty_file()`/`resolve_archive_redundancy()` -- S042, Miguel
    Ángel: "no podemos nosotros borrar nada... dotar al sistema de las
    herramientas pertinentes para que lo haga de forma automática."

    ---

    Cierto cuando la extensión de `entry` está en `_JUNK_EXTENSIONS`
    -- basura real confirmada extensión a extensión (ver el propio
    comentario de ese conjunto para el incidente real de `.log`,
    S043), nunca una heurística genérica de "parece no soportado".
    Deliberadamente más estrecho que "Gemini no puede leer esto"
    (`_SUPPORTED_MIME_TYPES`/`_LIBREOFFICE_CONVERTIBLE_EXTENSIONS`/
    `_XPS_EXTENSIONS`): muchos tipos no soportados son contenido real
    a la espera de un conversor futuro, no basura -- esto solo casa
    con extensiones confirmadas basura por un incidente real, añadidas
    al conjunto una a una, nunca inferidas de "classify_entry() ya lo
    rechaza."

    Corre antes de cualquier llamada a Gemini, mismo razonamiento y
    misma directriz que `is_empty_file()`/`resolve_archive_
    redundancy()` -- S042, Miguel Ángel: "no podemos nosotros borrar
    nada... dotar al sistema de las herramientas pertinentes para que
    lo haga de forma automática."
    """
    extension = (
        entry.name.rsplit(".", 1)[-1].lower() if "." in entry.name else ""
    )
    return extension in _JUNK_EXTENSIONS


def is_empty_file(entry) -> bool:
    """
    True when `entry` is a genuine 0-byte file -- real junk, never
    ambiguous, confirmed against production data (S042): `pru4eba.
    docx`/`pru4eba (1).docx`, both `size_bytes=0`, both sent to NO
    CONFORMES with Gemini's own reasoning confirming there was
    nothing to read ("El documento está completamente en blanco").
    Zero bytes needs no API call to confirm it is empty -- calling
    Gemini on it is pure wasted cost for a certain answer this check
    already has for free.

    S042, Miguel Ángel, same directive as `resolve_archive_
    redundancy()`: **"no podemos nosotros borrar nada... dotar al
    sistema de las herramientas pertinentes para que lo haga de forma
    automática."** Runs before any Gemini call, same reasoning.

    Deliberately narrow -- ONLY `size_bytes == 0`, never "small" or
    "probably junk" by any fuzzier heuristic. A 1-byte file could
    still be something real (a lone character someone typed); 0 bytes
    cannot be anything at all, by definition, regardless of
    extension.

    ---

    Cierto cuando `entry` es un archivo genuinamente de 0 bytes --
    basura real, nunca ambigua, confirmado contra datos de producción
    (S042): `pru4eba.docx`/`pru4eba (1).docx`, ambos `size_bytes=0`,
    ambos enviados a NO CONFORMES con el propio razonamiento de
    Gemini confirmando que no había nada que leer ("El documento está
    completamente en blanco"). Cero bytes no necesita ninguna llamada
    a la API para confirmar que está vacío -- llamar a Gemini para
    esto es coste puro tirado por una respuesta segura que esta
    comprobación ya tiene gratis.

    S042, Miguel Ángel, misma directriz que
    `resolve_archive_redundancy()`: **"no podemos nosotros borrar
    nada... dotar al sistema de las herramientas pertinentes para que
    lo haga de forma automática."** Corre antes de cualquier llamada a
    Gemini, mismo razonamiento.

    Deliberadamente estrecho -- SOLO `size_bytes == 0`, nunca
    "pequeño" o "probablemente basura" por ninguna heurística más
    difusa. Un archivo de 1 byte todavía podría ser algo real (un
    único carácter que alguien tecleó); 0 bytes no puede ser nada en
    absoluto, por definición, sea cual sea su extensión.
    """
    return entry.size_bytes == 0


def resolve_duplicate_of_filed_document(entry) -> bool:
    """
    True when `entry` is a byte-for-byte duplicate (same real CRC32C
    + same size, both already indexed on the row -- no download, no
    extraction, cheaper than `resolve_archive_redundancy()`) of a
    document that ALREADY lives outside quarantine/NO CONFORMES --
    i.e. a real, already-filed copy exists, and this one adds
    nothing.

    S042, Miguel Ángel, verbatim, after discovering the real incident
    that motivated this: **"cuando detecte un duplicado, borrarlo, el
    que se está colando, y dejamos el que ya tenemos guardado... se
    envía a la papelera."** Real case that surfaced it: `A-69 Leasing
    BBVA.pdf` had TWO live rows, identical CRC32C and size -- one
    already correctly filed under `DOC. MAQUINAS/GRUAS MOVILES (A)/
    A-69 SANY SAC700E`, the other endlessly cycling through quarantine
    (142 classification passes, Gemini confidently resolving domain/
    type nearly every time, never once relocating -- see
    `RequeueNoConformesView`'s own docstring for the real root cause
    of THAT loop, fixed separately). Even with that loop fixed, a
    quarantine copy that is a pure duplicate of something already
    filed has nothing left to classify -- Gemini would just confirm
    what the real copy already proves.

    Never touches the `duplicates_service.py` panel or its own
    resolution flow (hash-group review, human-facing) -- this is a
    narrower, automatic, pre-Gemini check specific to quarantine: is
    there a REAL, already-filed twin RIGHT NOW, yes or no. `entry`
    itself gets trashed (via the already-existing `trash_dossier_
    entry()`, same recoverable per-user papelera) when this is True;
    the kept copy is whichever one was already filed, untouched.

    ---

    Cierto cuando `entry` es un duplicado byte a byte (mismo CRC32C
    real + mismo tamaño, los dos ya indexados en la propia fila --
    sin descargar nada, sin extraer nada, más barato que
    `resolve_archive_redundancy()`) de un documento que YA vive fuera
    de cuarentena/NO CONFORMES -- es decir, ya existe una copia real,
    archivada, y esta no aporta nada.

    S042, Miguel Ángel, verbatim, tras descubrir el incidente real que
    lo motivó: **"cuando detecte un duplicado, borrarlo, el que se
    está colando, y dejamos el que ya tenemos guardado... se envía a
    la papelera."** Caso real que lo sacó a la luz: `A-69 Leasing
    BBVA.pdf` tenía DOS filas vivas, mismo CRC32C y tamaño idénticos --
    una ya bien archivada bajo `DOC. MAQUINAS/GRUAS MOVILES (A)/A-69
    SANY SAC700E`, la otra dando vueltas sin fin por cuarentena (142
    pasadas de clasificación, Gemini resolviendo dominio/tipo con
    confianza casi siempre, sin reubicar ni una sola vez -- ver el
    propio docstring de `RequeueNoConformesView` para la causa raíz
    real de ESE bucle, corregida aparte). Incluso con ese bucle ya
    arreglado, una copia de cuarentena que es puro duplicado de algo
    ya archivado no tiene nada que clasificar -- Gemini solo
    confirmaría lo que la copia real ya demuestra.

    Nunca toca el panel de `duplicates_service.py` ni su propio flujo
    de resolución (revisión por grupos de hash, de cara al humano) --
    esta es una comprobación más estrecha, automática, previa a
    Gemini, específica de cuarentena: ¿existe ahora mismo un gemelo
    REAL ya archivado, sí o no? La propia `entry` se envía a la
    papelera (vía el ya existente `trash_dossier_entry()`, misma
    papelera recuperable por usuario) cuando esto es Cierto; la copia
    que se conserva es la que ya estaba archivada, intacta.
    """
    if not entry.crc32c or not entry.size_bytes:
        return False
    return (
        DocumentIndexEntry.objects.filter(
            bucket=entry.bucket, crc32c=entry.crc32c,
            size_bytes=entry.size_bytes,
            deleted_at__isnull=True, purged_at__isnull=True,
        )
        .exclude(pk=entry.pk)
        .exclude(quarantine_scope_q())
        .exclude(parent_path=NO_CONFORMES_PREFIX.rstrip("/"))
        .exists()
    )


def resolve_archive_redundancy(entry) -> dict | None:
    """
    Checks whether a `.zip`/`.rar` quarantine file is 100% redundant
    -- every single entry inside it already exists, byte-for-byte
    (real CRC32C + size match, `archive_service.compute_crc32c()`),
    as a real, already-filed document somewhere OUTSIDE quarantine/NO
    CONFORMES. Never checks type or content meaning -- pure "does an
    identical copy already exist," the same trustworthy signal
    `duplicates_service.py` already uses for everything else.

    S042, Miguel Ángel, verbatim, after being shown two real archives
    whose every entry already existed as loose, correctly-filed
    files: **"no podemos nosotros borrar nada... dotar al sistema de
    las herramientas pertinentes para que lo haga de forma
    automática."** Gemini is never called for this -- it can't read
    archive bytes at all (`_SUPPORTED_MIME_TYPES`/`_LIBREOFFICE_
    CONVERTIBLE_EXTENSIONS`/`_XPS_EXTENSIONS` all exclude them), so
    this check runs BEFORE any Gemini call, cheap and deterministic.
    A fully-redundant match is soft-deleted via the already-existing
    `trash_dossier_entry()` -- same per-user trash, same
    `_DOSSIER_TRASH_USERNAME` automated identity, no new deletion
    mechanism needed.

    Returns a dict `{"fully_redundant": bool, "matched_paths": [...]}`
    when the archive could be listed and every entry could be
    extracted -- `fully_redundant=True` only when ALL entries matched
    a real file. Returns None when the archive can't even be listed/
    read, or any single entry fails to extract -- callers must treat
    that exactly like "can't determine," never guess a fallback
    either way.

    **Deliberately scoped, S042**: only ever DELETES a fully-redundant
    archive. An archive with SOME genuinely new content inside stays
    flagged in NO CONFORMES as before -- automatically extracting and
    uploading new content as fresh GCS objects is a real
    infrastructure decision (new writes to GCS, not just index moves)
    that deserves its own explicit design, not a silent extra
    behaviour bolted onto this check.

    ---

    Comprueba si un archivo `.zip`/`.rar` de cuarentena es 100%
    redundante -- cada entrada de dentro ya existe, byte a byte
    (coincidencia real de CRC32C + tamaño,
    `archive_service.compute_crc32c()`), como un documento real ya
    archivado en algún sitio FUERA de cuarentena/NO CONFORMES. Nunca
    comprueba tipo ni significado del contenido -- pura "¿ya existe
    una copia idéntica?", la misma señal de confianza que ya usa
    `duplicates_service.py` para todo lo demás.

    S042, Miguel Ángel, verbatim, tras ver dos archivos comprimidos
    reales cuyo contenido entero ya existía como archivos sueltos bien
    archivados: **"no podemos nosotros borrar nada... dotar al
    sistema de las herramientas pertinentes para que lo haga de forma
    automática."** Nunca se llama a Gemini para esto -- no puede leer
    bytes de un archivo comprimido en absoluto
    (`_SUPPORTED_MIME_TYPES`/`_LIBREOFFICE_CONVERTIBLE_EXTENSIONS`/
    `_XPS_EXTENSIONS` los excluyen todos), así que esta comprobación
    corre ANTES de cualquier llamada a Gemini, barata y determinista.
    Una coincidencia 100% redundante se borra lógicamente vía el ya
    existente `trash_dossier_entry()` -- misma papelera por usuario,
    misma identidad automática `_DOSSIER_TRASH_USERNAME`, ningún
    mecanismo de borrado nuevo.

    Devuelve un diccionario `{"fully_redundant": bool,
    "matched_paths": [...]}` cuando el archivo se pudo listar y cada
    entrada se pudo extraer -- `fully_redundant=True` solo cuando
    TODAS las entradas coincidieron con un archivo real. Devuelve
    None cuando el archivo ni siquiera se puede listar/leer, o
    cualquier entrada falla al extraerse -- quien llama debe tratarlo
    exactamente igual que "no se puede determinar", nunca adivinar un
    resultado por defecto tampoco.

    **Acotado a propósito, S042**: solo BORRA nunca un archivo 100%
    redundante. Un archivo comprimido con ALGÚN contenido genuinamente
    nuevo dentro se queda marcado en NO CONFORMES como hasta ahora --
    extraer y subir contenido nuevo como objetos GCS reales es una
    decisión de infraestructura real (escrituras nuevas a GCS, no
    solo movimientos de índice) que merece su propio diseño explícito,
    no un comportamiento extra añadido en silencio a esta
    comprobación.
    """
    extension = (
        entry.name.rsplit(".", 1)[-1].lower()
        if "." in entry.name else ""
    )
    if extension not in archive_service.ARCHIVE_EXTENSIONS:
        return None

    content = download_bytes(entry.bucket, entry.blob_name)
    raw_items = archive_service.list_entries(content, extension)
    if not raw_items:
        return None

    matched_paths = []
    for item in raw_items:
        inner_bytes = archive_service.extract_entry(
            content, extension, item["path"],
        )
        if inner_bytes is None:
            return None
        crc32c = archive_service.compute_crc32c(inner_bytes)
        size = len(inner_bytes)
        real_match = (
            DocumentIndexEntry.objects.filter(
                bucket=entry.bucket, crc32c=crc32c, size_bytes=size,
                deleted_at__isnull=True, purged_at__isnull=True,
            )
            .exclude(quarantine_scope_q())
            .exclude(parent_path=NO_CONFORMES_PREFIX.rstrip("/"))
            .exists()
        )
        if not real_match:
            return {
                "fully_redundant": False, "matched_paths": matched_paths,
            }
        matched_paths.append(item["path"])

    return {"fully_redundant": True, "matched_paths": matched_paths}


_DNI_NORMALIZE_RE = re.compile(r"[^A-Z0-9]")

# Letra de control real del DNI/NIE español -- algoritmo público y
# determinista (los 8 dígitos, en NIE con la letra inicial sustituida
# por 0/1/2, módulo 23, indexan esta tabla). Confirmado con datos
# reales, S040: Gemini leyó "25902678A" para un documento cuyo DNI
# real (verificado con 5 documentos distintos de la misma persona,
# más el propio DNI escaneado) es "24902678A" -- "25902678A" no pasa
# esta comprobación (letra esperada "D", no "A"), así que ni siquiera
# hacía falta abrir el documento para descartarlo.
_DNI_CHECK_LETTERS = "TRWAGMYFPDXBNJZSQVHLCKE"
_NIE_PREFIX_DIGIT = {"X": "0", "Y": "1", "Z": "2"}


def _normalize_dni(raw_dni: str) -> str:
    """
    Strips everything but letters/digits and uppercases -- plus one
    real correction, S042: a DNI is ALWAYS exactly 8 digits + 1 check
    letter (a NIE is 1 prefix letter + 7 digits + 1 check letter,
    already exactly 9 characters with no ambiguity). A cleaned value
    of exactly 10 characters that starts with "0" and is otherwise 8
    digits + letter can only be a real DNI with a spurious leading
    zero Gemini added -- never a genuinely different 9-digit number,
    Spanish DNIs don't have those. Confirmed against real production
    data (S042): the SAME real person (`PersonIdentity` already
    seeded, DNI `77773964Q`) had two of three documents read as
    `077773964Q` -- exact right number, wrong length purely from the
    leading zero -- which failed `is_valid_spanish_dni()`'s plain
    length check before ever reaching a lookup, sending both files to
    NO CONFORMES despite the identity already existing.

    ---

    Quita todo menos letras/dígitos y pasa a mayúsculas -- más una
    corrección real, S042: un DNI son SIEMPRE exactamente 8 dígitos +
    1 letra de control (un NIE es 1 letra de prefijo + 7 dígitos + 1
    letra de control, ya exactamente 9 caracteres sin ambigüedad). Un
    valor limpio de exactamente 10 caracteres que empieza por "0" y el
    resto son 8 dígitos + letra solo puede ser un DNI real con un cero
    espurio que añadió Gemini -- nunca un número de 9 dígitos
    genuinamente distinto, los DNI españoles no los tienen. Confirmado
    contra datos reales de producción (S042): la MISMA persona real
    (`PersonIdentity` ya sembrada, DNI `77773964Q`) tenía dos de tres
    documentos leídos como `077773964Q` -- el número exacto correcto,
    con la longitud mal solo por el cero delante -- que fallaba la
    simple comprobación de longitud de `is_valid_spanish_dni()` antes
    de llegar siquiera a una búsqueda, enviando los dos archivos a NO
    CONFORMES pese a que la identidad ya existía.
    """
    value = _DNI_NORMALIZE_RE.sub("", raw_dni.upper())
    if (
        len(value) == 10 and value[0] == "0"
        and value[1:9].isdigit() and value[9].isalpha()
    ):
        value = value[1:]
    return value


def is_valid_spanish_dni(raw_dni: str) -> bool:
    """
    Validates a Spanish DNI/NIE by its real, public check-letter
    algorithm -- purely arithmetic, no network call, no Gemini,
    catches a misread digit for free. A `dni_hint` that fails this
    can never be a real DNI, so it is rejected before ever reaching
    `PersonIdentity` -- see module-level note above for the real case
    that motivated this (S040).

    ---

    Valida un DNI/NIE español con su algoritmo real y público de letra
    de control -- puramente aritmético, sin llamada de red, sin
    Gemini, detecta gratis un dígito mal leído. Un `dni_hint` que no
    pasa esto nunca puede ser un DNI real, así que se rechaza antes de
    llegar siquiera a `PersonIdentity` -- ver la nota a nivel de
    módulo más arriba para el caso real que motivó esto (S040).
    """
    value = _normalize_dni(raw_dni)
    if len(value) != 9:
        return False
    digits_part, letter = value[:8], value[8]
    if not letter.isalpha():
        return False
    first_char = digits_part[0]
    if first_char in _NIE_PREFIX_DIGIT:
        digits_part = _NIE_PREFIX_DIGIT[first_char] + digits_part[1:]
    if not digits_part.isdigit():
        return False
    return letter == _DNI_CHECK_LETTERS[int(digits_part) % 23]


def resolve_person_identity(dni_hint: str) -> PersonIdentity | None:
    """
    Looks up `PersonIdentity` by a normalized `dni_hint`. A DNI is a
    hard identifier (unlike a name -- H28 annex, Hallazgo 5: the same
    operator's name spelled eight different ways) so an exact match
    here is trustworthy enough to override whatever Gemini read off
    one particular document, same principle already applied to
    machine code (`resolve_machine_asset`, H29 3.27).

    Rejects a `dni_hint` that fails `is_valid_spanish_dni()` before
    ever querying -- a real Gemini misread (S040) is caught for free,
    arithmetically, without needing the document open.

    Returns None both when `dni_hint` is empty/invalid/unreadable and
    when no `PersonIdentity` has been seeded for it yet
    (`seed_person_identities` hasn't classified that person's DNI, or
    never will if their DNI was never uploaded) -- callers must treat
    all these cases the same way: "cannot resolve", never guess a
    folder from the name alone.

    ---

    Busca `PersonIdentity` por un `dni_hint` normalizado. Un DNI es un
    identificador duro (a diferencia de un nombre -- anexo H28,
    Hallazgo 5: el nombre del mismo operario escrito de ocho formas
    distintas), así que una coincidencia exacta aquí es suficientemente
    fiable para prevalecer sobre lo que Gemini haya leído en un
    documento concreto -- mismo principio ya aplicado al código de
    máquina (`resolve_machine_asset`, H29 3.27).

    Rechaza un `dni_hint` que no pase `is_valid_spanish_dni()` antes
    siquiera de consultar -- una lectura errónea real de Gemini (S040)
    se detecta gratis, aritméticamente, sin necesitar el documento
    abierto.

    Devuelve None tanto cuando `dni_hint` está vacío/inválido/ilegible
    como cuando todavía no se ha sembrado ningún `PersonIdentity` para
    él (`seed_person_identities` no ha clasificado el DNI de esa
    persona todavía, o nunca lo hará si su DNI nunca se subió) -- quien
    llama debe tratar todos estos casos igual: "no se puede resolver",
    nunca adivinar una carpeta solo por el nombre.
    """
    dni_hint = (dni_hint or "").strip()
    if not dni_hint or not is_valid_spanish_dni(dni_hint):
        return None
    return PersonIdentity.objects.filter(dni=_normalize_dni(dni_hint)).first()


# Regla de negocio real de resolución de persona por nombre, verbatim
# de Miguel Ángel (H30, S69) -- NUNCA una lógica inventada de
# "nombre+primer apellido es único en 70 personas": "Cuando tengas
# nombre y apellido, que lo compruebes en la base de datos. ¿Cuántos
# hay con ese nombre y ese primer apellido? Hay solo uno. Ya está
# resuelto. No hay ninguno. Ya no trabaja aquí. Si hay más de uno, no
# se puede resuelve." Sustituye cualquier resolución de persona hecha
# a mano con DNIs sueltos en un comando de un solo uso (incidente real
# S69: dos archivos de PLAN_ACTUACION_CALOR resueltos con DNIs
# hardcodeados en vez de con esta regla como código reutilizable,
# corregido en la misma sesión).
NAME_MATCH_UNIQUE = "UNIQUE"
NAME_MATCH_INACTIVE = "INACTIVE"
NAME_MATCH_AMBIGUOUS = "AMBIGUOUS"


def resolve_person_by_name_count(given_name, first_surname, second_surname=None):
    """
    Implements Miguel Ángel's exact rule (H30, S69): count real
    `PersonIdentity` rows matching `given_name` + `first_surname`
    (case-insensitive). If `second_surname` is provided (the file
    name actually carries it), it's used as an extra real filter, not
    ignored -- it only narrows an already-ambiguous count, it is never
    required when absent.

    Returns a `(status, person_or_none)` tuple:
    - `(NAME_MATCH_UNIQUE, person)` -- exactly one real match, resolved.
    - `(NAME_MATCH_INACTIVE, None)` -- zero matches, this is itself a
      real fact (the person is not/no longer in the roster), not an
      "unresolved" case -- caller decides what that means (e.g. trash
      candidate), never leaves it in limbo.
    - `(NAME_MATCH_AMBIGUOUS, None)` -- two or more real matches, NEVER
      resolved by guessing the first candidate or by analogy.

    ---

    Implementa la regla exacta de Miguel Ángel (H30, S69): cuenta
    filas reales de `PersonIdentity` que coincidan en `given_name` +
    `first_surname` (sin distinguir mayúsculas). Si se aporta
    `second_surname` (el nombre de archivo lo trae de verdad), se usa
    como filtro real adicional, nunca se ignora -- pero solo acota un
    recuento ya ambiguo, nunca es obligatorio cuando no está presente.

    Devuelve una tupla `(estado, persona_o_none)`:
    - `(NAME_MATCH_UNIQUE, persona)` -- exactamente una coincidencia
      real, resuelto.
    - `(NAME_MATCH_INACTIVE, None)` -- cero coincidencias, esto es en
      sí mismo un dato real (la persona no está/ya no está en la
      plantilla), no un caso "sin resolver" -- quien llama decide qué
      hacer con eso (p. ej. candidato a papelera), nunca lo deja en
      limbo.
    - `(NAME_MATCH_AMBIGUOUS, None)` -- dos o más coincidencias reales,
      NUNCA se resuelve adivinando el primer candidato ni por analogía.
    """
    qs = PersonIdentity.objects.filter(
        given_name__iexact=(given_name or "").strip(),
        first_surname__iexact=(first_surname or "").strip(),
    )
    if second_surname:
        qs = qs.filter(second_surname__iexact=second_surname.strip())

    matches = list(qs)
    if len(matches) == 1:
        return NAME_MATCH_UNIQUE, matches[0]
    if len(matches) == 0:
        return NAME_MATCH_INACTIVE, None
    return NAME_MATCH_AMBIGUOUS, None





# Categoría de aterrizaje para toda identidad creada de forma
# automática (S041, decisión explícita de Miguel Ángel) -- ningún
# documento dice de forma fiable a cuál de las 13 categorías reales
# bajo DOC. PERSONAL/PERSONAL/ pertenece un trabajador nuevo
# (OPERARIOS, TALLER, ADMINISTRACION...), así que aterriza aquí,
# pendiente de que un humano la mueva a la real con la herramienta de
# mover ya existente.
_NEW_WORKER_STAGING_FOLDER = "DOC. PERSONAL/PERSONAL/PTE CONTRATACION"


def resolve_or_create_person_identity(
    result: dict, entry=None,
) -> PersonIdentity | None:
    """
    Same lookup as `resolve_person_identity()`, extended with two
    more behaviours confirmed explicitly by Miguel Ángel (S041) for
    when the `dni_hint` is well-formed (passes `is_valid_spanish_
    dni()`) but matches no existing `PersonIdentity`:

    1. Checks whether the extracted full name (`first_surname_hint`
       + `second_surname_hint` + `given_name_hint`) matches an
       existing `PersonIdentity` under a DIFFERENT dni. If so, this
       is treated as a suspected DNI misreading (same real-world
       failure mode as `is_valid_spanish_dni`'s own docstring, S040:
       Gemini can misread a digit even on a clear document) --
       NEVER creates a duplicate person for this. Sets
       `result["person_identity_note"]` with both DNIs so a human can
       decide, and returns None (unresolved, stays flagged).
    2. If the name doesn't match anyone either, this is a genuinely
       new worker. Creates a real new `PersonIdentity`, landing under
       `_NEW_WORKER_STAGING_FOLDER` -- verbatim, Miguel Ángel: "hay
       que dotar al sistema de la función de crear ese nuevo
       trabajador, para que tenga su carpeta y su documentación esté
       en su sitio." Sets `result["person_identity_note"]`
       announcing the creation. The file this run is processing gets
       relocated there this same pass, same as any resolved identity.

    Only creates a new identity when `dni_hint` passes
    `is_valid_spanish_dni()` -- no name or first/given name missing
    means not enough to safely create anyone, returns None without
    creating. **No longer requires the check letter to pass before
    checking whether the name matches someone already seeded
    (fixed S042)**: a misread digit almost always breaks the check
    letter too (that is precisely what it is designed to detect), so
    requiring it before this check left the "name matches a different
    DNI" safety net practically unreachable for the real case it was
    built to catch. Confirmed against real data (S042): the same real
    person (`GUTIERREZ MATEO, CRISTHIAN`, real DNI `77773964Q`
    already seeded) had a third document read as `77773969Q` --
    wrong check letter for that number, so it never reached this
    check even though the name matched exactly. The check letter is
    still mandatory to CREATE a new identity, just never to attempt
    this name check.

    ---

    Misma búsqueda que `resolve_person_identity()`, ampliada con dos
    comportamientos más confirmados explícitamente por Miguel Ángel
    (S041) para cuando el `dni_hint` está bien formado (pasa
    `is_valid_spanish_dni()`) pero no coincide con ningún
    `PersonIdentity` existente:

    1. Comprueba si el nombre completo extraído (`first_surname_hint`
       + `second_surname_hint` + `given_name_hint`) coincide con un
       `PersonIdentity` ya existente bajo un DNI DISTINTO. Si es así,
       se trata como sospecha de error de lectura del DNI (mismo
       fallo real ya documentado en el propio docstring de
       `is_valid_spanish_dni`, S040: Gemini puede leer mal un dígito
       incluso en un documento claro) -- NUNCA se crea una persona
       duplicada por esto. Deja `result["person_identity_note"]` con
       los dos DNI para que lo decida un humano, y devuelve None (sin
       resolver, se queda marcado).
    2. Si el nombre tampoco coincide con nadie, es un trabajador
       nuevo de verdad. Crea un `PersonIdentity` real, que aterriza
       en `_NEW_WORKER_STAGING_FOLDER` -- verbatim, Miguel Ángel: "hay
       que dotar al sistema de la función de crear ese nuevo
       trabajador, para que tenga su carpeta y su documentación esté
       en su sitio." Deja `result["person_identity_note"]` anunciando
       la creación. El archivo de esta pasada se reubica ahí mismo,
       igual que con cualquier identidad ya resuelta.

    Solo crea una identidad nueva cuando el `dni_hint` pasa
    `is_valid_spanish_dni()` -- sin nombre o sin nombre de pila no hay
    datos suficientes para crear a nadie con seguridad, devuelve None
    sin crear nada. **Ya NO exige que el `dni_hint` pase la letra de
    control antes de comprobar si el nombre coincide con alguien ya
    sembrado (corregido S042)**: un dígito mal leído casi siempre
    rompe también la letra de control (es justo lo que la letra de
    control detecta), así que exigirla antes de esta comprobación
    dejaba la propia salvaguarda de "nombre coincide con DNI
    distinto" prácticamente inalcanzable para el caso real que se
    construyó para detectar. Confirmado con datos reales (S042): a la
    misma persona real (`GUTIERREZ MATEO, CRISTHIAN`, DNI real
    `77773964Q` ya sembrado) un tercer documento le leyó
    `77773969Q` -- letra de control incorrecta para ese número, así
    que nunca llegaba a esta comprobación pese a que el nombre
    coincidía exactamente. La letra de control solo sigue siendo
    obligatoria para CREAR una identidad nueva, nunca para intentar
    esta comprobación de nombre.
    """
    dni_hint = (result.get("dni_hint") or "").strip()
    identity = resolve_person_identity(dni_hint)
    if identity:
        return identity
    if not dni_hint:
        return None

    first_surname = (result.get("first_surname_hint") or "").strip()
    second_surname = (result.get("second_surname_hint") or "").strip()
    given_name = (result.get("given_name_hint") or "").strip()
    if not first_surname or not given_name:
        return None

    dni = _normalize_dni(dni_hint)
    name_match = PersonIdentity.objects.filter(
        first_surname__iexact=first_surname,
        given_name__iexact=given_name,
    )
    if second_surname:
        name_match = name_match.filter(second_surname__iexact=second_surname)
    suspect = name_match.exclude(dni=dni).first()
    if suspect:
        result["person_identity_note"] = (
            "Posible error de lectura del DNI: el nombre coincide "
            "con %s %s, %s (DNI registrado %s), pero este documento "
            "trae %s -- no se crea a nadie nuevo, revisar a mano."
            % (
                suspect.first_surname, suspect.second_surname,
                suspect.given_name, suspect.dni, dni,
            )
        )
        return None

    if not is_valid_spanish_dni(dni_hint):
        return None

    folder_name = (
        "%s %s, %s" % (first_surname, second_surname, given_name)
        if second_surname
        else "%s, %s" % (first_surname, given_name)
    )
    identity = PersonIdentity.objects.create(
        dni=dni,
        first_surname=first_surname,
        second_surname=second_surname,
        given_name=given_name,
        folder_path="%s/%s" % (_NEW_WORKER_STAGING_FOLDER, folder_name),
        source_entry=entry,
    )
    result["person_identity_note"] = (
        "Trabajador nuevo creado automáticamente (%s, DNI %s) en "
        "PTE CONTRATACION -- pendiente de que un humano lo mueva a "
        "su categoría real." % (folder_name, dni)
    )
    return identity


# Cuenta a cuya papelera van los dossiers eliminados automáticamente
# (H29, S041) -- Miguel Ángel, dato real verificado en base de datos
# (pk=1, único CompanyUser con ese username): "el que va es al mío,
# al de administrador total, el superusuario. Yo soy el único que
# puede recuperar esos archivos." Cuenta compartida del departamento
# de administración, no una cuenta personal -- decisión explícita de
# Miguel Ángel de todos modos, se aplica tal cual.
_DOSSIER_TRASH_USERNAME = "alvarez_admin"


def _resolve_dossier_trash_user():
    """
    Returns the `CompanyUser` to attribute automatic dossier
    deletions to, or None if it can't be resolved (account renamed
    or removed) -- callers must never trash to a null `deleted_by`:
    an orphaned `deleted_at` with no owner is invisible in every
    papelera view (`deleted_by=company_user` filter), unrecoverable
    in practice from the panel -- exactly the "borrado accidental sin
    poder recuperar" H29 exists to prevent.

    ---

    Devuelve el `CompanyUser` al que se atribuyen los borrados
    automáticos de dossiers, o None si no se puede resolver (cuenta
    renombrada o eliminada) -- quien llama nunca debe reubicar a
    papelera con un `deleted_by` nulo: un `deleted_at` huérfano sin
    dueño es invisible en cualquier vista de papelera (filtro
    `deleted_by=company_user`), irrecuperable en la práctica desde el
    panel -- justo el "borrado accidental sin poder recuperar" que
    H29 existe para evitar.
    """
    from ivr_config.models import CompanyUser
    return CompanyUser.objects.select_related("user").filter(
        user__username=_DOSSIER_TRASH_USERNAME,
    ).first()


def trash_dossier_entry(entry) -> bool:
    """
    Soft-deletes `entry` to `_DOSSIER_TRASH_USERNAME`'s papelera --
    pure index write (`deleted_at`/`deleted_by`), `blob_name` in GCS
    never touched, same principle as every other operation in this
    module. Returns False (no-op, entry left untouched) when the
    admin `CompanyUser` can't be resolved -- see
    `_resolve_dossier_trash_user`.

    ---

    Reubica `entry` a la papelera de `_DOSSIER_TRASH_USERNAME` --
    escritura de índice pura (`deleted_at`/`deleted_by`), el
    `blob_name` en GCS nunca se toca, mismo principio que cualquier
    otra operación de este módulo. Devuelve False (no hace nada,
    `entry` queda intacto) cuando no se puede resolver el
    `CompanyUser` administrador -- ver `_resolve_dossier_trash_user`.
    """
    admin = _resolve_dossier_trash_user()
    if admin is None:
        logger.error(
            "# [trash_dossier_entry] No se pudo resolver el "
            "CompanyUser '%s' -- dossier NO eliminado, se deja "
            "clasificado sin aplicar (pk=%d).",
            _DOSSIER_TRASH_USERNAME, entry.pk,
        )
        return False
    entry.deleted_at = timezone.now()
    entry.deleted_by = admin
    entry.save(update_fields=["deleted_at", "deleted_by"])
    return True


def check_machine_mismatch(entry, result: dict) -> str | None:
    """
    Compares Gemini's `brand_model_hint` against the REAL brand/model
    of the machine whose folder this file lives in (via
    `resolve_machine_asset`) -- Miguel Ángel, S040: "cuando ese
    documento (...) se encuentra en (...) resulta que es una Liebherr.
    Y ahora nos encontramos que es una Liebherr y nos encontramos un
    documento que dice que es la Luna modelo tal. Error. Tiene que
    avisar." Deliberately NOT the same check as `machine_code_hint`
    (that one is about which fleet code the document names, already
    fixed to ignore the manufacturer's own model -- this one is about
    whether the manufacturer's own model, which the document DOES
    genuinely carry, matches the folder it's filed under).

    Compares only the first word (the brand) case-insensitively --
    deliberately coarse. A mismatched model within the same brand
    ("LUNA GT-60/42" filed under a "LUNA AT-35/32" machine) is far more
    likely to be a real variant/typo than a genuinely wrong machine;
    a mismatched BRAND ("LUNA" vs "LIEBHERR") is the case Miguel Ángel
    described and is safe to flag automatically without false
    positives from minor model-string differences.

    Returns a warning string when brands clearly differ, or None when
    there's nothing to flag (hint missing, asset not resolved, or
    brands match) -- callers must never escalate None into a warning.

    ---

    Compara el `brand_model_hint` de Gemini contra la marca/modelo REAL
    de la máquina de la carpeta donde vive el archivo (vía
    `resolve_machine_asset`) -- Miguel Ángel, S040: "cuando ese
    documento (...) se encuentra en (...) resulta que es una Liebherr.
    Y ahora nos encontramos que es una Liebherr y nos encontramos un
    documento que dice que es la Luna modelo tal. Error. Tiene que
    avisar." Deliberadamente NO es la misma comprobación que
    `machine_code_hint` (esa es sobre qué código de flota nombra el
    documento, ya corregida para ignorar el modelo propio del
    fabricante -- esta es sobre si el modelo propio del fabricante, que
    el documento SÍ lleva de verdad, coincide con la carpeta donde está
    archivado).

    Compara solo la primera palabra (la marca) sin distinguir
    mayúsculas -- deliberadamente basto. Un modelo distinto dentro de
    la misma marca ("LUNA GT-60/42" archivado bajo una máquina "LUNA
    AT-35/32") es mucho más probable que sea una variante/errata real
    que una máquina genuinamente equivocada; una MARCA distinta ("LUNA"
    frente a "LIEBHERR") es el caso que describió Miguel Ángel y es
    seguro avisar automáticamente sin falsos positivos por pequeñas
    diferencias en la cadena del modelo.

    Devuelve una cadena de aviso cuando las marcas difieren claramente,
    o None cuando no hay nada que señalar (falta la pista, no se pudo
    resolver la máquina, o las marcas coinciden) -- quien llama nunca
    debe convertir None en un aviso.
    """
    brand_model_hint = (result.get("brand_model_hint") or "").strip()
    if not brand_model_hint:
        return None
    asset = resolve_machine_asset(entry)
    if not asset or not asset.brand_model:
        return None

    hint_brand = brand_model_hint.split()[0].upper()
    real_brand = asset.brand_model.split()[0].upper()
    if hint_brand == real_brand:
        return None

    return (
        "⚠️ Posible documento archivado en la máquina equivocada -- el "
        "documento dice ser de «%s», pero la máquina de esta carpeta "
        "(%s) es «%s»." % (brand_model_hint, asset.code, asset.brand_model)
    )


def _pdf_page_count(content_bytes: bytes) -> int | None:
    """
    Real page count of a PDF via `fitz` -- used to decide, for EVERY
    PDF, whether to send it whole or trimmed to edges
    (`_extract_pdf_edges()`), per Miguel Ángel's own general rule
    (S042, repeated twice): "hasta cuatro páginas enviamos íntegro el
    archivo, a partir de cuatro páginas, las dos primeras y las dos
    últimas" -- applied to every single PDF, never only as a reaction
    to a specific API error.

    Returns None when the file can't even be opened as a PDF (corrupt)
    -- callers must treat that the same as "needs trimming" (there is
    nothing safe to send whole), never assume it's fine.

    ---

    Número real de páginas de un PDF vía `fitz` -- usado para decidir,
    para CUALQUIER PDF, si se envía entero o recortado a extremos
    (`_extract_pdf_edges()`), según la regla general del propio Miguel
    Ángel (S042, repetida dos veces): "hasta cuatro páginas enviamos
    íntegro el archivo, a partir de cuatro páginas, las dos primeras y
    las dos últimas" -- aplicada a todos y cada uno de los PDF, nunca
    solo como reacción a un error concreto de la API.

    Devuelve None cuando el archivo ni siquiera se puede abrir como
    PDF (dañado) -- quien llama debe tratarlo igual que "necesita
    recorte" (no hay nada seguro que enviar entero), nunca suponer que
    está bien.
    """
    try:
        with fitz.open(stream=content_bytes, filetype="pdf") as doc:
            return doc.page_count
    except Exception as exc:
        logger.warning(
            "# [_pdf_page_count] Fallo abriendo PDF: %s",
            exc, exc_info=True,
        )
        return None


def _extract_pdf_edges(
    content_bytes: bytes,
    first_pages: int = _PDF_EXCERPT_FIRST_PAGES,
    last_pages: int = _PDF_EXCERPT_LAST_PAGES,
) -> bytes | None:
    """
    Extracts the first `first_pages` AND the last `last_pages` of a
    PDF into a new, small, in-memory PDF -- for classification
    purposes only, never persisted anywhere. Real incident, S040:
    several genuine catalogs of spare parts (150-270 MB) hit Vertex
    AI's real, documented PDF limit (`52428800` bytes, 50 MiB) even
    referenced by `gs://` URI (`Part.from_uri`) -- confirmed directly
    by the API's own error message, not assumed. A second real limit
    surfaced later (S042): a document can also be rejected for
    exceeding Vertex AI's separate 1000-page ceiling regardless of
    byte size (a text-heavy manual with few images can run to
    thousands of pages while staying well under 50 MiB).

    **Replaced first-N-pages-only with first+last, S042 -- Miguel
    Ángel, on his own proposal after reviewing real data**: a sample
    of 20 real dossiers Gemini had already correctly caught (multiple
    distinct catalogued documents scanned together as one PDF, H29
    3.14/S041) showed only 3 of 20 fit inside 3 pages and only 4 of 20
    inside 5 -- median far higher, up to 176 pages, because the join
    between the two documents can land anywhere. Bumping the page
    count alone barely moved that number; what actually helps is
    seeing BOTH edges of the file. Most dossiers stack a short
    document at the very end of a longer one (or vice-versa), so the
    first and last pages are exactly where the seam between the two
    documents is most likely to be visible -- a letterhead or cover
    that clearly doesn't match page 1 is a strong dossier signal even
    without seeing anything in between. Only ever used as a fallback
    for the rare oversized/over-page-limit file; the overwhelming
    majority of files are still classified whole.

    Since classification only needs to recognise WHAT KIND of
    document this is (cover page, title, header) -- and, when
    relevant, whether it is secretly more than one document -- a
    handful of pages from each end are enough, almost always
    dramatically smaller than the full file.

    Uses PyMuPDF (`fitz`), already a project dependency -- no new
    package needed, no `pip-compile`/`pip-sync` coordination required.

    Returns None on any failure (corrupt PDF, etc.) -- callers must
    fall back to the "unsupported"/error path, never guess.

    ---

    Extrae las primeras `first_pages` Y las últimas `last_pages` de un
    PDF a un PDF nuevo, pequeño, en memoria -- solo para clasificar,
    nunca se persiste en ningún sitio. Incidente real, S040: varios
    catálogos de piezas reales (150-270 MB) chocaban con el límite
    real y documentado de Vertex AI para PDF (`52428800` bytes, 50
    MiB) incluso referenciados por URI `gs://` (`Part.from_uri`) --
    confirmado directamente por el propio mensaje de error de la API,
    no supuesto. Un segundo límite real apareció después (S042): un
    documento también puede rechazarse por superar el techo SEPARADO
    de 1000 páginas de Vertex AI sea cual sea su peso en bytes (un
    manual de texto con pocas imágenes puede llegar a miles de páginas
    y seguir pesando muy poco).

    **Sustituido "solo primeras N páginas" por "primeras + últimas",
    S042 -- Miguel Ángel, propuesta suya propia tras revisar datos
    reales**: una muestra de 20 dosieres reales que Gemini ya había
    detectado bien (varios documentos catalogados distintos
    escaneados juntos como un único PDF, H29 3.14/S041) mostró que
    solo 3 de 20 cabían en 3 páginas y solo 4 de 20 en 5 -- la
    mediana muy por encima, hasta 176 páginas, porque la unión entre
    los dos documentos puede caer en cualquier sitio. Subir solo el
    número de páginas apenas movía esa cifra; lo que de verdad ayuda
    es ver LOS DOS EXTREMOS del archivo. La mayoría de los dosieres
    apilan un documento corto al final de uno más largo (o al
    revés), así que el principio y el final son justo donde más
    probable es que se vea la costura entre los dos documentos -- un
    membrete o portada que claramente no encaja con la página 1 es una
    señal fuerte de dosier incluso sin ver nada de en medio. Solo se
    usa como último recurso para el archivo raro que supera el tamaño
    o el límite de páginas; la inmensa mayoría de archivos se sigue
    clasificando entero.

    Como clasificar solo necesita reconocer DE QUÉ TIPO es el
    documento (portada, título, cabecera) -- y, cuando aplica, si en
    realidad son varios documentos distintos -- unas pocas páginas de
    cada extremo bastan, casi siempre mucho más pequeñas que el
    archivo completo.

    Usa PyMuPDF (`fitz`), ya dependencia del proyecto -- ningún
    paquete nuevo, ninguna coordinación de `pip-compile`/`pip-sync`
    necesaria.

    Devuelve None ante cualquier fallo (PDF corrupto, etc.) -- quien
    llama debe caer al camino de "no soportado"/error, nunca adivinar.
    """
    try:
        source = fitz.open(stream=content_bytes, filetype="pdf")
        try:
            total = source.page_count
            excerpt = fitz.open()
            if total <= first_pages + last_pages:
                excerpt.insert_pdf(source, from_page=0, to_page=total - 1)
            else:
                excerpt.insert_pdf(
                    source, from_page=0, to_page=first_pages - 1,
                )
                excerpt.insert_pdf(
                    source, from_page=total - last_pages, to_page=total - 1,
                )
            return excerpt.tobytes()
        finally:
            source.close()
    except Exception as exc:
        logger.warning(
            "# [_extract_pdf_edges] Fallo extrayendo páginas: %s",
            exc, exc_info=True,
        )
        return None


def _convert_to_pdf(content_bytes: bytes, extension: str) -> bytes | None:
    """
    Converts an Office document to PDF using LibreOffice headless
    (`soffice`), confirmed installed on the server (`/usr/bin/soffice`,
    6.4.7.2) before writing this function -- never assumed. Purely
    in-memory from the caller's point of view: writes to a throwaway
    temp directory, reads the resulting PDF bytes back, and deletes
    everything before returning. **Never touches GCS** -- the
    converted PDF exists only long enough to hand to Gemini, per the
    same "clasificar nunca toca GCS" rule as the rest of this module
    (H29 annex 3.19); it is not a new document, just a disposable
    intermediate for reading content Gemini can't read natively.

    Runs with `-env:UserInstallation=file://<tmp>` pointing at its own
    throwaway LibreOffice profile directory -- avoids the well-known
    "user installation is locked" failure if two conversions ever ran
    at once (today's Celery worker has concurrency=1, so this is
    precautionary, not currently load-bearing).

    Returns None on any failure (timeout, `soffice` missing, corrupt
    input, unexpected output) -- callers must fall back to the
    "unsupported" error path, never guess or retry silently.

    ---

    Convierte un documento de Office a PDF con LibreOffice headless
    (`soffice`), confirmado instalado en el servidor
    (`/usr/bin/soffice`, 6.4.7.2) antes de escribir esta función --
    nunca asumido. Puramente en memoria desde el punto de vista de
    quien llama: escribe en un directorio temporal desechable, lee de
    vuelta los bytes del PDF resultante, y borra todo antes de
    devolver. **Nunca toca GCS** -- el PDF convertido existe solo el
    tiempo necesario para dárselo a Gemini, según la misma regla de
    "clasificar nunca toca GCS" que el resto de este módulo (anexo H29
    3.19); no es un documento nuevo, solo un intermedio desechable
    para leer contenido que Gemini no sabe leer de forma nativa.

    Corre con `-env:UserInstallation=file://<tmp>` apuntando a su
    propio perfil desechable de LibreOffice -- evita el fallo conocido
    de "user installation is locked" si alguna vez corrieran dos
    conversiones a la vez (el worker Celery de hoy tiene
    concurrency=1, así que esto es precautorio, no necesario todavía).

    Devuelve None ante cualquier fallo (timeout, falta `soffice`,
    entrada corrupta, salida inesperada) -- quien llama debe caer al
    camino de "no soportado", nunca adivinar ni reintentar en
    silencio.
    """
    with tempfile.TemporaryDirectory() as workdir:
        input_path = os.path.join(workdir, "input." + extension)
        profile_dir = os.path.join(workdir, "profile")
        with open(input_path, "wb") as f:
            f.write(content_bytes)
        try:
            subprocess.run(
                [
                    "soffice", "--headless", "--norestore",
                    "-env:UserInstallation=file://%s" % profile_dir,
                    "--convert-to", "pdf", "--outdir", workdir, input_path,
                ],
                check=True, timeout=_SOFFICE_TIMEOUT_SECONDS,
                capture_output=True,
            )
        except Exception as exc:
            logger.warning(
                "# [_convert_to_pdf] Fallo convirtiendo .%s a PDF: %s",
                extension, exc, exc_info=True,
            )
            return None

        output_path = os.path.join(workdir, "input.pdf")
        if not os.path.exists(output_path):
            logger.warning(
                "# [_convert_to_pdf] soffice terminó sin error pero no "
                "generó input.pdf para .%s", extension,
            )
            return None
        with open(output_path, "rb") as f:
            return f.read()


def _convert_xps_to_pdf(content_bytes: bytes, extension: str) -> bytes | None:
    """
    Converts an XPS/OpenXPS document to PDF using `fitz` (PyMuPDF) --
    never `_convert_to_pdf()`/`soffice`, confirmed by direct test
    against a real production file (S042) that the server's
    LibreOffice (6.4.7.2) has no XPS import filter at all
    ("Error: source file could not be loaded"). MuPDF -- the engine
    behind `fitz`, already a project dependency used elsewhere in this
    same module for `_extract_pdf_edges()` -- describes itself
    as "a lightweight PDF **and XPS** viewer" and opens both formats
    natively; `Document.convert_to_pdf()` is a documented, official
    PyMuPDF method, not a workaround. No new package, no
    `pip-compile`/`pip-sync` coordination needed.

    The resulting PDF is very likely image-only with no extractable
    text layer -- confirmed on the real test file, an XPS produced by
    printing rather than authored directly. That's fine here: Gemini
    reads the PDF Part visually (multimodal), it never depends on a
    text layer to classify a document, so an image-only page is a
    completely normal, fully classifiable input.

    Returns None on any failure (corrupt input, unexpected structure)
    -- callers must fall back to the "unsupported" error path, same
    contract as `_convert_to_pdf()`.

    ---

    Convierte un documento XPS/OpenXPS a PDF usando `fitz` (PyMuPDF)
    -- nunca `_convert_to_pdf()`/`soffice`, confirmado con una prueba
    directa contra un archivo real de producción (S042): el
    LibreOffice del servidor (6.4.7.2) no trae ningún filtro de
    importación de XPS ("Error: source file could not be loaded").
    MuPDF -- el motor detrás de `fitz`, ya dependencia del proyecto,
    usado en este mismo módulo para `_extract_pdf_edges()` -- se
    describe a sí mismo como "a lightweight PDF **and XPS** viewer" y
    abre ambos formatos de forma nativa; `Document.convert_to_pdf()`
    es un método oficial y documentado de PyMuPDF, no un rodeo. Ningún
    paquete nuevo, ninguna coordinación de `pip-compile`/`pip-sync`
    necesaria.

    El PDF resultante muy probablemente queda basado en imagen, sin
    capa de texto extraíble -- confirmado en el propio archivo real de
    prueba, un XPS generado por impresión y no redactado
    directamente. Aquí no importa: Gemini lee el Part del PDF de forma
    visual (multimodal), nunca depende de una capa de texto para
    clasificar, así que una página basada en imagen es una entrada
    perfectamente normal y clasificable.

    Devuelve None ante cualquier fallo (entrada corrupta, estructura
    inesperada) -- quien llama debe caer al camino de "no soportado",
    mismo contrato que `_convert_to_pdf()`.
    """
    try:
        source = fitz.open(stream=content_bytes, filetype=extension)
        try:
            return source.convert_to_pdf()
        finally:
            source.close()
    except Exception as exc:
        logger.warning(
            "# [_convert_xps_to_pdf] Fallo convirtiendo .%s a PDF: %s",
            extension, exc, exc_info=True,
        )
        return None


def _is_page_limit_error(exc) -> bool:
    """
    True when Vertex AI rejected the document for exceeding its
    hard 1000-page limit -- a SEPARATE limit from the 50 MiB size
    ceiling already handled above, confirmed real (S042): a genuine
    1843-page operator manual, well under 45 MB, was rejected with
    "The document contains 1843 pages which exceeds the supported
    page limit of 1000." `classify_entry` catches this specifically
    to retry with a trimmed excerpt instead of exiling the file.

    ---

    Cierto cuando Vertex AI rechazó el documento por superar su
    límite duro de 1000 páginas -- un límite SEPARADO del techo de 50
    MiB por tamaño ya tratado más arriba, confirmado real (S042): un
    manual de operador real de 1843 páginas, muy por debajo de 45 MB,
    fue rechazado con "The document contains 1843 pages which exceeds
    the supported page limit of 1000." `classify_entry` lo detecta
    específicamente para reintentar con un extracto recortado en vez
    de desterrar el archivo.
    """
    return "exceeds the supported page limit" in str(exc)


def classify_entry(entry, domain: str | None = None) -> dict:
    """
    Downloads the real object content from GCS and asks Gemini to
    suggest a `DocumentTypeCatalog.code` plus a handful of hint
    fields. Never raises to the caller -- any failure comes back as a
    dict with `error` set, since this is meant to run over a batch
    where one bad file must not abort the rest.

    `domain` is optional -- pass it when already known (narrows the
    catalog, more accurate); leave it out for quarantine files, where
    Gemini determines the domain itself as part of the same call.

    Also reads `entry.curator_note` (H29, S042) when present and
    forwards it to `_build_prompt()` as a prioritised correction --
    see that function's docstring.

    Office documents (`.docx`/`.xlsx`/`.pptx`/...) are converted to
    PDF first via `_convert_to_pdf()` -- Gemini's own mimeType
    allow-list doesn't cover Office formats directly (see
    `_SUPPORTED_MIME_TYPES`'s docstring). XPS/OpenXPS (`.xps`/`.oxps`)
    go through the separate `_convert_xps_to_pdf()` (`fitz`) instead --
    S042, `soffice` confirmed by direct test to have no XPS import
    filter at all, see `_XPS_EXTENSIONS`'s comment for the real error.
    Only the converted PDF bytes are sent to Gemini; nothing about the
    conversion is persisted anywhere.

    A PDF Vertex AI rejects for exceeding its 1000-page limit
    (`_is_page_limit_error`, S042 -- separate from the 50 MiB size
    ceiling below, confirmed real against a genuine 1843-page manual)
    gets ONE retry with a trimmed excerpt instead of an immediate
    error -- same reasoning as the size-based trim: recognising the
    document's type only needs the first few pages, not the whole
    thing.

    For file types Gemini already accepts natively (PDF, images...),
    this never downloads the object at all -- it hands Gemini a
    direct `gs://` reference (`Part.from_uri`, confirmed supported on
    Vertex AI with no inline-payload size ceiling) instead of
    `Part.from_bytes`. Real incident, S040: several genuine spare-parts
    catalog PDFs (150-270 MB) failed with a raw 400 INVALID_ARGUMENT
    from Vertex AI -- verified online against current Gemini docs
    (2026-08-04) that the inline payload limit is 100 MB, well under
    these files' real size. Office documents still need a real
    download (LibreOffice can't convert a `gs://` URI), so that path
    is unchanged.

    ---

    Descarga el contenido real del objeto desde GCS y pide a Gemini
    que sugiera un `DocumentTypeCatalog.code` más un puñado de campos
    de pista. Nunca lanza excepción a quien llama -- cualquier fallo
    vuelve como un dict con `error` puesto, porque esto está pensado
    para correr sobre un lote donde un archivo malo no debe abortar el
    resto.

    `domain` es opcional -- se pasa cuando ya se conoce (acota el
    catálogo, más preciso); se omite para archivos de cuarentena,
    donde Gemini determina el propio dominio como parte de la misma
    llamada.

    También lee `entry.curator_note` (H29, S042) cuando existe y la
    reenvía a `_build_prompt()` como una corrección prioritaria -- ver
    el docstring de esa función.

    Los documentos de Office (`.docx`/`.xlsx`/`.pptx`/...) se
    convierten primero a PDF vía `_convert_to_pdf()` -- la lista de
    mimeTypes que acepta Gemini no cubre Office directamente (ver el
    docstring de `_SUPPORTED_MIME_TYPES`). XPS/OpenXPS (`.xps`/
    `.oxps`) pasa en cambio por `_convert_xps_to_pdf()` (`fitz`) --
    S042, se confirmó con una prueba directa que `soffice` no trae
    ningún filtro de importación de XPS, ver el comentario de
    `_XPS_EXTENSIONS` para el error real. Solo los bytes del PDF
    convertido se envían a Gemini; nada de la conversión se persiste
    en ningún sitio.

    Un PDF que Vertex AI rechaza por superar su límite de 1000
    páginas (`_is_page_limit_error`, S042 -- separado del techo de 50
    MiB por tamaño de más abajo, confirmado real contra un manual
    genuino de 1843 páginas) recibe UN reintento con un extracto
    recortado en vez de un error inmediato -- mismo razonamiento que
    el recorte por tamaño: reconocer el tipo de documento solo
    necesita las primeras páginas, no el documento entero.

    Para los tipos que Gemini ya acepta de forma nativa (PDF,
    imágenes...), esto nunca descarga el objeto -- le pasa a Gemini
    una referencia `gs://` directa (`Part.from_uri`, confirmado
    soportado en Vertex AI sin techo de tamaño de payload en línea) en
    vez de `Part.from_bytes`. Incidente real, S040: varios catálogos
    de piezas reales (150-270 MB) fallaban con un 400 INVALID_ARGUMENT
    en crudo de Vertex AI -- verificado online contra la documentación
    real de Gemini (2026-08-04) que el límite de payload en línea es
    100 MB, muy por debajo del tamaño real de estos archivos. Los
    documentos de Office siguen necesitando descarga real (LibreOffice
    no puede convertir una URI `gs://`), así que ese camino no cambia.
    """
    import json

    mime_type = entry.content_type or "application/pdf"
    extension = (
        entry.name.rsplit(".", 1)[-1].lower()
        if "." in entry.name else ""
    )

    try:
        if mime_type in _SUPPORTED_MIME_TYPES:
            needs_trim = False
            content_bytes = None
            if mime_type == "application/pdf":
                # Miguel Ángel, verbatim, repetido dos veces: "hasta
                # cuatro páginas enviamos íntegro el archivo, a partir
                # de cuatro páginas, las dos primeras y las dos
                # últimas." Regla GENERAL para TODO PDF, siempre --
                # nunca solo una reacción a un error concreto de la
                # API. Incidente real que confirma por qué: un manual
                # de 979 páginas (979 imágenes escaneadas, 0 texto)
                # pesaba muy por debajo del límite de 45 MB y tenía
                # muy por debajo de las 1000 páginas de Vertex AI --
                # nunca disparaba ningún error conocido, y aun así
                # Gemini fallaba ("no se ha proporcionado el texto o
                # contenido"), confirmado con fitz que el archivo es
                # real y legible. Esperar a un error para recortar
                # dejaba huérfanos justo los casos como este. Por eso
                # el número de páginas real se cuenta SIEMPRE, para
                # cualquier PDF, sin excepción por tamaño ni por
                # ningún otro motivo -- nunca se espera a que falle.
                content_bytes = download_bytes(
                    entry.bucket, entry.blob_name,
                )
                page_count = _pdf_page_count(content_bytes)
                needs_trim = (
                    page_count is None
                    or page_count > (
                        _PDF_EXCERPT_FIRST_PAGES + _PDF_EXCERPT_LAST_PAGES
                    )
                )
            if needs_trim:
                excerpt = _extract_pdf_edges(content_bytes)
                if excerpt is None:
                    return {
                        "error": (
                            "No se pudieron extraer las páginas "
                            "extremas del PDF para clasificarlo (ver "
                            "logs del servidor)."
                        ),
                    }
                file_part = Part.from_bytes(
                    data=excerpt, mime_type="application/pdf",
                )
                is_partial_excerpt = True
            else:
                file_part = Part.from_uri(
                    file_uri="gs://%s/%s" % (entry.bucket, entry.blob_name),
                    mime_type=mime_type,
                )
                is_partial_excerpt = False
        else:
            if extension in _XPS_EXTENSIONS:
                content_bytes = download_bytes(entry.bucket, entry.blob_name)
                converted = _convert_xps_to_pdf(content_bytes, extension)
                if converted is None:
                    return {
                        "error": (
                            "No se pudo convertir .%s a PDF con fitz/"
                            "PyMuPDF para poder clasificarlo (ver logs "
                            "del servidor para el detalle)." % extension
                        ),
                    }
            elif extension in _LIBREOFFICE_CONVERTIBLE_EXTENSIONS:
                content_bytes = download_bytes(entry.bucket, entry.blob_name)
                converted = _convert_to_pdf(content_bytes, extension)
                if converted is None:
                    return {
                        "error": (
                            "No se pudo convertir .%s a PDF con "
                            "LibreOffice para poder clasificarlo (ver "
                            "logs del servidor para el detalle)."
                            % extension
                        ),
                    }
            else:
                return {
                    "error": (
                        "Tipo de archivo no soportado para clasificación "
                        "con Gemini (%s) y sin conversión conocida para "
                        "la extensión .%s." % (mime_type, extension)
                    ),
                }
            file_part = Part.from_bytes(
                data=converted, mime_type="application/pdf",
            )
            is_partial_excerpt = False

        client = get_gemini_client()

        def _call_gemini(part, is_excerpt):
            return _generate_content_with_retry(
                client,
                model=DEFAULT_MODEL,
                contents=[
                    part,
                    _build_prompt(
                        domain, getattr(entry, "curator_note", ""),
                        is_partial_excerpt=is_excerpt,
                    ),
                ],
                config=GenerateContentConfig(
                    http_options=HttpOptions(timeout=90_000),
                    response_mime_type="application/json",
                    response_schema=_RESPONSE_SCHEMA,
                    temperature=0.0,
                ),
            )

        try:
            response = _call_gemini(file_part, is_partial_excerpt)
        except Exception as exc:
            if not _is_page_limit_error(exc):
                raise
            # Incidente real S042: un manual real de 1843 páginas
            # (muy por debajo del límite de 50 MB, así que llegó aquí
            # por Part.from_uri sin pasar por el recorte de tamaño de
            # más arriba) chocó con el límite SEPARADO de 1000
            # páginas de Vertex AI y se desterraba a NO CONFORMES sin
            # ninguna segunda oportunidad. Mismo criterio que el
            # recorte por tamaño: clasificar solo necesita reconocer
            # el tipo de documento, no transcribirlo entero, así que
            # unas pocas páginas de cada extremo bastan.
            logger.warning(
                "# [classify_entry] %s supera el límite de páginas "
                "de Vertex AI, reintentando con extracto recortado.",
                entry.blob_name,
            )
            content_bytes = download_bytes(entry.bucket, entry.blob_name)
            excerpt = _extract_pdf_edges(content_bytes)
            if excerpt is None:
                raise
            file_part = Part.from_bytes(
                data=excerpt, mime_type="application/pdf",
            )
            response = _call_gemini(file_part, True)
        return json.loads(response.text.strip())
    except Exception as exc:
        logger.warning(
            "# [classify_entry] Fallo clasificando %s: %s",
            entry.blob_name, exc, exc_info=True,
        )
        return {"error": str(exc)}


def _resolve_date(entry, result) -> datetime.date:
    """
    Real date extracted by Gemini when available (`date_hint`,
    AAAA-MM-DD); falls back to the object's own GCS modification date,
    and only then to today -- never blocks naming just because the
    document itself didn't carry a readable date.

    ---

    Fecha real extraída por Gemini cuando está disponible
    (`date_hint`, AAAA-MM-DD); si no, cae en la fecha de modificación
    propia del objeto en GCS, y solo entonces en hoy -- nunca bloquea
    el nombrado solo porque el documento en sí no traía una fecha
    legible.
    """
    date_hint = (result.get("date_hint") or "").strip()
    if date_hint:
        try:
            return datetime.date.fromisoformat(date_hint)
        except ValueError:
            pass
    if entry.gcs_updated_at:
        return entry.gcs_updated_at.date()
    return datetime.date.today()


def build_new_name(
    entry, domain: str, result: dict, ordinal: int | None = None,
    asset: "MachineAsset | None" = None,
) -> str | None:
    """
    Build the virtual filename `naming_service` would produce from a
    Gemini suggestion, or None when there isn't enough to go on
    (unknown type, or missing the field the chosen domain's format
    requires) -- callers must treat None as "leave this one for manual
    review", never invent a placeholder.

    `asset` (S043 addition): the MACHINE-domain caller may already
    have resolved (or just created) the real `MachineAsset` via
    `resolve_or_create_machine_asset()` -- real incident this fixes:
    that resolver already understands company-vehicle folders
    identified by plate (`_FOLDER_PLATE_RE`), but this function used
    to call the plain, read-only `resolve_machine_asset()` again from
    scratch, which only ever understood the classic fleet-code pattern
    (`_FOLDER_MACHINE_CODE_RE`). A file correctly classified as
    PROFORMA/RECIBO_SENAL_COMPRA, with its `MachineAsset` already
    created by matrícula, still fell back to `machine_code_hint` (often
    empty) and landed in NO CONFORMES anyway -- the asset the pipeline
    had just resolved was silently discarded one call later. When
    `asset` is passed, it is trusted directly; only when it is `None`
    (every other MACHINE-domain caller, e.g. `apply_classification()`
    reclassifying a file already living under `DOC. MAQUINAS`) does
    this function fall back to the original `resolve_machine_asset()`
    lookup, unchanged.

    `ordinal` is forwarded to `naming_service` as-is -- Miguel Ángel's
    own format ("...tipo de documento, y fecha y ordinal por si hay
    varios documentos que se llamen igual") already has a place for
    it; a collision must never be resolved by bolting move_service's
    " (N)" suffix on top of a name this function already built in a
    different, fixed format.

    ---

    Construye el nombre de archivo virtual que produciría
    `naming_service` a partir de una sugerencia de Gemini, o None
    cuando no hay suficiente con qué construirlo (tipo desconocido, o
    falta el campo que exige el formato de ese dominio) -- quien llama
    debe tratar None como "dejar este para revisión manual", nunca
    inventar un valor de relleno.

    `asset` (añadido S043): quien llama en dominio MÁQUINA puede haber
    resuelto (o creado) ya el `MachineAsset` real vía
    `resolve_or_create_machine_asset()` -- incidente real que esto
    corrige: ese resolutor ya entiende carpetas de vehículo de empresa
    identificadas por matrícula (`_FOLDER_PLATE_RE`), pero esta función
    volvía a llamar desde cero a la `resolve_machine_asset()` de solo
    lectura, que solo entendía el patrón clásico de código de flota
    (`_FOLDER_MACHINE_CODE_RE`). Un archivo correctamente clasificado
    como PROFORMA/RECIBO_SENAL_COMPRA, con su `MachineAsset` ya creado
    por matrícula, seguía cayendo al `machine_code_hint` (a menudo
    vacío) y aterrizaba en NO CONFORMES igual -- el asset que el propio
    flujo acababa de resolver se descartaba en silencio una llamada
    después. Cuando se pasa `asset`, se confía en él directamente; solo
    cuando es `None` (cualquier otro llamador de dominio MÁQUINA, p.
    ej. `apply_classification()` reclasificando un archivo que ya vive
    bajo `DOC. MAQUINAS`) esta función recurre a la búsqueda original
    de `resolve_machine_asset()`, sin cambios.

    `ordinal` se reenvía tal cual a `naming_service` -- el propio
    formato de Miguel Ángel ("...tipo de documento, y fecha y ordinal
    por si hay varios documentos que se llamen igual") ya tiene un
    hueco para esto; una colisión nunca debe resolverse pegando el
    sufijo " (N)" de move_service encima de un nombre que esta función
    ya construyó en un formato fijo distinto.
    """
    code = result.get("document_type_code") or ""
    if not code or code == "DESCONOCIDO":
        return None
    extension = entry.name.rsplit(".", 1)[-1] if "." in entry.name else "pdf"
    date = _resolve_date(entry, result)

    if domain == "MACHINE":
        # Corrección S040, misma sesión: para archivos que ya viven en
        # una carpeta de máquina conocida, el código de flota real
        # (resuelto por carpeta, determinista) prevalece siempre sobre
        # lo que Gemini lea dentro del documento -- Gemini no es
        # perfectamente determinista entre llamadas (temperature=0.0
        # no lo garantiza al 100%) y ya se ha visto en producción
        # devolver un código de máquina distinto para el mismo archivo
        # en dos pasadas seguidas. Gemini solo decide el código cuando
        # la carpeta no resuelve a ninguna máquina real -- el caso de
        # cuarentena, que es donde de verdad hace falta que adivine.
        resolved_asset = asset if asset is not None else resolve_machine_asset(entry)
        machine_code = (
            resolved_asset.code if resolved_asset
            else (result.get("machine_code_hint") or "").strip()
        )
        if not machine_code:
            return None
        return naming_service.build_filename_machine(
            machine_code, code, date, ordinal=ordinal, extension=extension,
        )
    if domain == "PERSONAL":
        # Corrección S040, mismo principio que 3.27 para máquina: si
        # el DNI leído en este documento concreto resuelve a una
        # identidad ya sembrada, sus apellidos/nombre canónicos
        # prevalecen sobre lo que Gemini haya leído aquí -- evita que
        # una variante de escritura de este documento (Hallazgo 5)
        # genere un nombre de archivo distinto al resto de documentos
        # de la misma persona.
        identity = resolve_person_identity(result.get("dni_hint"))
        if identity:
            first_surname = identity.first_surname
            second_surname = identity.second_surname
            given_name = identity.given_name
        else:
            first_surname = (result.get("first_surname_hint") or "").strip()
            given_name = (result.get("given_name_hint") or "").strip()
            second_surname = (result.get("second_surname_hint") or "").strip()
        if not first_surname or not given_name:
            return None
        return naming_service.build_filename_personal(
            first_surname, second_surname, given_name, code, date,
            ordinal=ordinal, extension=extension,
        )
    return None


def apply_classification(entry) -> dict:
    """
    Classifies `entry` and, if there was enough to build a proper
    name, applies it -- **virtually only**: writes `DocumentIndexEntry.
    name`, never touches `blob_name` or moves anything in GCS. Miguel
    Ángel, S040: "no vamos a tocar CGS, lo vamos a hacer todo a nivel
    de base de datos (...) al clasificarla le damos el nombre nuevo en
    base de datos."

    `entry.parent_path` is left untouched by this function -- for
    files already living under DOC. MAQUINAS/DOC. PERSONAL this is
    exactly the wanted behaviour (rename in place). Relocating a
    quarantine file into its classified folder virtually is a
    separate, still-unbuilt step (the future always-on task) that will
    reuse `move_service`'s own virtual-relocation machinery, not this
    function.

    Collision-safe: appends the ordinal `naming_service`'s own format
    already has a place for -- never `move_service`'s " (N)" suffix,
    which belongs to a different, unrelated feature (moving files) with
    its own naming convention. Corrected S040 after the first
    controlled test: the original version called
    `move_service._resolve_free_name` directly, which silently produced
    names like `... (1).pdf` instead of Miguel Ángel's own specified
    `..._1.pdf` ordinal.

    Returns the raw Gemini result dict, plus `new_name` (None if
    nothing could be applied), `classified` (bool -- whether a valid
    name could be built at all, true even if it turned out identical
    to the current one) and `renamed` (bool, whether the name
    actually changed). `classified=True, renamed=False` means "already
    had the right name" -- callers must never treat that as a failure.

    ---

    Clasifica `entry` y, si hubo suficiente para construir un nombre
    correcto, lo aplica -- **solo de forma virtual**: escribe
    `DocumentIndexEntry.name`, nunca toca `blob_name` ni mueve nada en
    GCS. Miguel Ángel, S040: "no vamos a tocar CGS, lo vamos a hacer
    todo a nivel de base de datos (...) al clasificarla le damos el
    nombre nuevo en base de datos."

    `entry.parent_path` queda intacto en esta función -- para archivos
    que ya viven bajo DOC. MAQUINAS/DOC. PERSONAL es exactamente el
    comportamiento deseado (renombrar en el sitio). Reubicar
    virtualmente un archivo de cuarentena en su carpeta clasificada es
    un paso aparte, todavía sin construir (la futura tarea always-on)
    que reutilizará la maquinaria de reubicación virtual de
    `move_service`, no esta función.

    A salvo de colisiones: añade el ordinal para el que el propio
    formato de `naming_service` ya tiene hueco -- nunca el sufijo
    " (N)" de `move_service`, que pertenece a otra funcionalidad
    distinta (mover archivos) con su propia convención de nombres.
    Corregido en S040 tras la primera prueba controlada: la versión
    original llamaba directamente a
    `move_service._resolve_free_name`, que generaba en silencio
    nombres tipo `... (1).pdf` en vez del ordinal `..._1.pdf` que
    especificó Miguel Ángel.

    Devuelve el dict de resultado en crudo de Gemini, más `new_name`
    (None si no se pudo aplicar nada) y `renamed` (bool, si el nombre
    cambió de verdad).
    """
    domain = domain_for_entry(entry)
    result = classify_entry(entry, domain)
    if "error" in result:
        result["new_name"] = None
        result["classified"] = False
        result["renamed"] = False
        return result

    result["machine_mismatch_warning"] = check_machine_mismatch(entry, result)

    effective_domain = domain or result.get("domain")
    candidate_name = build_new_name(entry, effective_domain, result)
    if not candidate_name:
        # Bug real S040: esto es un fallo genuino (no hubo suficiente
        # para construir un nombre) -- distinto de "ya tenía el nombre
        # correcto", que es el caso de abajo. Antes de esta corrección
        # los dos caminos devolvían renamed=False y ClassifyView los
        # mostraba igual como "no se pudo aplicar", generando falsos
        # avisos cada vez que se reclasificaba un archivo ya bien
        # nombrado (incidente real: Miguel Ángel repitió la prueba
        # sobre los mismos 21 archivos y la mayoría de los ya
        # correctos salieron como fallo).
        result["new_name"] = None
        result["classified"] = False
        result["renamed"] = False
        return result

    final_name = candidate_name
    ordinal = 1
    while _virtual_location_taken(
        entry.bucket, entry.parent_path, final_name, exclude_pk=entry.pk,
    ):
        final_name = build_new_name(
            entry, effective_domain, result, ordinal=ordinal,
        )
        ordinal += 1

    renamed = final_name != entry.name
    if renamed:
        entry.name = final_name
        entry.save(update_fields=["name", "updated_at"])

    result["new_name"] = final_name
    result["classified"] = True
    result["renamed"] = renamed
    return result


def apply_personal_canonical_rename(
    entry, fictitious_date=None, apply_changes=False, reserved_names=None,
) -> dict:
    """
    No-Gemini counterpart of `apply_classification()`, PERSONAL domain
    only, for documents that are already fully classified in the
    database -- `document_type`, `domain_object` (a `PersonIdentity`)
    and, real or not, a date. Never calls Gemini: every input comes
    from already-resolved DB fields. H31 (S98), Miguel Angel's own
    forward-looking reason for building this as a separate, named,
    reusable function rather than inline script code: the predictive
    classifier he plans to train will also classify from pure Python,
    without Gemini in the loop -- this is meant to be the renaming
    half of that future pipeline too, not a one-off.

    Same "virtual-only" contract as `apply_classification()`: only
    `DocumentIndexEntry.name` changes, never `blob_name`/GCS (S040).
    Same collision-safe ordinal loop against `_virtual_location_taken`
    (never `move_service`'s " (N)" suffix).

    `fictitious_date` (S98): when neither `expiry_date` nor
    `issue_date` is set, callers may pass a fixed placeholder date --
    Miguel Angel's own convention, 2021-01-01, deliberately a national
    holiday no real document will ever carry -- so the fixed-format
    name can still be built for a document that was never dated. The
    real `expiry_date`/`issue_date` columns are never touched by this
    function; the placeholder only ever appears inside the filename
    string. `None` (default) means: leave undated entries alone,
    reason `"sin_fecha"`.

    `apply_changes` (default `False`, safe): when `False`, computes
    and returns the candidate name without writing anything -- dry-run
    reporting, same convention as every other bulk command of this
    project.

    `reserved_names` (S98, real incident on the first dry-run of this
    very function): an optional `set` the caller owns and passes
    across every call of the same batch. `_virtual_location_taken`
    only sees what is already committed in the database, so two
    entries that collide with EACH OTHER inside the same batch (same
    surnames/name/type/date -- the exact case the fictitious date is
    designed to group together, e.g. several undated old DNIs of one
    person) would both compute the identical bare name in a dry-run,
    since neither has been written yet. Passing a shared `set` fixes
    this without touching the database: every final name this
    function settles on gets added to it (`(bucket, parent_path,
    name)`), regardless of `apply_changes`, and every collision check
    consults it in addition to `_virtual_location_taken` -- so a
    dry-run preview shows the exact same ordinals a real `--apply` run
    would produce. `None` (default) keeps the old behaviour (checks
    only the database) for callers that process entries one at a time
    with no batch of their own.

    Returns `{"new_name": str | None, "renamed": bool, "reason":
    str | None}`. `reason` is only set when nothing could be built
    (`"sin_persona_resuelta"`, `"sin_tipo"`, `"sin_fecha"`) -- callers
    must treat that as "leave this one for manual review", never
    invent a value, same rule as `build_new_name()`.

    ---

    Homólogo sin Gemini de `apply_classification()`, solo dominio
    PERSONAL, para documentos ya totalmente clasificados en la base de
    datos -- `document_type`, `domain_object` (una `PersonIdentity`) y,
    real o no, una fecha. Nunca llama a Gemini: toda la entrada sale de
    campos ya resueltos en BD. H31 (S98), motivo explícito de Miguel
    Ángel para construir esto como función propia, nombrada y
    reutilizable, en vez de código suelto dentro del script: el
    clasificador predictivo que planea entrenar también clasificará en
    Python puro, sin Gemini de por medio -- esto está pensado para ser
    también la mitad de renombrado de ese futuro pipeline, no un
    apaño de una sola vez.

    Mismo contrato "solo virtual" que `apply_classification()`: solo
    cambia `DocumentIndexEntry.name`, nunca `blob_name`/GCS (S040).
    Mismo bucle de ordinal a salvo de colisiones contra
    `_virtual_location_taken` (nunca el sufijo " (N)" de
    `move_service`).

    `fictitious_date` (S98): cuando ni `expiry_date` ni `issue_date`
    están rellenos, quien llama puede pasar una fecha fija de relleno
    -- convención propia de Miguel Ángel, 2021-01-01, festivo nacional
    a propósito para que ningún documento real la lleve nunca -- para
    poder construir igualmente el nombre de formato fijo de un
    documento que nunca se fechó. Las columnas reales `expiry_date`/
    `issue_date` nunca se tocan desde esta función; el relleno solo
    aparece dentro de la cadena del nombre de archivo. `None`
    (por defecto) significa: dejar tal cual las entradas sin fecha,
    motivo `"sin_fecha"`.

    `apply_changes` (por defecto `False`, seguro): con `False`,
    calcula y devuelve el nombre candidato sin escribir nada --
    informe en seco, misma convención que cualquier otro comando
    masivo de este proyecto.

    `reserved_names` (S98, incidente real en la primera prueba en seco
    de esta misma función): un `set` opcional que quien llama posee y
    pasa a través de todas las llamadas del mismo lote.
    `_virtual_location_taken` solo ve lo que ya está comiteado en base
    de datos, así que dos entradas que colisionan ENTRE SÍ dentro del
    mismo lote (mismos apellidos/nombre/tipo/fecha -- justo el caso
    que la fecha ficticia está pensada para agrupar, p. ej. varios DNI
    antiguos sin fecha de la misma persona) calculaban en seco el
    mismo nombre sin ordinal, porque ninguna de las dos se había
    escrito todavía. Pasar un `set` compartido lo corrige sin tocar la
    base de datos: cada nombre final en el que se asienta esta función
    se añade a él (`(bucket, parent_path, name)`), sea cual sea
    `apply_changes`, y cada comprobación de colisión lo consulta
    además de `_virtual_location_taken` -- así una vista previa en
    seco muestra exactamente los mismos ordinales que produciría una
    ejecución real con `--apply`. `None` (por defecto) mantiene el
    comportamiento anterior (solo comprueba la base de datos) para
    quien llame procesando entradas de una en una sin lote propio.

    Devuelve `{"new_name": str | None, "renamed": bool, "reason":
    str | None}`. `reason` solo se rellena cuando no se pudo construir
    nada (`"sin_persona_resuelta"`, `"sin_tipo"`, `"sin_fecha"`) --
    quien llama debe tratarlo como "dejar este para revisión manual",
    nunca inventar un valor, misma regla que `build_new_name()`.
    """
    identity = entry.domain_object
    if not isinstance(identity, PersonIdentity):
        return {
            "new_name": None, "renamed": False,
            "reason": "sin_persona_resuelta",
        }
    if not entry.document_type or not entry.document_type.code:
        return {"new_name": None, "renamed": False, "reason": "sin_tipo"}
    date = entry.expiry_date or entry.issue_date or fictitious_date
    if date is None:
        return {"new_name": None, "renamed": False, "reason": "sin_fecha"}

    extension = entry.name.rsplit(".", 1)[-1] if "." in entry.name else "pdf"
    code = entry.document_type.code

    def _taken(name):
        if _virtual_location_taken(
            entry.bucket, entry.parent_path, name, exclude_pk=entry.pk,
        ):
            return True
        if reserved_names is not None:
            return (entry.bucket, entry.parent_path, name) in reserved_names
        return False

    candidate_name = naming_service.build_filename_personal(
        identity.first_surname, identity.second_surname,
        identity.given_name, code, date, extension=extension,
    )
    final_name = candidate_name
    ordinal = 1
    while _taken(final_name):
        final_name = naming_service.build_filename_personal(
            identity.first_surname, identity.second_surname,
            identity.given_name, code, date, ordinal=ordinal,
            extension=extension,
        )
        ordinal += 1

    if reserved_names is not None:
        reserved_names.add((entry.bucket, entry.parent_path, final_name))

    renamed = final_name != entry.name
    if renamed and apply_changes:
        entry.name = final_name
        entry.save(update_fields=["name", "updated_at"])

    return {"new_name": final_name, "renamed": renamed, "reason": None}


def quarantine_domain_for_entry(entry) -> str | None:
    """
    Domain of a file sitting inside `_CUARENTENA/` -- same rule as
    `domain_for_entry`, but checking the part of `blob_name` AFTER the
    quarantine prefix, since the agent mirrors the original relative
    path underneath it (`_CUARENTENA/DOC. MAQUINAS/...`,
    `h28_migration_agent/uploader.py`'s `build_quarantine_blob_name`).

    ---

    Dominio de un archivo dentro de `_CUARENTENA/` -- misma regla que
    `domain_for_entry`, pero mirando la parte de `blob_name` DESPUÉS
    del prefijo de cuarentena, porque el agente refleja la ruta
    relativa original justo debajo de él
    (`_CUARENTENA/DOC. MAQUINAS/...`, `build_quarantine_blob_name` de
    `h28_migration_agent/uploader.py`).
    """
    relative = entry.blob_name
    if relative.startswith(QUARANTINE_PREFIX):
        relative = relative[len(QUARANTINE_PREFIX):]
    if relative.startswith("DOC. MAQUINAS/"):
        return DocumentTypeCatalog.DOMAIN_MACHINE
    if relative.startswith("DOC. PERSONAL/"):
        return DocumentTypeCatalog.DOMAIN_PERSONAL
    return None


# DNI/NIE detectado en texto OCR libre -- 8 digitos (DNI) o letra
# X/Y/Z + 7 digitos (NIE), seguido de la letra de control, tolerando
# un espacio o guion intermedio que el OCR mete a veces. Candidato
# amplio a proposito -- la validacion real la hace
# is_valid_spanish_dni() (algoritmo de letra de control), asi que un
# falso positivo aqui (un numero de telefono, un codigo de curso) casi
# nunca pasa esa comprobacion.
_DNI_OCR_CANDIDATE_RE = re.compile(
    r"\b([0-9]{8}|[XYZxyz][0-9]{7})[\s\-]?([A-Za-z])\b"
)


def _extract_dni_via_ocr(entry) -> str | None:
    """
    H30 (S51). Intenta leer un DNI/NIE válido del contenido real del
    documento vía OCR (Tesseract, `date_verification_service.
    extract_text()` -- la misma función ya usada para fecha, sin
    tocarla), sin llamar a Gemini. Nunca se fía de una coincidencia
    ambigua: si el texto trae más de un DNI/NIE distinto que pase la
    letra de control, se considera irresuelto (mejor dejarlo para
    Gemini que adivinar cuál es el de verdad).

    Devuelve el DNI normalizado (`_normalize_dni()`) si hay
    exactamente uno válido, o `None` si no hay ninguno, hay más de
    uno, o el archivo no es un tipo que `extract_text()` sepa leer.
    Nunca lanza excepción -- cualquier fallo de descarga/OCR se trata
    como "no se pudo leer", igual que el resto de este módulo.
    """
    from document_explorer.date_verification_service import extract_text

    try:
        data = download_bytes(entry.bucket, entry.blob_name)
        text = extract_text(entry.name, data)
    except Exception:
        logger.exception(
            "# [_extract_dni_via_ocr] Fallo leyendo/OCR de #%d (%s) -- "
            "se trata como DNI no encontrado.", entry.pk, entry.name,
        )
        return None
    if not text:
        return None

    valid_candidates = set()
    for match in _DNI_OCR_CANDIDATE_RE.finditer(text):
        raw = match.group(1) + match.group(2)
        if is_valid_spanish_dni(raw):
            valid_candidates.add(_normalize_dni(raw))

    if len(valid_candidates) == 1:
        return next(iter(valid_candidates))
    return None


def _try_heuristic_classification(entry, domain) -> dict | None:
    """
    H30 (S51). Camino barato antes de gastar una llamada a Gemini --
    decisión explícita de Miguel Ángel: heurística de nombre (ya
    validada en Fase A) + OCR de contenido, y solo si algo falla o es
    ambiguo se cae a Gemini exactamente como hasta ahora. Aplica solo
    a archivos de carpeta vigilada (`domain` resuelto por
    `quarantine_domain_for_entry()`, MACHINE o PERSONAL) -- el buzón
    de correo (`ACCESO_BUZON_DOCUMENTACION`, donde `domain` sale
    siempre `None` por no tener carpeta MÁQUINA/PERSONAL debajo)
    nunca entra aquí, siempre Gemini, sin excepción, tal como decidió
    Miguel Ángel: no hay carpeta de origen en la que confiar.

    MÁQUINA: si la heurística resuelve un único tipo sin ambigüedad,
    se acepta directamente -- la identidad de la máquina ya se
    resuelve por carpeta en el resto del pipeline (`resolve_or_create
    _machine_asset`, sin depender de ningún hint de Gemini en el caso
    normal), así que no hace falta comprobarla aquí.

    PERSONAL: además del tipo por heurística, hace falta un DNI válido
    y que resuelva a una `PersonIdentity` YA EXISTENTE
    (`resolve_person_identity()`) -- Miguel Ángel, verbatim (S51):
    "no podemos dar de alta a un trabajador sin llamar a Gemini". Si
    el DNI no se lee, o se lee pero no coincide con nadie, se cae a
    Gemini sin excepción -- el alta de trabajador nuevo sigue
    exigiendo su verificación de nombre.

    Devuelve un `dict` con la misma forma mínima que `classify_entry()`
    (`document_type_code`, `domain`, y `dni_hint` cuando aplica) listo
    para que el resto de `apply_quarantine_classification()` lo procese
    sin ningún cambio, o `None` cuando hay que caer a Gemini.
    """
    if domain not in (
        DocumentTypeCatalog.DOMAIN_MACHINE, DocumentTypeCatalog.DOMAIN_PERSONAL,
    ):
        return None

    code, dossier_pair = resolve_document_type_heuristic(entry, domain)
    if not code or dossier_pair:
        return None

    if domain == DocumentTypeCatalog.DOMAIN_MACHINE:
        return {
            "domain": domain, "document_type_code": code,
            "confidence": "N/A", "is_dossier": False, "is_photo": False,
            "reasoning": (
                "Tipo resuelto por heurística de nombre de archivo, "
                "sin llamada a Gemini (S51)."
            ),
        }

    dni_hint = _extract_dni_via_ocr(entry)
    if not dni_hint:
        return None
    if not resolve_person_identity(dni_hint):
        # DNI válido pero no coincide con nadie -- alta de trabajador
        # nuevo exige Gemini, decisión explícita de Miguel Ángel (S51).
        return None

    return {
        "domain": domain, "document_type_code": code,
        "confidence": "N/A", "is_dossier": False, "is_photo": False,
        "dni_hint": dni_hint,
        "reasoning": (
            "Tipo resuelto por heurística de nombre de archivo, DNI "
            "leído por OCR y coincide con un trabajador ya existente, "
            "sin llamada a Gemini (S51)."
        ),
    }


def apply_quarantine_classification(entry) -> dict:
    """
    Full pipeline for ONE quarantine file (H29, S040 -- the "Always-on
    Task que clasifique la cuarentena" of the H29 roadmap, point 2):
    classify, and -- only for MACHINE domain, only when the real
    machine can be resolved with certainty from the mirrored folder
    path already inside quarantine (`resolve_machine_asset`, same as
    3.27) -- relocate it out of quarantine into its real `DOC.
    MAQUINAS` folder, renamed, via `move_service.move_entry()` (pure
    index write, `blob_name` in GCS is never touched, same as every
    other operation in this module).

    PERSONAL domain follows the same certainty principle, corrected
    S041 at Miguel Ángel's explicit direction (working copy of the
    Microsoft 365 reality, DB-only operation, low risk -- "vamos a
    hacer ya los movimientos de manera real [en base de datos] (...)
    vamos a ver los resultados y si hay que cambiar algo, se cambia"):
    when the `dni_hint` read off this document resolves to an already
    seeded `PersonIdentity` (`resolve_person_identity()` -- exact DNI
    match, the same hard-identifier principle as `resolve_machine_asset`
    for MACHINE, H29 3.27), it IS relocated out of quarantine into
    `PersonIdentity.folder_path`, renamed via the canonical
    surnames/name on the identity.

    Extended further, same session: a well-formed `dni_hint`
    (`is_valid_spanish_dni()`) matching no existing `PersonIdentity`
    is no longer an automatic dead end --
    `resolve_or_create_person_identity()` checks the extracted name
    against every existing identity first (suspected DNI misreading,
    never a duplicate created) and, only when the name doesn't match
    anyone either, creates a real new worker landing in
    `_NEW_WORKER_STAGING_FOLDER` ("PTE CONTRATACION" -- Miguel Ángel:
    no document reliably says which of the real categories a brand
    new worker belongs to). Either way `result["person_identity_note"]`
    carries the explanation into the audit log detail.

    No identity resolved or created (DNI unreadable, invalid, name
    missing) means the same fallback as before: classified, never
    relocated, left flagged for human review. Same caution for
    MACHINE files whose folder can't be resolved: classified, never
    relocated.

    Before any domain branching -- a file gets ONE more chance to be
    intercepted regardless of domain: when Gemini is CERTAIN the file
    is a composition of two or more distinct catalogued documents
    (`document_type_code == "DESCONOCIDO"` AND `is_dossier` true --
    H29, S041, Miguel Ángel's explicit decision, real examples: an
    ITV card + a permiso de circulación; a DNI + a course
    certificate; a DNI + a driving licence), it is soft-deleted
    straight to `_DOSSIER_TRASH_USERNAME`'s papelera
    (`trash_dossier_entry()`) instead of being left flagged for
    review. `is_dossier` is a certainty signal, never a guess --
    "DESCONOCIDO" alone (couldn't recognise a single document, e.g.
    an uncatalogued type) never triggers this, only stays flagged as
    before.

    **Second interception, S042 -- `document_type_code == "MANUAL_USO"`
    (closed-vocabulary type, seeded since 0004_seed_closed_vocabulary,
    domain MACHINE) always relocates straight to the real
    `MANUAL_USO_FOLDER` ("MANUALES DE USO"), regardless of domain or
    machine resolution.** Root cause this fixes, confirmed against a
    real batch: a generic operator manual almost never sits under a
    per-machine quarantine subfolder, so `resolve_machine_asset()`
    (which only scans `parent_path`, never the filename) had nothing
    to match even when Gemini correctly read a fleet code off the
    file's own name -- every MANUAL_USO file landed in NO CONFORMES
    on its one pass, forever, since the type existed but nothing
    routed it. The file's current `entry.name` is kept as-is (never
    `naming_service`'s `{CÓDIGO_MÁQUINA}_{TIPO}_{FECHA}` scheme, which
    doesn't apply to a model-generic manual); a name collision at the
    destination gets `move_service`'s automatic " (N)" ordinal, same
    as any other move.

    Returns the same shape as `apply_classification()`
    (`new_name`/`classified`/`renamed`), plus `relocated` (bool -- the
    file's `parent_path` actually changed) and, when relocated,
    `new_parent_path`.

    ---

    Pipeline completo para UN archivo de cuarentena (H29, S040 -- la
    "Always-on Task que clasifique la cuarentena" del punto 2 de la
    hoja de ruta H29): clasifica, y -- solo para dominio MÁQUINA, solo
    cuando la máquina real se puede resolver con certeza a partir de
    la ruta de carpeta ya reflejada dentro de cuarentena
    (`resolve_machine_asset`, igual que 3.27) -- la reubica fuera de
    cuarentena a su carpeta real de `DOC. MAQUINAS`, renombrada, vía
    `move_service.move_entry()` (escritura de índice pura, el
    `blob_name` en GCS nunca se toca, igual que cualquier otra
    operación de este módulo).

    El dominio PERSONAL sigue el mismo principio de certeza, corregido
    en S041 por indicación explícita de Miguel Ángel (estamos sobre
    una copia de la realidad de Microsoft 365, operación solo de base
    de datos, riesgo bajo -- "vamos a hacer ya los movimientos de
    manera real [en base de datos] (...) vamos a ver los resultados y
    si hay que cambiar algo, se cambia"): cuando el `dni_hint` leído en
    este documento resuelve a un `PersonIdentity` ya sembrado
    (`resolve_person_identity()` -- coincidencia exacta de DNI, mismo
    principio de identificador duro que `resolve_machine_asset` para
    MÁQUINA, H29 3.27), SÍ se reubica fuera de cuarentena a
    `PersonIdentity.folder_path`, renombrada con los apellidos/nombre
    canónicos de la identidad.

    Ampliado más adelante, misma sesión: un `dni_hint` bien formado
    (`is_valid_spanish_dni()`) que no coincide con ningún
    `PersonIdentity` ya no es un callejón sin salida automático --
    `resolve_or_create_person_identity()` primero comprueba el nombre
    extraído contra todas las identidades existentes (sospecha de
    error de lectura del DNI, nunca se crea un duplicado) y, solo
    cuando el nombre tampoco coincide con nadie, crea un trabajador
    nuevo de verdad que aterriza en `_NEW_WORKER_STAGING_FOLDER`
    ("PTE CONTRATACION" -- Miguel Ángel: ningún documento dice de
    forma fiable a cuál de las categorías reales pertenece un
    trabajador recién llegado). En cualquiera de los dos casos,
    `result["person_identity_note"]` lleva la explicación hasta el
    detalle del historial.

    Sin identidad resuelta ni creada (DNI ilegible, inválido, sin
    nombre) se mantiene el mismo fallback de antes: se clasifica,
    nunca se reubica, queda marcado para revisión humana. Misma
    cautela para archivos de MÁQUINA cuya carpeta no se pueda
    resolver: se clasifican, nunca se reubican.

    Antes de cualquier ramificación por dominio -- un archivo tiene
    UNA oportunidad más de ser interceptado sea cual sea su dominio:
    cuando Gemini tiene CERTEZA de que el archivo es la composición
    de dos o más documentos catalogados distintos
    (`document_type_code == "DESCONOCIDO"` Y `is_dossier` cierto --
    H29, S041, decisión explícita de Miguel Ángel, ejemplos reales:
    una tarjeta ITV + un permiso de circulación; un DNI + un
    certificado de curso; un DNI + un permiso de conducción), se
    reubica directamente a la papelera de `_DOSSIER_TRASH_USERNAME`
    (`trash_dossier_entry()`) en vez de quedar marcado para revisión.
    `is_dossier` es una señal de certeza, nunca una sospecha --
    "DESCONOCIDO" a secas (no se reconoce un único documento, p. ej.
    un tipo sin catalogar) nunca dispara esto, sigue quedando
    marcado como antes.

    **Segunda intercepción, S042 -- `document_type_code == "MANUAL_USO"`
    (tipo de vocabulario cerrado, sembrado desde 0004_seed_closed_
    vocabulary, dominio MÁQUINA) se reubica siempre directamente a la
    carpeta real `MANUAL_USO_FOLDER` ("MANUALES DE USO"), sea cual sea
    el dominio o si se resuelve la máquina.** Causa raíz que esto
    corrige, confirmada contra un lote real: un manual de operador
    genérico casi nunca vive bajo una subcarpeta de cuarentena por
    máquina, así que `resolve_machine_asset()` (que solo recorre
    `parent_path`, nunca el nombre de archivo) no tenía nada que
    encontrar aunque Gemini leyera bien un código de flota en el
    propio nombre del archivo -- todo archivo MANUAL_USO caía en NO
    CONFORMES en su única pasada, para siempre, porque el tipo existía
    pero nada lo enrutaba. El `entry.name` actual se conserva tal cual
    (nunca el esquema `{CÓDIGO_MÁQUINA}_{TIPO}_{FECHA}` de
    `naming_service`, que no aplica a un manual genérico al modelo);
    una colisión de nombre en el destino recibe el ordinal automático
    " (N)" de `move_service`, igual que cualquier otro movimiento.

    Devuelve la misma forma que `apply_classification()`
    (`new_name`/`classified`/`renamed`), más `relocated` (bool -- si
    el `parent_path` del archivo cambió de verdad) y, cuando se
    reubica, `new_parent_path`.
    """
    domain = quarantine_domain_for_entry(entry)
    result = _try_heuristic_classification(entry, domain)
    if result is None:
        result = classify_entry(entry, domain)
    if "error" in result:
        result.update(
            new_name=None, classified=False,
            renamed=False, relocated=False,
        )
        return result

    if result.get("document_type_code") == "DESCONOCIDO" \
            and result.get("is_dossier"):
        if trash_dossier_entry(entry):
            result.update(
                new_name=None, classified=False,
                renamed=False, relocated=False, trashed=True,
            )
            return result
        result["trashed"] = False

    if result.get("is_photo"):
        # S043, Miguel Ángel, verbatim, tras dos fotografías reales de
        # una grúa (guardadas como PDF, "A-69 E-0124-BJL WhatsApp
        # Image...") atascadas en NO CONFORMES sin ningún tipo de
        # catálogo que pudiera encajarlas nunca -- una fotografía no
        # es un documento administrativo, nunca lo será, y forzarla a
        # un tipo del vocabulario cerrado sería inventar un tipo que
        # no le corresponde: "Fotos sin asignar específicamente a una
        # máquina se eliminan, tenemos que tener una tabla de media
        # para añadir fotos a las máquinas pero tendrá otra vía de
        # subida, no por aquí, si no directamente desde el CRUD de
        # maquinaria." Interpretación explícita, a confirmar con
        # Miguel Ángel si no es la deseada: mientras esa vía de subida
        # por CRUD no exista, NINGUNA foto queda "asignada de verdad"
        # por este flujo -- da igual que la carpeta de cuarentena
        # nombre una máquina real (como aquí, `A-69`, código de flota
        # real) -- así que se eliminan todas las detectadas como foto,
        # sin excepción por carpeta. Borrado blando
        # (`trash_dossier_entry()`, papelera de
        # `_DOSSIER_TRASH_USERNAME`, recuperable), nunca un borrado
        # real de GCS (4.12).
        if trash_dossier_entry(entry):
            result.update(
                new_name=None, classified=False,
                renamed=False, relocated=False, trashed=True,
                trash_reason="FOTOGRAFÍA ELIMINADA",
            )
            return result
        result["trashed"] = False

    if result.get("document_type_code") == "MANUAL_USO":
        # Caso especial, S042 -- Miguel Ángel: un manual de uso es
        # genérico al modelo, no específico de un activo concreto, no
        # tiene sentido perseguir un `MachineAsset` real como el resto
        # de dominio MÁQUINA (`resolve_machine_asset` busca un código
        # de flota en `parent_path`, y un manual sin carpeta por
        # máquina nunca lo tendrá -- esto era justo lo que dejaba a
        # este tipo, ya en el catálogo desde 0004_seed_closed_
        # vocabulary, sin poder reubicarse nunca y cayendo siempre en
        # NO CONFORMES). Va directo a su propia carpeta real
        # (MANUAL_USO_FOLDER), con el nombre que ya traía -- nunca el
        # esquema {CÓDIGO_MÁQUINA}_{TIPO}_{FECHA} de naming_service,
        # que no aplica aquí -- y ordinal automático solo si hay
        # colisión (`move_service.move_entry`, igual que cualquier
        # otro movimiento de este módulo).
        move_entry(entry, MANUAL_USO_FOLDER)
        result.update(
            new_name=entry.name, classified=True,
            renamed=False, relocated=True,
            new_parent_path=MANUAL_USO_FOLDER,
        )
        return result

    effective_domain = domain or result.get("domain")
    if domain and result.get("domain") and result.get("domain") != domain:
        # Incidente real S043: Gemini devolvió "domain": "PERSONAL"
        # para un DNI de comprador que vivía bajo una carpeta ya
        # deterministamente MÁQUINA (`quarantine_domain_for_entry()`,
        # nunca sobreescrita -- ver el `or` de la línea de arriba, que
        # ya protegía la clasificación real). El bug real era solo de
        # AUDITORÍA: el detalle del log seguía mostrando el "Dominio"
        # crudo que devolvió Gemini, no el que el sistema usó de
        # verdad para procesar el archivo -- confundía el diagnóstico
        # (llevó a sospechar un enrutado a PERSONAL que nunca ocurrió).
        # `result["domain"]` se corrige aquí mismo para que cualquier
        # consumidor futuro (el propio detalle del log, u otro) vea
        # siempre el dominio real aplicado, nunca el que Gemini
        # ignoró la instrucción de "ya conocido, no lo cambies".
        result["reasoning"] = (
            "%s -- Gemini devolvió dominio %s pese a estar fijado como "
            "%s por la propia carpeta; se ha usado %s, el real."
            % (
                result.get("reasoning", ""), result.get("domain"),
                domain, domain,
            )
        )
    result["domain"] = effective_domain
    result["machine_mismatch_warning"] = (
        check_machine_mismatch(entry, result)
        if effective_domain == "MACHINE" else None
    )

    if effective_domain == "PERSONAL":
        identity = resolve_or_create_person_identity(result, entry)
        if not identity:
            result.update(
                new_name=None, classified=False,
                renamed=False, relocated=False,
            )
            return result

        candidate_name = build_new_name(entry, "PERSONAL", result)
        if not candidate_name:
            result.update(
                new_name=None, classified=False,
                renamed=False, relocated=False,
            )
            return result

        target_parent_path = identity.folder_path.strip("/")

        final_name = candidate_name
        ordinal = 1
        while _virtual_location_taken(
            entry.bucket, target_parent_path, final_name, exclude_pk=entry.pk,
        ):
            final_name = build_new_name(
                entry, "PERSONAL", result, ordinal=ordinal,
            )
            ordinal += 1

        entry.name = final_name
        move_entry(entry, target_parent_path)

        result["new_name"] = final_name
        result["classified"] = True
        result["renamed"] = True
        result["relocated"] = True
        result["new_parent_path"] = target_parent_path
        return result

    if effective_domain != "MACHINE":
        result.update(
            new_name=None, classified=False,
            renamed=False, relocated=False,
        )
        return result

    asset = resolve_or_create_machine_asset(entry, result)
    if not asset:
        result.update(
            new_name=None, classified=False,
            renamed=False, relocated=False,
        )
        return result

    candidate_name = build_new_name(entry, "MACHINE", result, asset=asset)
    if not candidate_name:
        result.update(
            new_name=None, classified=False,
            renamed=False, relocated=False,
        )
        return result

    target_parent_path = entry.parent_path
    if target_parent_path.startswith(QUARANTINE_PREFIX):
        target_parent_path = target_parent_path[len(QUARANTINE_PREFIX):]

    final_name = candidate_name
    ordinal = 1
    while _virtual_location_taken(
        entry.bucket, target_parent_path, final_name, exclude_pk=entry.pk,
    ):
        final_name = build_new_name(
            entry, "MACHINE", result, ordinal=ordinal, asset=asset,
        )
        ordinal += 1

    entry.name = final_name
    move_entry(entry, target_parent_path)

    result["new_name"] = final_name
    result["classified"] = True
    result["renamed"] = True
    result["relocated"] = True
    result["new_parent_path"] = target_parent_path
    return result
