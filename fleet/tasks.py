# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/fleet/tasks.py
"""
H30 (S135). Periodic tasks of the fleet app.

---

H30 (S135). Tareas periódicas de la app fleet: sincronización de
GasoGes (programa del surtidor) para que las lecturas de km y horas
entren solas en Revisiones y Avisos.
"""
import fcntl
import logging
import os
import tempfile
from datetime import date
from datetime import timedelta

from celery import shared_task

from fleet.gasoges_sync import run_sync

logger = logging.getLogger(__name__)

SYNC_DAYS = 3
COMPANY_SLUG = "grupo-alvarez"
# S137: corre cada 5 minutos; si la anterior no ha terminado, esta no
# empieza (evita preguntar dos veces por el mismo repostaje).
LOCK_PATH = os.path.join(tempfile.gettempdir(), "enterprisebot_gasoges.lock")


@shared_task(name="fleet.tasks.sync_gasoges_task")
def sync_gasoges_task():
    """
    Sync the last days of GasoGes (idempotent: nothing is duplicated).

    ---

    Sincroniza los últimos días de GasoGes. Idempotente: un suministro
    ya guardado no se vuelve a guardar ni a convertir en lectura.
    """
    with open(LOCK_PATH, "w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            logger.info("GasoGes: la sincronización anterior sigue en "
                        "marcha; esta se salta.")
            return {"saltada": True}
        return _sync()


def _sync():
    """
    One GasoGes sync and its WhatsApp questions.

    ---

    Una sincronización de GasoGes y sus preguntas por WhatsApp.
    """
    from fleet.refuel_questions import send_pending_questions
    from ivr_config.models import Company

    end = date.today()
    start = end - timedelta(days=SYNC_DAYS - 1)
    summary = run_sync(start, end, logger.info)
    # H30 (S135): después, las preguntas por WhatsApp al chófer (solo
    # salen cuando Meta ha aprobado las plantillas).
    company = Company.objects.filter(slug=COMPANY_SLUG).first()
    if company is not None:
        summary["preguntas"] = send_pending_questions(company, logger.info)
    return summary
