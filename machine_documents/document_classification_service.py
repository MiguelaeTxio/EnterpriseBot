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

1. classify_document() -- clasificación de un único documento,
   ESPECÍFICA de este dominio (prompt de documentación de maquinaria).
   document_type es deliberadamente texto libre, no validado contra
   una lista cerrada: Gemini puede proponer categorías nuevas por su
   cuenta (decisión abierta #2 de este hito).
2. assess_master_coverage() -- AGNÓSTICA de dominio, extraída a
   ai_services.document_vision_service en S024 (ver ese módulo) y
   reexportada aquí para no romper machine_documents/tasks.py. Dado un
   PDF candidato a "maestro" y los documentos individuales ya
   conocidos del mismo lote de subida, pide a Gemini comparar por
   SIMILITUD DE CONTENIDO (decisión abierta #4, no por número de
   páginas) qué páginas del candidato no están representadas por
   ningún documento individual.
3. extract_pages() -- AGNÓSTICA de dominio, extraída igualmente a
   ai_services.document_vision_service y reexportada aquí. Una vez que
   Gemini ha identificado las páginas no cubiertas, las extrae a un
   PDF independiente nuevo usando PyMuPDF (`fitz`).

Reparto de módulos (S024, premisa de modularidad de Miguel Ángel --
"cuanto más modularizado esté todo, mejor"): este archivo ya NO
contiene el helper de reintento 429, el parseo de fechas ISO, ni las
funciones agnósticas de dominio -- viven en
ai_services.document_vision_service (compartido también por
personal_documents/H25). Este archivo se queda únicamente con lo que
es específico de documentación de maquinaria: el prompt de
clasificación y las reglas de heurística de nombre de archivo.
"""
import json
import logging

from ai_services.document_vision_service import (
    _generate_content_with_retry,
    assess_master_coverage,  # noqa: F401 -- reexportado para machine_documents/tasks.py
    clean_display_name,
    extract_pages,  # noqa: F401 -- reexportado para machine_documents/tasks.py
    parse_iso_date,
)
from ai_services.gemini_client import DEFAULT_MODEL, get_gemini_client
from google.genai.types import (
    GenerateContentConfig,
    HttpOptions,
    Part,
    ThinkingConfig,
)

logger = logging.getLogger(__name__)

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
                "display_name": clean_display_name(filename),
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
            "expiry_date": parse_iso_date(parsed.get("expiry_date", "")),
            "issue_date": parse_iso_date(parsed.get("issue_date", "")),
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


# assess_master_coverage() y extract_pages() son agnósticas de dominio
# -- viven en ai_services.document_vision_service e importadas arriba,
# reexportadas para machine_documents/tasks.py (ver docstring del
# módulo, S024).
