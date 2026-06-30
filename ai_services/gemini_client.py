# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/ai_services/gemini_client.py
"""
Shared Gemini client initialisation for Vertex AI (google-genai SDK).
Centralises the client construction pattern already validated in
production by work_order_processor.services._get_gemini_client(),
so every app that needs text/vision Gemini calls (non-Live API)
imports from here instead of duplicating the logic (DRY principle,
see doc-master-enterprisebot section 4.1.1).

Default model is gemini-3.5-flash (mandatory for new code as of
S001-H10, 2026-06-30 — see DEUDA TÉCNICA note in
doc-master-enterprisebot section 4.1.1 for the gemini-2.5-flash
migration still pending in existing code).

---

Inicialización compartida del cliente Gemini para Vertex AI (SDK
google-genai). Centraliza el patrón de construcción de cliente ya
validado en producción por
work_order_processor.services._get_gemini_client(), de forma que
toda app que necesite llamadas de texto/visión a Gemini (no Live
API) importe desde aquí en vez de duplicar la lógica (principio DRY,
ver doc-master-enterprisebot sección 4.1.1).

El modelo por defecto es gemini-3.5-flash (obligatorio para código
nuevo desde S001-H10, 2026-06-30 — ver nota DEUDA TÉCNICA en
doc-master-enterprisebot sección 4.1.1 para la migración de
gemini-2.5-flash todavía pendiente en código existente).
"""
import logging
import os

from google import genai
from google.genai.types import GenerateContentConfig, HttpOptions

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Default model — Directriz 4.1 / Modelo por defecto — Directriz 4.1
# ---------------------------------------------------------------------------
DEFAULT_MODEL = 'gemini-3.5-flash'

# Default per-request timeout in milliseconds. With vertexai=True the
# client-level HttpOptions.timeout is not reliably forwarded to httpx
# on a per-request basis; the guaranteed mechanism is passing
# HttpOptions inside GenerateContentConfig on every generate_content
# call (pattern validated in work_order_processor.services).
#
# Timeout por petición por defecto, en milisegundos. Con vertexai=True
# el HttpOptions.timeout a nivel de cliente no se propaga de forma
# fiable a httpx por petición; el mecanismo garantizado es pasar
# HttpOptions dentro de GenerateContentConfig en cada llamada a
# generate_content (patrón validado en work_order_processor.services).
DEFAULT_TIMEOUT_MS = 60_000

# Default Vertex AI region. 'global' dynamically routes requests to
# the region with the most available capacity, reducing 429 errors
# from temporary contention on regional endpoints.
#
# Región por defecto de Vertex AI. 'global' enruta dinámicamente las
# peticiones a la región con más capacidad disponible, reduciendo
# errores 429 por contención temporal en endpoints regionales.
DEFAULT_LOCATION = 'global'

# Default API version for the underlying REST calls.
# Versión de API por defecto para las llamadas REST subyacentes.
DEFAULT_API_VERSION = 'v1'


def get_gemini_client(
    location: str = DEFAULT_LOCATION,
    api_version: str = DEFAULT_API_VERSION,
) -> genai.Client:
    """
    Instantiates and returns a fresh Gemini client configured for
    Vertex AI. A new client is created on every call to avoid stale
    connection state after worker restarts (Celery prefork model).
    Credentials are sourced from the GCP_CREDENTIALS_PATH,
    GOOGLE_CLOUD_PROJECT environment variables, consistent with the
    EnterpriseBot platform (Directriz 4.1).

    Args:
        location: Vertex AI region. Defaults to 'global'. Override
            only if a future use case requires a specific regional
            endpoint instead of dynamic global routing.
        api_version: REST API version. Defaults to 'v1' (stable).

    ---

    Instancia y devuelve un cliente Gemini nuevo configurado para
    Vertex AI. Se crea un cliente nuevo en cada llamada para evitar
    estado de conexión obsoleto tras reinicios del worker (modelo
    prefork de Celery). Las credenciales provienen de las variables
    de entorno GCP_CREDENTIALS_PATH, GOOGLE_CLOUD_PROJECT, en
    coherencia con la plataforma EnterpriseBot (Directriz 4.1).

    Args:
        location: Región de Vertex AI. Por defecto 'global'. Solo
            sobrescribir si un caso futuro requiere un endpoint
            regional específico en vez de enrutado dinámico global.
        api_version: Versión de la API REST. Por defecto 'v1' (estable).
    """
    os.environ.setdefault(
        'GOOGLE_APPLICATION_CREDENTIALS',
        os.environ.get('GCP_CREDENTIALS_PATH', ''),
    )
    client = genai.Client(
        http_options=HttpOptions(api_version=api_version),
        vertexai=True,
        project=os.environ.get('GOOGLE_CLOUD_PROJECT'),
        location=location,
    )
    logger.info(
        '# Cliente Gemini compartido inicializado correctamente '
        '(Vertex AI, location=%s, api_version=%s).',
        location, api_version,
    )
    return client


def get_request_config(timeout_ms: int = DEFAULT_TIMEOUT_MS) -> GenerateContentConfig:
    """
    Builds a reusable GenerateContentConfig with a guaranteed
    per-request timeout. Callers that need additional config options
    (response_schema, response_mime_type, etc.) should build their
    own GenerateContentConfig using this timeout value rather than
    reusing this object directly, since GenerateContentConfig fields
    are not designed to be merged.

    ---

    Construye un GenerateContentConfig reutilizable con timeout por
    petición garantizado. Quien necesite opciones de configuración
    adicionales (response_schema, response_mime_type, etc.) debe
    construir su propio GenerateContentConfig usando este valor de
    timeout, en vez de reutilizar este objeto directamente, ya que
    los campos de GenerateContentConfig no están pensados para
    fusionarse.
    """
    return GenerateContentConfig(
        http_options=HttpOptions(timeout=timeout_ms),
    )
