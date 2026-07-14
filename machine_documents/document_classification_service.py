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
# Single-document classification / Clasificación de un único documento
# ---------------------------------------------------------------------------

_CLASSIFY_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "document_type": {"type": "string"},
        "display_name": {"type": "string"},
        "is_possible_master": {"type": "boolean"},
    },
    "required": ["document_type", "display_name", "is_possible_master"],
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

Responde únicamente con el JSON solicitado."""


def classify_document(pdf_bytes: bytes, filename: str) -> dict:
    """
    Classifies a single PDF document via Gemini Vision, returning its
    proposed type, a human-readable display name, and whether it
    looks like a "master" document combining several others.

    Args:
        pdf_bytes: raw bytes of the PDF file.
        filename: original filename as uploaded (used only as a hint
            in the prompt -- classification is always driven by
            content, never inferred from the filename, per this
            milestone's principle #1).

    Returns a dict with document_type (str), display_name (str) and
    is_possible_master (bool). On any error, returns an empty/False
    fallback and logs the exception -- callers decide how to surface
    the failure (never raises).

    ---

    Clasifica un único documento PDF vía Gemini Vision, devolviendo
    su tipo propuesto, un nombre legible y si parece un documento
    "maestro" que combina varios otros.

    Args:
        pdf_bytes: bytes crudos del archivo PDF.
        filename: nombre de archivo original tal como se subió (solo
            se usa como pista en el prompt -- la clasificación
            siempre se basa en el contenido, nunca se infiere del
            nombre de archivo, según el principio #1 de este hito).

    Devuelve un dict con document_type (str), display_name (str) e
    is_possible_master (bool). Ante cualquier error, devuelve un
    fallback vacío/False y registra la excepción -- quien llama
    decide cómo mostrar el fallo (nunca lanza excepción).
    """
    _empty = {
        "document_type": "",
        "display_name": "",
        "is_possible_master": False,
    }

    try:
        client = get_gemini_client()
        response = client.models.generate_content(
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
        }
        logger.info(
            "# [classify_document] %s -> tipo=%r maestro_posible=%s",
            filename, result["document_type"], result["is_possible_master"],
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
        response = client.models.generate_content(
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
