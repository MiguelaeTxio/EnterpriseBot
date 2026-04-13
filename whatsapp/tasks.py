# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/whatsapp/tasks.py
"""
Celery tasks for the whatsapp channel app.
Implements three periodic tasks managed by Celery Beat:
  - expire_whatsapp_sessions: deactivates sessions older than 24 hours.
  - check_in_meeting_reminders: sends presence reminders via WhatsApp template.
  - expire_presence_statuses: closes PresenceStatus records past their ends_at.
The latter two close the presence system loop deferred from Hito 3.
---
Tareas Celery para la app del canal WhatsApp.
Implementa tres tareas periódicas gestionadas por Celery Beat:
  - expire_whatsapp_sessions: desactiva sesiones con más de 24 horas de antigüedad.
  - check_in_meeting_reminders: envía recordatorios de presencia vía template WhatsApp.
  - expire_presence_statuses: cierra registros PresenceStatus que han superado su ends_at.
Las dos últimas cierran el bucle del sistema de presencia diferido del Hito 3.
"""

import logging
import os
from datetime import timedelta

from celery import shared_task
from django.utils.timezone import now
from twilio.rest import Client as TwilioClient

from ivr_config.models import Contact, PresenceStatus
from .models import WhatsAppSession, WhatsAppTemplate

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# INTERNAL HELPERS
# ---------------------------------------------------------------------------

def _build_twilio_client() -> TwilioClient:
    """
    Builds and returns an authenticated Twilio REST Client using API Key
    credentials from the environment. Isolated here to avoid circular imports
    with whatsapp.services.
    ---
    Construye y devuelve un Twilio REST Client autenticado usando credenciales
    API Key del entorno. Aislado aquí para evitar imports circulares con
    whatsapp.services.
    """
    return TwilioClient(
        username=os.environ["TWILIO_API_KEY_SID"],
        password=os.environ["TWILIO_API_KEY_SECRET"],
        account_sid=os.environ["TWILIO_ACCOUNT_SID"],
    )


def _get_whatsapp_sender() -> str:
    """
    Returns the primary WhatsApp sender number from the environment.
    Reads TWILIO_WHATSAPP_SENDER — the E.164 number registered as a
    WhatsApp sender in the Twilio Console for Grupo Álvarez.
    Falls back to TWILIO_PHONE_NUMBER for backward compatibility.
    ---
    Devuelve el número sender de WhatsApp principal del entorno.
    Lee TWILIO_WHATSAPP_SENDER — el número E.164 registrado como sender
    de WhatsApp en el Console de Twilio para Grupo Álvarez.
    Usa TWILIO_PHONE_NUMBER como fallback por compatibilidad.
    """
    return os.environ.get(
        "TWILIO_WHATSAPP_SENDER",
        os.environ.get("TWILIO_PHONE_NUMBER", ""),
    )


# ---------------------------------------------------------------------------
# TASK 1 — expire_whatsapp_sessions
# Deactivates WhatsApp sessions whose 24-hour Meta window has expired.
# Desactiva sesiones de WhatsApp cuya ventana Meta de 24 horas ha expirado.
# ---------------------------------------------------------------------------

@shared_task(name="whatsapp.tasks.expire_whatsapp_sessions")
def expire_whatsapp_sessions() -> str:
    """
    Periodic task — runs every 30 minutes via Celery Beat.
    Queries all active WhatsAppSession records whose last_message_at timestamp
    is older than 24 hours and marks them as inactive (is_active=False).
    This enforces the Meta 24-hour session window boundary in the database,
    ensuring IncomingWhatsAppView always opens a fresh session when the window
    has expired rather than appending to a stale one.
    ---
    Tarea periódica — se ejecuta cada 30 minutos vía Celery Beat.
    Consulta todos los registros WhatsAppSession activos cuyo timestamp
    last_message_at es anterior a 24 horas y los marca como inactivos
    (is_active=False). Esto impone el límite de la ventana de sesión Meta de
    24 horas en la base de datos, asegurando que IncomingWhatsAppView siempre
    abra una sesión nueva cuando la ventana ha expirado en lugar de anexar
    mensajes a una sesión obsoleta.
    """
    threshold = now() - timedelta(hours=24)

    expired_count = WhatsAppSession.objects.filter(
        is_active=True,
        last_message_at__lt=threshold,
    ).update(is_active=False)

    result = (
        f"# [CELERY] expire_whatsapp_sessions: "
        f"{expired_count} sesión(es) expirada(s) desactivada(s)."
    )
    logger.info(result)
    return result


# ---------------------------------------------------------------------------
# TASK 2 — check_in_meeting_reminders
# Sends WhatsApp presence reminders to users stuck in IN_MEETING status.
# Envía recordatorios de presencia por WhatsApp a usuarios en estado IN_MEETING.
# Closes the presence system loop deferred from Hito 3 (V03DOC_PRESENCE_SYSTEM).
# Cierra el bucle del sistema de presencia diferido del Hito 3 (V03DOC_PRESENCE_SYSTEM).
# ---------------------------------------------------------------------------

@shared_task(name="whatsapp.tasks.check_in_meeting_reminders")
def check_in_meeting_reminders() -> str:
    """
    Periodic task — runs every 15 minutes via Celery Beat.
    Searches for all active PresenceStatus records with status=IN_MEETING,
    ends_at=None (open-ended meeting) and reminder_sent_at=None (no reminder
    sent yet). For each record where at least 3 hours have elapsed since
    starts_at, sends a WhatsApp reminder message using the presence_reminder
    template (UTILITY category) to the Contact's phone number, then sets
    reminder_sent_at = now() to prevent duplicate sends.
    Implements the pending item from V03DOC_PRESENCE_SYSTEM.md section 3.
    ---
    Tarea periódica — se ejecuta cada 15 minutos vía Celery Beat.
    Busca todos los registros PresenceStatus activos con status=IN_MEETING,
    ends_at=None (reunión sin fin definido) y reminder_sent_at=None (sin
    recordatorio enviado aún). Para cada registro donde han transcurrido al
    menos 3 horas desde starts_at, envía un mensaje de recordatorio WhatsApp
    usando la plantilla presence_reminder (categoría UTILITY) al número de
    teléfono del Contact, y establece reminder_sent_at = now() para evitar
    envíos duplicados.
    Implementa el punto pendiente de la sección 3 de V03DOC_PRESENCE_SYSTEM.md.
    """
    current_time  = now()
    reminder_threshold = current_time - timedelta(hours=3)
    sent_count    = 0
    error_count   = 0

    # Fetch eligible IN_MEETING statuses.
    # Obtener los estados IN_MEETING elegibles.
    candidates = PresenceStatus.objects.filter(
        status=PresenceStatus.STATUS_IN_MEETING,
        ends_at__isnull=True,
        reminder_sent_at__isnull=True,
        starts_at__lte=reminder_threshold,
    ).select_related(
        "company_user__user",
        "company_user__company",
    )

    if not candidates.exists():
        result = "# [CELERY] check_in_meeting_reminders: sin candidatos elegibles."
        logger.info(result)
        return result

    twilio_client  = _build_twilio_client()
    sender_number  = _get_whatsapp_sender()

    for status in candidates:
        company_user = status.company_user
        company      = company_user.company

        # Resolve the internal Contact for this CompanyUser.
        # Resolver el Contact interno para este CompanyUser.
        try:
            contact = Contact.objects.get(company_user=company_user, is_internal=True)
        except Exception:
            logger.warning(
                "# [CELERY] check_in_meeting_reminders: "
                "CompanyUser %s sin Contact interno. Omitiendo.",
                company_user,
            )
            error_count += 1
            continue

        if not contact.phone_number:
            logger.warning(
                "# [CELERY] check_in_meeting_reminders: "
                "Contact %s sin número de teléfono. Omitiendo.",
                contact,
            )
            error_count += 1
            continue

        # Retrieve the presence_reminder template for this company.
        # Recuperar la plantilla presence_reminder para esta empresa.
        try:
            template = WhatsAppTemplate.objects.get(
                company=company,
                name="presence_reminder",
                is_active=True,
            )
        except WhatsAppTemplate.DoesNotExist:
            logger.warning(
                "# [CELERY] check_in_meeting_reminders: "
                "Plantilla 'presence_reminder' no encontrada para %s. Omitiendo.",
                company.name,
            )
            error_count += 1
            continue

        # Send the reminder via Twilio ContentSid template.
        # Enviar el recordatorio vía plantilla ContentSid de Twilio.
        # SANDBOX VALIDATION MODE: using free-form text while ContentSid is PENDING.
        # MODO VALIDACIÓN SANDBOX: usando texto libre mientras ContentSid está PENDING.
        _use_freeform = template.content_sid.startswith("PENDING_")
        try:
            if _use_freeform:
                twilio_client.messages.create(
                    from_=f"whatsapp:{sender_number}",
                    to=f"whatsapp:{contact.phone_number}",
                    body=(
                        "¿Sigues reunido/a? Responde con una de estas opciones:\n"
                        "1h — Seguiré ocupado/a 1 hora más\n"
                        "2h — Seguiré ocupado/a 2 horas más\n"
                        "disponible — Ya estoy disponible"
                    ),
                )
            else:
                twilio_client.messages.create(
                    from_=f"whatsapp:{sender_number}",
                    to=f"whatsapp:{contact.phone_number}",
                    content_sid=template.content_sid,
                )

            # Mark reminder as sent to prevent duplicate dispatch.
            # Marcar el recordatorio como enviado para evitar despacho duplicado.
            status.reminder_sent_at = current_time
            status.save(update_fields=["reminder_sent_at"])

            sent_count += 1
            logger.info(
                "# [CELERY] Recordatorio enviado a %s (%s).",
                contact.phone_number,
                company_user,
            )

        except Exception as exc:
            logger.error(
                "# [CELERY] check_in_meeting_reminders: "
                "Error enviando recordatorio a %s: %s",
                contact.phone_number,
                exc,
            )
            error_count += 1

    result = (
        f"# [CELERY] check_in_meeting_reminders: "
        f"{sent_count} recordatorio(s) enviado(s), "
        f"{error_count} error(es)."
    )
    logger.info(result)
    return result


# ---------------------------------------------------------------------------
# TASK 3 — expire_presence_statuses
# Closes PresenceStatus records that have passed their ends_at timestamp.
# Cierra registros PresenceStatus que han superado su timestamp ends_at.
# Closes the presence system loop deferred from Hito 3 (V03DOC_PRESENCE_SYSTEM).
# Cierra el bucle del sistema de presencia diferido del Hito 3 (V03DOC_PRESENCE_SYSTEM).
# ---------------------------------------------------------------------------

@shared_task(name="whatsapp.tasks.expire_presence_statuses")
def expire_presence_statuses() -> str:
    """
    Periodic task — runs every 5 minutes via Celery Beat.
    Finds all PresenceStatus records that have a defined ends_at in the past
    and are still open (ends_at is not None but the record has not been
    explicitly closed by setting a newer ends_at). For each expired record,
    creates a new AVAILABLE PresenceStatus to restore the user's availability,
    maintaining the append-only ledger pattern of the presence system.
    Implements the pending item from V03DOC_PRESENCE_SYSTEM.md section 3.
    ---
    Tarea periódica — se ejecuta cada 5 minutos vía Celery Beat.
    Encuentra todos los registros PresenceStatus que tienen un ends_at definido
    en el pasado y siguen abiertos (ends_at no es None pero el registro no ha
    sido cerrado explícitamente estableciendo un ends_at más reciente). Para
    cada registro expirado, crea un nuevo PresenceStatus AVAILABLE para
    restaurar la disponibilidad del usuario, manteniendo el patrón de libro
    mayor de solo adición del sistema de presencia.
    Implementa el punto pendiente de la sección 3 de V03DOC_PRESENCE_SYSTEM.md.
    """
    current_time  = now()
    expired_count = 0

    # Find PresenceStatus records with ends_at in the past that have not yet
    # been superseded by a newer record for the same user.
    # Encontrar registros PresenceStatus con ends_at en el pasado que aún no
    # han sido reemplazados por un registro más reciente para el mismo usuario.
    expired_statuses = PresenceStatus.objects.filter(
        ends_at__isnull=False,
        ends_at__lte=current_time,
    ).exclude(
        status=PresenceStatus.STATUS_AVAILABLE,
    ).select_related("company_user")

    for status in expired_statuses:
        company_user = status.company_user

        # Check whether a newer PresenceStatus already exists for this user.
        # Comprobar si ya existe un PresenceStatus más reciente para este usuario.
        newer_exists = PresenceStatus.objects.filter(
            company_user=company_user,
            starts_at__gt=status.ends_at,
        ).exists()

        if newer_exists:
            # A newer status already covers this user — skip.
            # Un estado más reciente ya cubre a este usuario — omitir.
            continue

        # Create a new AVAILABLE status to restore the user's availability.
        # Crear un nuevo estado AVAILABLE para restaurar la disponibilidad del usuario.
        PresenceStatus.objects.create(
            company_user=company_user,
            status=PresenceStatus.STATUS_AVAILABLE,
            starts_at=status.ends_at,
        )

        expired_count += 1
        logger.info(
            "# [CELERY] expire_presence_statuses: "
            "%s restaurado a AVAILABLE tras expiración de %s.",
            company_user,
            status.ends_at.strftime("%Y-%m-%d %H:%M"),
        )

    result = (
        f"# [CELERY] expire_presence_statuses: "
        f"{expired_count} usuario(s) restaurado(s) a AVAILABLE."
    )
    logger.info(result)
    return result
