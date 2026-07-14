# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/machine_documents/document_classification_service.py
"""
Gemini Vision classification service for MachineAsset (cost centre)
documentation ingestion (Hito 23).

Verified online 2026-07-14 (Directriz 4.4/SINE QUA NON) against
Google's current documentation (ai.google.dev/gemini-api/docs/
document-processing, docs.cloud.google.com/gemini-enterprise-agent-
platform): Gemini processes PDF files natively with full multimodal
vision -- up to 1000 pages / 50MB per file -- without needing to
rasterise page by page first. This differs from the manual process
used ad hoc in S016 (pypdf text extraction + pdftoppm rasterisation):
here the whole PDF is sent directly to Gemini as a single Part, and
`response_schema` forces structured JSON output for both
classification and master-coverage comparison.

Three operations, matching the milestone's three open questions
already resolved with Miguel Angel:

1. classify_document() -- single-document classification.
   document_type is intentionally free text, not validated against a
   closed list: Gemini may propose new categories on its own (open
   decision #2 of this milestone).
2. assess_master_coverage() -- given a candidate "master" PDF and the
   individual documents already known from the same upload batch,
   asks Gemini to compare by CONTENT SIMILARITY (open decision #4,
   not by page count) which pages of the candidate are not
   represented by any individual document.
3. extract_pages() -- once Gemini has identified the uncovered pages,
   extracts them into a new standalone PDF using PyMuPDF (`fitz`),
   already a project dependency (work_order_processor.tasks,
   fleet.management.commands.import_machine_catalog) -- no new
   dependency added, DRY principle. Replaces the pypdf
   PdfWriter/add_page mechanism used by hand in S016.

---

Servicio de clasificación Gemini Vision para la ingesta de
documentación de MachineAsset (centro de gasto) (Hito 23).

Verificado en línea 2026-07-14 (Directriz 4.4/SINE QUA NON) contra la
documentación actual de Google (ai.google.dev/gemini-api/docs/
document-processing, docs.cloud.google.com/gemini-enterprise-agent-
platform): Gemini procesa archivos PDF de forma nativa con visión
multimodal completa -- hasta 1000 páginas / 50MB por archivo -- sin
necesidad de rasterizar página a página antes. Esto difiere del
proceso manual usado ad hoc en S016 (extracción de texto con pypdf +
rasterización con pdftoppm): aquí el PDF completo se envía
directamente a Gemini como un único Part, y `response_schema` fuerza
salida JSON estructurada tanto para la clasificación como para la
comparación de cobertura del documento maestro.

Tres operaciones, correspondientes a las tres preguntas abiertas del
hito ya resueltas con Miguel Ángel:

1. classify_document() -- clasificación de un único documento.
   document_type es deliberadamente texto libre, no validado contra
   una lista cerrada: Gemini puede proponer categorías nuevas por su
   cuenta (decisión abierta #2 de este hito).
2. assess_master_coverage() -- dado un PDF candidato a "maestro" y
   los documentos individuales ya conocidos del mismo lote de subida,
   pide a Gemini comparar por SIMILITUD DE CONTENIDO (decisión
   abierta #4, no por número de páginas) qué páginas del candidato no
   están representadas por ningún documento individual.
3. extract_pages() -- una vez que Gemini ha identificado las páginas
   no cubiertas, las extrae a un PDF independiente nuevo usando
   PyMuPDF (`fitz`), ya dependencia del proyecto
   (work_order_processor.tasks,
   fleet.management.commands.import_machine_catalog) -- sin añadir
   dependencia nueva, principio DRY. Sustituye al mecanismo pypdf
   PdfWriter/add_page usado a mano en S016.
"""
import json
import logging
import time
from datetime import date, datetime

import fitz  # PyMuPDF -- ya en requirements (ver cabecera del módulo)
from google.genai.types import (
    GenerateContentConfig,
    HttpOptions,
    Part,
    ThinkingConfig,
)

from ai_services.gemini_client import DEFAULT_MODEL, get_gemini_client

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 429 retry helper / Helper de reintento ante 429
# ---------------------------------------------------------------------------
#
# Added 2026-07-14 alongside the move to an async Celery task
# (machine_documents.tasks.process_machine_document_batch): the real
# incident log for this milestone showed a 429 RESOURCE_EXHAUSTED
# immediately after a 504 DEADLINE_EXCEEDED retry storm. A blocking
# time.sleep() here is safe now that these calls run inside a Celery
# worker (Always-on Task), never on a PythonAnywhere webapp request
# thread -- there is no 5-minute wall-clock limit to protect against
# anymore for this specific wait.
# ---
# Añadido 2026-07-14 junto con el paso a tarea Celery asíncrona
# (machine_documents.tasks.process_machine_document_batch): el log
# real del incidente de este hito mostró un 429 RESOURCE_EXHAUSTED
# justo después de una tormenta de reintentos por 504
# DEADLINE_EXCEEDED. Un time.sleep() bloqueante aquí es seguro ahora
# que estas llamadas se ejecutan dentro de un worker Celery (Always-on
# Task), nunca en el hilo de una petición del webapp de PythonAnywhere
# -- ya no hay límite de 5 minutos del que protegerse para esta espera
# concreta.

_MAX_GEMINI_ATTEMPTS = 3
_RETRY_DELAY_SECONDS = 60


def _generate_content_with_retry(client, **kwargs):
    """
    Calls client.models.generate_content(**kwargs), retrying up to
    _MAX_GEMINI_ATTEMPTS times with a _RETRY_DELAY_SECONDS blocking
    wait when the failure looks like a Vertex AI 429
    (RESOURCE_EXHAUSTED). Any other exception propagates immediately
    on the first attempt -- only quota/rate-limit errors are worth
    waiting out.
    ---
    Llama a client.models.generate_content(**kwargs), reintentando
    hasta _MAX_GEMINI_ATTEMPTS veces con una espera bloqueante de
    _RETRY_DELAY_SECONDS cuando el fallo parece un 429 de Vertex AI
    (RESOURCE_EXHAUSTED). Cualquier otra excepción se propaga de
    inmediato en el primer intento -- solo merece la pena esperar
    errores de cuota/límite de tasa.
    """
    last_exc = None
    for attempt in range(1, _MAX_GEMINI_ATTEMPTS + 1):
        try:
            return client.models.generate_content(**kwargs)
        except Exception as exc:
            last_exc = exc
            exc_str = str(exc)
            is_quota_error = (
                "429" in exc_str or "RESOURCE_EXHAUSTED" in exc_str
            )
            if not is_quota_error or attempt == _MAX_GEMINI_ATTEMPTS:
                raise
            logger.warning(
                "# [_generate_content_with_retry] 429 de Vertex AI "
                "(intento %d/%d). Reintentando en %ds.",
                attempt, _MAX_GEMINI_ATTEMPTS, _RETRY_DELAY_SECONDS,
            )
            time.sleep(_RETRY_DELAY_SECONDS)
    raise last_exc  # pragma: no cover -- inalcanzable, el bucle siempre retorna o lanza


def _parse_iso_date(value: str) -> date | None:
    """
    Parses a 'YYYY-MM-DD' string into a date, returning None for
    empty/missing/malformed values instead of raising -- Gemini output
    for optional date fields is untrusted input, never assume it's
    well-formed.
    ---
    Parsea una cadena 'YYYY-MM-DD' a date, devolviendo None para
    valores vacíos/ausentes/mal formados en vez de lanzar excepción --
    la salida de Gemini para campos de fecha opcionales es entrada no
    confiable, nunca asumir que está bien formada.
    """
    value = (value or "").strip()
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        logger.warning(
            "# [_parse_iso_date] Valor de fecha no parseable "
            "devuelto por Gemini: %r. Se descarta (None).",
            value,
        )
        return None

# ---------------------------------------------------------------------------
# Filename heuristic classification (NEVER calls Gemini) / Clasificación
# heurística por nombre de archivo (NUNCA llama a Gemini)
# ---------------------------------------------------------------------------
#
# Introduced after an incident (2026-07-14): a user manual PDF included by
# mistake in a real test batch caused Gemini to time out (heavy/long
# document, 60s DEADLINE_EXCEEDED) and burned enough retries to push the
# whole request against PythonAnywhere's hard 5-minute webapp timeout
# (confirmed via server error log -- 504 DEADLINE_EXCEEDED from Vertex AI,
# then 429 RESOURCE_EXHAUSTED on retry). Miguel Ángel's explicit decision:
# user manuals must NEVER be sent to Gemini at all -- classified by
# filename heuristic and uploaded directly instead. Keeping the rule table
# a list (not a single hardcoded check) so future filename-based
# categories can be added the same way without touching the calling code.
#
# Introducido tras un incidente (2026-07-14): un manual de uso incluido
# por error en un lote de prueba real provocó un timeout de Gemini
# (documento pesado/largo, 60s DEADLINE_EXCEEDED) y consumió suficientes
# reintentos como para empujar toda la petición contra el timeout duro de
# 5 minutos de PythonAnywhere (confirmado vía log de errores del servidor
# -- 504 DEADLINE_EXCEEDED de Vertex AI, después 429 RESOURCE_EXHAUSTED en
# el reintento). Decisión explícita de Miguel Ángel: los manuales de uso
# NUNCA deben enviarse a Gemini -- se clasifican por heurística de nombre
# de archivo y se suben directamente. La tabla de reglas se mantiene como
# lista (no un único check hardcodeado) para que futuras categorías
# basadas en nombre de archivo puedan añadirse igual sin tocar el código
# que llama.
_FILENAME_HEURISTIC_RULES = [
    # (palabra clave, MAYÚSCULAS, buscada como subcadena en el nombre de
    # archivo en mayúsculas -> document_type asignado sin pasar por Gemini)
    ("MANUAL", "Manual de uso"),
]


def _clean_display_name(filename: str) -> str:
    """
    Builds a human-readable display_name straight from a filename,
    for heuristic classification (no Gemini call, so no
    content-derived name is available). Strips the extension,
    replaces '-'/'_' with spaces, and collapses repeated whitespace.
    ---
    Construye un display_name legible directamente a partir de un
    nombre de archivo, para clasificación heurística (sin llamada a
    Gemini, así que no hay nombre derivado del contenido disponible).
    Quita la extensión, sustituye '-'/'_' por espacios, y colapsa
    espacios repetidos.
    """
    stem = filename.rsplit(".", 1)[0]
    cleaned = stem.replace("_", " ").replace("-", " ")
    return " ".join(cleaned.split())


def classify_by_filename_heuristic(filename: str) -> dict | None:
    """
    Classifies a document purely from its filename, WITHOUT calling
    Gemini at all -- for document categories that must never be sent
    to the API (currently: user manuals, per Miguel Ángel's decision
    above). Returns a dict shaped exactly like classify_document()'s
    return value (document_type, display_name, is_possible_master),
    or None if no heuristic rule matches -- in which case the caller
    must fall back to classify_document() (Gemini).

    is_possible_master is always False for heuristic matches: user
    manuals are never master documents combining others, and treating
    them as individuals-to-compare-against in
    assess_master_coverage() would defeat the whole point of this
    heuristic (their bytes would end up sent to Gemini anyway via that
    call) -- callers must exclude heuristic-classified entries from
    the `individual_docs` list passed to assess_master_coverage().

    ---

    Clasifica un documento únicamente a partir de su nombre de
    archivo, SIN llamar a Gemini en ningún momento -- para categorías
    de documento que nunca deben enviarse a la API (actualmente:
    manuales de uso, según la decisión de Miguel Ángel de arriba).
    Devuelve un dict con la misma forma que el valor de retorno de
    classify_document() (document_type, display_name,
    is_possible_master), o None si ninguna regla heurística coincide
    -- en cuyo caso quien llama debe recurrir a classify_document()
    (Gemini).

    is_possible_master es siempre False en coincidencias heurísticas:
    los manuales de uso nunca son documentos maestros que combinan
    otros, y tratarlos como individuales-contra-los-que-comparar en
    assess_master_coverage() anularía el propósito de esta heurística
    (sus bytes acabarían enviándose a Gemini igualmente por esa
    llamada) -- quien llama debe excluir las entradas clasificadas por
    heurística de la lista `individual_docs` que se pasa a
    assess_master_coverage().
    """
    upper_name = filename.upper()
    for keyword, document_type in _FILENAME_HEURISTIC_RULES:
        if keyword in upper_name:
            logger.info(
                "# [classify_by_filename_heuristic] %s -> tipo=%r "
                "(coincidencia %r, sin llamada a Gemini)",
                filename, document_type, keyword,
            )
            return {
                "document_type": document_type,
                "display_name": _clean_display_name(filename),
                "is_possible_master": False,
                "expiry_date": None,
                "issue_date": None,
                "document_number": "",
                "issuing_entity": "",
            }
    return None


# ---------------------------------------------------------------------------
# Single-document classification / Clasificación de un único documento
# ---------------------------------------------------------------------------

_CLASSIFY_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "document_type": {"type": "string"},
        "display_name": {"type": "string"},
        "is_possible_master": {"type": "boolean"},
        "expiry_date": {"type": "string"},
        "issue_date": {"type": "string"},
        "document_number": {"type": "string"},
        "issuing_entity": {"type": "string"},
    },
    "required": [
        "document_type", "display_name", "is_possible_master",
        "expiry_date", "issue_date", "document_number", "issuing_entity",
    ],
}

_CLASSIFY_PROMPT = """Eres un sistema de clasificación de documentación oficial de
maquinaria industrial pesada (grúas, carretillas elevadoras, equipos de obra,
camiones) para una empresa de servicios de grúa en España.

Se te proporciona un documento PDF llamado "{filename}". Analiza su
contenido (nunca el nombre de archivo, que puede ser arbitrario) y
determina:

1. document_type: una categoría breve y precisa que describa qué tipo
   de documento es. Ejemplos habituales en este sector: "Ficha
   técnica", "Tarjeta ITV", "Certificado de inspección OCA", "Recibo
   de seguro", "Inscripción de registro de grúas", "Declaración de
   conformidad CE". Si el contenido no encaja bien en ninguna
   categoría conocida, propón tú mismo una categoría nueva y precisa
   -- no fuerces la clasificación a una categoría genérica.
2. display_name: un nombre legible por una persona, útil para
   identificar este documento concreto en un listado (ej.
   "Certificado OCA 2025-2026 (vigente)", incluyendo fechas o
   identificadores relevantes si aparecen en el documento).
3. is_possible_master: true si el documento parece combinar el
   contenido de VARIOS documentos distintos entre sí (por ejemplo, un
   PDF único que agrupa ficha técnica + ITV + certificados + seguro,
   cada uno en un rango de páginas distinto); false si es un único
   documento de un solo tipo.
4. expiry_date: fecha de fin de vigencia/caducidad del documento
   (ITV, certificado OCA, póliza de seguro, etc.), en formato
   "YYYY-MM-DD". Cadena vacía "" si el documento no tiene fecha de
   caducidad (ej. una ficha técnica) o no aparece en el contenido.
5. issue_date: fecha de emisión/expedición del documento, en formato
   "YYYY-MM-DD". Cadena vacía "" si no aplica o no se identifica.
6. document_number: número de expediente, póliza, certificado o
   referencia equivalente, tal como aparece en el documento. Cadena
   vacía "" si no tiene uno reconocible.
7. issuing_entity: organismo o empresa que emite el documento (ej.
   una aseguradora, un OCA concreto, la Junta de Andalucía). Cadena
   vacía "" si no se identifica.

Responde únicamente con el JSON solicitado."""


def classify_document(pdf_bytes: bytes, filename: str) -> dict:
    """
    Classifies a single PDF document via Gemini Vision in a SINGLE
    call, returning its proposed type, a human-readable display name,
    whether it looks like a "master" document combining several
    others, AND (added 2026-07-14, Miguel Ángel's decision) its
    expiry_date/issue_date/document_number/issuing_entity when
    present. All four metadata fields are extracted in this same call
    rather than a follow-up one: an extra field in the same
    response_schema costs a handful of output tokens, while a second
    call per document would double the request count against
    PythonAnywhere's 5-minute webapp timeout -- exactly the failure
    mode from the 2026-07-14 incident these fields are being added
    right after.

    Args:
        pdf_bytes: raw bytes of the PDF file.
        filename: original filename as uploaded (used only as a hint
            in the prompt -- classification is always driven by
            content, never inferred from the filename, per this
            milestone's principle #1).

    Returns a dict with document_type (str), display_name (str),
    is_possible_master (bool), expiry_date (date | None), issue_date
    (date | None), document_number (str) and issuing_entity (str). On
    any error (including exhausting the 429 retry budget), returns an
    empty/False/None fallback and logs the exception -- callers decide
    how to surface the failure (never raises).

    ---

    Clasifica un único documento PDF vía Gemini Vision en UNA SOLA
    llamada, devolviendo su tipo propuesto, un nombre legible, si
    parece un documento "maestro" que combina varios otros, Y (añadido
    2026-07-14, decisión de Miguel Ángel) su expiry_date/issue_date/
    document_number/issuing_entity cuando están presentes. Los cuatro
    campos de metadatos se extraen en esta misma llamada en vez de en
    una llamada posterior: un campo extra en el mismo response_schema
    cuesta un puñado de tokens de salida más, mientras que una segunda
    llamada por documento duplicaría el número de peticiones contra el
    timeout de 5 minutos del webapp de PythonAnywhere -- exactamente
    el modo de fallo del incidente del 2026-07-14 justo después del
    cual se añaden estos campos.

    Args:
        pdf_bytes: bytes crudos del archivo PDF.
        filename: nombre de archivo original tal como se subió (solo
            se usa como pista en el prompt -- la clasificación
            siempre se basa en el contenido, nunca se infiere del
            nombre de archivo, según el principio #1 de este hito).

    Devuelve un dict con document_type (str), display_name (str),
    is_possible_master (bool), expiry_date (date | None), issue_date
    (date | None), document_number (str) e issuing_entity (str). Ante
    cualquier error (incluido agotar el presupuesto de reintentos por
    429), devuelve un fallback vacío/False/None y registra la
    excepción -- quien llama decide cómo mostrar el fallo (nunca lanza
    excepción).
    """
    _empty = {
        "document_type": "",
        "display_name": "",
        "is_possible_master": False,
        "expiry_date": None,
        "issue_date": None,
        "document_number": "",
        "issuing_entity": "",
    }

    try:
        client = get_gemini_client()
        response = _generate_content_with_retry(
            client,
            model=DEFAULT_MODEL,
            contents=[
                Part.from_bytes(data=pdf_bytes, mime_type="application/pdf"),
                _CLASSIFY_PROMPT.format(filename=filename),
            ],
            config=GenerateContentConfig(
                http_options=HttpOptions(timeout=60_000),
                response_mime_type="application/json",
                response_schema=_CLASSIFY_RESPONSE_SCHEMA,
                thinking_config=ThinkingConfig(thinking_budget=0),
                temperature=0.0,
            ),
        )

        parsed = json.loads(response.text.strip())
        result = {
            "document_type": str(parsed.get("document_type", "")).strip(),
            "display_name": str(parsed.get("display_name", "")).strip(),
            "is_possible_master": bool(
                parsed.get("is_possible_master", False)
            ),
            "expiry_date": _parse_iso_date(parsed.get("expiry_date", "")),
            "issue_date": _parse_iso_date(parsed.get("issue_date", "")),
            "document_number": str(
                parsed.get("document_number", "")
            ).strip(),
            "issuing_entity": str(
                parsed.get("issuing_entity", "")
            ).strip(),
        }
        logger.info(
            "# [classify_document] %s -> tipo=%r maestro_posible=%s "
            "caducidad=%s",
            filename, result["document_type"],
            result["is_possible_master"], result["expiry_date"],
        )
        return result

    except Exception as exc:
        logger.error(
            "# [classify_document] Error clasificando %s: %s",
            filename, exc, exc_info=True,
        )
        return dict(_empty)


# ---------------------------------------------------------------------------
# Master-document coverage comparison / Comparación de cobertura de maestro
# ---------------------------------------------------------------------------

_COVERAGE_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "is_master": {"type": "boolean"},
        "fully_covered": {"type": "boolean"},
        "uncovered_pages": {
            "type": "array",
            "items": {"type": "integer"},
        },
        "reasoning": {"type": "string"},
    },
    "required": [
        "is_master", "fully_covered", "uncovered_pages", "reasoning",
    ],
}

_COVERAGE_PROMPT = """Se te proporciona un documento PDF candidato a "maestro"
(el primero de los archivos adjuntos, llamado "{candidate_filename}"), seguido
de {n_individuals} documento(s) individual(es) ya subidos en el mismo lote.

Tu tarea es comparar el CONTENIDO (no el número de páginas, el
contenido real) del candidato a maestro contra el contenido de cada
documento individual, y determinar:

1. is_master: true si el candidato efectivamente combina el
   contenido de varios de los documentos individuales adjuntos (o
   contenido equivalente); false si es en realidad un documento
   independiente sin relación de contención con los individuales.
2. fully_covered: true si TODO el contenido del candidato está ya
   representado por la suma de los documentos individuales
   adjuntos; false si falta contenido.
3. uncovered_pages: lista de números de página (1-indexados, según
   la numeración del propio PDF candidato) del candidato cuyo
   contenido NO aparece en ningún documento individual adjunto. Lista
   vacía si fully_covered es true o si is_master es false.
4. reasoning: explicación breve (2-3 frases) de la comparación
   realizada.

Responde únicamente con el JSON solicitado."""


def assess_master_coverage(
    candidate_bytes: bytes,
    candidate_filename: str,
    individual_docs: list[tuple[str, bytes]],
) -> dict:
    """
    Compares a candidate "master" PDF against the individual documents
    already known from the same upload batch, using Gemini's
    understanding of CONTENT SIMILARITY (never page count) to decide
    which pages of the candidate, if any, are not yet represented by
    an individual document (open decision #4 of this milestone).

    Args:
        candidate_bytes: raw bytes of the candidate master PDF.
        candidate_filename: its original filename (prompt context
            only).
        individual_docs: list of (filename, pdf_bytes) tuples for the
            individual documents already present in the same upload
            batch to compare against. Must be non-empty -- a
            candidate with no individuals to compare against cannot
            be assessed, callers should skip this call entirely in
            that case.

    Returns a dict with is_master (bool), fully_covered (bool),
    uncovered_pages (list[int], 1-indexed) and reasoning (str). On any
    error, returns a conservative fallback (is_master=False) and logs
    the exception -- never raises.

    ---

    Compara un PDF candidato a "maestro" contra los documentos
    individuales ya conocidos del mismo lote de subida, usando el
    entendimiento de Gemini sobre SIMILITUD DE CONTENIDO (nunca
    número de páginas) para decidir qué páginas del candidato, si
    las hay, no están todavía representadas por un documento
    individual (decisión abierta #4 de este hito).

    Args:
        candidate_bytes: bytes crudos del PDF candidato a maestro.
        candidate_filename: su nombre de archivo original (solo
            contexto de prompt).
        individual_docs: lista de tuplas (filename, pdf_bytes) de los
            documentos individuales ya presentes en el mismo lote de
            subida contra los que comparar. Debe ser no vacía -- un
            candidato sin individuales contra los que comparar no
            puede evaluarse, quien llama debe omitir esta llamada por
            completo en ese caso.

    Devuelve un dict con is_master (bool), fully_covered (bool),
    uncovered_pages (list[int], 1-indexado) y reasoning (str). Ante
    cualquier error, devuelve un fallback conservador
    (is_master=False) y registra la excepción -- nunca lanza.
    """
    _fallback = {
        "is_master": False,
        "fully_covered": True,
        "uncovered_pages": [],
        "reasoning": "",
    }

    if not individual_docs:
        logger.warning(
            "# [assess_master_coverage] Llamada sin individuales contra "
            "los que comparar para %s -- se omite, fallback conservador.",
            candidate_filename,
        )
        return dict(_fallback)

    try:
        contents = [
            Part.from_bytes(
                data=candidate_bytes, mime_type="application/pdf",
            ),
        ]
        for _fname, fbytes in individual_docs:
            contents.append(
                Part.from_bytes(data=fbytes, mime_type="application/pdf")
            )
        contents.append(
            _COVERAGE_PROMPT.format(
                candidate_filename=candidate_filename,
                n_individuals=len(individual_docs),
            )
        )

        client = get_gemini_client()
        response = _generate_content_with_retry(
            client,
            model=DEFAULT_MODEL,
            contents=contents,
            config=GenerateContentConfig(
                http_options=HttpOptions(timeout=90_000),
                response_mime_type="application/json",
                response_schema=_COVERAGE_RESPONSE_SCHEMA,
                thinking_config=ThinkingConfig(thinking_budget=0),
                temperature=0.0,
            ),
        )

        parsed = json.loads(response.text.strip())
        result = {
            "is_master": bool(parsed.get("is_master", False)),
            "fully_covered": bool(parsed.get("fully_covered", True)),
            "uncovered_pages": [
                int(p) for p in parsed.get("uncovered_pages", [])
            ],
            "reasoning": str(parsed.get("reasoning", "")).strip(),
        }
        logger.info(
            "# [assess_master_coverage] %s -> maestro=%s cubierto=%s "
            "paginas_sin_cubrir=%s",
            candidate_filename, result["is_master"],
            result["fully_covered"], result["uncovered_pages"],
        )
        return result

    except Exception as exc:
        logger.error(
            "# [assess_master_coverage] Error comparando %s: %s",
            candidate_filename, exc, exc_info=True,
        )
        return dict(_fallback)


# ---------------------------------------------------------------------------
# Page extraction (PyMuPDF) / Extracción de páginas (PyMuPDF)
# ---------------------------------------------------------------------------

def extract_pages(pdf_bytes: bytes, page_numbers: list[int]) -> bytes:
    """
    Extracts the given 1-indexed pages from a PDF into a new,
    standalone PDF, using PyMuPDF (`fitz`) -- already a project
    dependency, no new one added (DRY). Replaces the pypdf
    PdfWriter/add_page mechanism used by hand in S016 for this exact
    purpose (splitting the A-45 combined document).

    Args:
        pdf_bytes: raw bytes of the source PDF.
        page_numbers: 1-indexed page numbers to extract, typically
            the `uncovered_pages` returned by assess_master_coverage().

    Returns the raw bytes of the new PDF containing only the
    requested pages, in ascending page order.

    ---

    Extrae las páginas indicadas (1-indexadas) de un PDF a un PDF
    independiente nuevo, usando PyMuPDF (`fitz`) -- ya dependencia
    del proyecto, sin añadir una nueva (DRY). Sustituye al mecanismo
    pypdf PdfWriter/add_page usado a mano en S016 para este mismo
    propósito (separar el documento combinado de la máquina A-45).

    Args:
        pdf_bytes: bytes crudos del PDF origen.
        page_numbers: números de página 1-indexados a extraer,
            típicamente el `uncovered_pages` devuelto por
            assess_master_coverage().

    Devuelve los bytes crudos del PDF nuevo que contiene únicamente
    las páginas solicitadas, en orden ascendente de página.
    """
    source_doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    new_doc = fitz.open()
    try:
        for page_number in sorted(set(page_numbers)):
            zero_indexed = page_number - 1
            new_doc.insert_pdf(
                source_doc, from_page=zero_indexed, to_page=zero_indexed,
            )
        return new_doc.tobytes()
    finally:
        new_doc.close()
        source_doc.close()
