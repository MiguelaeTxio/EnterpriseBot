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


@shared_task(bind=True, max_retries=3, default_retry_delay=10, queue='work_orders')
def broadcast_inbound_message(self, message_pk: int, room_name: str = "") -> None:
    """
    Relays a ChatMessage(INBOUND) to all section members via WhatsApp.
    Routing logic mirrors ChatSendView Step 6:
      - Contact has opt_out_broadcast=True           -> skip entirely.
      - Contact has no alias                         -> send chat_onboarding template.
      - Contact has alias but no active WA session   -> send chat_session_renewal
                                                        (fallback: chat_onboarding).
      - Contact has alias and active WA session      -> send free-text message
                                                        prefixed with "[{room_name}]".
    Excludes the original sender in all cases.
    Retries up to 3 times with a 10-second delay on Twilio errors.
    Enqueued in the 'work_orders' queue so the existing always-on worker
    consumes it without script changes.
    The room_name parameter is injected by _persist_and_broadcast and used
    to prefix the WhatsApp message so recipients can identify the originating
    room in their 1:1 bot conversation. The ChatMessage.body stored in the
    panel does NOT carry this prefix (panel users are already inside the room).
    ---
    Reenvía un ChatMessage(INBOUND) a todos los miembros de la sección via WhatsApp.
    La lógica de enrutamiento replica el Step 6 de ChatSendView:
      - Contacto con opt_out_broadcast=True           -> omitir completamente.
      - Contacto sin alias                            -> enviar template chat_onboarding.
      - Contacto con alias pero sin sesión WA activa  -> enviar chat_session_renewal
                                                          (fallback: chat_onboarding).
      - Contacto con alias y sesión WA activa         -> enviar mensaje libre
                                                          prefijado con "[{room_name}]".
    Excluye al remitente original en todos los casos.
    Reintenta hasta 3 veces con retardo de 10 segundos en errores de Twilio.
    Encolada en 'work_orders' para que el worker always-on existente la consuma
    sin necesidad de cambiar el script de arranque.
    El parámetro room_name es inyectado por _persist_and_broadcast y se usa para
    prefijar el mensaje WhatsApp de forma que los destinatarios identifiquen la
    sala de origen en su conversación 1:1 con el bot. El ChatMessage.body
    almacenado en el panel NO lleva este prefijo (los usuarios del panel ya
    están dentro de la sala).
    """
    from chat.models import ChatMessage
    from ivr_config.models import PhoneNumber
    from whatsapp.models import WhatsAppSession, WhatsAppTemplate
    from whatsapp.services import WhatsAppChatService

    # --- Resolve message --- Resolución del mensaje. ---
    try:
        message = ChatMessage.objects.select_related(
            "room__section",
            "room__company",
            "sender_contact",
        ).get(pk=message_pk)
    except ChatMessage.DoesNotExist:
        logger.error(
            "# [BROADCAST] ChatMessage pk=%s no encontrado. Tarea abortada.",
            message_pk,
        )
        return

    room    = message.room
    company = room.company

    sender_contact = message.sender_contact

    # --- Resolve WhatsApp sender number for this company. ---
    # --- Resolver número WhatsApp remitente de la empresa. ---
    phone_record = PhoneNumber.objects.filter(
        company=company,
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
            company.name,
        )
        return

    from_number = phone_record.number

    # --- Resolve templates once for all recipients. ---
    # --- Resolver templates una vez para todos los destinatarios. ---
    try:
        onboarding_template = WhatsAppTemplate.objects.get(
            company=company,
            name="chat_onboarding",
            is_active=True,
        )
    except WhatsAppTemplate.DoesNotExist:
        onboarding_template = None
        logger.warning(
            "# [BROADCAST] Template chat_onboarding no encontrado para empresa pk=%s.",
            company.pk,
        )

    try:
        renewal_template = WhatsAppTemplate.objects.get(
            company=company,
            name="chat_session_renewal",
            is_active=True,
        )
    except WhatsAppTemplate.DoesNotExist:
        renewal_template = None
        logger.info(
            "# [BROADCAST] Template chat_session_renewal no disponible para empresa pk=%s. "
            "Se usará chat_onboarding como fallback para contactos fuera de ventana.",
            company.pk,
        )

    # --- Collect recipients depending on room type. ---
    # SECTION rooms   -> all contacts of room.section.
    # BREAKDOWNS rooms -> all contacts of every section in breakdown_sections M2M.
    # The original sender is always excluded.
    # --- Obtener destinatarios según tipo de sala. ---
    # Salas SECTION     -> todos los contactos de room.section.
    # Salas BREAKDOWNS  -> todos los contactos de cada sección en breakdown_sections M2M.
    # El remitente original siempre queda excluido.
    from chat.models import ChatRoom as _ChatRoom
    from ivr_config.models import Contact as _Contact

    if room.room_type == _ChatRoom.ROOM_TYPE_BREAKDOWNS:
        # Aggregate contacts from all sections registered in breakdown_sections.
        # Agregar contactos de todas las secciones registradas en breakdown_sections.
        _breakdown_section_pks = list(
            room.breakdown_sections.values_list("pk", flat=True)
        )
        if not _breakdown_section_pks:
            logger.warning(
                "# [BROADCAST] Sala BREAKDOWNS pk=%s sin secciones en breakdown_sections. "
                "Broadcast omitido.",
                room.pk,
            )
            return
        section_contacts = list(
            _Contact.objects
            .select_related("company_user")
            .filter(
                company=company,
                sections__pk__in=_breakdown_section_pks,
                phone_number__gt="",
            )
            .exclude(pk=sender_contact.pk if sender_contact else None)
            .exclude(opt_out_broadcast=True)
            .distinct()
        )
        logger.info(
            "# [BROADCAST] Sala BREAKDOWNS '%s' — %d secciones, %d destinatarios.",
            room.name, len(_breakdown_section_pks), len(section_contacts),
        )
    else:
        # SECTION room — use the room's own section.
        # Sala SECTION — usar la sección propia de la sala.
        section = room.section
        if section is None:
            logger.warning(
                "# [BROADCAST] Sala SECTION pk=%s sin sección asociada. Tarea abortada.",
                room.pk,
            )
            return
        section_contacts = list(
            section.contacts
            .select_related("company_user")
            .filter(phone_number__gt="")
            .exclude(pk=sender_contact.pk if sender_contact else None)
            .exclude(opt_out_broadcast=True)
        )

    if not section_contacts:
        logger.info(
            "# [BROADCAST] Sin destinatarios para sala '%s'. Broadcast omitido.",
            room.name,
        )
        return

    sent      = 0
    skipped   = 0
    onboarded = 0
    renewed   = 0

    for contact in section_contacts:
        phone_number = contact.phone_number

        # Resolve canonical alias for this contact.
        # Resolver alias canónico del contacto.
        if contact.company_user_id and contact.company_user:
            _alias = contact.company_user.alias or ""
        else:
            _alias = contact.alias or ""

        # Check for active WhatsApp session (24-hour window).
        # Verificar sesión WhatsApp activa (ventana de 24h).
        has_active_session = WhatsAppSession.objects.filter(
            company=company,
            phone_number=phone_number,
            is_active=True,
        ).exists()

        # --- Case 1: No alias -> send chat_onboarding. ---
        # --- Caso 1: Sin alias -> enviar chat_onboarding. ---
        if not _alias:
            if onboarding_template is None:
                logger.warning(
                    "# [BROADCAST] Sin alias y sin template onboarding para %s. Omitido.",
                    phone_number,
                )
                skipped += 1
                continue
            try:
                WhatsAppChatService.send_template(
                    from_number=from_number,
                    to_number=phone_number,
                    content_sid=onboarding_template.content_sid,
                    content_variables={
                        "1": contact.name or phone_number,
                        "2": company.name,
                    },
                )
                onboarded += 1
                logger.info(
                    "# [BROADCAST] chat_onboarding enviado a %s (sin alias).",
                    phone_number,
                )
            except Exception as exc:
                logger.error(
                    "# [BROADCAST] Error enviando chat_onboarding a %s: %s",
                    phone_number, exc,
                )
                skipped += 1
            continue

        # --- Case 2: Alias present, no active session -> renewal or onboarding fallback. ---
        # --- Caso 2: Alias presente, sin sesión activa -> renewal o fallback onboarding. ---
        if not has_active_session:
            if renewal_template is not None:
                try:
                    WhatsAppChatService.send_template(
                        from_number=from_number,
                        to_number=phone_number,
                        content_sid=renewal_template.content_sid,
                        content_variables={
                            "1": _alias,
                            "2": company.name,
                            "3": "https://enterprisebot-miguelaetxio.pythonanywhere.com/panel/",
                        },
                    )
                    renewed += 1
                    logger.info(
                        "# [BROADCAST] chat_session_renewal enviado a '%s' (%s).",
                        _alias, phone_number,
                    )
                except Exception as exc:
                    logger.error(
                        "# [BROADCAST] Error enviando chat_session_renewal a '%s' (%s): %s",
                        _alias, phone_number, exc,
                    )
                    skipped += 1
            else:
                # Fallback: chat_onboarding when renewal template not yet approved.
                # Fallback: chat_onboarding cuando renewal template aun no aprobado.
                if onboarding_template is None:
                    logger.warning(
                        "# [BROADCAST] Sin renewal ni onboarding para '%s' (%s). Omitido.",
                        _alias, phone_number,
                    )
                    skipped += 1
                    continue
                try:
                    WhatsAppChatService.send_template(
                        from_number=from_number,
                        to_number=phone_number,
                        content_sid=onboarding_template.content_sid,
                        content_variables={
                            "1": _alias,
                            "2": company.name,
                        },
                    )
                    onboarded += 1
                    logger.info(
                        "# [BROADCAST] chat_onboarding (fallback) enviado a '%s' (%s).",
                        _alias, phone_number,
                    )
                except Exception as exc:
                    logger.error(
                        "# [BROADCAST] Error enviando onboarding fallback a '%s' (%s): %s",
                        _alias, phone_number, exc,
                    )
                    skipped += 1
            continue

        # --- Case 3: Alias present and active session -> send free-text message. ---
        # Prefix with "[{room_name}]" so the WhatsApp recipient knows which room
        # the message belongs to (panel users already see the room context).
        # --- Caso 3: Alias presente y sesión activa -> enviar mensaje libre. ---
        # Se prefija con "[{room_name}]" para que el destinatario WhatsApp sepa
        # de qué sala proviene el mensaje (los usuarios del panel ya tienen el contexto).
        _wa_body = f"[{room_name}] {message.body}" if room_name else message.body
        try:
            WhatsAppChatService.send_reply(
                from_number=from_number,
                to_number=phone_number,
                reply_text=_wa_body,
            )
            sent += 1
            logger.info(
                "# [BROADCAST] Mensaje libre enviado a '%s' (%s).",
                _alias, phone_number,
            )
        except Exception as exc:
            logger.error(
                "# [BROADCAST] Error enviando mensaje a '%s' (%s): %s",
                _alias, phone_number, exc,
            )
            skipped += 1

    logger.info(
        "# [BROADCAST] Sala '%s' — enviados: %d, onboarding: %d, renewal: %d, omitidos: %d.",
        room.name, sent, onboarded, renewed, skipped,
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
