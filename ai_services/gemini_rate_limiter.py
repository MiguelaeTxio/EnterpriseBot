# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/ai_services/gemini_rate_limiter.py
"""
Proactive token-bucket rate limiter for Gemini Vision calls, shared
across every app that classifies documents via Gemini
(machine_documents/H23, personal_documents/H25, and the future H27
email ingestion) -- transversal by design, same reasoning as
ai_services.gemini_client (DRY, doc-master-enterprisebot sección
4.1.1).

Added S024, during the design of the multi-folder batch upload
feature for H23: until now, quota protection was purely REACTIVE
(machine_documents.document_classification_service._generate_content_with_retry
waits 60s and retries after a 429 already happened). That is still
the last-resort safety net (kept as-is, see
ai_services.document_vision_service), but a folder-sized batch can
queue dozens of documents at once, and firing all of their Gemini
calls back-to-back invites a burst of 429s instead of avoiding them.
This module adds a PROACTIVE gate: every caller acquires a token
before firing a call, spacing requests out instead of only reacting
after a failure.

Verified online 2026-07-17 (Directriz 4.4/SINE QUA NON): Vertex AI's
Standard PayGo consumption mode for current Gemini models (the one
this project uses) does not expose a single fixed per-project RPM
quota the way older/free-tier Gemini access does -- it runs on shared
throughput tiers instead. There is no one true RPM number to target,
so instead of hardcoding one, the limit is a conservative,
operator-adjustable setting (GEMINI_VISION_MAX_RPM env var, same
pattern as GCP_CREDENTIALS_PATH/GOOGLE_CLOUD_PROJECT in
ai_services.gemini_client) -- turn it down if 429s show up in the
logs, turn it up if the queue is draining slower than it needs to.

Thread/process-local by design (in-memory bucket, no cross-worker
coordination): Celery on this project runs with the default prefork
pool (see enterprise_core/celery.py), so each worker process gets its
own bucket. GEMINI_VISION_MAX_RPM should be set with that in mind (per
worker process, not a global project-wide ceiling) until a real need
for cross-process coordination appears -- not built preemptively
(YAGNI), same principle as not building the "sin asignar" auto-link
CRUD before it's needed (ver anexo H23, "Decisiones cerradas en
S024").

---

Limitador proactivo tipo token bucket para llamadas a Gemini Vision,
compartido por cualquier app que clasifique documentos vía Gemini
(machine_documents/H23, personal_documents/H25, y la futura ingesta
de correo de H27) -- transversal por diseño, mismo razonamiento que
ai_services.gemini_client (DRY, doc-master-enterprisebot sección
4.1.1).

Añadido en S024, durante el diseño de la subida de carpeta en lote
para H23: hasta ahora la protección de cuota era puramente REACTIVA
(machine_documents.document_classification_service._generate_content_with_retry
espera 60s y reintenta después de que un 429 ya ha ocurrido). Eso
sigue siendo la red de seguridad de último recurso (se mantiene tal
cual, ver ai_services.document_vision_service), pero un lote del
tamaño de una carpeta puede encolar decenas de documentos de golpe, y
lanzar todas sus llamadas a Gemini una detrás de otra invita a una
tormenta de 429 en vez de evitarla. Este módulo añade una compuerta
PROACTIVA: quien llama adquiere un token antes de disparar una
llamada, espaciando las peticiones en vez de solo reaccionar tras un
fallo.

Verificado en línea 2026-07-17 (Directriz 4.4/SINE QUA NON): el modo
de consumo Standard PayGo de Vertex AI para los modelos Gemini
actuales (el que usa este proyecto) no expone una cuota RPM fija por
proyecto como sí hace el acceso a Gemini más antiguo/de nivel
gratuito -- funciona con niveles de rendimiento compartido
("shared throughput tiers") en su lugar. No hay un único número RPM
"verdadero" al que apuntar, así que en vez de fijarlo a fuego, el
límite es un ajuste conservador y configurable por el operador
(variable de entorno GEMINI_VISION_MAX_RPM, mismo patrón que
GCP_CREDENTIALS_PATH/GOOGLE_CLOUD_PROJECT en ai_services.gemini_client)
-- se baja si aparecen 429 reales en los logs, se sube si la cola
drena más despacio de lo necesario.

Local a cada proceso/hilo por diseño (bucket en memoria, sin
coordinación entre workers): Celery en este proyecto corre con el
pool prefork por defecto (ver enterprise_core/celery.py), así que cada
proceso worker tiene su propio bucket. GEMINI_VISION_MAX_RPM debe
fijarse teniendo esto en cuenta (por proceso worker, no un techo
global de todo el proyecto) hasta que aparezca una necesidad real de
coordinación entre procesos -- no se construye por adelantado (YAGNI),
mismo principio que no construir el CRUD de vinculación automática de
"sin asignar" antes de que haga falta (ver anexo H23, "Decisiones
cerradas en S024").
"""
import logging
import os
import threading
import time

logger = logging.getLogger(__name__)

# Conservador a propósito -- ajustar vía variable de entorno según lo
# que muestren los logs reales, nunca a ciegas (mismo principio
# empírico de siempre). Sin GEMINI_VISION_MAX_RPM en el entorno, 20
# RPM por proceso worker es un punto de partida prudente para Standard
# PayGo sin haber visto todavía 429 reales en producción con el
# volumen de una carpeta completa.
#
# Conservative on purpose -- adjust via environment variable based on
# real logs, never blindly (same empirical principle as always).
# Without GEMINI_VISION_MAX_RPM in the environment, 20 RPM per worker
# process is a prudent starting point for Standard PayGo without
# having seen real 429s yet at folder-batch volume.
_DEFAULT_MAX_RPM = 20


class _TokenBucket:
    """
    Simple thread-safe token-bucket rate limiter. One instance per
    Celery worker process (module-level singleton below) -- see module
    docstring for why cross-process coordination isn't built here.
    ---
    Limitador de tasa tipo token bucket, simple y thread-safe. Una
    instancia por proceso worker de Celery (singleton a nivel de
    módulo, más abajo) -- ver el docstring del módulo para el motivo
    de no coordinar entre procesos.
    """

    def __init__(self, requests_per_minute: int):
        self.rate_per_second = requests_per_minute / 60.0
        self.max_tokens = float(requests_per_minute)
        self.tokens = float(requests_per_minute)
        self.last_refill = time.monotonic()
        self.lock = threading.Lock()

    def acquire(self) -> None:
        """
        Blocks until a token is available, then consumes it. Never
        raises -- worst case it waits.
        ---
        Bloquea hasta que hay un token disponible, y lo consume. Nunca
        lanza excepción -- en el peor caso, espera.
        """
        while True:
            with self.lock:
                now = time.monotonic()
                elapsed = now - self.last_refill
                self.tokens = min(
                    self.max_tokens,
                    self.tokens + elapsed * self.rate_per_second,
                )
                self.last_refill = now
                if self.tokens >= 1:
                    self.tokens -= 1
                    return
            time.sleep(0.1)


def _get_max_rpm() -> int:
    """
    Reads GEMINI_VISION_MAX_RPM from the environment on every call
    (not cached at import time) so it can be tuned without a code
    deploy -- same operational spirit as adjusting a setting, but this
    project keeps Gemini config in env vars, not settings.py (see
    ai_services.gemini_client).
    ---
    Lee GEMINI_VISION_MAX_RPM del entorno en cada llamada (no se cachea
    en el import) para poder ajustarlo sin desplegar código -- mismo
    espíritu operativo que tocar un setting, pero este proyecto
    mantiene la configuración de Gemini en variables de entorno, no en
    settings.py (ver ai_services.gemini_client).
    """
    raw = os.environ.get("GEMINI_VISION_MAX_RPM", "")
    try:
        value = int(raw)
        if value > 0:
            return value
    except ValueError:
        pass
    return _DEFAULT_MAX_RPM


_bucket_lock = threading.Lock()
_bucket: _TokenBucket | None = None
_bucket_rpm: int | None = None


def acquire_gemini_slot() -> None:
    """
    Blocks until it's safe to fire one more Gemini Vision call under
    the configured GEMINI_VISION_MAX_RPM budget. Call this immediately
    before every client.models.generate_content(...) that classifies a
    document -- both machine_documents and personal_documents wrap
    their Gemini calls with this (see
    ai_services.document_vision_service._generate_content_with_retry,
    which calls this internally so callers never have to remember to).

    Recreates the underlying bucket if GEMINI_VISION_MAX_RPM changed
    since it was created (picks up an env var change on the next
    worker restart, or mid-process if something reloads the env --
    rare, but cheap to support).

    ---

    Bloquea hasta que es seguro disparar una llamada más a Gemini
    Vision dentro del presupuesto configurado en
    GEMINI_VISION_MAX_RPM. Llamar justo antes de cada
    client.models.generate_content(...) que clasifique un documento --
    tanto machine_documents como personal_documents envuelven sus
    llamadas a Gemini con esto (ver
    ai_services.document_vision_service._generate_content_with_retry,
    que lo llama internamente para que quien invoca no tenga que
    acordarse).

    Recrea el bucket subyacente si GEMINI_VISION_MAX_RPM cambió desde
    que se creó (recoge un cambio de variable de entorno en el
    siguiente reinicio del worker, o a media ejecución si algo recarga
    el entorno -- caso raro, pero barato de soportar).
    """
    global _bucket, _bucket_rpm

    max_rpm = _get_max_rpm()
    with _bucket_lock:
        if _bucket is None or _bucket_rpm != max_rpm:
            _bucket = _TokenBucket(max_rpm)
            _bucket_rpm = max_rpm
            logger.info(
                "# [acquire_gemini_slot] Bucket de cuota (re)creado: "
                "%d RPM por proceso worker.",
                max_rpm,
            )
    _bucket.acquire()
