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
"""
import logging
import time

from google.genai.types import GenerateContentConfig, HttpOptions, Part

from ai_services.gemini_client import DEFAULT_MODEL, get_gemini_client
from ai_services.gemini_rate_limiter import acquire_gemini_slot
from spare_parts.gcs_service import download_bytes

from .models import DocumentTypeCatalog

logger = logging.getLogger(__name__)

_MAX_GEMINI_ATTEMPTS = 3
_RETRY_DELAY_SECONDS = 60

_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "domain": {"type": "string", "enum": ["MACHINE", "PERSONAL", "DESCONOCIDO"]},
        "document_type_code": {"type": "string"},
        "confidence": {"type": "string", "enum": ["ALTA", "MEDIA", "BAJA"]},
        "reasoning": {"type": "string"},
        "machine_code_hint": {"type": "string"},
        "first_surname_hint": {"type": "string"},
        "second_surname_hint": {"type": "string"},
        "given_name_hint": {"type": "string"},
        "date_hint": {"type": "string"},
    },
    "required": [
        "domain", "document_type_code", "confidence", "reasoning",
        "machine_code_hint", "first_surname_hint", "second_surname_hint",
        "given_name_hint", "date_hint",
    ],
}

_PROMPT_TEMPLATE = """Eres un clasificador de documentación administrativa de una empresa \
española de grúas y maquinaria pesada. Se te da UN documento (PDF), y debes \
identificar su tipo dentro de una lista CERRADA de tipos posibles -- nunca \
inventes un tipo fuera de esta lista, ni renombres uno existente con tus \
propias palabras.

{domain_instruction}

TIPOS DE DOCUMENTO POSIBLES (código -- descripción):
{catalog_lines}

Si el documento no encaja claramente en ninguno de los tipos anteriores, \
usa el código "DESCONOCIDO" y explica por qué en "reasoning".

Además del tipo, extrae estas pistas SI aparecen de forma clara en el propio \
documento (deja la cadena vacía "" si no aparecen -- nunca inventes un valor):
- machine_code_hint: código interno o matrícula de la máquina/vehículo al \
que se refiere el documento (solo si el dominio es de máquina).
- first_surname_hint, second_surname_hint, given_name_hint: primer apellido, \
segundo apellido y nombre de pila de la persona a la que se refiere el \
documento (solo si el dominio es de personal). Si el documento es un DNI, \
estos son exactamente los campos que aparecen impresos en él.
- date_hint: la fecha más relevante del documento para decidir cuándo se \
emitió o cuándo caduca (formato AAAA-MM-DD), si se puede leer con claridad.

Responde ÚNICAMENTE el JSON solicitado, sin texto adicional."""

_DOMAIN_LABELS = {
    "MACHINE": "MÁQUINA / VEHÍCULO",
    "PERSONAL": "PERSONAL / TRABAJADOR",
}


def _build_prompt(domain: str | None) -> str:
    """
    Builds the classification prompt. If the domain is already known
    (file living under DOC. MAQUINAS or DOC. PERSONAL), the catalog is
    narrowed to that domain's own codes plus BOTH, and "domain" is
    given as a fact. If the domain is unknown (a quarantine file,
    which is exactly the real use case -- nobody has sorted it yet),
    the full active catalog is listed and Gemini is asked to decide
    the domain too.

    ---

    Construye el prompt de clasificación. Si el dominio ya se conoce
    (archivo que vive bajo DOC. MAQUINAS o DOC. PERSONAL), el catálogo
    se acota a los códigos propios de ese dominio más BOTH, y "domain"
    se da como un hecho. Si el dominio se desconoce (un archivo de
    cuarentena, que es exactamente el caso de uso real -- todavía
    nadie lo ha clasificado), se lista el catálogo activo completo y
    se le pide a Gemini que decida también el dominio.
    """
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
        domain_instruction=domain_instruction, catalog_lines=catalog_lines,
    )


def _generate_content_with_retry(client, **kwargs):
    """
    Same retry pattern already validated in
    `ai_services.document_vision_service._generate_content_with_retry`
    (proactive rate-limit slot + up to 3 attempts on a Vertex AI 429),
    kept local to this app instead of importing that module's private
    helper across app boundaries.

    ---

    Mismo patrón de reintento ya validado en
    `ai_services.document_vision_service._generate_content_with_retry`
    (slot de límite de tasa proactivo + hasta 3 intentos ante un 429 de
    Vertex AI), mantenido local a esta app en vez de importar el
    auxiliar privado de ese módulo cruzando el límite entre apps.
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
                "# [classification_service] 429 de Vertex AI "
                "(intento %d/%d). Reintentando en %ds.",
                attempt, _MAX_GEMINI_ATTEMPTS, _RETRY_DELAY_SECONDS,
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
    """
    import json

    try:
        content_bytes = download_bytes(entry.bucket, entry.blob_name)
        client = get_gemini_client()
        response = _generate_content_with_retry(
            client,
            model=DEFAULT_MODEL,
            contents=[
                Part.from_bytes(
                    data=content_bytes, mime_type=entry.content_type or "application/pdf",
                ),
                _build_prompt(domain),
            ],
            config=GenerateContentConfig(
                http_options=HttpOptions(timeout=90_000),
                response_mime_type="application/json",
                response_schema=_RESPONSE_SCHEMA,
                temperature=0.0,
            ),
        )
        return json.loads(response.text.strip())
    except Exception as exc:
        logger.warning(
            "# [classify_entry] Fallo clasificando %s: %s",
            entry.blob_name, exc, exc_info=True,
        )
        return {"error": str(exc)}
