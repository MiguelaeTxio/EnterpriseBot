# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/h28_migration_agent/state.py
"""Persistence of watched folders across agent restarts.
---
Persistencia de carpetas vigiladas entre reinicios del agente.

Decision de Miguel Angel (S031): "el agente tiene que recordar que
es lo que estaba haciendo y seguir haciendolo" — al reiniciar, las
carpetas ya elegidas se retoman automaticamente, sin volver a
seleccionarlas a mano.
"""

import json
import logging
import os

from config import get_watched_folders_state_path

logger = logging.getLogger(__name__)


def load_watched_folders():
    """Load the list of folders the agent was watching.
    ---
    Carga la lista de carpetas que el agente estaba vigilando.

    Returns
    -------
    list[str]
        Folder paths from the last run. Empty list if there is no
        state file yet, or if it is unreadable/corrupt (logged as a
        warning, never raised — a corrupt state file must not stop
        the agent from starting).
        ---
        Rutas de carpetas de la ultima ejecucion. Lista vacia si
        todavia no hay archivo de estado, o si esta ilegible/corrupto
        (se registra como aviso, nunca se relanza — un archivo de
        estado corrupto no debe impedir que el agente arranque).
    """
    state_path = get_watched_folders_state_path()
    if not os.path.isfile(state_path):
        return []
    try:
        with open(state_path, "r", encoding="utf-8") as state_file:
            data = json.load(state_file)
        folders = data.get("watched_folders", [])
        if not isinstance(folders, list):
            raise ValueError("watched_folders no es una lista")
        return folders
    except (OSError, ValueError, json.JSONDecodeError) as error:
        logger.warning(
            "No se pudo leer el estado de carpetas vigiladas (%s): "
            "%s. Se arranca sin retomar ninguna carpeta.",
            state_path,
            error,
        )
        return []


def save_watched_folders(folders):
    """Persist the current list of watched folders.
    ---
    Persiste la lista actual de carpetas vigiladas.

    Parameters
    ----------
    folders : Iterable[str]
    """
    state_path = get_watched_folders_state_path()
    try:
        with open(state_path, "w", encoding="utf-8") as state_file:
            json.dump(
                {"watched_folders": sorted(set(folders))},
                state_file,
                indent=2,
                ensure_ascii=False,
            )
    except OSError as error:
        # Losing persistence is not fatal — the agent keeps working
        # this run, it just won't resume automatically next time.
        # ---
        # Perder la persistencia no es fatal — el agente sigue
        # funcionando esta ejecucion, simplemente no retomara solo
        # la proxima vez.
        logger.error(
            "No se pudo guardar el estado de carpetas vigiladas: %s",
            error,
        )
