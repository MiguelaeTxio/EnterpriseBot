# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/fleet/tasks.py
"""
H30 (S135). Periodic tasks of the fleet app.

---

H30 (S135). Tareas periódicas de la app fleet: sincronización de
GasoGes (programa del surtidor) para que las lecturas de km y horas
entren solas en Revisiones y Avisos.
"""
import logging
from datetime import date
from datetime import timedelta

from celery import shared_task

from fleet.gasoges_sync import run_sync

logger = logging.getLogger(__name__)

SYNC_DAYS = 3


@shared_task(name="fleet.tasks.sync_gasoges_task")
def sync_gasoges_task():
    """
    Sync the last days of GasoGes (idempotent: nothing is duplicated).

    ---

    Sincroniza los últimos días de GasoGes. Idempotente: un suministro
    ya guardado no se vuelve a guardar ni a convertir en lectura.
    """
    end = date.today()
    start = end - timedelta(days=SYNC_DAYS - 1)
    return run_sync(start, end, logger.info)
