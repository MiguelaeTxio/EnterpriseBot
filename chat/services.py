# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/chat/services.py
"""
Service layer for the chat module.
Implements the inbound message dispatcher, the alias collection flow,
the dynamic BREAKDOWNS routing and the Gemini breakdown agent.

dispatch_inbound_message(company, from_number, body, to_number) -> DispatchResult
    Entry point called from IncomingWhatsAppView before the existing Hito 4
    chatbot pipeline. Returns a DispatchResult indicating whether the message
    was consumed by the chat dispatcher or should continue to the Hito 4 flow.

_handle_alias_collection(contact, section, room, body, from_number, to_number) -> bool
    Manages the alias collection dialogue for contacts without an alias.

_handle_breakdown_routing(contact, section, body, from_number, to_number) -> bool
    Sends the breakdown_routing Quick Reply and stores routing state in DB.

_resolve_pending_routing(contact, section, room, breakdown_room, body, from_number, to_number) -> bool
    Processes the contact routing selection and routes the held message.

process_breakdown_turn(contact, body, room, to_number, from_number) -> None
    Gemini 2.5 Flash conversational agent for breakdown ticket collection.

_persist_and_broadcast(room, contact, body) -> None
    Creates the ChatMessage(INBOUND) and enqueues the Celery broadcast task.
---
Capa de servicios para el módulo de chat.
Implementa el despachador de mensajes entrantes, el flujo de recogida de alias,
el enrutamiento dinámico a BREAKDOWNS y el agente Gemini de averías.

dispatch_inbound_message(company, from_number, body, to_number) -> DispatchResult
    Punto de entrada llamado desde IncomingWhatsAppView antes del pipeline
    del chatbot del Hito 4.

_handle_alias_collection(contact, section, room, body, from_number, to_number) -> bool
    Gestiona el diálogo de recogida de alias para contactos sin alias.

_handle_breakdown_routing(contact, section, body, from_number, to_number) -> bool
    Envía el Quick Reply breakdown_routing y guarda el estado de enrutamiento.

_resolve_pending_routing(contact, section, room, breakdown_room, body, from_number, to_number) -> bool
    Procesa la selección de sala del contacto y enruta el mensaje retenido.

process_breakdown_turn(contact, body, room, to_number, from_number) -> None
    Agente conversacional Gemini 2.5 Flash para recogida de tickets de avería.

_persist_and_broadcast(room, contact, body) -> None
    Crea el ChatMessage(INBOUND) y encola la tarea Celery de broadcast.
"""

import datetime
import logging
from dataclasses import dataclass
from typing import Optional

from django.db import transaction
from django.utils import timezone

from ivr_config.models import Contact
from chat.models import ChatRoom, ChatMessage

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# ALIAS RESOLVER
# ---------------------------------------------------------------------------

def _resolve_alias(contact):
    # Returns the canonical alias for a contact.
    # Resolution order:
    #   1. CompanyUser.alias if the contact has a linked CompanyUser.
    #   2. Contact.alias for external contacts (WhatsApp only).
    # Returns empty string if no alias is configured.
    # ---
    # Devuelve el alias canónico para un contacto.
    # Orden de resolución:
    #   1. CompanyUser.alias si el contacto tiene CompanyUser vinculado.
    #   2. Contact.alias para contactos externos (solo WhatsApp).
    # Devuelve cadena vacía si no hay alias configurado.
    if contact.company_user_id and contact.company_user:
        return contact.company_user.alias or ''
    return contact.alias or ''


# ---------------------------------------------------------------------------
# DISPATCH RESULT — Immutable result object returned by dispatch_inbound_message.
# Objeto de resultado inmutable devuelto por dispatch_inbound_message.
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DispatchResult:
    """
    Result of the chat dispatcher evaluation for an inbound message.

    consumed  — True if the message was fully handled by the chat dispatcher
                and must NOT be passed to the Hito 4 chatbot pipeline.
    room      — ChatRoom the message was routed to, or None if not consumed.
    contact   — Contact resolved from the inbound phone number, or None.
    ---
    Resultado de la evaluación del despachador de chat para un mensaje entrante.

    consumed  — True si el mensaje fue gestionado completamente por el
                despachador de chat y NO debe pasarse al pipeline del Hito 4.
    room      — ChatRoom a la que se enrutó el mensaje, o None si no se consumió.
    contact   — Contact resuelto desde el número entrante, o None.
    """

    consumed : bool
    room     : Optional[object] = None
    contact  : Optional[object] = None


# ---------------------------------------------------------------------------
# ALIAS STATE — Persisted in Contact.alias_onboarding_step and
# Contact.alias_onboarding_proposed (DB fields, migration 0022).
# Estado de alias — persistido en Contact.alias_onboarding_step y
# Contact.alias_onboarding_proposed (campos en BD, migración 0022).
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# EMPLOYEE HELP REQUEST DETECTION
# Detección de solicitud de ayuda de empleado — quick-reply con enlace y contraseña.
# ---------------------------------------------------------------------------

# SID of the employee_help_menu Content Template (twilio/quick-reply).
# Two buttons: 'Acceder al panel' (help_panel_link) and
# 'Recordar contraseña' (help_password).
# SID de la plantilla Content employee_help_menu (twilio/quick-reply).
# Dos botones: 'Acceder al panel' (help_panel_link) y
# 'Recordar contraseña' (help_password).
_EMPLOYEE_HELP_TEMPLATE_SID: str = "HXe8c20c02d4cf4ab340924ed5e2b0ac6f"


def _is_employee_help_request(body: str) -> bool:
    """
    Returns True when the normalised body is exactly 'ayuda'.
    ---
    Devuelve True cuando el body normalizado es exactamente 'ayuda'.
    """
    return body.strip().lower() == "ayuda"


def _send_employee_help_menu(
    contact,
    from_number: str,
    to_number: str,
) -> None:
    """
    Sends the employee_help_menu quick-reply template to the employee.
    Only called when the inbound contact is linked to a CompanyUser.
    ---
    Envía la plantilla quick-reply employee_help_menu al empleado.
    Solo se llama cuando el contacto entrante tiene CompanyUser vinculado.
    """
    from whatsapp.services import WhatsAppChatService

    try:
        WhatsAppChatService.send_quick_reply(
            from_number=from_number,
            to_number=to_number,
            content_sid=_EMPLOYEE_HELP_TEMPLATE_SID,
            content_variables={},
        )
        logger.info(
            "# [CHAT DISPATCH] Menú de ayuda de empleado enviado a %s.",
            to_number,
        )
    except Exception as exc:
        logger.error(
            "# [CHAT DISPATCH] Error enviando menú de ayuda de empleado a %s: %s",
            to_number,
            exc,
        )


# ---------------------------------------------------------------------------
# PUBLIC ENTRY POINT
# Punto de entrada público.
# ---------------------------------------------------------------------------

def dispatch_inbound_message(
    company,
    from_number: str,
    body: str,
    to_number: str,
) -> DispatchResult:
    """
    Evaluates an inbound WhatsApp message against the chat dispatcher rules.
    Must be called as the very first step in IncomingWhatsAppView.post(),
    before any Hito 4 chatbot logic, once company has been resolved.

    Dispatch rules (evaluated in order):
      1. Resolve Contact by phone number within the company scope.
         If not found → not consumed (client flow, Hito 5).
      2. If Contact has no section assigned → not consumed (client, Hito 5).
      3. Resolve ChatRoom(SECTION) for the contact's section.
         If not found → not consumed (room not yet initialised).
      4. If Contact has no alias → handle alias collection dialogue.
         Message is consumed. The chatbot asks for the alias via WhatsApp.
      5. Contact has alias → persist ChatMessage(INBOUND) and broadcast.
         Message is consumed.
    ---
    Evalúa un mensaje entrante de WhatsApp contra las reglas del despachador.
    Debe llamarse como primer paso en IncomingWhatsAppView.post(), antes de
    cualquier lógica del chatbot del Hito 4, una vez resuelta la company.

    Reglas de despacho (evaluadas en orden):
      1. Resolver Contact por número de teléfono en el ámbito de la empresa.
         Si no se encuentra → no consumido (flujo cliente, Hito 5).
      2. Si Contact no tiene sección asignada → no consumido (cliente, Hito 5).
      3. Resolver ChatRoom(SECTION) para la sección del contacto.
         Si no se encuentra → no consumido (sala aún no inicializada).
      4. Si Contact no tiene alias → gestionar diálogo de recogida de alias.
         El mensaje es consumido. El chatbot pregunta el alias vía WhatsApp.
      5. Contact tiene alias → persistir ChatMessage(INBOUND) y broadcast.
         El mensaje es consumido.
    """
    # --- Rule 1: Resolve Contact by phone number. ---
    # --- Regla 1: Resolver Contact por número de teléfono. ---
    try:
        contact = Contact.objects.prefetch_related("sections").get(
            company=company,
            phone_number=from_number,
        )
    except Contact.DoesNotExist:
        logger.info(
            "# [CHAT DISPATCH] Contacto no encontrado para %s en empresa '%s'. "
            "Flujo Hito 5.",
            from_number,
            company.name,
        )
        return DispatchResult(consumed=False)
    except Contact.MultipleObjectsReturned:
        logger.warning(
            "# [CHAT DISPATCH] Múltiples contactos para %s en empresa '%s'. "
            "Flujo Hito 5.",
            from_number,
            company.name,
        )
        return DispatchResult(consumed=False)

    # --- Rule 2: Contact must have a section assigned. ---
    # --- Regla 2: El contacto debe tener sección asignada. ---
    section = contact.sections.filter(company=company).first()
    if section is None:
        logger.info(
            "# [CHAT DISPATCH] Contacto %s sin sección asignada. Flujo Hito 5.",
            from_number,
        )
        return DispatchResult(consumed=False)

    # --- Rule 3: Resolve the SECTION ChatRoom. ---
    # --- Regla 3: Resolver la ChatRoom de tipo SECTION. ---
    room = ChatRoom.objects.filter(
        company=company,
        section=section,
        room_type=ChatRoom.ROOM_TYPE_SECTION,
        is_active=True,
    ).first()

    if room is None:
        logger.warning(
            "# [CHAT DISPATCH] No existe sala SECTION para sección '%s' "
            "en empresa '%s'. Flujo Hito 5.",
            section.name,
            company.name,
        )
        return DispatchResult(consumed=False)

    # --- Rule 3b: Intercept employee help requests and button responses. ---
    # Fires only when the contact is linked to a CompanyUser (internal employee).
    # Three cases handled:
    #   1. body == 'ayuda'            -> send employee_help_menu quick-reply.
    #   2. body == 'help_panel_link'  -> send panel URL.
    #   3. body == 'help_password'    -> send username reminder.
    # --- Regla 3b: Interceptar solicitudes de ayuda de empleados y respuestas de botón. ---
    # Solo se activa cuando el contacto tiene CompanyUser vinculado.
    # Tres casos gestionados:
    #   1. body == 'ayuda'            -> envía quick-reply employee_help_menu.
    #   2. body == 'help_panel_link'  -> envía URL del panel.
    #   3. body == 'help_password'    -> envía recordatorio de usuario.
    if contact.company_user_id and contact.company_user:
        _body_norm = body.strip().lower()
        _cu = contact.company_user
        if _is_employee_help_request(body):
            _send_employee_help_menu(
                contact=contact,
                from_number=to_number,
                to_number=from_number,
            )
            logger.info(
                "# [CHAT DISPATCH] Menú de ayuda de empleado enviado a %s.",
                from_number,
            )
            return DispatchResult(consumed=True, room=room, contact=contact)

        if _body_norm == "acceder al panel":
            import os
            from whatsapp.services import WhatsAppChatService
            _panel_url = os.environ.get(
                "PANEL_URL", "https://enterprisebot-miguelaetxio.pythonanywhere.com/panel/"
            )
            try:
                WhatsAppChatService.send_reply(
                    from_number=to_number,
                    to_number=from_number,
                    reply_text=(
                        "📱 Accede al panel aquí:\n" + _panel_url
                    ),
                )
            except Exception as exc:
                logger.error(
                    "# [CHAT DISPATCH] Error enviando enlace de panel a %s: %s",
                    from_number, exc,
                )
            return DispatchResult(consumed=True, room=room, contact=contact)

        if _body_norm == "recordar contraseña":
            from whatsapp.services import WhatsAppChatService
            _username = _cu.user.username if _cu.user else ""
            try:
                WhatsAppChatService.send_reply(
                    from_number=to_number,
                    to_number=from_number,
                    reply_text=(
                        "🔑 Tu usuario es: " + _username + "\n"
                        "Si no recuerdas tu contraseña, contacta con tu administrador."
                    ),
                )
            except Exception as exc:
                logger.error(
                    "# [CHAT DISPATCH] Error enviando recordatorio de contraseña a %s: %s",
                    from_number, exc,
                )
            return DispatchResult(consumed=True, room=room, contact=contact)


    # --- Rule 4: Handle alias collection if alias is missing. ---
    # --- Regla 4: Gestionar recogida de alias si falta el alias. ---
    if not _resolve_alias(contact):
        consumed = _handle_alias_collection(
            contact=contact,
            section=section,
            room=room,
            body=body,
            from_number=from_number,
            to_number=to_number,
        )
        return DispatchResult(consumed=consumed, room=room, contact=contact)

    # --- Rule 5: Resolve BREAKDOWNS room, check breakdown access and pending routing. ---
    # The breakdown_routing Quick Reply is sent ONLY to contacts whose section
    # belongs to breakdown_sections. Contacts without breakdown access are routed
    # directly to their SECTION room without being asked.
    # --- Regla 5: Resolver sala BREAKDOWNS, comprobar acceso y enrutamiento pendiente. ---
    # El Quick Reply de enrutamiento se envía Únicamente a los contactos cuya
    # sección pertenece a breakdown_sections. Los contactos sin acceso a BREAKDOWNS
    # se enrutan directamente a su sala SECTION sin ser preguntados.
    breakdown_room = ChatRoom.objects.filter(
        company=company,
        room_type=ChatRoom.ROOM_TYPE_BREAKDOWNS,
        is_active=True,
    ).first()

    has_breakdown_access = (
        breakdown_room is not None
        and breakdown_room.breakdown_sections.filter(pk=section.pk).exists()
    )

    # --- Rule 5a: Contact is AWAITING_BREAKDOWN_CONFIRM — process routing response. ---
    # --- Regla 5a: Contacto en AWAITING_BREAKDOWN_CONFIRM — procesar respuesta. ---
    if contact.routing_state == contact.ROUTING_STATE_AWAITING_BREAKDOWN_CONFIRM:
        consumed = _resolve_breakdown_confirm(
            contact=contact,
            body=body,
            breakdown_room=breakdown_room,
            from_number=from_number,
            to_number=to_number,
        )
        return DispatchResult(consumed=consumed, room=room, contact=contact)

    # --- Rule 5a-bis: Breakdown in progress — route directly to Gemini agent. ---
    # --- Regla 5a-bis: Recogida de avería en curso — enrutar al agente Gemini. ---
    if contact.routing_state == contact.ROUTING_STATE_BREAKDOWN_IN_PROGRESS:
        if breakdown_room is not None:
            from chat.models import BreakdownTicket as _BT
            ticket = _BT.objects.filter(
                room=breakdown_room,
                contact=contact,
                status__in=[_BT.STATUS_OPEN, _BT.STATUS_IN_PROGRESS],
            ).order_by("-created_at").first()
            if ticket is not None:
                process_breakdown_turn(
                    contact=contact,
                    body=body,
                    room=breakdown_room,
                    to_number=to_number,
                    from_number=from_number,
                )
                return DispatchResult(consumed=True, room=breakdown_room, contact=contact)
        # Ticket not found — reset state and fall through.
        # Ticket no encontrado — resetear estado y continuar.
        contact.routing_state        = contact.ROUTING_STATE_NONE
        contact.pending_routing_body = ""
        contact.save(update_fields=["routing_state", "pending_routing_body"])

    # --- Rule 5b: Section has breakdown access — send routing Quick Reply. ---
    # Only for EXTERNAL contacts (choferes, clientes). Internal contacts
    # (workshop members) are routed directly to their SECTION room — they
    # have breakdown_sections membership only for IRC read access, not to
    # report breakdowns via WhatsApp.
    # --- Regla 5b: Sección con acceso a BREAKDOWNS — enviar Quick Reply. ---
    # Solo para contactos EXTERNOS (choferes, clientes). Los contactos internos
    # (miembros del taller) se enrutan directamente a su sala SECTION — su
    # membresía en breakdown_sections es solo para lectura IRC, no para
    # reportar averías por WhatsApp.
    if has_breakdown_access and not contact.is_internal:
        consumed = _handle_breakdown_confirm(
            contact=contact,
            body=body,
            from_number=from_number,
            to_number=to_number,
        )
        return DispatchResult(consumed=consumed, room=room, contact=contact)

    # --- Rule 6: No breakdown access — persist and broadcast directly to SECTION. ---
    # --- Regla 6: Sin acceso a BREAKDOWNS — persistir y broadcast directo a SECTION. ---
    _persist_and_broadcast(room=room, contact=contact, body=body)
    logger.info(
        "# [CHAT DISPATCH] Mensaje de '%s' (%s) enrutado directamente a sala '%s'.",
        _resolve_alias(contact),
        from_number,
        room.name,
    )
    return DispatchResult(consumed=True, room=room, contact=contact)


# ---------------------------------------------------------------------------
# PRIVATE HELPERS
# Auxiliares privados.
# ---------------------------------------------------------------------------

def _handle_alias_collection(
    contact: Contact,
    section,
    room,
    body: str,
    from_number: str,
    to_number: str,
) -> bool:
    """
    Manages the three-step alias collection dialogue.

    Step A — contact has no alias and is NOT in any state set:
      Send the alias request message via WhatsApp.
      Add from_number to _ALIAS_PENDING.
      Return True (message consumed).

    Step B — contact is in _ALIAS_PENDING:
      Interpret body as the proposed alias (stripped, max 50 chars).
      Ask for confirmation, explaining this will be their group identity.
      Move from_number from _ALIAS_PENDING to _ALIAS_CONFIRMING.
      Return True (message consumed).

    Step C — contact is in _ALIAS_CONFIRMING:
      If body is affirmative (SI / SÍ / S / YES / Y) — persist alias, confirm.
      Otherwise — interpret body as a new proposed alias, repeat confirmation.
      Return True (message consumed).
    ---
    Gestiona el diálogo de recogida de alias en tres pasos.

    Paso A — sin alias y sin estado previo:
      Envía la solicitud de nombre vía WhatsApp.
      Añade from_number a _ALIAS_PENDING.
      Devuelve True (mensaje consumido).

    Paso B — en _ALIAS_PENDING:
      Interpreta body como el alias propuesto (máx. 50 chars).
      Solicita confirmación explicando que será su identidad en el grupo.
      Mueve from_number de _ALIAS_PENDING a _ALIAS_CONFIRMING.
      Devuelve True (mensaje consumido).

    Paso C — en _ALIAS_CONFIRMING:
      Si body es afirmativo (SI / SÍ / S / YES / Y) — persiste alias, confirma.
      En caso contrario — interpreta body como nuevo alias propuesto, repite confirmación.
      Devuelve True (mensaje consumido).
    """
    from whatsapp.services import WhatsAppChatService

    # --- Step A: No state — request name. ---
    # --- Paso A: Sin estado — solicitar nombre. ---
    step = contact.alias_onboarding_step

    # --- Step A: No state — request name. ---
    # --- Paso A: Sin estado — solicitar nombre. ---
    if step == contact.ALIAS_STEP_NONE:
        # --- Step A: Internal contact with CompanyUser — propose panel username as alias. ---
        # Skip the open-ended name question and jump straight to confirmation
        # using the full name (or username) already registered in the panel.
        # ---
        # --- Paso A: Contacto interno con CompanyUser — proponer username del panel como alias. ---
        # Omitir la pregunta abierta de nombre y saltar directamente a la confirmación
        # usando el nombre completo (o username) ya registrado en el panel.
        if contact.company_user_id and contact.company_user:
            _cu = contact.company_user
            _proposed = (
                _cu.user.get_full_name().strip()
                or _cu.user.username.strip()
            )
            contact.alias_onboarding_step     = contact.ALIAS_STEP_CONFIRMING
            contact.alias_onboarding_proposed = _proposed
            contact.save(update_fields=["alias_onboarding_step", "alias_onboarding_proposed"])

            # Attempt quick-reply confirmation via alias_confirmation template.
            # Fall back to plain text if template not found or API fails.
            # Intentar confirmación con botones vía template alias_confirmation.
            # Caer a texto plano si el template no se encuentra o la API falla.
            from whatsapp.models import WhatsAppTemplate
            _sent = False
            try:
                _alias_template = WhatsAppTemplate.objects.get(
                    company=contact.company,
                    name="alias_confirmation",
                    is_active=True,
                )
                WhatsAppChatService.send_quick_reply(
                    from_number=to_number,
                    to_number=from_number,
                    content_sid=_alias_template.content_sid,
                    content_variables={"1": _proposed},
                )
                _sent = True
                logger.info(
                    "# [CHAT DISPATCH] Confirmación de alias con username propuesto enviada "
                    "a contacto interno %s: '%s'.",
                    from_number, _proposed,
                )
            except WhatsAppTemplate.DoesNotExist:
                logger.warning(
                    "# [CHAT DISPATCH] Template alias_confirmation no encontrado "
                    "para empresa pk=%s — fallback a texto plano.",
                    contact.company_id,
                )
            except Exception as exc:
                logger.error(
                    "# [CHAT DISPATCH] Error enviando confirmación de alias interno a %s: %s",
                    from_number, exc,
                )
            if not _sent:
                try:
                    WhatsAppChatService.send_reply(
                        from_number=to_number,
                        to_number=from_number,
                        reply_text=(
                            f"Hemos recibido tu nombre: *{_proposed}*. "
                            "Este será tu alias en el chat de grupo de tu sección. "
                            "Confirmas que quieres usar este nombre? "
                            "Responde \"Sí, usar este nombre\" o \"Cambiar nombre\"."
                        ),
                    )
                except Exception as exc:
                    logger.error(
                        "# [CHAT DISPATCH] Error enviando fallback de alias interno a %s: %s",
                        from_number, exc,
                    )
            return True

        # --- Step A: External contact or operator without CompanyUser — ask for name. ---
        # --- Paso A: Contacto externo u operario sin CompanyUser — preguntar nombre. ---
        contact.alias_onboarding_step = contact.ALIAS_STEP_PENDING
        contact.save(update_fields=["alias_onboarding_step"])
        alias_request = (
            "Para participar en el chat de grupo de tu seccion necesito saber "
            "como quieres que te identifiquen los demas companeros.\n\n"
            "Con que nombre o apodo quieres aparecer en el chat?"
        )
        try:
            WhatsAppChatService.send_reply(
                from_number=to_number,
                to_number=from_number,
                reply_text=alias_request,
            )
            logger.info(
                "# [CHAT DISPATCH] Solicitud de alias enviada a %s.",
                from_number,
            )
        except Exception as exc:
            logger.error(
                "# [CHAT DISPATCH] Error enviando solicitud de alias a %s: %s",
                from_number,
                exc,
            )
        return True

    # --- Step B: Pending — receive proposed name, ask for confirmation. ---
    # --- Paso B: Pendiente — recibir nombre propuesto, pedir confirmacion. ---
    if step == contact.ALIAS_STEP_PENDING:
        proposed_alias = body.strip()[:50]
        if not proposed_alias:
            try:
                WhatsAppChatService.send_reply(
                    from_number=to_number,
                    to_number=from_number,
                    reply_text=(
                        "El nombre no puede estar vacio. "
                        "Por favor, indicame el nombre o apodo con el que quieres aparecer."
                    ),
                )
            except Exception as exc:
                logger.error(
                    "# [CHAT DISPATCH] Error enviando re-solicitud de alias a %s: %s",
                    from_number,
                    exc,
                )
            return True

        contact.alias_onboarding_step     = contact.ALIAS_STEP_CONFIRMING
        contact.alias_onboarding_proposed = proposed_alias
        contact.save(update_fields=["alias_onboarding_step", "alias_onboarding_proposed"])

        # Attempt to send quick-reply buttons via the pre-registered
        # alias_confirmation Content Template (HX...). If the template is not
        # found in DB or the Twilio API call fails, fall back to a plain-text
        # reply so the onboarding flow is never silently broken.
        # Intentar enviar botones de respuesta rápida vía el Content Template
        # alias_confirmation pre-registrado (HX...). Si el template no se
        # encuentra en BD o la llamada a la API de Twilio falla, caer a un
        # reply de texto plano para que el flujo de onboarding nunca se rompa
        # silenciosamente.
        from whatsapp.models import WhatsAppTemplate

        _quick_reply_sent = False
        try:
            _alias_template = WhatsAppTemplate.objects.get(
                company=contact.company,
                name="alias_confirmation",
                is_active=True,
            )
            WhatsAppChatService.send_quick_reply(
                from_number=to_number,
                to_number=from_number,
                content_sid=_alias_template.content_sid,
                content_variables={"1": proposed_alias},
            )
            _quick_reply_sent = True
            logger.info(
                "# [CHAT DISPATCH] Confirmacion de alias con botones enviada a %s para alias '%s'.",
                from_number,
                proposed_alias,
            )
        except WhatsAppTemplate.DoesNotExist:
            logger.error(
                "# [CHAT DISPATCH] Template alias_confirmation no encontrado en BD "
                "para empresa pk=%s — activando fallback a texto plano.",
                contact.company_id,
            )
        except Exception as exc:
            logger.error(
                "# [CHAT DISPATCH] Error enviando confirmacion de alias con botones "
                "a %s — activando fallback a texto plano. Error: %s",
                from_number,
                exc,
            )

        if not _quick_reply_sent:
            # --- Fallback: plain-text confirmation with explicit instruction. ---
            # --- Fallback: confirmacion en texto plano con instruccion explicita. ---
            fallback_confirmation = (
                f"Hemos recibido tu nombre: *{proposed_alias}*. "
                "Este sera tu alias en el chat de grupo de tu seccion. "
                "Confirmas que quieres usar este nombre?\n\n"
                "Responde con una de las siguientes opciones: "
                "\"Si, usar este nombre\" / \"Cambiar nombre\""
            )
            try:
                WhatsAppChatService.send_reply(
                    from_number=to_number,
                    to_number=from_number,
                    reply_text=fallback_confirmation,
                )
                logger.info(
                    "# [CHAT DISPATCH] Fallback de texto plano enviado a %s para alias '%s'.",
                    from_number,
                    proposed_alias,
                )
            except Exception as exc:
                logger.error(
                    "# [CHAT DISPATCH] Error enviando fallback de confirmacion a %s: %s",
                    from_number,
                    exc,
                )
        return True

    # --- Step C: Confirming — save alias or re-ask. ---
    # --- Paso C: Confirmando — guardar alias o volver a pedir. ---
    if step == contact.ALIAS_STEP_CONFIRMING:
        proposed_alias = contact.alias_onboarding_proposed
        # Detect button press or free-text affirmative.
        # Detectar pulsación de botón o texto libre afirmativo.
        _body_upper = body.strip().upper()
        affirmative = (
            _body_upper in ("SI", "SÍ", "S", "YES", "Y")
            or body.strip().lower() == "si, usar este nombre"
        )

        if affirmative:
            # Persist alias and provision CompanyUser if not yet registered.
            # Persistir alias y provisionar CompanyUser si aun no esta registrado.
            _provision_company_user(
                contact=contact,
                section=section,
                proposed_alias=proposed_alias,
                to_number=to_number,
                from_number=from_number,
            )
            contact.alias_onboarding_step     = contact.ALIAS_STEP_NONE
            contact.alias_onboarding_proposed = ""
            contact.save(update_fields=["alias_onboarding_step", "alias_onboarding_proposed"])

            final_confirmation = (
                f"Perfecto, a partir de ahora aparecerás como *{proposed_alias}* "
                "en el chat de grupo de tu seccion. "
                "Ya puedes escribir tus mensajes con normalidad."
            )
            try:
                WhatsAppChatService.send_reply(
                    from_number=to_number,
                    to_number=from_number,
                    reply_text=final_confirmation,
                )
                logger.info(
                    "# [CHAT DISPATCH] Alias '%s' confirmado y registrado para contacto pk=%s.",
                    proposed_alias,
                    contact.pk,
                )
            except Exception as exc:
                logger.error(
                    "# [CHAT DISPATCH] Error enviando confirmacion final a %s: %s",
                    from_number,
                    exc,
                )

            # Relay the last pending OUTBOUND message from the room so the
            # contact receives the message that triggered the onboarding.
            # The body already carries the canonical format "{alias}: {body}"
            # — relay it as-is, no additional prefix needed.
            # Reenviar el ultimo mensaje OUTBOUND pendiente de la sala para
            # que el contacto reciba el mensaje que origino el onboarding.
            # El body ya lleva el formato canonico "{alias}: {body}"
            # — se reenvía tal cual, sin prefijo adicional.
            try:
                last_outbound = ChatMessage.objects.filter(
                    room=room,
                    direction=ChatMessage.DIRECTION_OUTBOUND,
                ).order_by("-created_at").first()

                if last_outbound and last_outbound.body:
                    WhatsAppChatService.send_reply(
                        from_number=to_number,
                        to_number=from_number,
                        reply_text=last_outbound.body,
                    )
                    logger.info(
                        "# [CHAT DISPATCH] Mensaje pendiente reenviado a '%s' (%s): '%s'.",
                        proposed_alias,
                        from_number,
                        last_outbound.body,
                    )
            except Exception as exc:
                logger.error(
                    "# [CHAT DISPATCH] Error reenviando mensaje pendiente a %s: %s",
                    from_number,
                    exc,
                )
        else:
            # Interpret body as a new proposed alias.
            # Interpretar body como nuevo alias propuesto.
            new_alias = body.strip()[:50]
            if not new_alias:
                try:
                    WhatsAppChatService.send_reply(
                        from_number=to_number,
                        to_number=from_number,
                        reply_text=(
                            "El nombre no puede estar vacio. "
                            "Por favor, escribe el nombre con el que quieres aparecer."
                        ),
                    )
                except Exception as exc:
                    logger.error(
                        "# [CHAT DISPATCH] Error enviando re-solicitud de alias a %s: %s",
                        from_number,
                        exc,
                    )
                return True

            contact.alias_onboarding_proposed = new_alias
            contact.save(update_fields=["alias_onboarding_proposed"])

            # Attempt quick-reply re-confirmation via alias_confirmation template.
            # Fall back to plain text if template not found or API fails.
            # Intentar re-confirmacion con botones vía template alias_confirmation.
            # Caer a texto plano si el template no se encuentra o la API falla.
            from whatsapp.models import WhatsAppTemplate

            _reconfirm_sent = False
            try:
                _alias_template = WhatsAppTemplate.objects.get(
                    company=contact.company,
                    name="alias_confirmation",
                    is_active=True,
                )
                WhatsAppChatService.send_quick_reply(
                    from_number=to_number,
                    to_number=from_number,
                    content_sid=_alias_template.content_sid,
                    content_variables={"1": new_alias},
                )
                _reconfirm_sent = True
                logger.info(
                    "# [CHAT DISPATCH] Re-confirmacion de alias con botones enviada a %s para alias '%s'.",
                    from_number,
                    new_alias,
                )
            except WhatsAppTemplate.DoesNotExist:
                logger.error(
                    "# [CHAT DISPATCH] Template alias_confirmation no encontrado en BD "
                    "para empresa pk=%s — activando fallback a texto plano.",
                    contact.company_id,
                )
            except Exception as exc:
                logger.error(
                    "# [CHAT DISPATCH] Error enviando re-confirmacion con botones "
                    "a %s — activando fallback a texto plano. Error: %s",
                    from_number,
                    exc,
                )

            if not _reconfirm_sent:
                # --- Fallback: plain-text re-confirmation. ---
                # --- Fallback: re-confirmacion en texto plano. ---
                fallback_reconfirmation = (
                    f"De acuerdo, usamos *{new_alias}* como tu nombre en el grupo?\n\n"
                    "Responde con una de las siguientes opciones: "
                    "\"Si, usar este nombre\" / \"Cambiar nombre\""
                )
                try:
                    WhatsAppChatService.send_reply(
                        from_number=to_number,
                        to_number=from_number,
                        reply_text=fallback_reconfirmation,
                    )
                    logger.info(
                        "# [CHAT DISPATCH] Fallback de re-confirmacion enviado a %s para alias '%s'.",
                        from_number,
                        new_alias,
                    )
                except Exception as exc:
                    logger.error(
                        "# [CHAT DISPATCH] Error enviando fallback de re-confirmacion a %s: %s",
                        from_number,
                        exc,
                    )

    return True


# ---------------------------------------------------------------------------
# _PROVISION_COMPANY_USER
# Creates or updates a CompanyUser for the given contact after alias confirmation.
# Crea o actualiza un CompanyUser para el contacto tras la confirmación del alias.
# ---------------------------------------------------------------------------

def _provision_company_user(
    contact,
    section,
    proposed_alias: str,
    to_number: str,
    from_number: str,
) -> None:
    """
    Provisions or updates the CompanyUser associated with the given contact
    after the three-step alias confirmation dialogue completes successfully.

    Branch A — contact already has a linked CompanyUser:
        Updates CompanyUser.alias only. No new User or CompanyUser is created.

    Branch B — contact has no linked CompanyUser:
        1. Generates a slug-based username from proposed_alias (lowercase).
           Appends a numeric suffix if the username is already taken in auth.User.
        2. Creates auth.User with password "1234" (must_change_password=True).
        3. Creates CompanyUser linked to the new User with section.default_role.
        4. Links contact.company_user = new CompanyUser.
           Clears contact.alias (canonical alias is now CompanyUser.alias).
           Sets contact.is_internal = True.
        5. Sends WhatsApp credentials message to the contact.
    ---
    Provisiona o actualiza el CompanyUser asociado al contacto tras completarse
    con éxito el diálogo de confirmación de alias en tres pasos.

    Rama A — el contacto ya tiene CompanyUser vinculado:
        Actualiza únicamente CompanyUser.alias. No se crea ningún User ni CompanyUser.

    Rama B — el contacto no tiene CompanyUser vinculado:
        1. Genera un username basado en slug del alias propuesto (minúsculas).
           Añade sufijo numérico si el username ya existe en auth.User.
        2. Crea auth.User con contraseña "1234" (must_change_password=True).
        3. Crea CompanyUser vinculado al nuevo User con section.default_role.
        4. Vincula contact.company_user = nuevo CompanyUser.
           Vacía contact.alias (el alias canónico es ahora CompanyUser.alias).
           Establece contact.is_internal = True.
        5. Envía mensaje WhatsApp al contacto con sus credenciales de acceso.
    """
    from django.contrib.auth import get_user_model
    from django.utils.text import slugify
    from ivr_config.models import CompanyUser
    from whatsapp.services import WhatsAppChatService

    User = get_user_model()

    # --- Branch A: CompanyUser already linked — update alias only. ---
    # If must_change_password is True, it is the first alias setup after the
    # supervisor created the account from the panel. Send credentials so the
    # worker knows how to log in and understands the difference between their
    # panel username and their chat alias.
    # ---
    # --- Rama A: CompanyUser ya vinculado — actualizar solo el alias. ---
    # Si must_change_password es True, es la primera configuracion de alias
    # tras la creacion de la cuenta por el supervisor desde el panel.
    if contact.company_user_id and contact.company_user:
        cu       = contact.company_user
        cu.alias = proposed_alias
        # Force is_active=True for WORKSHOP/DRIVER — panel creation defaults to False.
        # Forzar is_active=True para WORKSHOP/DRIVER — la creacion desde panel usa False por defecto.
        _fields_to_save = ["alias"]
        if cu.role in ("WORKSHOP", "DRIVER") and not cu.is_active:
            cu.is_active = True
            _fields_to_save.append("is_active")
        cu.save(update_fields=_fields_to_save)
        logger.info(
            "# [PROVISION] Alias actualizado para CompanyUser pk=%s: '%s'.",
            cu.pk,
            proposed_alias,
        )
        if cu.must_change_password:
            _panel_username = cu.user.username
            _bienvenido = (
                "✅ ¡Bienvenido/a a la plataforma de "
                + cu.company.name + ", " + proposed_alias + "!\n\n"
                + "🔐 *Acceso al panel de gestión:*\n"
                "https://enterprisebot-miguelaetxio.pythonanywhere.com/panel/login/\n\n"
                + "👤 *Usuario del panel:* " + _panel_username + "\n"
                + "🔑 *Contraseña inicial:* 1234\n"
                "_(Te pediremos que la cambies en tu primer inicio de sesión.)_\n\n"
                + "💬 *Tu alias en el chat:* " + proposed_alias + "\n"
                "_(Este es tu nombre visible en las salas de chat, "
                "distinto al usuario del panel.)_"
            )
            try:
                WhatsAppChatService.send_reply(
                    from_number=to_number,
                    to_number=from_number,
                    reply_text=_bienvenido,
                )
                logger.info(
                    "# [PROVISION] Credenciales enviadas (Rama A) a %s para username '%s'.",
                    from_number,
                    _panel_username,
                )
            except Exception as exc:
                logger.error(
                    "# [PROVISION] Error enviando credenciales (Rama A) a %s: %s",
                    from_number,
                    exc,
                )
        return

    # --- Branch B: No CompanyUser — create User, CompanyUser and link. ---
    # --- Rama B: Sin CompanyUser — crear User, CompanyUser y vincular. ---

    # Step B-1: Generate a unique slug-based username.
    # Paso B-1: Generar un username único basado en slug.
    base_username = slugify(proposed_alias).lower() or "usuario"
    username      = base_username
    suffix        = 1
    while User.objects.filter(username=username).exists():
        username = f"{base_username}{suffix}"
        suffix  += 1

    # Step B-2: Create auth.User with a temporary password.
    # Paso B-2: Crear auth.User con contraseña temporal.
    new_user = User(username=username)
    new_user.set_password("1234")
    new_user.save()
    logger.info(
        "# [PROVISION] auth.User creado: username='%s' pk=%s.",
        username,
        new_user.pk,
    )

    # Step B-3: Create CompanyUser with section role and alias.
    # Paso B-3: Crear CompanyUser con el rol de sección y el alias.
    new_company_user = CompanyUser.objects.create(
        company=section.company,
        user=new_user,
        role=section.default_role,
        alias=proposed_alias,
        must_change_password=True,
        is_active=True,
    )
    logger.info(
        "# [PROVISION] CompanyUser creado: pk=%s rol='%s'.",
        new_company_user.pk,
        section.default_role,
    )

    # Step B-4: Link contact to new CompanyUser and clear contact.alias.
    # Paso B-4: Vincular contacto al nuevo CompanyUser y vaciar contact.alias.
    contact.company_user = new_company_user
    contact.alias        = ""
    contact.is_internal  = True
    contact.save(update_fields=["company_user", "alias", "is_internal"])
    logger.info(
        "# [PROVISION] Contacto pk=%s vinculado a CompanyUser pk=%s.",
        contact.pk,
        new_company_user.pk,
    )

    # Step B-5: Send credentials via WhatsApp.
    # Distinguishes panel username from chat alias clearly.
    # Paso B-5: Enviar credenciales via WhatsApp.
    # Distingue claramente el usuario del panel del alias del chat.
    credentials_message = (
        "✅ ¡Bienvenido/a a la plataforma de "
        + section.company.name + ", " + proposed_alias + "!\n\n"
        + "🔐 *Acceso al panel de gestión:*\n"
        "https://enterprisebot-miguelaetxio.pythonanywhere.com/panel/login/\n\n"
        + "👤 *Usuario del panel:* " + username + "\n"
        + "🔑 *Contraseña inicial:* 1234\n"
        "_(Te pediremos que la cambies en tu primer inicio de sesión.)_\n\n"
        + "💬 *Tu alias en el chat:* " + proposed_alias + "\n"
        "_(Este es tu nombre visible en las salas de chat, "
        "distinto al usuario del panel.)_"
    )
    try:
        WhatsAppChatService.send_reply(
            from_number=to_number,
            to_number=from_number,
            reply_text=credentials_message,
        )
        logger.info(
            "# [PROVISION] Credenciales enviadas a %s para username '%s'.",
            from_number,
            username,
        )
    except Exception as exc:
        logger.error(
            "# [PROVISION] Error enviando credenciales a %s: %s",
            from_number,
            exc,
        )


# ---------------------------------------------------------------------------
# _HANDLE_BREAKDOWN_CONFIRM
# ---------------------------------------------------------------------------

def _handle_breakdown_confirm(
    contact,
    body: str,
    from_number: str,
    to_number: str,
) -> bool:
    """
    Sends the breakdown confirmation Quick Reply to the contact and stores
    routing_state=AWAITING_BREAKDOWN_CONFIRM and pending_routing_body in DB.
    Returns True (message consumed).
    ---
    Envia el Quick Reply de confirmacion de averia al contacto y guarda
    routing_state=AWAITING_BREAKDOWN_CONFIRM y pending_routing_body en BD.
    Devuelve True (mensaje consumido).
    """
    from whatsapp.services import WhatsAppChatService

    contact.routing_state        = contact.ROUTING_STATE_AWAITING_BREAKDOWN_CONFIRM
    contact.pending_routing_body = body
    contact.save(update_fields=["routing_state", "pending_routing_body"])

    _BREAKDOWN_CONFIRM_SID = "HX71d736523adabbd1e6d0fdf8acc2e99c"

    try:
        WhatsAppChatService.send_quick_reply(
            from_number=to_number,
            to_number=from_number,
            content_sid=_BREAKDOWN_CONFIRM_SID,
            content_variables={},
        )
        logger.info(
            "# [CHAT DISPATCH] Quick Reply de confirmacion de averia enviado a %s.",
            from_number,
        )
    except Exception as exc:
        logger.error(
            "# [CHAT DISPATCH] Error enviando Quick Reply de confirmacion a %s: %s",
            from_number, exc,
        )
        contact.routing_state        = contact.ROUTING_STATE_NONE
        contact.pending_routing_body = ""
        contact.save(update_fields=["routing_state", "pending_routing_body"])

    return True


# ---------------------------------------------------------------------------
# _RESOLVE_BREAKDOWN_CONFIRM
# ---------------------------------------------------------------------------

def _resolve_breakdown_confirm(
    contact,
    body: str,
    breakdown_room,
    from_number: str,
    to_number: str,
) -> bool:
    """
    Processes the contact Yes/No response to the breakdown confirmation Quick Reply.
    Yes   - activates Gemini breakdown agent.
    No    - informs contact the channel is for breakdowns only, resets state.
    Other - re-sends the Quick Reply.
    Returns True (message consumed).
    ---
    Procesa la respuesta Si/No del contacto al Quick Reply de confirmacion de averia.
    Si    - activa el agente Gemini de averias.
    No    - informa al contacto que el canal es exclusivo de averias, resetea estado.
    Otro  - reenvía el Quick Reply.
    Devuelve True (mensaje consumido).
    """
    from whatsapp.services import WhatsAppChatService

    body_norm    = body.strip().lower()
    pending_body = contact.pending_routing_body

    import unicodedata as _ud
    body_plain = "".join(
        c for c in _ud.normalize("NFD", body_norm)
        if _ud.category(c) != "Mn"
    )
    affirmative = (
        body_plain in ("opt_in", "si", "s", "yes", "y", "si, quiero recibirlos")
        or body_plain.startswith("si,")
        or body_plain.startswith("si ")
        or body_plain == "si"
    )
    negative = (
        body_plain in ("opt_out", "no", "n", "no, gracias")
        or body_plain.startswith("no,")
        or body_plain.startswith("no ")
        or body_plain == "no"
    )

    if affirmative:
        contact.routing_state        = contact.ROUTING_STATE_BREAKDOWN_IN_PROGRESS
        contact.pending_routing_body = ""
        contact.save(update_fields=["routing_state", "pending_routing_body"])
        if breakdown_room is not None:
            _persist_inbound_only(room=breakdown_room, contact=contact, body=pending_body)
            try:
                WhatsAppChatService.send_reply(
                    from_number=to_number,
                    to_number=from_number,
                    reply_text=(
                        "Vamos a registrar la averia. "
                        "Describeme el problema con el mayor detalle posible."
                    ),
                )
            except Exception as exc:
                logger.error(
                    "# [CHAT DISPATCH] Error enviando confirmacion de inicio de averia a %s: %s",
                    from_number, exc,
                )
            process_breakdown_turn(
                contact=contact,
                body=pending_body,
                room=breakdown_room,
                to_number=to_number,
                from_number=from_number,
            )
        logger.info(
            "# [CHAT DISPATCH] Averia confirmada para %s - agente Gemini activado.",
            from_number,
        )
        return True

    if negative:
        contact.routing_state        = contact.ROUTING_STATE_NONE
        contact.pending_routing_body = ""
        contact.save(update_fields=["routing_state", "pending_routing_body"])
        try:
            WhatsAppChatService.send_reply(
                from_number=to_number,
                to_number=from_number,
                reply_text=(
                    "Este canal es exclusivo para el reporte de averias. "
                    "Si necesitas comunicar una averia, envia cualquier mensaje y te guiare."
                ),
            )
        except Exception as exc:
            logger.error(
                "# [CHAT DISPATCH] Error enviando mensaje de canal exclusivo a %s: %s",
                from_number, exc,
            )
        logger.info(
            "# [CHAT DISPATCH] Averia denegada por %s - informado canal exclusivo.",
            from_number,
        )
        return True

    _BREAKDOWN_CONFIRM_SID = "HX71d736523adabbd1e6d0fdf8acc2e99c"
    logger.info(
        "# [CHAT DISPATCH] Respuesta de confirmacion no reconocida de %s: %r.",
        from_number, body[:60],
    )
    try:
        WhatsAppChatService.send_quick_reply(
            from_number=to_number,
            to_number=from_number,
            content_sid=_BREAKDOWN_CONFIRM_SID,
            content_variables={},
        )
    except Exception as exc:
        logger.error(
            "# [CHAT DISPATCH] Error reenviando Quick Reply de confirmacion a %s: %s",
            from_number, exc,
        )
    return True


# ---------------------------------------------------------------------------
# PROCESS_BREAKDOWN_TURN
# ---------------------------------------------------------------------------

def process_breakdown_turn(
    contact: Contact,
    body: str,
    room,
    to_number: str,
    from_number: str,
) -> None:
    """
    Gemini 2.5 Flash conversational agent for breakdown ticket collection.
    Collects machine, fault, urgency and location field by field.
    Persists BreakdownConversationTurn records and finalises the ticket
    when [TICKET_COMPLETE:{...}] marker is detected in the Gemini reply.
    ---
    Agente conversacional Gemini 2.5 Flash para recogida de tickets de averia.
    Recoge maquina, fallo, urgencia y ubicacion campo a campo.
    Persiste turnos BreakdownConversationTurn y finaliza el ticket cuando
    detecta el marcador [TICKET_COMPLETE:{...}] en la respuesta de Gemini.
    """
    import json as _json
    import re   as _re
    from chat.models import BreakdownTicket, BreakdownConversationTurn
    from whatsapp.services import WhatsAppChatService, _build_genai_client
    from fleet.models import MachineAsset

    company = contact.company

    # Resolve or create open ticket.
    ticket = BreakdownTicket.objects.filter(
        room=room,
        contact=contact,
        status__in=[BreakdownTicket.STATUS_OPEN, BreakdownTicket.STATUS_IN_PROGRESS],
    ).order_by("-created_at").first()

    if ticket is None:
        section = contact.sections.filter(company=company).first()
        ticket  = BreakdownTicket.objects.create(
            room=room,
            contact=contact,
            section=section,
            status=BreakdownTicket.STATUS_OPEN,
        )
        logger.info(
            "# [BREAKDOWN] Nuevo BreakdownTicket pk=%s creado para contacto pk=%s.",
            ticket.pk, contact.pk,
        )

    # Persist USER turn.
    BreakdownConversationTurn.objects.create(
        ticket=ticket,
        role=BreakdownConversationTurn.ROLE_USER,
        content=body,
    )

    # Reconstruct history.
    turns = list(
        BreakdownConversationTurn.objects.filter(ticket=ticket).order_by("created_at")
    )
    history_parts = [
        {
            "role":  "user" if t.role == BreakdownConversationTurn.ROLE_USER else "model",
            "parts": [{"text": t.content}],
        }
        for t in turns
    ]

    # Build system prompt — no catalogue passed; validation is done server-side.
    # System prompt sin catálogo — la validación se hace en el servidor.
    system_prompt = (
        "Eres un asistente de gestion de averias de " + company.name + ". "
        "Tu mision es recoger los siguientes datos campo a campo mediante dialogo natural: "
        "1) Codigo de la maquina afectada (pide el codigo exacto tal como aparece en la maquina). "
        "2) Descripcion del problema o sintoma. "
        "3) Urgencia (CRITICAL/HIGH/MEDIUM/LOW). "
        "4) Ubicacion actual de la maquina. "
        "Reglas: pregunta UN campo a la vez, maximo 2 frases por turno. "
        "Acepta el codigo de maquina tal como lo escriba el contacto, sin validar. "
        "Cuando tengas los 4 campos responde EXCLUSIVAMENTE con: "
        "[TICKET_COMPLETE:{\"machine_raw\": \"X\", \"fault_summary\": \"X\", "
        "\"urgency\": \"HIGH|MEDIUM|LOW|CRITICAL\", \"location\": \"X\"}] "
        "sin ningun texto adicional. Si el contacto cancela responde: CANCELADO."
    )

    # Call Gemini.
    try:
        genai_client = _build_genai_client()
        response     = genai_client.models.generate_content(
            model="gemini-2.5-flash",
            contents=history_parts,
            config={"system_instruction": system_prompt, "temperature": 0.3},
        )
        reply_text = response.text.strip()
    except Exception as exc:
        logger.error(
            "# [BREAKDOWN] Error llamando a Gemini para ticket pk=%s: %s",
            ticket.pk, exc,
        )
        try:
            WhatsAppChatService.send_reply(
                from_number=to_number,
                to_number=from_number,
                reply_text=(
                    "Lo sentimos, ha habido un error procesando tu averia. "
                    "Por favor, intentalo de nuevo en unos instantes."
                ),
            )
        except Exception:
            pass
        return

    # Parse TICKET_COMPLETE marker.
    _COMPLETE_RE = _re.compile(r'\[TICKET_COMPLETE:\s*(\{[^\]]+\})\s*\]', _re.DOTALL)
    match = _COMPLETE_RE.search(reply_text)

    if match:
        try:
            data = _json.loads(match.group(1))
        except (_json.JSONDecodeError, TypeError):
            data = {}

        machine_raw   = data.get("machine_raw",   "").strip()
        fault_summary = data.get("fault_summary", "").strip()
        location      = data.get("location",      "").strip()
        urgency_raw   = data.get("urgency",        "").strip().upper()
        urgency_map   = {
            "HIGH":     BreakdownTicket.URGENCY_HIGH,
            "MEDIUM":   BreakdownTicket.URGENCY_MEDIUM,
            "LOW":      BreakdownTicket.URGENCY_LOW,
            "CRITICAL": BreakdownTicket.URGENCY_CRITICAL,
        }
        urgency = urgency_map.get(urgency_raw, BreakdownTicket.URGENCY_MEDIUM)

        # Resolve machine asset using the shared normalise+resolve pipeline.
        # Resolver activo usando el pipeline compartido normalizar+resolver.
        from work_order_processor.services import (
            _normalise_machine_code,
            _resolve_machine_asset,
        )
        machine_asset = _resolve_machine_asset(
            _normalise_machine_code(machine_raw), company=company,
        )

        ticket.machine_raw   = machine_raw
        ticket.fault_summary = fault_summary
        ticket.location      = location
        ticket.urgency       = urgency
        ticket.machine       = machine_asset
        ticket.status        = BreakdownTicket.STATUS_IN_PROGRESS
        ticket.save(update_fields=[
            "machine_raw", "fault_summary", "location", "urgency", "machine", "status",
        ])

        BreakdownConversationTurn.objects.create(
            ticket=ticket,
            role=BreakdownConversationTurn.ROLE_MODEL,
            content=reply_text,
        )

        contact_msg = (
            "Averia registrada con el numero #" + str(ticket.ticket_date_code) + ". "
            "Maquina: " + (machine_raw or "Sin identificar") + ". "
            "Urgencia: " + ticket.get_urgency_display() + ". "
            "El equipo de mantenimiento ha sido notificado."
        )
        try:
            WhatsAppChatService.send_reply(
                from_number=to_number, to_number=from_number, reply_text=contact_msg,
            )
        except Exception as exc:
            logger.error(
                "# [BREAKDOWN] Error enviando confirmacion al contacto %s: %s",
                from_number, exc,
            )

        # Persist summary in BREAKDOWNS room as OUTBOUND for panel history.
        # Persistir resumen en sala BREAKDOWNS como OUTBOUND para historial del panel.
        from chat.models import ChatMessage as _CM
        supervisor_body = (
            "Nuevo ticket de averia #" + str(ticket.ticket_date_code) + " | "
            "Contacto: " + (_resolve_alias(contact) or contact.name) + " | "
            "Maquina: " + (machine_raw or "Sin identificar") + " | "
            "Problema: " + fault_summary + " | "
            "Ubicacion: " + location + " | "
            "Urgencia: " + ticket.get_urgency_display()
        )
        _CM.objects.create(
            room=room, direction=_CM.DIRECTION_OUTBOUND,
            body=supervisor_body, whatsapp_sid="",
        )

        # Reset routing_state — contact returns to idle after ticket completion.
        # Resetear routing_state — el contacto vuelve a estado idle tras completar el ticket.
        contact.routing_state        = contact.ROUTING_STATE_NONE
        contact.pending_routing_body = ""
        contact.save(update_fields=["routing_state", "pending_routing_body"])

        # Dispatch breakdown card 1:1 to all workshop section members.
        # Despachar tarjeta de averia 1:1 a todos los miembros de la seccion de taller.
        _dispatch_breakdown_card(
            ticket=ticket,
            contact=contact,
            to_number=to_number,
        )

        logger.info(
            "# [BREAKDOWN] Ticket pk=%s #%s finalizado para contacto pk=%s.",
            ticket.pk, ticket.ticket_date_code, contact.pk,
        )

    else:
        BreakdownConversationTurn.objects.create(
            ticket=ticket,
            role=BreakdownConversationTurn.ROLE_MODEL,
            content=reply_text,
        )
        try:
            WhatsAppChatService.send_reply(
                from_number=to_number, to_number=from_number, reply_text=reply_text,
            )
            logger.info(
                "# [BREAKDOWN] Turno intermedio enviado a %s para ticket pk=%s.",
                from_number, ticket.pk,
            )
        except Exception as exc:
            logger.error(
                "# [BREAKDOWN] Error enviando turno Gemini a %s: %s",
                from_number, exc,
            )


def _persist_and_broadcast(room: ChatRoom, contact: Contact, body: str) -> None:
    """
    Creates a ChatMessage(INBOUND) in the room and enqueues the Celery
    broadcast task to relay the message to all section members via WhatsApp.

    Storage format  (panel):    "{alias}: {body}"
    WhatsApp format (broadcast): "[{room.name}] {alias}: {body}"

    The room name prefix is only needed in WhatsApp so recipients can identify
    which room the message belongs to when they receive it in a 1:1 conversation
    with the bot. Inside the panel the user is already inside the room so the
    prefix would be redundant noise.
    The task is enqueued in the 'work_orders' queue (declared in the task
    decorator) so the existing always-on worker consumes it without changes.
    ---
    Crea un ChatMessage(INBOUND) en la sala y encola la tarea Celery de
    broadcast para reenviar el mensaje a todos los miembros vía WhatsApp.

    Formato almacenado (panel):      "{alias}: {body}"
    Formato WhatsApp (broadcast):    "[{room.name}] {alias}: {body}"

    El prefijo de sala solo es necesario en WhatsApp para que los destinatarios
    identifiquen de qué sala proviene el mensaje al recibirlo en su conversación
    1:1 con el bot. En el panel el usuario ya está dentro de la sala, por lo que
    el prefijo sería ruido innecesario.
    La tarea se encola en la cola 'work_orders' (declarada en el decorador
    de la tarea) para que el worker always-on existente la consuma sin cambios.
    """
    from chat.tasks import broadcast_inbound_message

    panel_body = f"{_resolve_alias(contact)}: {body}"

    chat_message = ChatMessage.objects.create(
        room=room,
        direction=ChatMessage.DIRECTION_INBOUND,
        sender_contact=contact,
        body=panel_body,
        whatsapp_sid="",
    )

    try:
        broadcast_inbound_message.delay(chat_message.pk, room.name)
        logger.info(
            "# [CHAT DISPATCH] ChatMessage pk=%s encolado para broadcast.",
            chat_message.pk,
        )
    except Exception as exc:
        logger.error(
            "# [CHAT DISPATCH] Error encolando broadcast para ChatMessage pk=%s: %s",
            chat_message.pk,
            exc,
        )


def _persist_inbound_only(room: ChatRoom, contact: Contact, body: str) -> None:
    """
    Creates a ChatMessage(INBOUND) in the BREAKDOWNS room without enqueuing
    any broadcast task. Used for driver messages that are stored as individual
    history in the panel but not relayed to other contacts.
    ---
    Crea un ChatMessage(INBOUND) en la sala BREAKDOWNS sin encolar ninguna
    tarea de broadcast. Usado para mensajes de choferes que se almacenan como
    historial individual en el panel sin reenvio a otros contactos.
    """
    panel_body = f"{_resolve_alias(contact)}: {body}"
    ChatMessage.objects.create(
        room=room,
        direction=ChatMessage.DIRECTION_INBOUND,
        sender_contact=contact,
        body=panel_body,
        whatsapp_sid="",
    )
    logger.info(
        "# [CHAT DISPATCH] ChatMessage(INBOUND) persistido sin broadcast en sala '%s'.",
        room.name,
    )


def _dispatch_breakdown_card(ticket, contact, to_number: str) -> None:
    """
    Sends the breakdown card 1:1 to all active members of the target workshop
    ChatRoom and persists it as OUTBOUND in that room for panel history.

    Routing logic (no WorkshopFamilyMapping required):
      - family == 'PLATAFOR'  → room named 'Elevación'
      - anything else         → room named 'Taller Mecánico'
    If the target room is not found, falls back to any active SECTION room.

    All CompanyUser members of the room receive an individual WhatsApp message,
    regardless of role (ADMIN, SUPERVISOR, WORKSHOPBOSS, WORKSHOP).
    ---
    Envía la tarjeta de avería 1:1 a todos los miembros activos de la ChatRoom
    de taller destino y la persiste como OUTBOUND en esa sala para el historial.

    Lógica de enrutamiento (sin WorkshopFamilyMapping):
      - family == 'PLATAFOR'  → sala 'Elevación'
      - cualquier otra        → sala 'Taller Mecánico'
    Si no se encuentra la sala destino, usa cualquier sala SECTION activa.

    Todos los CompanyUser miembros de la sala reciben un mensaje WhatsApp
    individual, independientemente del rol.
    """
    from whatsapp.services import WhatsAppChatService
    from ivr_config.models import CompanyUser, Contact as _Contact

    company = contact.company

    # Resolve target room by machine family — no mapping table needed.
    # Resolver sala destino por familia de máquina — sin tabla de mapeo.
    family = (ticket.machine.family if ticket.machine else "") or ""
    if family.upper() == "PLATAFOR":
        target_name = "Elevación"
    else:
        target_name = "Taller Mecánico"

    target_room = ChatRoom.objects.filter(
        company=company,
        room_type=ChatRoom.ROOM_TYPE_SECTION,
        name=target_name,
        is_active=True,
    ).first()

    # Fallback: first active SECTION room.
    # Fallback: primera sala SECTION activa.
    if target_room is None:
        target_room = ChatRoom.objects.filter(
            company=company,
            room_type=ChatRoom.ROOM_TYPE_SECTION,
            is_active=True,
        ).first()

    if target_room is None:
        logger.warning(
            "# [BREAKDOWN CARD] No hay sala SECTION activa para empresa pk=%s — "
            "tarjeta no enviada.",
            company.pk,
        )
        return

    # Build card text.
    # Construir texto de la tarjeta.
    card_text = (
        "Nueva averia #" + str(ticket.ticket_date_code) + "\n"
        "Maquina: " + (ticket.machine_raw or "Sin identificar") + "\n"
        "Problema: " + (ticket.fault_summary or "-") + "\n"
        "Ubicacion: " + (ticket.location or "-") + "\n"
        "Urgencia: " + ticket.get_urgency_display() + "\n"
        "Reportado por: " + (_resolve_alias(contact) or contact.name)
    )

    # Persist card as OUTBOUND in room for panel history (simulate group message).
    # Persistir tarjeta como OUTBOUND en la sala para historial del panel.
    ChatMessage.objects.create(
        room=target_room,
        direction=ChatMessage.DIRECTION_OUTBOUND,
        body=card_text,
        whatsapp_sid="",
    )

    # Dispatch 1:1 WhatsApp to ALL CompanyUser members of the room, any role.
    # Route: room.section → Contact (who has that section) → company_user.
    # Respects the 24h WhatsApp session window:
    #   - Active session   → send free-text card directly.
    #   - Inactive session → send chat_session_renewal template + queue card
    #                        in pending_broadcast_messages for delivery on opt_in.
    # Despachar WhatsApp 1:1 a TODOS los miembros de la sala.
    # Respeta la ventana de sesión de 24h de WhatsApp:
    #   - Sesión activa   → enviar tarjeta como texto libre.
    #   - Sesión inactiva → enviar plantilla chat_session_renewal + encolar tarjeta
    #                       en pending_broadcast_messages para entrega al opt_in.
    from whatsapp.models import WhatsAppSession, WhatsAppTemplate
    import datetime as _dt
    import json as _json_card

    try:
        renewal_template = WhatsAppTemplate.objects.get(
            company=company,
            name="chat_session_renewal",
            is_active=True,
        )
    except WhatsAppTemplate.DoesNotExist:
        renewal_template = None
        logger.warning(
            "# [BREAKDOWN CARD] Template chat_session_renewal no encontrado "
            "para empresa pk=%s. Mensajes fuera de ventana omitidos.",
            company.pk,
        )

    if target_room.section is not None:
        members_qs = _Contact.objects.filter(
            company=company,
            sections=target_room.section,
            company_user__isnull=False,
            company_user__is_active=True,
        ).select_related("company_user").distinct()
    else:
        members_qs = _Contact.objects.none()

    sent = 0
    renewed = 0
    skipped = 0
    sent_pks = set()

    for member_contact in members_qs:
        if not member_contact.phone_number or member_contact.pk in sent_pks:
            continue

        phone_number = member_contact.phone_number
        _alias = (
            member_contact.company_user.alias
            if member_contact.company_user_id and member_contact.company_user
            else member_contact.alias or ""
        ) or member_contact.name or phone_number

        has_active_session = WhatsAppSession.objects.filter(
            company=company,
            phone_number=phone_number,
            is_active=True,
        ).exists()

        if has_active_session:
            # Active session — send card as free-text message.
            # Sesión activa — enviar tarjeta como mensaje de texto libre.
            try:
                WhatsAppChatService.send_reply(
                    from_number=to_number,
                    to_number=phone_number,
                    reply_text=card_text,
                )
                sent_pks.add(member_contact.pk)
                sent += 1
                logger.info(
                    "# [BREAKDOWN CARD] Tarjeta enviada a Contact pk=%s (%s).",
                    member_contact.pk, phone_number,
                )
            except Exception as exc:
                logger.error(
                    "# [BREAKDOWN CARD] Error enviando tarjeta a Contact pk=%s: %s",
                    member_contact.pk, exc,
                )
                skipped += 1
        else:
            # Inactive session — queue card and send renewal template.
            # Sesión inactiva — encolar tarjeta y enviar plantilla renewal.
            if renewal_template is None:
                logger.warning(
                    "# [BREAKDOWN CARD] Contact pk=%s fuera de ventana sin renewal — omitido.",
                    member_contact.pk,
                )
                skipped += 1
                continue

            # Queue the card in WhatsAppSession.pending_broadcast_messages.
            # Encolar la tarjeta en WhatsAppSession.pending_broadcast_messages.
            session = WhatsAppSession.objects.filter(
                company=company,
                phone_number=phone_number,
            ).order_by("-session_start").first()

            pending_entry = {
                "body":       card_text,
                "created_at": _dt.datetime.utcnow().isoformat(),
            }

            if session is not None:
                pending = list(session.pending_broadcast_messages or [])
                pending.append(pending_entry)
                session.pending_broadcast_messages = pending
                session.save(update_fields=["pending_broadcast_messages"])
            else:
                # No session record — create one inactive so opt_in can find it.
                # Sin registro de sesión — crear uno inactivo para que opt_in lo encuentre.
                WhatsAppSession.objects.create(
                    company=company,
                    phone_number=phone_number,
                    is_active=False,
                    pending_broadcast_messages=[pending_entry],
                )

            try:
                WhatsAppChatService.send_template(
                    from_number=to_number,
                    to_number=phone_number,
                    content_sid=renewal_template.content_sid,
                    content_variables={
                        "1": _alias,
                        "2": company.name,
                        "3": "https://enterprisebot-miguelaetxio.pythonanywhere.com/panel/",
                    },
                )
                sent_pks.add(member_contact.pk)
                renewed += 1
                logger.info(
                    "# [BREAKDOWN CARD] Renewal enviado a Contact pk=%s (%s) — "
                    "tarjeta encolada.",
                    member_contact.pk, phone_number,
                )
            except Exception as exc:
                logger.error(
                    "# [BREAKDOWN CARD] Error enviando renewal a Contact pk=%s: %s",
                    member_contact.pk, exc,
                )
                skipped += 1

    logger.info(
        "# [BREAKDOWN CARD] Ticket pk=%s — enviados: %d, renewals: %d, omitidos: %d — "
        "sala '%s'.",
        ticket.pk, sent, renewed, skipped, target_room.name,
    )


# ---------------------------------------------------------------------------
# RESOLUCIÓN DE BREAKDOWNTICKET PARA ANCLAJE DE REPUESTOS (H10 Paso 4-bis)
# Diseño cerrado en S006 — ver ENTERPRISEBOT_ATTACHED_MILESTONE_V10.md,
# sección "Paso 4-bis". Esta sección implementa SOLO los puntos 1 y 2 de
# los 12 del diseño: resolución de ticket por centro de gasto (máquina)
# y el mutex get_or_create con select_for_update(). NO implementa
# todavía: tipo_tarea (punto 4), transición de estado al grabar la
# tarea (punto 8), ni el punto de invocación real desde el formulario
# de parte o desde confirm_delivery_note() (bloques posteriores del
# mismo diseño) — ambos siguen sin tocar tras este bloque.
#
# BREAKDOWNTICKET RESOLUTION FOR SPARE PARTS ANCHORING (H10 Paso 4-bis).
# Design closed in S006 — see ENTERPRISEBOT_ATTACHED_MILESTONE_V10.md,
# "Paso 4-bis" section. This section implements ONLY points 1 and 2 of
# the 12-point design: cost-centre (machine) ticket resolution and the
# select_for_update() get_or_create mutex. NOT implemented yet:
# tipo_tarea (point 4), status transition on task save (point 8), or
# the real call site from the work-order form or confirm_delivery_note()
# (later blocks of the same design) — both remain untouched after this
# block.
# ---------------------------------------------------------------------------

# Ventana de reapertura del punto 1 del diseño: si no hay ningún ticket
# abierto para la máquina pero sí uno cerrado dentro de esta ventana, se
# ofrece reabrirlo antes de generar uno nuevo (cubre el caso viernes →
# lunes de fin de semana/festivo).
# ---
# Reopening window from design point 1: if there is no open ticket for
# the machine but one was closed within this window, offer to reopen it
# before generating a new one (covers the Friday → Monday weekend/
# holiday case).
REOPEN_WINDOW_HOURS = 72


@dataclass(frozen=True)
class TicketResolution:
    """
    Immutable, read-only result of evaluating the breakdown-ticket-per-
    machine resolution rules (Paso 4-bis, punto 1, revisado en S007 a
    petición de Miguel Ángel) for a given fleet.MachineAsset. Never
    creates, attaches, reopens or modifies anything — used by the
    caller (work-order form view or confirm_delivery_note()) to decide
    what to tell the mechanic before calling
    get_or_create_ticket_for_machine().

    action:
      'CREATE'  — no OPEN/IN_PROGRESS/PAUSED ticket for this machine,
                  and nothing closed within REOPEN_WINDOW_HOURS. No
                  choice possible — the caller must simply NOTIFY the
                  mechanic a new ticket will be generated (no question,
                  per Miguel Ángel: "no hay elección cuando no haya").
      'ASK_REOPEN' — no OPEN/IN_PROGRESS/PAUSED ticket, but `ticket`
                  was closed within REOPEN_WINDOW_HOURS. Caller must
                  ask ("¿es la misma avería?") before calling
                  get_or_create_ticket_for_machine(reopen=True/False).
      'CHOOSE'  — one or more OPEN/IN_PROGRESS/PAUSED tickets exist
                  for this machine (`candidates` holds them, length
                  1+). Revised behaviour (S007): even with a single
                  candidate there is no silent auto-attach anymore —
                  the caller must always ask the mechanic to confirm
                  ("¿esta tarea es del ticket [X]?") with an explicit
                  "es una avería nueva" option alongside the
                  candidate(s), before calling
                  get_or_create_ticket_for_machine(chosen_ticket_pk=...)
                  or (..., create_new=True).

    ---

    Resultado inmutable y de solo lectura de evaluar las reglas de
    resolución de ticket de avería por máquina (Paso 4-bis, punto 1,
    revisado en S007 a petición de Miguel Ángel) para un
    fleet.MachineAsset dado. Nunca crea, engancha, reabre ni modifica
    nada — lo usa quien llama (vista de formulario de parte o
    confirm_delivery_note()) para decidir qué decirle al mecánico
    antes de llamar a get_or_create_ticket_for_machine().

    action:
      'CREATE'  — no hay ningún ticket OPEN/IN_PROGRESS/PAUSED para
                  esta máquina, ni nada cerrado dentro de
                  REOPEN_WINDOW_HOURS. Sin elección posible — el
                  llamante solo debe AVISAR al mecánico de que se va a
                  generar un ticket nuevo (sin pregunta, según Miguel
                  Ángel: "no hay elección cuando no haya").
      'ASK_REOPEN' — no hay ticket OPEN/IN_PROGRESS/PAUSED, pero
                  `ticket` se cerró dentro de REOPEN_WINDOW_HOURS. El
                  llamante debe preguntar ("¿es la misma avería?")
                  antes de llamar a
                  get_or_create_ticket_for_machine(reopen=True/False).
      'CHOOSE'  — hay uno o más tickets OPEN/IN_PROGRESS/PAUSED para
                  esta máquina (`candidates` los contiene, longitud
                  1+). Comportamiento revisado (S007): incluso con un
                  único candidato ya no hay enganche silencioso — el
                  llamante siempre debe preguntar al mecánico
                  ("¿esta tarea es del ticket [X]?") con una opción
                  explícita "es una avería nueva" junto al/los
                  candidato(s), antes de llamar a
                  get_or_create_ticket_for_machine(chosen_ticket_pk=...)
                  o (..., create_new=True).
    """

    action: str
    ticket: Optional[object] = None
    candidates: tuple = ()


def resolve_ticket_for_machine(machine) -> "TicketResolution":
    """
    Read-only evaluation of Paso 4-bis punto 1 (revisado en S007) for
    `machine` (fleet.MachineAsset). Never locks, never writes — safe
    to call as many times as needed while rendering a form or a
    confirmation screen. The definitive, race-free evaluation happens
    again inside get_or_create_ticket_for_machine(), under the mutex.

    PAUSED counts as an open candidate (S007, confirmado por Miguel
    Ángel): un ticket se pausa cuando el mecánico se reasigna a una
    avería de otra máquina con más prioridad, y sigue siendo un
    candidato real a retomar en esta máquina — no un estado terminal
    como CLOSED.
    ---
    Evaluación de solo lectura del punto 1 de Paso 4-bis (revisado en
    S007) para `machine` (fleet.MachineAsset). Nunca bloquea, nunca
    escribe — se puede llamar tantas veces como haga falta al
    renderizar un formulario o una pantalla de confirmación. La
    evaluación definitiva y libre de condiciones de carrera vuelve a
    ocurrir dentro de get_or_create_ticket_for_machine(), bajo el
    mutex.

    PAUSED cuenta como candidato abierto (S007, confirmado por Miguel
    Ángel): un ticket se pausa cuando el mecánico se reasigna a una
    avería de otra máquina con más prioridad, y sigue siendo un
    candidato real a retomar en esta máquina — no es un estado
    terminal como CLOSED.
    """
    from chat.models import BreakdownTicket

    open_candidates = list(
        BreakdownTicket.objects.filter(
            machine=machine,
            status__in=[
                BreakdownTicket.STATUS_OPEN,
                BreakdownTicket.STATUS_IN_PROGRESS,
                BreakdownTicket.STATUS_PAUSED,
            ],
        ).order_by("-created_at")
    )

    if open_candidates:
        return TicketResolution(action="CHOOSE", candidates=tuple(open_candidates))

    # 0 candidatos abiertos/pausados -- mirar cerrados dentro de la
    # ventana de reapertura. Si hubiera más de uno cerrado dentro de la
    # ventana se ofrece el más reciente -- el diseño de S006 no
    # contempla varios candidatos cerrados simultáneos; asunción
    # declarada, no bloqueante, a confirmar con Miguel Ángel si llega a
    # darse en la práctica.
    # ---
    # 0 open/paused candidates -- look at those closed within the
    # reopening window. If more than one were closed within the
    # window, the most recent is offered -- the S006 design does not
    # contemplate several simultaneous closed candidates; declared,
    # non-blocking assumption, to confirm with Miguel Ángel if it
    # happens in practice.
    cutoff = timezone.now() - datetime.timedelta(hours=REOPEN_WINDOW_HOURS)
    recently_closed = (
        BreakdownTicket.objects.filter(
            machine=machine,
            status=BreakdownTicket.STATUS_CLOSED,
            resolved_at__gte=cutoff,
        )
        .order_by("-resolved_at")
        .first()
    )
    if recently_closed is not None:
        return TicketResolution(action="ASK_REOPEN", ticket=recently_closed)

    return TicketResolution(action="CREATE")


def _resolve_ticket_contact(company_user):
    """
    Resolves (or lazily creates) the Contact used to satisfy the
    mandatory BreakdownTicket.contact FK when a ticket is pregenerated
    without a real external reporter (Paso 4-bis, bloque CREATE).

    Resolution order:
      1. Any Contact already linked to this company_user (its
         `company_user` FK) — deliberately NOT filtered by
         `is_internal`, because CompanyUserCreateView
         (panel/views_auth.py) sets `is_internal=is_ivr_active` on
         creation, so a linked Contact may exist with
         `is_internal=False` and would be missed by the
         is_internal=True filter used elsewhere (whatsapp/tasks.py,
         chat/views.py) for a different purpose (WhatsApp-capable
         contacts). Here we only need a valid Contact belonging to
         this company_user, whatever its is_internal flag.
      2. If none exists at all — CompanyUserCreateView only
         links/creates a Contact when a phone_number or a section was
         given at creation time (panel/views_auth.py:214-261), so some
         CompanyUsers may have none — create one on the fly following
         the exact same no-phone pattern already used there
         (phone_number='', is_internal=True, company_user=company_user).

    Never raises for a missing Contact — self-heals instead, so
    get_or_create_ticket_for_machine() never fails on this account.
    ---

    Resuelve (o crea de forma perezosa) el Contact usado para
    satisfacer el FK obligatorio BreakdownTicket.contact cuando se
    pregenera un ticket sin un reportante externo real (Paso 4-bis,
    bloque CREATE).

    Orden de resolución:
      1. Cualquier Contact ya vinculado a este company_user (su FK
         `company_user`) — deliberadamente SIN filtrar por
         `is_internal`, porque CompanyUserCreateView
         (panel/views_auth.py) fija `is_internal=is_ivr_active` al
         crear, así que puede existir un Contact vinculado con
         `is_internal=False` que el filtro is_internal=True usado en
         otros sitios (whatsapp/tasks.py, chat/views.py) para otro
         propósito (contactos con capacidad de WhatsApp) no
         encontraría. Aquí solo hace falta un Contact válido de este
         company_user, sea cual sea su is_internal.
      2. Si no existe ninguno — CompanyUserCreateView solo
         vincula/crea un Contact cuando se dio phone_number o sección
         al crear el usuario (panel/views_auth.py:214-261), así que
         algunos CompanyUser pueden no tener ninguno — se crea uno al
         vuelo siguiendo el mismo patrón sin teléfono ya usado allí
         (phone_number='', is_internal=True, company_user=company_user).

    Nunca lanza excepción por falta de Contact — se autorrepara, para
    que get_or_create_ticket_for_machine() nunca falle por este motivo.
    """
    contact = Contact.objects.filter(
        company=company_user.company,
        company_user=company_user,
    ).first()
    if contact is not None:
        return contact

    display_name = (
        company_user.user.get_full_name().strip()
        or company_user.user.username
    )
    contact = Contact.objects.create(
        company=company_user.company,
        phone_number="",
        name=display_name,
        is_internal=True,
        company_user=company_user,
    )
    logger.info(
        "# [H10-BIS] Contact interno pk=%s creado sobre la marcha para "
        "company_user pk=%s (no tenía ninguno vinculado todavía).",
        contact.pk, company_user.pk,
    )
    return contact


def get_or_create_ticket_for_machine(
    machine,
    company_user,
    reopen: Optional[bool] = None,
    chosen_ticket_pk: Optional[int] = None,
    create_new: bool = False,
):
    """
    Atomic, mutex-protected resolution of Paso 4-bis puntos 1-2
    (revisado en S007). Must be called from within the same DB
    transaction as the task save that needs the ticket (punto 11 del
    diseño — transacción única por tarea); Django reuses the caller's
    transaction if one is already open instead of nesting a new one.

    Re-evaluates the resolution rules AFTER acquiring the mutex (a
    select_for_update() lock on the MachineAsset row), never before —
    the read-only preview from resolve_ticket_for_machine() can be
    stale by the time the mechanic answers a question, so it is
    recomputed here to close the race between two concurrent requests
    for the same machine (punto 2 del diseño: cubre tanto la vía parte
    como la vía albarán, y el caso de "ayuda" entre operarios).

    Parameters:
      machine          -- fleet.MachineAsset, the cost centre.
      company_user     -- ivr_config.CompanyUser performing the action.
                           Used to resolve (or lazily create, via
                           _resolve_ticket_contact()) the mandatory
                           BreakdownTicket.contact field when a new
                           ticket must be created.
      reopen           -- required (True/False) only when the
                           re-evaluated state is ASK_REOPEN. Ignored
                           otherwise. False means "no es la misma
                           avería" -- falls through to CREATE, same as
                           create_new=True would for CHOOSE.
      chosen_ticket_pk -- when the re-evaluated state is CHOOSE, pass
                          this to attach to that specific candidate
                          (mechanic confirmed "sí, es este ticket").
                          Mutually exclusive with create_new.
      create_new       -- when the re-evaluated state is CHOOSE, pass
                          True to force a brand new ticket even though
                          candidate(s) exist (mechanic confirmed "es
                          una avería nueva"). Mutually exclusive with
                          chosen_ticket_pk.

    Returns the resolved chat.models.BreakdownTicket (existing,
    reopened, or newly created). Never fails for lack of a Contact —
    _resolve_ticket_contact() self-heals by creating one if needed.

    Raises ValueError if the caller's answer doesn't match what the
    re-evaluation actually needs (e.g. state is CHOOSE but neither
    chosen_ticket_pk nor create_new was given, or both were) — this is
    treated as a caller bug (stale UI state), never silently guessed.

    ---

    Resolución atómica y protegida por mutex de los puntos 1-2 del
    diseño de Paso 4-bis (revisado en S007). Debe llamarse dentro de
    la misma transacción de BD que el guardado de la tarea que
    necesita el ticket (punto 11 del diseño — transacción única por
    tarea); Django reutiliza la transacción de quien llama si ya hay
    una abierta, en vez de anidar una nueva.

    Reevalúa las reglas DESPUÉS de adquirir el mutex (bloqueo
    select_for_update() sobre la fila de MachineAsset), nunca antes —
    la vista previa de solo lectura de resolve_ticket_for_machine()
    puede haber quedado obsoleta para cuando el mecánico responde una
    pregunta, así que se recalcula aquí para cerrar la carrera entre
    dos peticiones concurrentes sobre la misma máquina (punto 2 del
    diseño: cubre tanto la vía parte como la vía albarán, y el caso de
    "ayuda" entre operarios).
    """
    from chat.models import BreakdownTicket
    from fleet.models import MachineAsset

    with transaction.atomic():
        # Mutex -- punto 2 del diseño. select_for_update() sobre la
        # fila de MachineAsset cubre tanto la vía parte como la vía
        # albarán, y el caso de "ayuda" entre operarios sobre la misma
        # máquina, sin condiciones de carrera.
        MachineAsset.objects.select_for_update().get(pk=machine.pk)

        resolution = resolve_ticket_for_machine(machine)

        if resolution.action == "CHOOSE":
            if bool(chosen_ticket_pk) == bool(create_new):
                raise ValueError(
                    "get_or_create_ticket_for_machine(): hay %d ticket(s) "
                    "abierto(s)/pausado(s) para la máquina pk=%s -- el "
                    "llamante debe pasar exactamente uno de "
                    "chosen_ticket_pk o create_new=True (nunca ambos, "
                    "nunca ninguno) tras preguntar al mecánico." % (
                        len(resolution.candidates), machine.pk,
                    )
                )
            if create_new:
                pass  # cae al bloque CREATE de abajo, igual que ASK_REOPEN con reopen=False.
            else:
                chosen = next(
                    (t for t in resolution.candidates if t.pk == chosen_ticket_pk),
                    None,
                )
                if chosen is None:
                    raise ValueError(
                        "get_or_create_ticket_for_machine(): chosen_ticket_pk=%s "
                        "no está entre los candidatos actuales (abiertos/"
                        "pausados) para la máquina pk=%s -- posible carrera "
                        "o estado de UI obsoleto." % (chosen_ticket_pk, machine.pk)
                    )
                return chosen

        elif resolution.action == "ASK_REOPEN":
            if reopen is None:
                raise ValueError(
                    "get_or_create_ticket_for_machine(): hay un ticket "
                    "cerrado hace menos de %sh para la máquina pk=%s y no "
                    "se indicó reopen -- el llamante debe preguntar al "
                    "mecánico antes de invocar esta función." % (
                        REOPEN_WINDOW_HOURS, machine.pk,
                    )
                )
            if reopen:
                ticket = resolution.ticket
                ticket.status = BreakdownTicket.STATUS_IN_PROGRESS
                ticket.resolved_at = None
                ticket.resolved_by = None
                ticket.save(update_fields=["status", "resolved_at", "resolved_by"])
                logger.info(
                    "# [H10-BIS] Ticket pk=%s reabierto para máquina pk=%s "
                    "(estaba cerrado hace menos de %sh).",
                    ticket.pk, machine.pk, REOPEN_WINDOW_HOURS,
                )
                return ticket
            # reopen=False -- el mecánico confirma que no es la misma
            # avería -- cae al bloque CREATE de abajo.

        # resolution.action == 'CREATE', o 'CHOOSE' con create_new=True,
        # o 'ASK_REOPEN' con reopen=False.
        contact = _resolve_ticket_contact(company_user)

        ticket = BreakdownTicket.objects.create(
            company=company_user.company,
            contact=contact,
            machine=machine,
            machine_raw=machine.code,
            origin=BreakdownTicket.ORIGIN_AUTO,
            status=BreakdownTicket.STATUS_OPEN,
        )
        logger.info(
            "# [H10-BIS] Ticket pk=%s pregenerado para máquina pk=%s "
            "(resolución: %s).",
            ticket.pk, machine.pk, resolution.action,
        )
        return ticket

