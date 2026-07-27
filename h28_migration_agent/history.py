# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/h28_migration_agent/history.py
"""Event history for the H28 migration agent's local viewer.
---
Historial de eventos para el visor local del agente de migracion
H28.

S033, decision de Miguel Angel: el visor de lo que hace el agente
vive en el propio agente, no en la plataforma web -- agente y
plataforma quedan deliberadamente separados. Este modulo guarda cada
copia y cada reconciliacion como un evento estructurado, para que la
ventana de historial (main.py) los muestre sin tener que parsear
h28_migration_agent.log.
---
S033, Miguel Angel's decision: the viewer of what the agent does
lives in the agent itself, not the web platform -- agent and
platform stay deliberately separate. This module stores every copy
and every reconciliation as a structured event, so the history
window (main.py) can display them without parsing
h28_migration_agent.log.
"""

import json
import logging
import os
from datetime import datetime, timezone

from config import HISTORY_MAX_EVENTS, get_history_state_path

logger = logging.getLogger(__name__)


def load_events():
    """Load the stored events, most recent first.
    ---
    Carga los eventos guardados, del mas reciente al mas antiguo.

    Returns
    -------
    list[dict]
        Empty list if there is no history file yet, or if it is
        unreadable/corrupt (logged as a warning, never raised -- a
        corrupt history file must not stop the agent from starting).
        ---
        Lista vacia si todavia no hay archivo de historial, o si
        esta ilegible/corrupto (se registra como aviso, nunca se
        relanza -- un historial corrupto no debe impedir que el
        agente arranque).
    """
    history_path = get_history_state_path()
    if not os.path.isfile(history_path):
        return []
    try:
        with open(history_path, "r", encoding="utf-8") as history_file:
            data = json.load(history_file)
        events = data.get("events", [])
        if not isinstance(events, list):
            raise ValueError("events no es una lista")
        return events
    except (OSError, ValueError, json.JSONDecodeError) as error:
        logger.warning(
            "No se pudo leer el historial (%s): %s. Se muestra "
            "vacio.", history_path, error,
        )
        return []


def append_event(event_type, folder, summary):
    """Append a new event and persist it, keeping only the most
    recent HISTORY_MAX_EVENTS.
    ---
    Anade un evento nuevo y lo persiste, conservando solo los
    HISTORY_MAX_EVENTS mas recientes.

    Parameters
    ----------
    event_type : str
        E.g. "Copia inicial", "Reconciliacion".
        ---
        P.ej. "Copia inicial", "Reconciliacion".
    folder : str
        Local folder the event refers to.
        ---
        Carpeta local a la que se refiere el evento.
    summary : str
        Human-readable one-line result, ready to display as-is.
        ---
        Resultado en una linea, legible por una persona, listo para
        mostrarse tal cual.
    """
    events = load_events()
    events.insert(0, {
        "timestamp": datetime.now(timezone.utc).isoformat(
            timespec="seconds"
        ),
        "event_type": event_type,
        "folder": folder,
        "summary": summary,
    })
    events = events[:HISTORY_MAX_EVENTS]

    history_path = get_history_state_path()
    try:
        with open(history_path, "w", encoding="utf-8") as history_file:
            json.dump(
                {"events": events}, history_file,
                indent=2, ensure_ascii=False,
            )
    except OSError as error:
        # Losing an event from the viewer is not fatal -- the agent
        # keeps working, it just won't show up in the history
        # window. The log file (source of truth) is unaffected.
        # ---
        # Perder un evento del visor no es fatal -- el agente sigue
        # funcionando, simplemente no aparecera en la ventana de
        # historial. El archivo de log (fuente de verdad) no se ve
        # afectado.
        logger.error(
            "No se pudo guardar el evento de historial: %s", error,
        )
