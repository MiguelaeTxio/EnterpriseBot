# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/ai_services/document_vision_service.py
"""
Domain-agnostic Gemini Vision helpers, shared by every app that
classifies documents (machine_documents/H23, personal_documents/H25,
future H27 email ingestion). Extracted in S024 from
machine_documents/document_classification_service.py -- everything
here was already domain-agnostic (the 429 retry helper, ISO date
parsing, filename-based display name cleanup, master-document coverage
comparison, PDF page extraction); only classify_document() and the
filename heuristic rules stayed behind in machine_documents, because
those ARE domain-specific (their prompt talks about machinery
documentation) -- see machine_documents/document_classification_service.py
and personal_documents/document_classification_service.py for the
per-domain prompts that build on top of these helpers.

Modularity is an explicit premise for H23/H25/H27 (Miguel Ángel, S024:
"cuanto más modularizado esté todo, mejor" / S022: "la modularidad ya
es importante porque el proyecto tiene una dimensión gigantesca") --
this split keeps each file responsible for exactly one thing: this
module is "how to safely call Gemini Vision and extract PDF pages",
the per-app modules are "what to ask Gemini about THIS kind of
document".

_generate_content_with_retry() now also acquires a proactive rate-limit
slot (ai_services.gemini_rate_limiter.acquire_gemini_slot()) before
firing every call -- added S024 alongside the folder-batch upload
feature, see that module's docstring for the full reasoning. The
existing REACTIVE 429 retry (blocking wait + retry, unchanged since
2026-07-14) stays as the last-resort safety net; the rate limiter is
the new proactive gate in front of it.

---

Helpers de Gemini Vision agnósticos de dominio, compartidos por
cualquier app que clasifique documentos (machine_documents/H23,
personal_documents/H25, futura ingesta de correo de H27). Extraídos en
S024 desde machine_documents/document_classification_service.py --
todo lo que hay aquí ya era agnóstico de dominio (el helper de
reintento 429, el parseo de fechas ISO, la limpieza de nombre legible
a partir de nombre de archivo, la comparación de cobertura de
documento maestro, la extracción de páginas de PDF); solo
classify_document() y las reglas de heurística de nombre de archivo se
quedaron en machine_documents, porque esas SÍ son específicas de
dominio (su prompt habla de documentación de maquinaria) -- ver
machine_documents/document_classification_service.py y
personal_documents/document_classification_service.py para los
prompts propios de cada dominio, construidos sobre estos helpers.

La modularidad es una premisa explícita para H23/H25/H27 (Miguel
Ángel, S024: "cuanto más modularizado esté todo, mejor" / S022: "la
modularidad ya es importante porque el proyecto tiene una dimensión
gigantesca") -- este reparto deja cada archivo responsable de
exactamente una cosa: este módulo es "cómo llamar a Gemini Vision de
forma segura y extraer páginas de PDF", los módulos de cada app son
"qué preguntarle a Gemini sobre ESTE tipo de documento".

_generate_content_with_retry() ahora también adquiere un slot de
límite de tasa proactivo (ai_services.gemini_rate_limiter.
acquire_gemini_slot()) antes de disparar cada llamada -- añadido en
S024 junto con la subida de carpeta en lote, ver el docstring de ese
módulo para el razonamiento completo. El reintento REACTIVO ante 429 ya
existente (espera bloqueante + reintento, sin cambios desde
2026-07-14) se mantiene como red de seguridad de último recurso; el
limitador de tasa es la compuerta proactiva nueva delante de él.
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

from .gemini_client import DEFAULT_MODEL, get_gemini_client
from .gemini_rate_limiter import acquire_gemini_slot

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 429 retry helper / Helper de reintento ante 429
# (sin cambios de comportamiento desde su introducción en
# machine_documents el 2026-07-14 -- solo se le añade la adquisición
# de slot proactiva antes de cada intento)
# ---------------------------------------------------------------------------

_MAX_GEMINI_ATTEMPTS = 3
_RETRY_DELAY_SECONDS = 60


def _generate_content_with_retry(client, **kwargs):
    """
    Acquires a proactive rate-limit slot (ai_services.
    gemini_rate_limiter.acquire_gemini_slot()), then calls
    client.models.generate_content(**kwargs), retrying up to
    _MAX_GEMINI_ATTEMPTS times with a _RETRY_DELAY_SECONDS blocking
    wait when the failure looks like a Vertex AI 429
    (RESOURCE_EXHAUSTED). Any other exception propagates immediately
    on the first attempt -- only quota/rate-limit errors are worth
    waiting out.
    ---
    Adquiere un slot proactivo de límite de tasa (ai_services.
    gemini_rate_limiter.acquire_gemini_slot()), y llama a
    client.models.generate_content(**kwargs), reintentando hasta
    _MAX_GEMINI_ATTEMPTS veces con una espera bloqueante de
    _RETRY_DELAY_SECONDS cuando el fallo parece un 429 de Vertex AI
    (RESOURCE_EXHAUSTED). Cualquier otra excepción se propaga de
    inmediato en el primer intento -- solo merece la pena esperar
    errores de cuota/límite de tasa.
    """
    last_exc = None
    for attempt in range(1, _MAX_GEMINI_ATTEMPTS + 1):
        acquire_gemini_slot()
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


def parse_iso_date(value: str) -> date | None:
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
            "# [parse_iso_date] Valor de fecha no parseable "
            "devuelto por Gemini: %r. Se descarta (None).",
            value,
        )
        return None


def clean_display_name(filename: str) -> str:
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


# ---------------------------------------------------------------------------
# Master-document coverage comparison / Comparación de cobertura de maestro
# Domain-agnostic prompt -- reused as-is by every document domain.
# Prompt agnóstico de dominio -- reutilizado tal cual por cada dominio
# de documento.
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
    an individual document. Domain-agnostic -- used as-is by every
    document domain (machine/personal/future email ingestion).

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
    uncovered_pages (list[int], 1-indexed), reasoning (str) and
    comparison_failed (bool, S025). On any error, comparison_failed
    is True and the caller MUST treat this as "comparison never
    happened" -- never as "fully covered" (fully_covered=True in the
    fallback dict is a historical default value, kept for backward
    key-shape compatibility, NOT a real determination) -- see the
    caller's handling in machine_documents.tasks/personal_documents.
    tasks, which preserves the candidate document instead of
    discarding it when comparison_failed is True. Never raises.

    ---

    Compara un PDF candidato a "maestro" contra los documentos
    individuales ya conocidos del mismo lote de subida, usando el
    entendimiento de Gemini sobre SIMILITUD DE CONTENIDO (nunca
    número de páginas) para decidir qué páginas del candidato, si
    las hay, no están todavía representadas por un documento
    individual. Agnóstico de dominio -- se usa tal cual desde
    cualquier dominio de documento (máquina/personal/futura ingesta
    de correo).

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
    uncovered_pages (list[int], 1-indexado), reasoning (str) y
    comparison_failed (bool, S025). Ante cualquier error,
    comparison_failed va en True y quien llama DEBE tratarlo como
    "la comparación nunca llegó a hacerse" -- nunca como "cobertura
    completa" (fully_covered=True en el dict de fallback es un valor
    histórico por defecto, mantenido solo por compatibilidad de forma
    del dict, NO una determinación real) -- ver el manejo real en
    machine_documents.tasks/personal_documents.tasks, que conserva el
    documento candidato en vez de descartarlo cuando comparison_failed
    es True. Nunca lanza excepción.
    """
    _fallback = {
        "is_master": False,
        "fully_covered": True,
        "uncovered_pages": [],
        "reasoning": "",
        "comparison_failed": False,
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
            "comparison_failed": False,
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
        # S025, hallazgo real (Miguel Ángel, log real de producción):
        # un error de la API (ej. 400 INVALID_ARGUMENT por límite de
        # tokens al acumular muchos individuales ya persistidos para
        # la misma máquina) NUNCA debe interpretarse como "cobertura
        # confirmada" -- el _fallback de arriba (fully_covered=True,
        # uncovered_pages=[]) es idéntico a como se ve una comparación
        # real que SÍ determinó cobertura completa, así que sin este
        # flag el llamador (machine_documents.tasks/personal_documents.
        # tasks) descartaba el maestro sin haber comparado nada de
        # verdad -- riesgo real de perder contenido único. Con
        # comparison_failed=True, el llamador debe CONSERVAR el
        # maestro como documento real (misma red de seguridad que ya
        # existía para el fallo de extract_pages/classify_document del
        # contenido extraído).
        error_fallback = dict(_fallback)
        error_fallback["comparison_failed"] = True
        error_fallback["reasoning"] = f"Comparación fallida: {exc}"
        return error_fallback


# ---------------------------------------------------------------------------
# Page extraction (PyMuPDF) / Extracción de páginas (PyMuPDF)
# ---------------------------------------------------------------------------

def extract_pages(pdf_bytes: bytes, page_numbers: list[int]) -> bytes:
    """
    Extracts the given 1-indexed pages from a PDF into a new,
    standalone PDF, using PyMuPDF (`fitz`) -- already a project
    dependency, no new one added (DRY).

    Args:
        pdf_bytes: raw bytes of the source PDF.
        page_numbers: 1-indexed page numbers to extract, typically
            the `uncovered_pages` returned by assess_master_coverage().

    Returns the raw bytes of the new PDF containing only the
    requested pages, in ascending page order.

    ---

    Extrae las páginas indicadas (1-indexadas) de un PDF a un PDF
    independiente nuevo, usando PyMuPDF (`fitz`) -- ya dependencia
    del proyecto, sin añadir una nueva (DRY).

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
