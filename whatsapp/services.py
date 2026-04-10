# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/whatsapp/services.py
"""
Service layer for the whatsapp channel app.
Implements WhatsAppChatService (chatbot logic via Gemini 2.5 Flash) and
PresenceResponseService (presence webhook response processing).
Both services are stateless — all state is persisted in the database and
reconstructed on each webhook invocation.
---
Capa de servicios para la app del canal WhatsApp.
Implementa WhatsAppChatService (lógica del chatbot vía Gemini 2.5 Flash) y
PresenceResponseService (procesamiento de respuestas del webhook de presencia).
Ambos servicios son sin estado — todo el estado se persiste en la base de datos
y se reconstruye en cada invocación del webhook.
"""

import logging
import os
from datetime import timedelta

from django.utils.timezone import now
from google import genai
from google.auth.transport.requests import Request
from google.oauth2 import service_account
from google.genai import types as genai_types
from twilio.rest import Client as TwilioClient

from ivr_config.models import Contact, PresenceStatus, Section
from .models import WhatsAppMessage, WhatsAppSession, WhatsAppTemplate

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# GOOGLE GENAI CLIENT FACTORY
# Authenticated Vertex AI client using Service Account JSON credentials.
# Cliente Vertex AI autenticado usando credenciales Service Account JSON.
# ---------------------------------------------------------------------------

def _build_genai_client() -> genai.Client:
    """
    Builds and returns an authenticated google-genai Client instance using
    Vertex AI Service Account JSON credentials. Reads GCP_CREDENTIALS_PATH,
    GOOGLE_CLOUD_PROJECT and GOOGLE_CLOUD_LOCATION from the environment.
    ---
    Construye y devuelve una instancia autenticada de google-genai Client usando
    credenciales Service Account JSON de Vertex AI. Lee GCP_CREDENTIALS_PATH,
    GOOGLE_CLOUD_PROJECT y GOOGLE_CLOUD_LOCATION del entorno.
    """
    credentials_path = os.environ["GCP_CREDENTIALS_PATH"]
    project          = os.environ["GOOGLE_CLOUD_PROJECT"]
    location         = os.environ["GOOGLE_CLOUD_LOCATION"]

    credentials = service_account.Credentials.from_service_account_file(
        credentials_path,
        scopes=["https://www.googleapis.com/auth/cloud-platform"],
    )
    credentials.refresh(Request())

    return genai.Client(
        vertexai=True,
        project=project,
        location=location,
        credentials=credentials,
    )


# ---------------------------------------------------------------------------
# TWILIO CLIENT FACTORY
# Authenticated Twilio REST client using API Key credentials.
# Cliente REST de Twilio autenticado usando credenciales API Key.
# ---------------------------------------------------------------------------

def _build_twilio_client() -> TwilioClient:
    """
    Builds and returns an authenticated Twilio REST Client instance using
    API Key SID and Secret from the environment. Uses TWILIO_ACCOUNT_SID,
    TWILIO_API_KEY_SID and TWILIO_API_KEY_SECRET.
    ---
    Construye y devuelve una instancia autenticada de Twilio REST Client usando
    API Key SID y Secret del entorno. Usa TWILIO_ACCOUNT_SID,
    TWILIO_API_KEY_SID y TWILIO_API_KEY_SECRET.
    """
    return TwilioClient(
        username=os.environ["TWILIO_API_KEY_SID"],
        password=os.environ["TWILIO_API_KEY_SECRET"],
        account_sid=os.environ["TWILIO_ACCOUNT_SID"],
    )


# ---------------------------------------------------------------------------
# WHATSAPP CHAT SERVICE
# Chatbot logic: system prompt construction, history reconstruction,
# Gemini invocation and Twilio reply dispatch.
# Lógica del chatbot: construcción del system prompt, reconstrucción del
# historial, invocación de Gemini y despacho de respuesta vía Twilio.
# ---------------------------------------------------------------------------

class WhatsAppChatService:
    """
    Stateless service that handles the full chatbot pipeline for an inbound
    WhatsApp message. On each invocation it:
      1. Builds a dynamic system prompt from the company's live configuration.
      2. Reconstructs the Gemini chat history from persisted WhatsAppMessage records.
      3. Sends the user message to Gemini 2.5 Flash and obtains a reply.
      4. Dispatches the reply to the user via the Twilio Messaging API.
    ---
    Servicio sin estado que gestiona el pipeline completo del chatbot para un
    mensaje entrante de WhatsApp. En cada invocación:
      1. Construye un system prompt dinámico desde la configuración viva de la empresa.
      2. Reconstruye el historial de chat de Gemini desde los registros WhatsAppMessage persistidos.
      3. Envía el mensaje del usuario a Gemini 2.5 Flash y obtiene una respuesta.
      4. Despacha la respuesta al usuario vía la API de Mensajería de Twilio.
    """

    # Gemini model for text-based WhatsApp chatbot.
    # Modelo Gemini para el chatbot de texto de WhatsApp.
    GEMINI_MODEL = "gemini-2.5-flash"

    @classmethod
    def build_system_prompt(cls, company, to_number: str) -> str:
        """
        Constructs the dynamic system prompt for the Gemini chat agent.
        Includes company identity, active sections with descriptions, internal
        contacts with their real-time PresenceStatus, and forbidden phrases
        from the CorporateVoiceProfile. Analogous to build_live_config() in
        ivr_config/services.py but oriented to text and WhatsApp.
        ---
        Construye el system prompt dinámico para el agente de chat de Gemini.
        Incluye identidad de la empresa, secciones activas con descripciones,
        contactos internos con su PresenceStatus en tiempo real, y frases
        prohibidas del CorporateVoiceProfile. Análogo a build_live_config() en
        ivr_config/services.py pero orientado a texto y WhatsApp.
        """
        lines = []

        # Company identity block.
        # Bloque de identidad de empresa.
        lines.append(f"Eres el asistente virtual de {company.name} por WhatsApp.")
        lines.append(
            "Atiendes consultas de clientes por mensajería. "
            "Tu tono es profesional, cálido y conciso. "
            "Respondes siempre en castellano salvo que el cliente se dirija a ti en otro idioma."
        )

        # Corporate voice profile — tone guidelines and forbidden phrases.
        # Perfil de voz corporativa — directrices de tono y frases prohibidas.
        try:
            profile = company.voice_profile
            if profile.is_active:
                lines.append(f"\nDIRECTRICES DE TONO:\n{profile.tone_guidelines}")
                if profile.forbidden_phrases:
                    forbidden = ", ".join(f'"{p}"' for p in profile.forbidden_phrases)
                    lines.append(f"\nFRASES PROHIBIDAS (nunca uses): {forbidden}")
        except Exception:
            # CorporateVoiceProfile may not exist for all companies.
            # CorporateVoiceProfile puede no existir para todas las empresas.
            pass

        # Active sections with descriptions.
        # Secciones activas con descripciones.
        sections = Section.objects.filter(
            company=company,
            is_active=True,
        ).prefetch_related("contacts")

        if sections.exists():
            lines.append("\nDEPARTAMENTOS Y SERVICIOS:")
            for section in sections:
                lines.append(f"\n— {section.name}: {section.description}")

        # Internal contacts with real-time presence status.
        # Contactos internos con estado de presencia en tiempo real.
        internal_contacts = Contact.objects.filter(
            company=company,
            is_internal=True,
        ).select_related("company_user")

        if internal_contacts.exists():
            lines.append("\nPERSONAL INTERNO Y DISPONIBILIDAD:")
            for contact in internal_contacts:
                presence_label = cls._get_presence_label(contact)
                lines.append(f"\n— {contact.name}: {presence_label}")

        # Behavioural rules.
        # Reglas de comportamiento.
        lines.append(
            "\nREGLAS GENERALES:"
            "\n- Nunca inventes información que no figure en este contexto."
            "\n- Nunca menciones que eres una inteligencia artificial salvo que "
            "el cliente te lo pregunte directamente."
            "\n- Sé conciso: no des explicaciones innecesarias."
            "\n- Si no puedes resolver la consulta, ofrece tomar nota y que un "
            "responsable se ponga en contacto."
        )

        return "\n".join(lines)

    @staticmethod
    def _get_presence_label(contact) -> str:
        """
        Returns a human-readable availability label for an internal contact
        based on their most recent active PresenceStatus record.
        ---
        Devuelve una etiqueta de disponibilidad legible para un contacto interno
        basada en su registro PresenceStatus activo más reciente.
        """
        try:
            status = PresenceStatus.objects.filter(
                company_user=contact.company_user,
            ).filter(
                starts_at__lte=now(),
            ).filter(
                models.Q(ends_at__isnull=True) | models.Q(ends_at__gt=now())
            ).latest("starts_at")

            label_map = {
                PresenceStatus.STATUS_AVAILABLE:        "Disponible",
                PresenceStatus.STATUS_IN_MEETING:       "Reunido/a",
                PresenceStatus.STATUS_BUSY_UNTIL:       f"Ocupado/a hasta {status.ends_at:%H:%M}",
                PresenceStatus.STATUS_ABSENT_SCHEDULED: "Ausente (programado)",
                PresenceStatus.STATUS_ABSENT_VACATION:  "De vacaciones",
            }
            return label_map.get(status.status, "Estado desconocido")

        except PresenceStatus.DoesNotExist:
            return "Disponible"

    @classmethod
    def build_history(cls, session: WhatsAppSession) -> list:
        """
        Reconstructs the Gemini chat history from all WhatsAppMessage records
        belonging to the given session, ordered chronologically. Returns a list
        of genai_types.Content objects compatible with client.chats.create(history=...).
        ---
        Reconstruye el historial de chat de Gemini desde todos los registros
        WhatsAppMessage pertenecientes a la sesión dada, ordenados cronológicamente.
        Devuelve una lista de objetos genai_types.Content compatible con
        client.chats.create(history=...).
        """
        history = []
        messages = session.messages.order_by("timestamp")

        for msg in messages:
            # Map WhatsApp direction to Gemini role.
            # Mapear dirección de WhatsApp al rol de Gemini.
            role = "user" if msg.direction == WhatsAppMessage.DIRECTION_IN else "model"
            history.append(
                genai_types.Content(
                    role=role,
                    parts=[genai_types.Part(text=msg.body)],
                )
            )

        return history

    @classmethod
    def get_gemini_reply(
        cls,
        system_prompt: str,
        history: list,
        user_message: str,
    ) -> str:
        """
        Sends the user message to Gemini 2.5 Flash via Vertex AI, providing
        the dynamic system prompt and reconstructed session history as context.
        Returns the model's plain-text reply.
        ---
        Envía el mensaje del usuario a Gemini 2.5 Flash vía Vertex AI, proporcionando
        el system prompt dinámico y el historial de sesión reconstruido como contexto.
        Devuelve la respuesta en texto plano del modelo.
        """
        client = _build_genai_client()

        chat = client.chats.create(
            model=cls.GEMINI_MODEL,
            config=genai_types.GenerateContentConfig(
                system_instruction=system_prompt,
            ),
            history=history,
        )

        response = chat.send_message(user_message)
        return response.text

    @classmethod
    def send_reply(
        cls,
        from_number: str,
        to_number: str,
        reply_text: str,
    ) -> str:
        """
        Dispatches a plain-text reply message to the user via the Twilio
        Messaging API using the whatsapp: URI scheme prefix. Returns the
        Twilio message SID for persistence in WhatsAppMessage.message_sid.
        ---
        Despacha un mensaje de respuesta en texto plano al usuario vía la API
        de Mensajería de Twilio usando el prefijo de esquema URI whatsapp:.
        Devuelve el SID del mensaje Twilio para persistencia en
        WhatsAppMessage.message_sid.
        """
        twilio_client = _build_twilio_client()

        message = twilio_client.messages.create(
            from_=f"whatsapp:{from_number}",
            to=f"whatsapp:{to_number}",
            body=reply_text,
        )

        logger.info(
            "# [WHATSAPP] Respuesta enviada a %s — SID: %s",
            to_number,
            message.sid,
        )
        return message.sid


# ---------------------------------------------------------------------------
# PRESENCE RESPONSE SERVICE
# Processes inbound presence webhook responses (1h / 2h / disponible).
# Procesa las respuestas entrantes del webhook de presencia (1h / 2h / disponible).
# ---------------------------------------------------------------------------

class PresenceResponseService:
    """
    Stateless service that processes the user's response to a presence reminder
    sent by the check_in_meeting_reminders Celery task. Parses the body of the
    inbound WhatsApp message ('1h', '2h' or 'disponible') and updates the
    CompanyUser's active PresenceStatus accordingly.
    ---
    Servicio sin estado que procesa la respuesta del usuario a un recordatorio
    de presencia enviado por la tarea Celery check_in_meeting_reminders. Analiza
    el cuerpo del mensaje entrante de WhatsApp ('1h', '2h' o 'disponible') y
    actualiza el PresenceStatus activo del CompanyUser en consecuencia.
    """

    # Canonical recognised responses and their hour deltas.
    # Respuestas canónicas reconocidas y sus deltas en horas.
    RESPONSE_1H          = "1h"
    RESPONSE_2H          = "2h"
    RESPONSE_AVAILABLE   = "disponible"

    VALID_RESPONSES = {RESPONSE_1H, RESPONSE_2H, RESPONSE_AVAILABLE}

    @classmethod
    def process_response(cls, from_number: str, body: str) -> str:
        """
        Main entry point. Identifies the CompanyUser from the inbound phone
        number, parses the response body and updates the PresenceStatus.
        Returns a confirmation message string to be sent back to the user.
        ---
        Punto de entrada principal. Identifica al CompanyUser a partir del
        número de teléfono entrante, analiza el cuerpo de la respuesta y
        actualiza el PresenceStatus. Devuelve una cadena de mensaje de
        confirmación para enviar de vuelta al usuario.
        """
        # Normalise response: strip whitespace and lowercase.
        # Normalizar respuesta: eliminar espacios y convertir a minúsculas.
        normalised = body.strip().lower()

        if normalised not in cls.VALID_RESPONSES:
            logger.warning(
                "# [PRESENCE] Respuesta no reconocida de %s: '%s'",
                from_number,
                body,
            )
            return (
                "No he reconocido tu respuesta. "
                "Por favor, responde con: 1h, 2h o disponible."
            )

        # Resolve CompanyUser from Contact phone number.
        # Resolver CompanyUser desde el número de teléfono del Contact.
        try:
            contact = Contact.objects.select_related("company_user").get(
                phone_number=from_number,
                is_internal=True,
            )
        except Contact.DoesNotExist:
            logger.error(
                "# [PRESENCE] Contact interno no encontrado para número: %s",
                from_number,
            )
            return "No se ha podido identificar tu usuario. Contacta con el administrador."
        except Contact.MultipleObjectsReturned:
            logger.error(
                "# [PRESENCE] Múltiples Contact internos para número: %s",
                from_number,
            )
            return "Error de configuración. Contacta con el administrador."

        company_user = contact.company_user
        if company_user is None:
            logger.error(
                "# [PRESENCE] Contact %s no tiene company_user vinculado.",
                from_number,
            )
            return "Error de configuración. Contacta con el administrador."

        return cls._apply_response(company_user, normalised)

    @classmethod
    def _apply_response(cls, company_user, normalised: str) -> str:
        """
        Applies the parsed presence response to the CompanyUser's active
        PresenceStatus record. Closes the current IN_MEETING status and
        creates a new one if extending, or creates AVAILABLE if done.
        ---
        Aplica la respuesta de presencia analizada al registro PresenceStatus
        activo del CompanyUser. Cierra el estado IN_MEETING actual y crea uno
        nuevo si se extiende, o crea AVAILABLE si ha finalizado.
        """
        current_time = now()

        # Close any currently open PresenceStatus for this user.
        # Cerrar cualquier PresenceStatus abierto actualmente para este usuario.
        open_statuses = PresenceStatus.objects.filter(
            company_user=company_user,
            ends_at__isnull=True,
        )
        open_statuses.update(ends_at=current_time)

        if normalised == cls.RESPONSE_AVAILABLE:
            # User is now available — create AVAILABLE status.
            # El usuario ya está disponible — crear estado AVAILABLE.
            PresenceStatus.objects.create(
                company_user=company_user,
                status=PresenceStatus.STATUS_AVAILABLE,
                starts_at=current_time,
            )
            logger.info(
                "# [PRESENCE] %s marcado como AVAILABLE.",
                company_user,
            )
            return "✅ Perfecto, te hemos marcado como disponible."

        # User is still busy — determine extension duration.
        # El usuario sigue ocupado — determinar duración de la extensión.
        hours = 1 if normalised == cls.RESPONSE_1H else 2
        new_ends_at = current_time + timedelta(hours=hours)

        PresenceStatus.objects.create(
            company_user=company_user,
            status=PresenceStatus.STATUS_IN_MEETING,
            starts_at=current_time,
            ends_at=new_ends_at,
        )

        logger.info(
            "# [PRESENCE] %s extendido IN_MEETING %sh hasta %s.",
            company_user,
            hours,
            new_ends_at.strftime("%H:%M"),
        )
        return (
            f"⏳ Entendido, seguirás como ocupado/a durante {hours} hora(s) más. "
            f"Te avisaremos de nuevo si es necesario."
        )
