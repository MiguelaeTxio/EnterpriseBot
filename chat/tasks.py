# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/chat/tasks.py
"""
Celery tasks for the chat module.

broadcast_inbound_message(message_pk) -> None
    Receives a ChatMessage(INBOUND) primary key and relays the message body
    to all active contacts of the room's section via Twilio WhatsApp API,
    excluding the original sender. Only contacts with a configured alias
    and an active WhatsApp session (24-hour window) receive the broadcast.

purge_old_chat_messages() -> None
    Periodic task registered in CELERY_BEAT_SCHEDULE.
    Deletes ChatMessage records older than 7 days.
    Deletes BreakdownConversationTurn records from RESOLVED tickets
    whose updated_at is older than 7 days.
    BreakdownTicket records are never deleted.
---
Tareas Celery para el módulo de chat.

broadcast_inbound_message(message_pk) -> None
    Recibe la clave primaria de un ChatMessage(INBOUND) y reenvía el cuerpo
    del mensaje a todos los contactos activos de la sección de la sala vía
    Twilio WhatsApp API, excluyendo al remitente original. Solo los contactos
    con alias configurado y sesión WhatsApp activa (ventana de 24h) reciben
    el broadcast.

purge_old_chat_messages() -> None
    Tarea periódica registrada en CELERY_BEAT_SCHEDULE.
    Elimina registros ChatMessage con más de 7 días.
    Elimina registros BreakdownConversationTurn de tickets RESOLVED
    cuyo updated_at supere los 7 días.
    Los registros BreakdownTicket nunca se eliminan.
"""

import logging
from datetime import timedelta

from celery import shared_task
from django.utils.timezone import now

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=10)
def broadcast_inbound_message(self, message_pk: int) -> None:
    """
    Relays a ChatMessage(INBOUND) to all active section members via WhatsApp.
    Excludes the original sender. Only sends to contacts with an alias and
    an active WhatsApp session (is_active=True, 24-hour window open).
    Retries up to 3 times with a 10-second delay on Twilio errors.
    ---
    Reenvía un ChatMessage(INBOUND) a todos los miembros activos de la sección
    vía WhatsApp. Excluye al remitente original. Solo envía a contactos con
    alias y sesión WhatsApp activa (is_active=True, ventana de 24h abierta).
    Reintenta hasta 3 veces con un retardo de 10 segundos en errores de Twilio.
    """
    from chat.models import ChatMessage
    from ivr_config.models import SectionContact
    from whatsapp.models import WhatsAppSession
    from whatsapp.services import WhatsAppChatService

    # Resolve message — resolución del mensaje.
    try:
        message = ChatMessage.objects.select_related(
            "room__section",
            "sender_contact",
        ).get(pk=message_pk)
    except ChatMessage.DoesNotExist:
        logger.error(
            "# [BROADCAST] ChatMessage pk=%s no encontrado. Tarea abortada.",
            message_pk,
        )
        return

    room    = message.room
    section = room.section

    if section is None:
        logger.warning(
            "# [BROADCAST] Sala pk=%s sin sección asociada. Tarea abortada.",
            room.pk,
        )
        return

    sender_contact = message.sender_contact

    # Resolve all contacts of the section with alias configured.
    # Resolver todos los contactos de la sección con alias configurado.
    # Broadcast to ALL section contacts with a phone number,
    # regardless of alias — contacts without alias receive the message
    # and are prompted to set their alias when they reply.
    # Broadcast a TODOS los contactos de la sección con número de teléfono,
    # independientemente del alias — los contactos sin alias reciben el mensaje
    # y se les pide que configuren su alias cuando respondan.
    section_contacts = (
        section.contacts
        .filter(phone_number__gt="")
        .exclude(pk=sender_contact.pk if sender_contact else None)
        .values_list("pk", "phone_number", "alias")
    )

    if not section_contacts:
        logger.info(
            "# [BROADCAST] Sin destinatarios para sala '%s'. Broadcast omitido.",
            room.name,
        )
        return

    # Resolve WhatsApp number for this company (To field).
    # Resolver el número WhatsApp de la empresa (campo To).
    from ivr_config.models import PhoneNumber
    phone_record = PhoneNumber.objects.filter(
        company=room.company,
        is_active=True,
        capabilities__in=[
            PhoneNumber.CAPABILITY_WHATSAPP,
            PhoneNumber.CAPABILITY_BOTH,
        ],
    ).first()

    if phone_record is None:
        logger.error(
            "# [BROADCAST] No hay PhoneNumber WhatsApp activo para empresa '%s'. "
            "Broadcast abortado.",
            room.company.name,
        )
        return

    from_number = phone_record.number
    sent        = 0
    skipped     = 0

    for contact_pk, phone_number, alias in section_contacts:
        # Check for active WhatsApp session (24-hour window).
        # Verificar sesión WhatsApp activa (ventana de 24h).
        has_active_session = WhatsAppSession.objects.filter(
            company=room.company,
            phone_number=phone_number,
            is_active=True,
        ).exists()

        if not has_active_session:
            logger.info(
                "# [BROADCAST] Contacto %s (%s) sin sesión activa. Omitido.",
                alias,
                phone_number,
            )
            skipped += 1
            continue

        try:
            WhatsAppChatService.send_reply(
                from_number=from_number,
                to_number=phone_number,
                reply_text=message.body,
            )
            sent += 1
            logger.info(
                "# [BROADCAST] Mensaje enviado a '%s' (%s).",
                alias,
                phone_number,
            )
        except Exception as exc:
            logger.error(
                "# [BROADCAST] Error enviando a '%s' (%s): %s",
                alias,
                phone_number,
                exc,
            )
            skipped += 1

    logger.info(
        "# [BROADCAST] Sala '%s' — enviados: %d, omitidos: %d.",
        room.name,
        sent,
        skipped,
    )


@shared_task
def purge_old_chat_messages() -> None:
    """
    Deletes ChatMessage records older than 7 days and
    BreakdownConversationTurn records from RESOLVED tickets
    whose updated_at is older than 7 days.
    BreakdownTicket records are never deleted.
    ---
    Elimina registros ChatMessage con más de 7 días y registros
    BreakdownConversationTurn de tickets RESOLVED cuyo updated_at
    supera los 7 días.
    Los registros BreakdownTicket nunca se eliminan.
    """
    from chat.models import ChatMessage, BreakdownConversationTurn, BreakdownTicket

    cutoff = now() - timedelta(days=7)

    # Purge old chat messages — eliminar mensajes de chat antiguos.
    deleted_messages, _ = ChatMessage.objects.filter(
        created_at__lt=cutoff,
    ).delete()
    logger.info(
        "# [PURGE] ChatMessage eliminados: %d (anteriores a %s).",
        deleted_messages,
        cutoff.strftime("%Y-%m-%d"),
    )

    # Purge conversation turns from old resolved tickets.
    # Eliminar turnos de conversación de tickets resueltos antiguos.
    old_resolved_tickets = BreakdownTicket.objects.filter(
        status=BreakdownTicket.STATUS_RESOLVED,
        updated_at__lt=cutoff,
    ).values_list("pk", flat=True)

    deleted_turns, _ = BreakdownConversationTurn.objects.filter(
        ticket__pk__in=list(old_resolved_tickets),
    ).delete()
    logger.info(
        "# [PURGE] BreakdownConversationTurn eliminados: %d.",
        deleted_turns,
    )
