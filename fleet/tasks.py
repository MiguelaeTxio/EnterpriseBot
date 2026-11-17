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


# H23 (S154, invasora): libro historial de las grúas A/H. Cada lectura
# de un escaneo es una llamada a Gemini; si la anterior sigue, esta no
# empieza (no se lee dos veces el mismo documento).
LOGBOOK_LOCK_PATH = os.path.join(tempfile.gettempdir(),
                                 "enterprisebot_logbook.lock")
LOGBOOK_SCANS_PER_RUN = 10


@shared_task(name="fleet.tasks.logbook_pipeline_task")
def logbook_pipeline_task(document_id=None):
    """
    Read new logbook scans and close signed reconstructions.

    ---

    Pipeline del libro historial (S154, Miguel Ángel: "dotar al sistema
    de un pipeline para poder escanear las revisiones que falten"): lee
    los escaneos LIBRO_HISTORIAL de grúas A/H que aún no se han leído
    (el recién subido si llega `document_id`; si no, hasta
    LOGBOOK_SCANS_PER_RUN de los pendientes, lleguen por donde lleguen)
    y cierra las reconstrucciones ya firmadas por el agente de firmas.
    """
    with open(LOGBOOK_LOCK_PATH, "w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            logger.info("Libro historial: la pasada anterior sigue en "
                        "marcha; esta se salta.")
            return {"saltada": True}
        return _logbook_pipeline(document_id)


def _logbook_pipeline(document_id):
    """
    One pass of the logbook pipeline.

    ---

    Una pasada del pipeline del libro historial.
    """
    from fleet import logbook_service as logbook

    pending = logbook.unread_scans()
    if document_id is not None:
        pending = [item for item in pending if item[0].pk == document_id]
    read = []
    for entry, machine in pending[:LOGBOOK_SCANS_PER_RUN]:
        result = logbook.read_and_store(entry, machine)
        logger.info("Libro historial: %s, documento %s -> %d filas.",
                    machine.code, entry.pk, result["rows"])
        read.append(entry.pk)
    summary = logbook.sync_reconstructions()
    summary["leidos"] = read
    return summary
