# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/h28_migration_agent/heartbeat.py
"""Heartbeat to the server every 5 minutes (H30, S123).
---
Latido al servidor cada 5 minutos (H30, S123, punto 7 de la hoja de ruta).

Miguel Angel, tras un corte de luz que dejo este agente parado sin que
nadie se enterase: el agente dice "fecha, hora, estoy vivo" cada 5
minutos y, si el servidor pasa mas de 15 minutos sin oirlo, avisa por
WhatsApp (`document_explorer.system_agent_service` en el servidor).

Misma via y mismo token que `server_notify.py` (POST con el token
compartido `H28_AGENT_API_TOKEN`), solo libreria estandar. Nunca es
fatal: un latido fallido se registra en el log y el siguiente se
intenta a los 5 minutos; nunca bloquea subidas ni el icono de bandeja
(hilo demonio aparte).
"""
import logging
import socket
import threading
import urllib.parse
import urllib.request

from config import (
    SERVER_BASE_URL, SERVER_NOTIFY_TIMEOUT_SECONDS, get_server_api_token,
)

logger = logging.getLogger(__name__)

AGENT_NAME = "h28_migration_agent"
HEARTBEAT_PATH = "/panel/explorador/agente/latido/"
HEARTBEAT_INTERVAL_SECONDS = 5 * 60


def send_heartbeat():
    """
    Send one heartbeat; True on a confirmed 200.

    ---

    Envia un latido; True ante un 200 confirmado del servidor.
    """
    token = get_server_api_token()
    if not token:
        logger.warning("Latido omitido: sin token de API configurado.")
        return False
    body = urllib.parse.urlencode({
        "agent_name": AGENT_NAME, "host": socket.gethostname(),
    }).encode("utf-8")
    request = urllib.request.Request(
        SERVER_BASE_URL + HEARTBEAT_PATH,
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
            ok = response.status == 200
    except Exception as exc:  # noqa: BLE001 -- nunca fatal
        logger.warning("Latido fallido: %s", exc)
        return False
    if ok:
        logger.info("Latido enviado.")
    return ok


def _heartbeat_loop(stop_event):
    while not stop_event.is_set():
        send_heartbeat()
        stop_event.wait(HEARTBEAT_INTERVAL_SECONDS)


def start_heartbeat_thread():
    """
    Start the heartbeat daemon thread (first beat right away).

    ---

    Arranca el hilo demonio del latido (el primero, en el acto).
    """
    stop_event = threading.Event()
    thread = threading.Thread(
        target=_heartbeat_loop, args=(stop_event,),
        name="h28-heartbeat", daemon=True,
    )
    thread.start()
    return stop_event
