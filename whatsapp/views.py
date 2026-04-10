# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/whatsapp/views.py
"""
Views for the whatsapp channel app.
Implements two CSRF-exempt webhook endpoints:
  - IncomingWhatsAppView: handles inbound user messages and dispatches chatbot replies.
  - PresenceWhatsAppView: handles presence reminder responses (1h / 2h / disponible).
Both views are synchronous Django WSGI views — no aiohttp or WebSocket required.
---
Vistas para la app del canal WhatsApp.
Implementa dos endpoints webhook exentos de CSRF:
  - IncomingWhatsAppView: gestiona mensajes entrantes del usuario y despacha respuestas del chatbot.
  - PresenceWhatsAppView: gestiona respuestas a recordatorios de presencia (1h / 2h / disponible).
Ambas vistas son vistas síncronas Django WSGI — no se requiere aiohttp ni WebSocket.
"""

import logging

from django.http import HttpResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from ivr_config.models import PhoneNumber
from .models import WhatsAppMessage, WhatsAppSession
from .services import PresenceResponseService, WhatsAppChatService

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# INCOMING WHATSAPP VIEW
# Handles inbound user messages and dispatches chatbot replies via Gemini.
# Gestiona mensajes entrantes del usuario y despacha respuestas del chatbot vía Gemini.
# ---------------------------------------------------------------------------

@method_decorator(csrf_exempt, name="dispatch")
class IncomingWhatsAppView(View):
    """
    Webhook endpoint: POST /api/whatsapp/incoming/
    Receives inbound WhatsApp messages from Twilio, resolves the target company
    from the destination number, manages the WhatsAppSession and message history,
    invokes WhatsAppChatService to obtain a Gemini reply, persists both the
    inbound and outbound messages, and dispatches the reply via Twilio.
    Returns HTTP 200 with an empty body on success — Twilio does not require
    a TwiML response for WhatsApp messaging webhooks.
    ---
    Endpoint webhook: POST /api/whatsapp/incoming/
    Recibe mensajes entrantes de WhatsApp de Twilio, resuelve la empresa destino
    desde el número de destino, gestiona la WhatsAppSession y el historial de
    mensajes, invoca WhatsAppChatService para obtener una respuesta de Gemini,
    persiste los mensajes entrante y saliente, y despacha la respuesta vía Twilio.
    Devuelve HTTP 200 con cuerpo vacío en caso de éxito — Twilio no requiere
    una respuesta TwiML para los webhooks de mensajería WhatsApp.
    """

    def post(self, request, *args, **kwargs):
        """
        Main POST handler for inbound WhatsApp messages.
        Orchestrates the full chatbot pipeline: resolve → session → prompt →
        history → gemini → persist → dispatch.
        ---
        Manejador POST principal para mensajes entrantes de WhatsApp.
        Orquesta el pipeline completo del chatbot: resolver → sesión → prompt →
        historial → gemini → persistir → despachar.
        """
        # --- Step 1: Extract Twilio webhook parameters. ---
        # --- Paso 1: Extraer parámetros del webhook de Twilio. ---
        from_number = request.POST.get("From", "").replace("whatsapp:", "")
        to_number   = request.POST.get("To", "").replace("whatsapp:", "")
        body        = request.POST.get("Body", "").strip()

        logger.info(
            "# [WHATSAPP] Mensaje entrante de %s a %s: '%s'",
            from_number,
            to_number,
            body[:80],
        )

        if not from_number or not to_number or not body:
            logger.warning(
                "# [WHATSAPP] Parámetros incompletos en webhook entrante. "
                "From=%s To=%s Body=%s",
                from_number,
                to_number,
                repr(body),
            )
            return HttpResponse(status=200)

        # --- Step 2: Resolve company from destination number. ---
        # --- Paso 2: Resolver empresa desde el número de destino. ---
        try:
            phone_number_record = PhoneNumber.objects.select_related(
                "company",
            ).get(
                number=to_number,
                is_active=True,
                capabilities__in=[
                    PhoneNumber.CAPABILITY_WHATSAPP,
                    PhoneNumber.CAPABILITY_BOTH,
                ],
            )
            company = phone_number_record.company

        except PhoneNumber.DoesNotExist:
            logger.error(
                "# [WHATSAPP] Número destino no registrado o sin capacidad WhatsApp: %s",
                to_number,
            )
            return HttpResponse(status=200)

        except PhoneNumber.MultipleObjectsReturned:
            logger.error(
                "# [WHATSAPP] Múltiples PhoneNumber activos para: %s",
                to_number,
            )
            return HttpResponse(status=200)

        # --- Step 3: Resolve or create active WhatsAppSession. ---
        # --- Paso 3: Resolver o crear WhatsAppSession activa. ---
        session = WhatsAppSession.objects.filter(
            company=company,
            phone_number=from_number,
            is_active=True,
        ).order_by("-session_start").first()

        if session is None:
            session = WhatsAppSession.objects.create(
                company=company,
                phone_number=from_number,
                is_active=True,
            )
            logger.info(
                "# [WHATSAPP] Nueva sesión creada para %s — empresa: %s",
                from_number,
                company.name,
            )
        else:
            # Touch the session to refresh last_message_at (auto_now=True).
            # Tocar la sesión para refrescar last_message_at (auto_now=True).
            session.save(update_fields=["last_message_at"])

        # --- Step 4: Persist inbound message. ---
        # --- Paso 4: Persistir mensaje entrante. ---
        WhatsAppMessage.objects.create(
            session=session,
            direction=WhatsAppMessage.DIRECTION_IN,
            body=body,
        )

        # --- Step 5: Build dynamic system prompt. ---
        # --- Paso 5: Construir system prompt dinámico. ---
        system_prompt = WhatsAppChatService.build_system_prompt(
            company=company,
            to_number=to_number,
        )

        # --- Step 6: Reconstruct Gemini chat history from session messages. ---
        # --- Paso 6: Reconstruir historial de chat de Gemini desde mensajes de sesión. ---
        history = WhatsAppChatService.build_history(session)

        # --- Step 7: Obtain Gemini reply. ---
        # --- Paso 7: Obtener respuesta de Gemini. ---
        try:
            reply_text = WhatsAppChatService.get_gemini_reply(
                system_prompt=system_prompt,
                history=history,
                user_message=body,
            )
        except Exception as exc:
            logger.error(
                "# [WHATSAPP] Error obteniendo respuesta de Gemini: %s",
                exc,
            )
            reply_text = (
                "Lo sentimos, en este momento no podemos procesar tu consulta. "
                "Por favor, inténtalo de nuevo en unos instantes."
            )

        # --- Step 8: Dispatch reply via Twilio and persist outbound message. ---
        # --- Paso 8: Despachar respuesta vía Twilio y persistir mensaje saliente. ---
        try:
            message_sid = WhatsAppChatService.send_reply(
                from_number=to_number,
                to_number=from_number,
                reply_text=reply_text,
            )
            WhatsAppMessage.objects.create(
                session=session,
                direction=WhatsAppMessage.DIRECTION_OUT,
                body=reply_text,
                message_sid=message_sid,
            )

        except Exception as exc:
            logger.error(
                "# [WHATSAPP] Error enviando respuesta vía Twilio: %s",
                exc,
            )
            # Persist the outbound message even if Twilio dispatch failed,
            # so the conversation history remains coherent for Gemini context.
            # Persistir el mensaje saliente aunque el despacho Twilio haya fallado,
            # para que el historial de conversación permanezca coherente para el contexto de Gemini.
            WhatsAppMessage.objects.create(
                session=session,
                direction=WhatsAppMessage.DIRECTION_OUT,
                body=reply_text,
                message_sid="",
            )

        return HttpResponse(status=200)


# ---------------------------------------------------------------------------
# PRESENCE WHATSAPP VIEW
# Handles inbound presence reminder responses from internal CompanyUsers.
# Gestiona respuestas entrantes a recordatorios de presencia de CompanyUsers internos.
# ---------------------------------------------------------------------------

@method_decorator(csrf_exempt, name="dispatch")
class PresenceWhatsAppView(View):
    """
    Webhook endpoint: POST /api/whatsapp/presence/
    Receives inbound WhatsApp messages from internal CompanyUsers responding
    to presence reminders sent by the check_in_meeting_reminders Celery task.
    Delegates all processing logic to PresenceResponseService, which resolves
    the user, parses the response and updates the PresenceStatus accordingly.
    Sends a plain-text confirmation reply within the open 24-hour session window.
    Returns HTTP 200 with an empty body — Twilio does not require TwiML for
    WhatsApp messaging webhooks.
    ---
    Endpoint webhook: POST /api/whatsapp/presence/
    Recibe mensajes entrantes de WhatsApp de CompanyUsers internos respondiendo
    a recordatorios de presencia enviados por la tarea Celery check_in_meeting_reminders.
    Delega toda la lógica de procesamiento a PresenceResponseService, que resuelve
    el usuario, analiza la respuesta y actualiza el PresenceStatus en consecuencia.
    Envía una respuesta de confirmación en texto plano dentro de la ventana abierta
    de sesión de 24 horas. Devuelve HTTP 200 con cuerpo vacío — Twilio no requiere
    TwiML para webhooks de mensajería WhatsApp.
    """

    def post(self, request, *args, **kwargs):
        """
        Main POST handler for presence reminder responses.
        Extracts From and Body from the Twilio webhook, delegates to
        PresenceResponseService and dispatches the confirmation reply.
        ---
        Manejador POST principal para respuestas a recordatorios de presencia.
        Extrae From y Body del webhook de Twilio, delega a PresenceResponseService
        y despacha la respuesta de confirmación.
        """
        # --- Step 1: Extract Twilio webhook parameters. ---
        # --- Paso 1: Extraer parámetros del webhook de Twilio. ---
        from_number = request.POST.get("From", "").replace("whatsapp:", "")
        to_number   = request.POST.get("To", "").replace("whatsapp:", "")
        body        = request.POST.get("Body", "").strip()

        logger.info(
            "# [PRESENCE] Respuesta de presencia de %s: '%s'",
            from_number,
            body,
        )

        if not from_number or not body:
            logger.warning(
                "# [PRESENCE] Parámetros incompletos en webhook de presencia. "
                "From=%s Body=%s",
                from_number,
                repr(body),
            )
            return HttpResponse(status=200)

        # --- Step 2: Delegate processing to PresenceResponseService. ---
        # --- Paso 2: Delegar procesamiento a PresenceResponseService. ---
        confirmation_message = PresenceResponseService.process_response(
            from_number=from_number,
            body=body,
        )

        # --- Step 3: Send confirmation reply via Twilio. ---
        # --- Paso 3: Enviar respuesta de confirmación vía Twilio. ---
        try:
            WhatsAppChatService.send_reply(
                from_number=to_number,
                to_number=from_number,
                reply_text=confirmation_message,
            )
        except Exception as exc:
            logger.error(
                "# [PRESENCE] Error enviando confirmación de presencia a %s: %s",
                from_number,
                exc,
            )

        return HttpResponse(status=200)
