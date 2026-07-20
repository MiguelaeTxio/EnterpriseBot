# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_management/tasks.py
"""
Motor de alertas de vencimiento de documentos (Hito 26, anexo seccion
2.1). Tarea Celery periodica que revisa los DocumentAlert pendientes,
dispara el envio via WhatsApp usando la plantilla ya creada y aprobada
en H23/S021 (document_expiry_alert, UTILITY, content_sid
HX55da66276bb2025f691c378abff0123e -- pendiente de aprobacion de Meta
a fecha de esta sesion, ver whatsapp/management/commands/
seed_whatsapp_templates.py), y marca cada alerta como enviada.

Reutiliza el patron real ya en produccion de
whatsapp.tasks.check_in_meeting_reminders (mismo mecanismo Twilio
Content API, mismas variables de entorno) -- no reinventa nada.

Este modulo NUNCA importa MachineDocument ni el futuro modelo de H25:
DocumentAlert ya lleva denormalizados document_label/subject_label
(rellenados por quien crea la alerta), asi que esta tarea no necesita
resolver el objeto generico para construir el texto del mensaje.

---

Document expiry alert engine (Milestone 26, annex section 2.1).
Periodic Celery task that checks pending DocumentAlert rows, dispatches
via WhatsApp using the template already created in H23/S021, and marks
each alert as sent. Reuses the real pattern already in production from
whatsapp.tasks.check_in_meeting_reminders -- same Twilio Content API
mechanism, same environment variables.
"""
import logging
from datetime import timedelta

from celery import shared_task
from django.utils.timezone import now

from .alert_service import send_alert_now
from .models import DocumentAlert

logger = logging.getLogger(__name__)


@shared_task(name="document_management.tasks.send_document_expiry_alerts")
def send_document_expiry_alerts() -> str:
    """
    Tarea periodica -- se ejecuta a diario via Celery Beat (hueco
    horario 3:00, reutilizado tras eliminar la tarea muerta de
    purge_old_chat_messages, ver enterprise_core/settings.py).

    Busca DocumentAlert con status=PENDING cuya fecha de aviso
    (expiry_date - alert_offset_days) ya se ha alcanzado, y delega el
    envio real en document_management.alert_service.send_alert_now()
    (S025 -- extraida de aqui para que el envio MANUAL desde el panel
    reutilice exactamente la misma logica, un unico punto de verdad
    para el mecanismo de Twilio/plantilla).

    Nunca deja que el fallo de una alerta aborte el resto del lote --
    mismo principio que process_machine_document_batch.

    ---

    Periodic task -- runs daily via Celery Beat. Finds PENDING
    DocumentAlert rows whose alert date has been reached and delegates
    the actual send to alert_service.send_alert_now() (S025 -- shared
    with the manual "send now" button in the panel).
    """
    today = now().date()

    due_alerts = list(
        DocumentAlert.objects
        .filter(status=DocumentAlert.Status.PENDING)
        .select_related("company")
        .prefetch_related("contacts")
    )
    due_alerts = [
        alert for alert in due_alerts
        if alert.expiry_date - timedelta(days=alert.alert_offset_days) <= today
    ]

    if not due_alerts:
        result = (
            "# [CELERY] send_document_expiry_alerts: sin alertas "
            "pendientes que disparar hoy."
        )
        logger.info(result)
        return result

    sent_count = 0
    error_count = 0

    for alert in due_alerts:
        success, detail = send_alert_now(alert)
        if success:
            sent_count += 1
        else:
            error_count += 1
            logger.warning(
                "# [CELERY] send_document_expiry_alerts: alerta #%d "
                "no enviada -- %s",
                alert.pk, detail,
            )

    result = (
        f"# [CELERY] send_document_expiry_alerts: {sent_count} "
        f"alerta(s) enviada(s), {error_count} con error/sin contacto "
        f"valido."
    )
    logger.info(result)
    return result
