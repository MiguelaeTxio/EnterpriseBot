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

import logging
from dataclasses import dataclass
from typing import Optional

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

    # --- Rule 5a: Contact is AWAITING_ROUTE — process routing response. ---
    # --- Regla 5a: Contacto en AWAITING_ROUTE — procesar respuesta de enrutamiento. ---
    if contact.routing_state == contact.ROUTING_STATE_AWAITING_ROUTE:
        consumed = _resolve_pending_routing(
            contact=contact,
            section=section,
            room=room,
            breakdown_room=breakdown_room,
            body=body,
            from_number=from_number,
            to_number=to_number,
        )
        return DispatchResult(consumed=consumed, room=room, contact=contact)

    # --- Rule 5b: Section has breakdown access — send routing Quick Reply. ---
    # --- Regla 5b: Sección con acceso a BREAKDOWNS — enviar Quick Reply de enrutamiento. ---
    if has_breakdown_access:
        consumed = _handle_breakdown_routing(
            contact=contact,
            section=section,
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
# _HANDLE_BREAKDOWN_ROUTING
# ---------------------------------------------------------------------------

def _handle_breakdown_routing(
    contact: Contact,
    section,
    body: str,
    from_number: str,
    to_number: str,
) -> bool:
    """
    Sends the breakdown_routing Quick Reply and stores routing_state in DB.
    Returns True (message consumed).
    ---
    Envia el Quick Reply breakdown_routing y guarda routing_state en BD.
    Devuelve True (mensaje consumido).
    """
    from whatsapp.models import WhatsAppTemplate
    from whatsapp.services import WhatsAppChatService

    contact.routing_state        = contact.ROUTING_STATE_AWAITING_ROUTE
    contact.pending_routing_body = body
    contact.save(update_fields=["routing_state", "pending_routing_body"])

    try:
        _tpl = WhatsAppTemplate.objects.get(
            company=contact.company,
            name="breakdown_routing",
            is_active=True,
        )
        WhatsAppChatService.send_quick_reply(
            from_number=to_number,
            to_number=from_number,
            content_sid=_tpl.content_sid,
            content_variables={"1": section.name},
        )
        logger.info(
            "# [CHAT DISPATCH] Quick Reply breakdown_routing enviado a %s.",
            from_number,
        )
    except WhatsAppTemplate.DoesNotExist:
        logger.error(
            "# [CHAT DISPATCH] Template breakdown_routing no encontrado empresa pk=%s.",
            contact.company_id,
        )
        contact.routing_state        = contact.ROUTING_STATE_NONE
        contact.pending_routing_body = ""
        contact.save(update_fields=["routing_state", "pending_routing_body"])
    except Exception as exc:
        logger.error(
            "# [CHAT DISPATCH] Error enviando breakdown_routing a %s: %s",
            from_number, exc,
        )
        contact.routing_state        = contact.ROUTING_STATE_NONE
        contact.pending_routing_body = ""
        contact.save(update_fields=["routing_state", "pending_routing_body"])

    return True


# ---------------------------------------------------------------------------
# _RESOLVE_PENDING_ROUTING
# ---------------------------------------------------------------------------

def _resolve_pending_routing(
    contact: Contact,
    section,
    room,
    breakdown_room,
    body: str,
    from_number: str,
    to_number: str,
) -> bool:
    """
    Processes the contact routing selection and routes the held message.
    Button id "section" routes to SECTION room.
    Button id "breakdowns" routes to BREAKDOWNS agent.
    Unrecognised input re-sends the Quick Reply.
    ---
    Procesa la seleccion de sala del contacto y enruta el mensaje retenido.
    Id "section" -> sala SECTION. Id "breakdowns" -> agente BREAKDOWNS.
    Entrada no reconocida reenvía el Quick Reply.
    """
    from whatsapp.models import WhatsAppTemplate
    from whatsapp.services import WhatsAppChatService

    body_norm          = body.strip().lower()
    pending_body       = contact.pending_routing_body
    selected_section   = body_norm in ("mi seccion", "mi sección", "section", "1")
    selected_breakdown = body_norm in ("sala de averias", "sala de averías", "breakdowns", "2")

    if selected_section:
        contact.routing_state        = contact.ROUTING_STATE_NONE
        contact.pending_routing_body = ""
        contact.save(update_fields=["routing_state", "pending_routing_body"])
        _persist_and_broadcast(room=room, contact=contact, body=pending_body)
        logger.info(
            "# [CHAT DISPATCH] Enrutamiento resuelto a SECTION para %s.",
            from_number,
        )
        return True

    if selected_breakdown:
        contact.routing_state        = contact.ROUTING_STATE_NONE
        contact.pending_routing_body = ""
        contact.save(update_fields=["routing_state", "pending_routing_body"])
        if breakdown_room is not None:
            # Persist message in BREAKDOWNS room and broadcast to all members
            # of all sections registered in breakdown_sections.
            # Gemini ticket flow is not invoked at this stage — provisional
            # implementation to verify end-to-end broadcast before adding
            # the ticket collection dialogue.
            # ---
            # Persistir mensaje en sala BREAKDOWNS y hacer broadcast a todos
            # los miembros de todas las secciones registradas en breakdown_sections.
            # El flujo de tickets Gemini no se invoca en esta fase — implementación
            # provisional para verificar el broadcast extremo a extremo antes de
            # añadir el diálogo de recogida de tickets.
            _persist_and_broadcast(
                room=breakdown_room,
                contact=contact,
                body=pending_body,
            )
        else:
            logger.warning(
                "# [CHAT DISPATCH] Sala BREAKDOWNS no encontrada para empresa. "
                "Mensaje de %s descartado.",
                from_number,
            )
        logger.info(
            "# [CHAT DISPATCH] Enrutamiento resuelto a BREAKDOWNS para %s.",
            from_number,
        )
        return True

    # Unrecognised — re-send Quick Reply.
    # No reconocido — reenviar Quick Reply.
    logger.info(
        "# [CHAT DISPATCH] Respuesta de enrutamiento no reconocida de %s: %r.",
        from_number, body[:60],
    )
    try:
        _tpl = WhatsAppTemplate.objects.get(
            company=contact.company,
            name="breakdown_routing",
            is_active=True,
        )
        WhatsAppChatService.send_quick_reply(
            from_number=to_number,
            to_number=from_number,
            content_sid=_tpl.content_sid,
            content_variables={"1": section.name},
        )
    except Exception as exc:
        logger.error(
            "# [CHAT DISPATCH] Error reenviando breakdown_routing a %s: %s",
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

    # Build machine catalogue snippet.
    catalogue_codes = list(
        MachineAsset.objects.filter(company=company, is_active=True)
        .values_list("code", flat=True).order_by("code")[:100]
    )
    machine_catalogue = ", ".join(catalogue_codes) if catalogue_codes else "Sin catalogo disponible"

    # Build system prompt.
    system_prompt = (
        "Eres un asistente de gestion de averias de " + company.name + ". "
        "Tu mision es recoger los siguientes datos campo a campo mediante dialogo natural: "
        "1) Maquina afectada (codigo o nombre). "
        "2) Descripcion del problema o sintoma. "
        "3) Urgencia (Alta/Media/Baja). "
        "4) Ubicacion actual de la maquina. "
        "Reglas: pregunta UN campo a la vez, maximo 2 frases por turno. "
        "Catalogo de maquinas: " + machine_catalogue + ". "
        "Cuando tengas los 4 campos responde EXCLUSIVAMENTE con: "
        "[TICKET_COMPLETE:{\"machine_raw\": \"X\", \"fault_summary\": \"X\", "
        "\"urgency\": \"HIGH|MEDIUM|LOW\", \"location\": \"X\"}] "
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

        machine_asset = MachineAsset.objects.filter(
            company=company, code__iexact=machine_raw, is_active=True,
        ).first()

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
            "Averia registrada con el numero #" + str(ticket.ticket_number) + ". "
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

        from chat.models import ChatMessage as _CM
        supervisor_body = (
            "Nuevo ticket de averia #" + str(ticket.ticket_number) + " | "
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
        logger.info(
            "# [BREAKDOWN] Ticket pk=%s #%s finalizado para contacto pk=%s.",
            ticket.pk, ticket.ticket_number, contact.pk,
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
