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
import os
from datetime import timedelta

from celery import shared_task
from django.utils.timezone import now
from twilio.rest import Client as TwilioClient

from ivr_config.models import Contact
from whatsapp.models import WhatsAppTemplate

from .models import DocumentAlert

logger = logging.getLogger(__name__)

TEMPLATE_NAME = "document_expiry_alert"


def _build_twilio_client() -> TwilioClient:
    """
    Mismo patron que whatsapp.tasks._build_twilio_client() -- aislado
    aqui para no crear un import cruzado entre apps por una sola
    funcion helper.
    """
    return TwilioClient(
        username=os.environ["TWILIO_API_KEY_SID"],
        password=os.environ["TWILIO_API_KEY_SECRET"],
        account_sid=os.environ["TWILIO_ACCOUNT_SID"],
    )


def _get_whatsapp_sender() -> str:
    """Mismo patron que whatsapp.tasks._get_whatsapp_sender()."""
    return os.environ["WHATSAPP_SENDER_NUMBER"]


@shared_task(name="document_management.tasks.send_document_expiry_alerts")
def send_document_expiry_alerts() -> str:
    """
    Tarea periodica -- se ejecuta a diario via Celery Beat (hueco
    horario 3:00, reutilizado tras eliminar la tarea muerta de
    purge_old_chat_messages, ver enterprise_core/settings.py).

    Busca DocumentAlert con status=PENDING cuya fecha de aviso
    (expiry_date - alert_offset_days) ya se ha alcanzado. Para cada
    una, envia un mensaje WhatsApp por cada contacto asociado usando
    la plantilla document_expiry_alert (4 variables: nombre del
    contacto, document_label, subject_label, expiry_date), y marca la
    alerta como SENT tras el primer envio con exito. Si la plantilla
    no esta activa/aprobada todavia, la tarea lo registra y no marca
    nada como enviado -- vuelve a intentarlo en la siguiente ejecucion.

    Nunca deja que el fallo de una alerta aborte el resto del lote --
    mismo principio que process_machine_document_batch.

    ---

    Periodic task -- runs daily via Celery Beat. Finds PENDING
    DocumentAlert rows whose alert date has been reached, sends a
    WhatsApp message per associated contact using the
    document_expiry_alert template, and marks the alert as SENT after
    the first successful send. Never lets one alert's failure abort
    the rest of the batch.
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

    twilio_client = _build_twilio_client()
    sender_number = _get_whatsapp_sender()

    sent_count = 0
    error_count = 0

    for alert in due_alerts:
        try:
            template = WhatsAppTemplate.objects.get(
                company=alert.company,
                name=TEMPLATE_NAME,
                is_active=True,
            )
        except WhatsAppTemplate.DoesNotExist:
            logger.warning(
                "# [CELERY] send_document_expiry_alerts: plantilla "
                "'%s' no activa/aprobada todavia para %s -- alerta #%d "
                "queda PENDING, se reintenta manana.",
                TEMPLATE_NAME, alert.company.name, alert.pk,
            )
            error_count += 1
            continue

        contacts_notified = 0
        for company_user in alert.contacts.all():
            try:
                contact = Contact.objects.get(
                    company_user=company_user, is_internal=True,
                )
            except Contact.DoesNotExist:
                logger.warning(
                    "# [CELERY] send_document_expiry_alerts: "
                    "CompanyUser %s sin Contact interno. Omitiendo.",
                    company_user,
                )
                continue
            if not contact.phone_number:
                logger.warning(
                    "# [CELERY] send_document_expiry_alerts: Contact "
                    "%s sin numero de telefono. Omitiendo.", contact,
                )
                continue

            try:
                twilio_client.messages.create(
                    from_=f"whatsapp:{sender_number}",
                    to=f"whatsapp:{contact.phone_number}",
                    content_sid=template.content_sid,
                    content_variables={
                        "1": company_user.user.get_full_name() or company_user.user.username,
                        "2": alert.document_label,
                        "3": alert.subject_label,
                        "4": alert.expiry_date.strftime("%d/%m/%Y"),
                    },
                )
                contacts_notified += 1
            except Exception as exc:
                logger.error(
                    "# [CELERY] send_document_expiry_alerts: error "
                    "enviando alerta #%d a %s: %s",
                    alert.pk, contact.phone_number, exc,
                )

        if contacts_notified > 0:
            alert.status = DocumentAlert.Status.SENT
            alert.sent_at = now()
            alert.save(update_fields=["status", "sent_at"])
            sent_count += 1
        else:
            error_count += 1

    result = (
        f"# [CELERY] send_document_expiry_alerts: {sent_count} "
        f"alerta(s) enviada(s), {error_count} con error/sin contacto "
        f"valido."
    )
    logger.info(result)
    return result
