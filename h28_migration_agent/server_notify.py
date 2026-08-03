# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/h28_migration_agent/server_notify.py
"""Instant server notification after a successful quarantine upload (H28/H29, S040).
---
Aviso instantaneo al servidor tras una subida a cuarentena con exito (H28/H29, S040).

Miguel Angel, verbatim: "cuando el agente sube el archivo a
cuarentena, inmediatamente se de una senal (...) para que esa subida
quede registrada en base de datos (...) deberia ser instantanea." The
panel's `document_explorer.views.RegisterUploadedObjectView` writes
the actual `DocumentIndexEntry` row; this module's only job is
telling it WHICH object was just written -- bucket and blob name,
nothing else. The server itself reads the object's real metadata
straight from GCS rather than trusting anything this module sends, so
there is nothing sensitive or authoritative in this payload beyond
"look at this path".

Deliberately stdlib-only (`urllib.request`), no new dependency:
this is one small POST, not worth adding `requests` to
`requirements.in` and forcing a pip-compile/pip-sync cycle on the
Windows build machine for it (com-environment-management, section
3.4 -- the lock is compiled where the agent runs, never assumed).

Never fatal. A failed notification never blocks or rolls back the
GCS upload that already succeeded -- S030 decision 4 already settled
that the upload itself goes straight to GCS, independent of the
server; this is a best-effort side channel on top of that, not a new
dependency for the upload path. The hourly Celery Beat safety net on
the server side (`document_explorer.tasks.refresh_quarantine_index_task`)
exists precisely to cover whatever this call fails to deliver.

---

Miguel Angel, verbatim: "cuando el agente sube el archivo a
cuarentena, inmediatamente se de una senal (...) para que esa subida
quede registrada en base de datos (...) deberia ser instantanea." La
fila real de `DocumentIndexEntry` la escribe
`document_explorer.views.RegisterUploadedObjectView` del panel; el
unico trabajo de este modulo es decirle QUE objeto se acaba de
escribir -- cubo y nombre de blob, nada mas. El propio servidor lee
los metadatos reales del objeto directamente de GCS en vez de fiarse
de lo que mande este modulo, asi que no hay nada sensible ni
autoritativo en este payload mas alla de "mira esta ruta".

Deliberadamente solo libreria estandar (`urllib.request`), sin
dependencia nueva: es un POST pequeno, no compensa anadir `requests`
a `requirements.in` y forzar un ciclo pip-compile/pip-sync en la
maquina Windows de compilacion por esto
(com-environment-management, seccion 3.4 -- el candado se compila
donde corre el agente, nunca se asume).

Nunca es fatal. Un aviso fallido nunca bloquea ni revierte la subida
a GCS que ya tuvo exito -- la decision 4 de S030 ya establecio que la
subida en si va directa a GCS, independiente del servidor; esto es un
canal aparte de mejor esfuerzo encima de eso, no una dependencia
nueva para el camino de subida. La red de seguridad horaria de Celery
Beat del lado servidor
(`document_explorer.tasks.refresh_quarantine_index_task`) existe
justamente para cubrir lo que este aviso no llegue a entregar.
"""
import json
import logging
import urllib.error
import urllib.parse
import urllib.request

from config import (
    SERVER_BASE_URL, SERVER_NOTIFY_TIMEOUT_SECONDS, get_server_api_token,
)

logger = logging.getLogger(__name__)

_NOTIFY_PATH = "/panel/documentacion/explorador/agente/registrar/"


def notify_server_of_upload(bucket_name, blob_name):
    """Best-effort POST telling the server which object was just uploaded.
    ---
    POST de mejor esfuerzo avisando al servidor de que objeto se
    acaba de subir.

    Returns True on a confirmed 200 from the server, False on
    anything else (missing token, network error, non-200 status) --
    the return value is informational only (used for the history
    viewer/log), never something the caller must act on.
    ---
    Devuelve True ante un 200 confirmado del servidor, False ante
    cualquier otra cosa (token ausente, error de red, estado
    distinto de 200) -- el valor de vuelta es solo informativo (lo
    usan el visor de historial/el log), nunca algo sobre lo que quien
    llama deba actuar.
    """
    token = get_server_api_token()
    if not token:
        logger.warning(
            "Aviso al servidor omitido para %s: sin token de API "
            "configurado (variable de entorno %s, o archivo %s en "
            "agent_data/).",
            blob_name, "H28_AGENT_API_TOKEN", "server_api_token.txt",
        )
        return False

    body = urllib.parse.urlencode({
        "bucket": bucket_name, "blob_name": blob_name,
    }).encode("utf-8")
    request = urllib.request.Request(
        SERVER_BASE_URL + _NOTIFY_PATH,
        data=body,
        method="POST",
        headers={
            "Authorization": "Bearer " + token,
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    try:
        with urllib.request.urlopen(
            request, timeout=SERVER_NOTIFY_TIMEOUT_SECONDS,
        ) as response:
            payload = json.loads(response.read().decode("utf-8"))
            logger.info(
                "Aviso al servidor OK para %s (creada=%s, "
                "actualizada=%s).",
                blob_name, payload.get("created"), payload.get("updated"),
            )
            return True
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Aviso al servidor fallido para %s: %s -- cubierto por la "
            "red de seguridad horaria del servidor mientras tanto.",
            blob_name, exc,
        )
        return False
