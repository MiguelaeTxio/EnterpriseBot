# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/chat/services.py
"""
Service layer for the chat module.
Implements the inbound message dispatcher and the alias collection flow.

dispatch_inbound_message(company, from_number, body) -> DispatchResult
    Entry point called from IncomingWhatsAppView before the existing Hito 4
    chatbot pipeline. Returns a DispatchResult indicating whether the message
    was consumed by the chat dispatcher or should continue to the Hito 4 flow.

_handle_alias_collection(contact, body, from_number, to_number) -> bool
    Manages the alias collection dialogue for contacts without an alias.
    Returns True if the message was consumed (alias pending or just set).
    Returns False if the contact already has an alias (message proceeds normally).

_persist_and_broadcast(room, contact, body) -> None
    Creates the ChatMessage(INBOUND) and enqueues the Celery broadcast task.
---
Capa de servicios para el módulo de chat.
Implementa el despachador de mensajes entrantes y el flujo de recogida de alias.

dispatch_inbound_message(company, from_number, body) -> DispatchResult
    Punto de entrada llamado desde IncomingWhatsAppView antes del pipeline
    del chatbot del Hito 4. Devuelve un DispatchResult indicando si el mensaje
    fue consumido por el despachador de chat o debe continuar al flujo del Hito 4.

_handle_alias_collection(contact, body, from_number, to_number) -> bool
    Gestiona el diálogo de recogida de alias para contactos sin alias.
    Devuelve True si el mensaje fue consumido (alias pendiente o recién establecido).
    Devuelve False si el contacto ya tiene alias (el mensaje prosigue normalmente).

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
# ALIAS STATE SETS — In-memory state machine for the three-step alias dialogue.
# Sets en memoria para la máquina de estados del diálogo de alias en tres pasos.
#
# _ALIAS_PENDING    : phone numbers that have been asked for their name
#                     but have not yet provided one.
#                     Números que han recibido la solicitud de nombre pero
#                     aún no han respondido.
#
# _ALIAS_CONFIRMING : maps phone_number -> proposed_alias for numbers that
#                     have provided a name and are awaiting confirmation (SÍ).
#                     Mapea phone_number -> alias_propuesto para los números
#                     que han dado un nombre y esperan confirmación (SÍ).
#
# NOTE: Intentionally simple for the pilot (single worker process).
# A Redis hash would be required for multi-process deployments.
# NOTA: Deliberadamente simple para el piloto (proceso único).
# Se requeriría un hash Redis para despliegues multiproceso.
# ---------------------------------------------------------------------------
_ALIAS_PENDING: set = set()
_ALIAS_CONFIRMING: dict = {}


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
    section = contact.sections.filter(company=company, is_active=True).first()
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
            body=body,
            from_number=from_number,
            to_number=to_number,
        )
        return DispatchResult(consumed=consumed, room=room, contact=contact)

    # --- Rule 5: Alias present — persist and broadcast. ---
    # --- Regla 5: Alias presente — persistir y broadcast. ---
    _persist_and_broadcast(room=room, contact=contact, body=body)
    logger.info(
        "# [CHAT DISPATCH] Mensaje de '%s' (%s) enrutado a sala '%s'.",
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
    if from_number not in _ALIAS_PENDING and from_number not in _ALIAS_CONFIRMING:
        _ALIAS_PENDING.add(from_number)
        alias_request = (
            "¡Hola! Para participar en el chat de grupo de tu sección necesito saber "
            "cómo quieres que te identifiquen los demás compañeros.\n\n"
            "¿Con qué nombre o apodo quieres aparecer en el chat?"
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
    # --- Paso B: Pendiente — recibir nombre propuesto, pedir confirmación. ---
    if from_number in _ALIAS_PENDING:
        proposed_alias = body.strip()[:50]
        if not proposed_alias:
            try:
                WhatsAppChatService.send_reply(
                    from_number=to_number,
                    to_number=from_number,
                    reply_text=(
                        "El nombre no puede estar vacío. "
                        "Por favor, indícame el nombre o apodo con el que quieres aparecer."
                    ),
                )
            except Exception as exc:
                logger.error(
                    "# [CHAT DISPATCH] Error enviando re-solicitud de alias a %s: %s",
                    from_number,
                    exc,
                )
            return True

        _ALIAS_PENDING.discard(from_number)
        _ALIAS_CONFIRMING[from_number] = proposed_alias

        confirmation_request = (
            f"Hemos recibido tu nombre: *{proposed_alias}*.\n\n"
            "Este será tu alias en el chat de grupo de tu sección — el nombre "
            "con el que te identificarán el resto de compañeros.\n\n"
            "¿Confirmas que quieres usar este nombre? "
            "Responde *SÍ* para confirmarlo o escribe el nombre que prefieras "
            "si quieres cambiarlo."
        )
        try:
            WhatsAppChatService.send_reply(
                from_number=to_number,
                to_number=from_number,
                reply_text=confirmation_request,
            )
            logger.info(
                "# [CHAT DISPATCH] Confirmación de alias solicitada a %s para alias '%s'.",
                from_number,
                proposed_alias,
            )
        except Exception as exc:
            logger.error(
                "# [CHAT DISPATCH] Error enviando confirmación de alias a %s: %s",
                from_number,
                exc,
            )
        return True

    # --- Step C: Confirming — save alias or re-ask. ---
    # --- Paso C: Confirmando — guardar alias o volver a pedir. ---
    if from_number in _ALIAS_CONFIRMING:
        proposed_alias = _ALIAS_CONFIRMING[from_number]
        affirmative    = body.strip().upper() in ("SI", "SÍ", "S", "YES", "Y")

        if affirmative:
            # Persist alias and provision CompanyUser if not yet registered.
            # Persistir alias y provisionar CompanyUser si aún no está registrado.
            _provision_company_user(
                contact=contact,
                section=section,
                proposed_alias=proposed_alias,
                to_number=to_number,
                from_number=from_number,
            )
            del _ALIAS_CONFIRMING[from_number]

            final_confirmation = (
                f"✓ Perfecto, a partir de ahora aparecerás como *{proposed_alias}* "
                "en el chat de grupo de tu sección. "
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
                    "# [CHAT DISPATCH] Error enviando confirmación final a %s: %s",
                    from_number,
                    exc,
                )
        else:
            contact.alias = proposed_alias
            contact.save(update_fields=["alias"])

            del _ALIAS_CONFIRMING[from_number]

            final_confirmation = (
                f"✓ Perfecto, a partir de ahora aparecerás como *{proposed_alias}* "
                "en el chat de grupo de tu sección. "
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
                    "# [CHAT DISPATCH] Error enviando confirmación final a %s: %s",
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
                            "El nombre no puede estar vacío. "
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

            _ALIAS_CONFIRMING[from_number] = new_alias

            re_confirmation_request = (
                f"De acuerdo, ¿confirmas que quieres usar *{new_alias}* "
                "como tu nombre en el grupo? "
                "Responde *SÍ* para confirmarlo o escribe otro nombre si prefieres cambiarlo."
            )
            try:
                WhatsAppChatService.send_reply(
                    from_number=to_number,
                    to_number=from_number,
                    reply_text=re_confirmation_request,
                )
                logger.info(
                    "# [CHAT DISPATCH] Re-confirmación de alias solicitada a %s para alias '%s'.",
                    from_number,
                    new_alias,
                )
            except Exception as exc:
                logger.error(
                    "# [CHAT DISPATCH] Error enviando re-confirmación de alias a %s: %s",
                    from_number,
                    exc,
                )

    return True


def _persist_and_broadcast(room: ChatRoom, contact: Contact, body: str) -> None:
    """
    Creates a ChatMessage(INBOUND) in the room and enqueues the Celery
    broadcast task to relay the message to all section members via WhatsApp.
    The message body is prefixed with the contact's alias.
    ---
    Crea un ChatMessage(INBOUND) en la sala y encola la tarea Celery de
    broadcast para reenviar el mensaje a todos los miembros de la sección
    vía WhatsApp. El cuerpo del mensaje se prefija con el alias del contacto.
    """
    from chat.tasks import broadcast_inbound_message

    prefixed_body = f"{_resolve_alias(contact)}: {body}"

    chat_message = ChatMessage.objects.create(
        room=room,
        direction=ChatMessage.DIRECTION_INBOUND,
        sender_contact=contact,
        body=prefixed_body,
        whatsapp_sid="",
    )

    try:
        broadcast_inbound_message.delay(chat_message.pk)
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
