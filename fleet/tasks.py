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
COMPANY_SLUG = "grupo-alvarez"


@shared_task(name="fleet.tasks.sync_gasoges_task")
def sync_gasoges_task():
    """
    Sync the last days of GasoGes (idempotent: nothing is duplicated).

    ---

    Sincroniza los últimos días de GasoGes. Idempotente: un suministro
    ya guardado no se vuelve a guardar ni a convertir en lectura.
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
