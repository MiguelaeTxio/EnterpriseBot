# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/ai_services/gemini_client.py
"""
Shared Gemini client initialisation for Vertex AI (google-genai SDK).
Centralises the client construction pattern already validated in
production by work_order_processor.services._get_gemini_client(),
so every app that needs text/vision Gemini calls (non-Live API)
imports from here instead of duplicating the logic (DRY principle,
see doc-master-enterprisebot section 4.1.1).

Default model is gemini-3.5-flash (mandatory for new code as of
S001-H10, 2026-06-30). The gemini-2.5-flash migration debt tracked in
doc-master-enterprisebot section 4.1.1 was closed in S93/H32 — every
consumer in the codebase now uses gemini-3.5-flash.

---

Inicialización compartida del cliente Gemini para Vertex AI (SDK
google-genai). Centraliza el patrón de construcción de cliente ya
validado en producción por
work_order_processor.services._get_gemini_client(), de forma que
toda app que necesite llamadas de texto/visión a Gemini (no Live
API) importe desde aquí en vez de duplicar la lógica (principio DRY,
ver doc-master-enterprisebot sección 4.1.1).

El modelo por defecto es gemini-3.5-flash (obligatorio para código
nuevo desde S001-H10, 2026-06-30). La deuda de migración de
gemini-2.5-flash registrada en doc-master-enterprisebot sección 4.1.1
se cerró en S93/H32 — todo consumidor del código usa ya
gemini-3.5-flash.
"""
import logging
import os
import random

from google import genai
from google.genai.types import (
    GenerateContentConfig,
    HttpOptions,
    HttpRetryOptions,
)

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

# S153: reintentos del propio SDK (google-genai 2.x, tenacity), según la
# estrategia de reintentos de la documentación de Vertex AI ("Retry
# strategy" y "Error code 429", Gemini Enterprise Agent Platform,
# consultadas el 17/11/2026): backoff exponencial truncado CON jitter,
# empezando en ~1-2 s, doblando, con tope de 60 s, y solo para 408,
# 429 y 5xx (nunca 400/401). Hasta S153 el cliente no reintentaba nada
# (sin retry_options el SDK hace un único intento) y los envoltorios de
# cada app esperaban 60 s FIJOS: todos los procesos que se topaban con
# el 429 a la vez volvían a la vez 60 s después y volvían a chocar. La
# documentación lo desaconseja: el 429 de Standard PayGo es contención
# momentánea de la cuota compartida, no un límite fijo agotado, y se
# resuelve con esperas cortas, crecientes y desincronizadas.
#
# SDK-level retries (Vertex AI "Retry strategy"): truncated exponential
# backoff with jitter on 408/429/5xx only.
RETRY_STATUS_CODES = [408, 429, 500, 502, 503, 504]
DEFAULT_RETRY_OPTIONS = HttpRetryOptions(
    attempts=5,
    initial_delay=2.0,
    exp_base=2,
    max_delay=60,
    jitter=1,
    http_status_codes=RETRY_STATUS_CODES,
)


def backoff_delay(attempt: int, base: float, cap: float = 300) -> float:
    """
    Exponential backoff with jitter for the apps' own outer retries.
    ---
    Espera del reintento propio de cada app (por encima de los del
    SDK): base, 2·base, 4·base... con tope `cap`, más un jitter
    aleatorio de hasta la mitad, para que varios procesos que chocaron
    a la vez no vuelvan a la vez (S153).
    """
    delay = min(base * (2 ** max(attempt - 1, 0)), cap)
    return delay + random.uniform(0, delay / 2)


# Default API version for the underlying REST calls.
# Versión de API por defecto para las llamadas REST subyacentes.
DEFAULT_API_VERSION = 'v1'


def ensure_gcp_credentials() -> None:
    """
    Configura `GOOGLE_APPLICATION_CREDENTIALS` (Application Default
    Credentials) a partir de `GCP_CREDENTIALS_PATH` si todavía no está
    definida -- mismo mecanismo que ya usaba `get_gemini_client()`,
    extraído aquí en H31/S100 para que cualquier otro cliente GCP de
    la plataforma (Cloud Vision, Cloud Storage, etc.) lo reutilice sin
    duplicar la línea. Idempotente -- `setdefault` no pisa un valor ya
    presente en el proceso.
    """
    os.environ.setdefault(
        'GOOGLE_APPLICATION_CREDENTIALS',
        os.environ.get('GCP_CREDENTIALS_PATH', ''),
    )


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
    ensure_gcp_credentials()
    client = genai.Client(
        http_options=HttpOptions(
            api_version=api_version,
            retry_options=DEFAULT_RETRY_OPTIONS,
        ),
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
