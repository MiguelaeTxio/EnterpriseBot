# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_management/tasks.py
"""
Motor de avisos de documentación (Hito 26, reescrito en H30/S122).

La tarea diaria delega en document_explorer.notice_delivery_service:
avisos calculados desde los requisitos de documentación, enviados a
cada supervisor según su ámbito, con las plantillas
document_expiry_notice / document_missing_notice. Las filas antiguas
de DocumentAlert (30/15/7 automáticas) ya no se envían ni se crean; se
conservan como histórico.

---

Document notice engine (Milestone 26, rewritten in H30/S122). The daily
task delegates to document_explorer.notice_delivery_service.
"""
import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(name="document_management.tasks.send_document_expiry_alerts")
def send_document_expiry_alerts() -> str:
    """
    Daily task (Celery Beat, 8:00): send the document notices.

    ---

    Tarea diaria (Celery Beat, 8:00). REESCRITA EN H30 (S122): ya no
    envía las filas de `DocumentAlert` (30/15/7 automáticas por
    documento, con la plantilla antigua `document_expiry_alert`, que
    decía "de la maquina" también para personal). Delega en
    `document_explorer.notice_delivery_service.send_due_notices()`:
    los avisos calculados desde los requisitos de documentación,
    exactamente los de Avisos > Pendientes, a cada supervisor según su
    ámbito, sin repeticiones y con recordatorio semanal de faltantes y
    caducados. Mismo nombre de tarea para no tocar Celery Beat.
    Respeta el interruptor de envío automático por empresa.
    """
    from document_explorer.notice_delivery_service import send_due_notices

    try:
        result = send_due_notices()
    except Exception:
        logger.exception(
            "# [CELERY] send_document_expiry_alerts: fallo del envío de "
            "avisos.",
        )
        raise
    result = "# [CELERY] send_document_expiry_alerts: " + result
    logger.info(result)
    return result
