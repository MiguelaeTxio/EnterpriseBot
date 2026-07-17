# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/personal_documents/document_classification_service.py
"""
Gemini Vision classification service for CompanyUser (worker)
documentation ingestion (Hito 25).

Sibling of machine_documents/document_classification_service.py (H23)
-- same design, built on the SAME shared helpers
(ai_services.document_vision_service: retry/rate-limit, ISO date
parsing, master-coverage comparison, PDF page extraction), extracted
precisely so this file only has to add what's specific to personnel
documentation: the classification prompt/schema. No duplication of the
generic Gemini-calling machinery (DRY, premisa de modularidad de
Miguel Ángel, S022/S024).

Only one operation lives here, unlike machine_documents (which also
keeps a filename heuristic for user manuals): classify_document().
No filename-heuristic rule is known yet for personnel documents (no
category identified so far that must NEVER reach Gemini, unlike
MachineDocument's "MANUAL" rule) -- not built preemptively (YAGNI,
same principle already applied to ai_services.gemini_rate_limiter's
single-process design). assess_master_coverage() and extract_pages()
are imported directly from ai_services.document_vision_service by
whoever needs them (personal_documents.tasks, not yet built) --
nothing to reexport here since this file adds no domain-specific
wrapper for them.

Two differences from machine_documents.classify_document(), matching
the two extra fields on PersonalDocument (ver ese modelo, S024):

1. Extracts validity_rule AND computed_expiry_date in the SAME call,
   for the "calculated vigencia" case identified in the real example
   folder Miguel Ángel provided in S022 (a medical check-up whose
   content only stated "la validez del resultado de su examen de
   salud es ANUAL" plus the real exam date, never a direct expiry
   date). Gemini itself computes computed_expiry_date by applying the
   rule it detects to issue_date -- deliberately NOT a Python-side
   rule parser: Miguel Ángel only specified the desired OUTCOME
   ("de forma explícita siempre que exista, calculada cuando no haya
   otra opción" -- decisión S022), not the calculation mechanism (que
   quedó como pregunta abierta #2 del anexo H25); asking Gemini to
   compute it directly, in the same call, handles arbitrary natural-
   language rules (ANUAL, BIENAL, "cada 5 años", etc.) without a
   fragile hardcoded parser, at the same one-call token cost already
   established as the pattern for this milestone family (never a
   second call per document, same reasoning as
   machine_documents.classify_document's 2026-07-14 decision).
2. document_type categories reflect the real folder Miguel Ángel
   analysed in S022 (identidad, contractual, permisos/carnets,
   reconocimiento médico, formación/cursos, EPIs, entregas de
   material) instead of machinery categories -- still free text, not
   a closed list (same open decision #3 as H23, resolved the same way
   for H25: "libre" -- Miguel Ángel, S024).

Worker/DNI detection (deciding WHICH CompanyUser a document belongs
to) is deliberately OUT of scope here -- that's the job of the future
folder-ingestion detection service (H23/H25 roadmap, still to be
built), not of this per-document classifier. Same separation of
concerns as machine_documents.classify_document(), which doesn't pick
the MachineAsset either.

---

Servicio de clasificación Gemini Vision para la ingesta de
documentación de CompanyUser (trabajador) (Hito 25).

Hermano de machine_documents/document_classification_service.py (H23)
-- mismo diseño, construido sobre los MISMOS helpers compartidos
(ai_services.document_vision_service: reintento/límite de tasa, parseo
de fechas ISO, comparación de cobertura de maestro, extracción de
páginas PDF), extraídos precisamente para que este archivo solo tenga
que añadir lo específico de documentación de personal: el prompt/
schema de clasificación. Sin duplicar la maquinaria genérica de
llamada a Gemini (DRY, premisa de modularidad de Miguel Ángel,
S022/S024).

Solo vive una operación aquí, a diferencia de machine_documents (que
además mantiene una heurística de nombre de archivo para manuales de
uso): classify_document(). Todavía no hay ninguna regla heurística de
nombre de archivo conocida para documentación de personal (ninguna
categoría identificada hasta ahora que deba NUNCA llegar a Gemini, a
diferencia de la regla "MANUAL" de MachineDocument) -- no se construye
por adelantado (YAGNI, mismo principio ya aplicado en el diseño de
proceso único de ai_services.gemini_rate_limiter).
assess_master_coverage() y extract_pages() se importan directamente
desde ai_services.document_vision_service por quien las necesite
(personal_documents.tasks, todavía sin construir) -- nada que
reexportar aquí, ya que este archivo no añade ningún envoltorio
específico de dominio para ellas.

Dos diferencias frente a machine_documents.classify_document(),
correspondientes a los dos campos extra de PersonalDocument (ver ese
modelo, S024):

1. Extrae validity_rule Y computed_expiry_date en la MISMA llamada,
   para el caso de "vigencia calculada" identificado en la carpeta de
   ejemplo real que aportó Miguel Ángel en S022 (un reconocimiento
   médico cuyo contenido solo indicaba "la validez del resultado de su
   examen de salud es ANUAL" más la fecha real del examen, nunca una
   fecha de caducidad directa). El propio Gemini calcula
   computed_expiry_date aplicando la regla que detecta a issue_date --
   deliberadamente NO un parser de reglas en Python: Miguel Ángel solo
   especificó el RESULTADO deseado ("de forma explícita siempre que
   exista, calculada cuando no haya otra opción" -- decisión S022), no
   el mecanismo de cálculo (que quedó como pregunta abierta #2 del
   anexo H25); pedirle a Gemini que lo calcule directamente, en la
   misma llamada, resuelve reglas en lenguaje natural arbitrarias
   (ANUAL, BIENAL, "cada 5 años", etc.) sin un parser hardcodeado
   frágil, al mismo coste de una sola llamada ya establecido como
   patrón para esta familia de hitos (nunca una segunda llamada por
   documento, mismo razonamiento que la decisión de
   machine_documents.classify_document del 2026-07-14).
2. Las categorías de document_type reflejan la carpeta real que
   analizó Miguel Ángel en S022 (identidad, contractual, permisos/
   carnets, reconocimiento médico, formación/cursos, EPIs, entregas de
   material) en vez de categorías de maquinaria -- sigue siendo texto
   libre, no una lista cerrada (misma decisión abierta #3 que H23,
   resuelta igual para H25: "libre" -- Miguel Ángel, S024).

La detección de A QUÉ trabajador pertenece un documento (qué
CompanyUser) queda deliberadamente FUERA del alcance de este archivo
-- es tarea del futuro servicio de detección de ingesta de carpeta
(hoja de ruta H23/H25, todavía sin construir), no de este clasificador
por documento. Misma separación de responsabilidades que
machine_documents.classify_document(), que tampoco elige el
MachineAsset.
"""
import json
import logging

from ai_services.document_vision_service import (
    _generate_content_with_retry,
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
        "validity_rule": {"type": "string"},
        "computed_expiry_date": {"type": "string"},
        "document_number": {"type": "string"},
        "issuing_entity": {"type": "string"},
    },
    "required": [
        "document_type", "display_name", "is_possible_master",
        "expiry_date", "issue_date", "validity_rule",
        "computed_expiry_date", "document_number", "issuing_entity",
    ],
}

_CLASSIFY_PROMPT = """Eres un sistema de clasificación de documentación oficial de
personal (identidad, contractual, permisos, formación, salud laboral) para una
empresa de servicios de grúa en España. La mayoría de los trabajadores son
chóferes y gruístas.

Se te proporciona un documento PDF llamado "{filename}". Analiza su
contenido (nunca el nombre de archivo, que puede ser arbitrario) y
determina:

1. document_type: una categoría breve y precisa que describa qué tipo
   de documento es. Ejemplos habituales en este sector: "DNI",
   "Tarjeta sanitaria", "Contrato", "Alta en Seguridad Social",
   "Carnet de grúas", "Tarjeta del conductor", "Tarjeta de
   cualificación del conductor", "Permiso de circulación",
   "Reconocimiento médico", "Certificado de curso de formación",
   "Entrega de EPI". Si el contenido no encaja bien en ninguna
   categoría conocida, propón tú mismo una categoría nueva y precisa
   -- no fuerces la clasificación a una categoría genérica. Cada curso
   de formación distinto (con su propio código de acción formativa) es
   su propia categoría, no un cajón genérico "formación".
2. display_name: un nombre legible por una persona, útil para
   identificar este documento concreto en un listado (ej. "Carnet de
   Grúas A (vigente)", "Certificado Curso Trabajos en Altura 2025",
   incluyendo fechas, códigos o identificadores relevantes si aparecen
   en el documento).
3. is_possible_master: true si el documento parece combinar el
   contenido de VARIOS documentos distintos entre sí en un único PDF;
   false si es un único documento de un solo tipo.
4. expiry_date: fecha de fin de vigencia/caducidad, en formato
   "YYYY-MM-DD", SOLO si el documento la declara directamente y de
   forma explícita (ej. un carnet con fecha de caducidad impresa).
   Cadena vacía "" en cualquier otro caso -- incluido cuando la
   vigencia se deriva de una regla textual en vez de una fecha directa
   (ver validity_rule/computed_expiry_date más abajo). Nunca rellenes
   expiry_date Y computed_expiry_date a la vez para el mismo
   documento.
5. issue_date: fecha de emisión/expedición del documento, o fecha real
   del examen/curso/trámite, en formato "YYYY-MM-DD". Cadena vacía ""
   si no aplica o no se identifica.
6. validity_rule: si el documento NO declara una fecha de caducidad
   directa pero SÍ indica una regla textual de vigencia (ej. "la
   validez del resultado de su examen de salud es ANUAL", encontrado
   literalmente en un reconocimiento médico real de este tipo de
   empresa), transcribe esa regla tal cual la expresa el documento.
   Cadena vacía "" si el documento declara expiry_date directamente o
   no tiene ninguna vigencia aplicable.
7. computed_expiry_date: SOLO si rellenaste validity_rule, calcula tú
   mismo la fecha de caducidad real aplicando esa regla a issue_date
   (ej. examen del 15/09/2025 + regla "ANUAL" -> "2026-09-15"), en
   formato "YYYY-MM-DD". Cadena vacía "" si validity_rule está vacío o
   si no puedes calcular la fecha con confianza.
8. document_number: número de carnet, expediente, código de acción
   formativa u otra referencia equivalente, tal como aparece en el
   documento. Cadena vacía "" si no tiene uno reconocible.
9. issuing_entity: organismo, entidad formadora o empresa que emite el
   documento (ej. la DGT, una mutua, un centro de formación). Cadena
   vacía "" si no se identifica.

Responde únicamente con el JSON solicitado."""


def classify_document(pdf_bytes: bytes, filename: str) -> dict:
    """
    Classifies a single PDF document via Gemini Vision in a SINGLE
    call -- same one-call-per-document principle as
    machine_documents.classify_document() (2026-07-14 decision: an
    extra response_schema field costs a handful of output tokens,
    while a second call per document doubles the request count).
    Returns type, display name, master-document hint, and vigencia
    fields (either a direct expiry_date or a computed one derived from
    validity_rule -- never both).

    Args:
        pdf_bytes: raw bytes of the PDF file.
        filename: original filename as uploaded (prompt hint only --
            classification is always driven by content).

    Returns a dict with document_type (str), display_name (str),
    is_possible_master (bool), expiry_date (date | None), issue_date
    (date | None), validity_rule (str), computed_expiry_date
    (date | None), document_number (str) and issuing_entity (str). On
    any error (including exhausting the 429 retry budget), returns an
    empty/False/None fallback and logs the exception -- callers decide
    how to surface the failure (never raises).

    ---

    Clasifica un único documento PDF vía Gemini Vision en UNA SOLA
    llamada -- mismo principio de una llamada por documento que
    machine_documents.classify_document() (decisión del 2026-07-14: un
    campo extra en el response_schema cuesta un puñado de tokens de
    salida más, mientras que una segunda llamada por documento
    duplica el número de peticiones). Devuelve tipo, nombre legible,
    pista de documento maestro, y campos de vigencia (una expiry_date
    directa o una calculada derivada de validity_rule -- nunca las
    dos).

    Args:
        pdf_bytes: bytes crudos del archivo PDF.
        filename: nombre de archivo original tal como se subió (solo
            pista de prompt -- la clasificación siempre se basa en el
            contenido).

    Devuelve un dict con document_type (str), display_name (str),
    is_possible_master (bool), expiry_date (date | None), issue_date
    (date | None), validity_rule (str), computed_expiry_date
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
        "validity_rule": "",
        "computed_expiry_date": None,
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
            "validity_rule": str(
                parsed.get("validity_rule", "")
            ).strip(),
            "computed_expiry_date": parse_iso_date(
                parsed.get("computed_expiry_date", "")
            ),
            "document_number": str(
                parsed.get("document_number", "")
            ).strip(),
            "issuing_entity": str(
                parsed.get("issuing_entity", "")
            ).strip(),
        }
        logger.info(
            "# [classify_document] %s -> tipo=%r maestro_posible=%s "
            "caducidad=%s caducidad_calculada=%s",
            filename, result["document_type"],
            result["is_possible_master"], result["expiry_date"],
            result["computed_expiry_date"],
        )
        return result

    except Exception as exc:
        logger.error(
            "# [classify_document] Error clasificando %s: %s",
            filename, exc, exc_info=True,
        )
        return dict(_empty)
