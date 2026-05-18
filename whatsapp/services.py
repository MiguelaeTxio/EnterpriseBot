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

from django.db.models import Q
from django.utils.timezone import now
from google import genai
from google.auth.transport.requests import Request
from google.oauth2 import service_account
from google.genai import types as genai_types
from google.genai.types import (
    GoogleMaps,
    HttpOptions,
    LatLng,
    RetrievalConfig,
    ToolConfig,
)
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
# GOOGLE GENAI CLIENT FACTORY — MAPS GROUNDING
# Authenticated Vertex AI client with api_version="v1", required for
# Grounding with Google Maps (Paso 20). Uses identical Service Account
# credentials as _build_genai_client().
# Cliente Vertex AI autenticado con api_version="v1", obligatorio para
# Grounding con Google Maps (Paso 20). Usa las mismas credenciales de
# Service Account que _build_genai_client().
# ---------------------------------------------------------------------------

def _build_genai_client_maps() -> genai.Client:
    """
    Builds and returns an authenticated google-genai Client instance with
    api_version="v1", which is required by the Grounding with Google Maps
    feature in Vertex AI. Credentials and project configuration are identical
    to _build_genai_client(). Used exclusively by get_gemini_reply() when
    Maps Grounding is activated.
    ---
    Construye y devuelve una instancia autenticada de google-genai Client con
    api_version="v1", obligatorio para la funcionalidad Grounding with Google
    Maps en Vertex AI. Las credenciales y la configuración de proyecto son
    idénticas a _build_genai_client(). Usado exclusivamente por
    get_gemini_reply() cuando se activa Maps Grounding.
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
        http_options=HttpOptions(api_version="v1"),
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
    def build_system_prompt(
        cls,
        company,
        to_number: str,
        session=None,
    ) -> str:
        """
        Constructs the dynamic system prompt for the Gemini chat agent.
        Includes company identity, active sections with descriptions, internal
        contacts with their real-time PresenceStatus, and forbidden phrases
        from the CorporateVoiceProfile. Analogous to build_live_config() in
        ivr_config/services.py but oriented to text and WhatsApp.

        If session is provided and contains geographic coordinates
        (session.latitude is not None), a location context block is injected
        into the prompt so the agent is aware of the client's position.
        This enables location-aware responses and is a prerequisite for
        Grounding with Google Maps (Paso 20).
        ---
        Construye el system prompt dinámico para el agente de chat de Gemini.
        Incluye identidad de la empresa, secciones activas con descripciones,
        contactos internos con su PresenceStatus en tiempo real, y frases
        prohibidas del CorporateVoiceProfile. Análogo a build_live_config() en
        ivr_config/services.py pero orientado a texto y WhatsApp.

        Si session se proporciona y contiene coordenadas geográficas
        (session.latitude no es None), se inyecta un bloque de contexto de
        ubicación en el prompt para que el agente sea consciente de la posición
        del cliente. Esto habilita respuestas con conciencia de ubicación y es
        un prerequisito para Grounding con Google Maps (Paso 20).

        Args:
            company: Instancia de Company — empresa destino de la sesión.
            to_number (str): Número Twilio destino en formato E.164.
            session (WhatsAppSession | None): Sesión activa del cliente. Si se
                proporciona y tiene coordenadas, se inyecta el bloque de ubicación.
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

        # Geographic location context block — Paso 19 (2026-04-16).
        # Injected only when the session contains valid coordinates. The agent
        # uses this information to provide location-aware responses (e.g. nearest
        # workshop, estimated travel distance). The location_address field is
        # included when available — it may be populated by Grounding with Google
        # Maps in Paso 20.
        # Bloque de contexto de ubicación geográfica — Paso 19 (2026-04-16).
        # Se inyecta únicamente cuando la sesión contiene coordenadas válidas.
        # El agente usa esta información para proporcionar respuestas con
        # conciencia de ubicación (p. ej. taller más cercano, distancia estimada).
        # El campo location_address se incluye cuando está disponible — puede
        # rellenarse mediante Grounding con Google Maps en el Paso 20.
        if session is not None and session.latitude is not None:
            location_lines = [
                "\nUBICACIÓN DEL CLIENTE:",
                f"— Coordenadas: {session.latitude}, {session.longitude}",
            ]
            if session.location_address:
                location_lines.append(
                    f"— Dirección aproximada: {session.location_address}"
                )
            if session.location_captured_at:
                location_lines.append(
                    f"— Capturada en: {session.location_captured_at.strftime('%H:%M')}"
                )
            location_lines.append(
                "Usa esta información para dar respuestas orientadas a la "
                "ubicación del cliente cuando sea relevante."
            )
            lines.extend(location_lines)
            logger.debug(
                "# [WHATSAPP] Bloque de ubicación inyectado en system prompt "
                "para sesión %s: lat=%s lon=%s",
                session.pk,
                session.latitude,
                session.longitude,
            )

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

        # Target section detection instruction block — Paso 21 (2026-04-20).
        # When the agent identifies that the client wants to be directed to a
        # specific company section, it must append a strict JSON marker at the
        # very end of its response. The marker is parsed and stripped by
        # IncomingWhatsAppView before the reply is sent to the user.
        # The list of valid section names is injected here so the agent does
        # not hallucinate section names outside those defined in the company.
        # Bloque de instrucción de detección de sección destino — Paso 21 (2026-04-20).
        # Cuando el agente identifica que el cliente desea ser dirigido a una
        # sección concreta de la empresa, debe añadir un marcador JSON estricto
        # al final de su respuesta. El marcador es parseado y eliminado por
        # IncomingWhatsAppView antes de enviar la respuesta al usuario.
        # La lista de nombres de sección válidos se inyecta aquí para que el
        # agente no invente nombres de sección fuera de los definidos en la empresa.
        section_names = [s.name for s in sections] if sections.exists() else []
        if section_names:
            valid_names_str = ", ".join(f'"{n}"' for n in section_names)
            lines.append(
                "\nDETECCIÓN DE SECCIÓN DESTINO:"
                "\nCuando el cliente exprese con claridad que desea ser atendido "
                "por o dirigido a una sección concreta de la empresa, añade AL FINAL "
                "de tu respuesta — y solo al final, sin texto posterior — el "
                "siguiente marcador JSON en una línea propia:"
                "\n[TARGET_SECTION:{\"name\": \"NOMBRE_SECCIÓN\"}]"
                f"\nSecciones válidas (usa el nombre exacto): {valid_names_str}."
                "\nSolo incluye el marcador cuando la intención del cliente sea "
                "inequívoca. No lo incluyas en respuestas informativas generales."
                "\nEjemplo correcto: si el cliente dice 'quiero hablar con Grúas' "
                "y existe una sección llamada 'Grúas', añade al final:"
                "\n[TARGET_SECTION:{\"name\": \"Grúas\"}]"
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
                Q(ends_at__isnull=True) | Q(ends_at__gt=now())
            ).latest("starts_at")

            label_map = {
                PresenceStatus.STATUS_AVAILABLE:        "Disponible",
                PresenceStatus.STATUS_IN_MEETING:       "Reunido/a",
                PresenceStatus.STATUS_BUSY_UNTIL:       f"Ocupado/a hasta {status.ends_at.strftime('%H:%M') if status.ends_at else 'hora desconocida'}",
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

    # Keywords that trigger Maps Grounding even without explicit coordinates.
    # Palabras clave que activan Maps Grounding incluso sin coordenadas explícitas.
    GEO_KEYWORDS = (
        "dónde", "donde", "cómo llegar", "como llegar", "dirección",
        "ubicación", "ubicacion", "cerca", "cercano", "mapa", "ruta",
        "distancia", "kilómetros", "kilometros", "metros", "taller",
        "instalaciones", "oficina", "sede", "local",
    )

    @classmethod
    def _should_use_maps_grounding(
        cls,
        session,
        user_message: str,
    ) -> bool:
        """
        Determines whether Grounding with Google Maps should be activated for
        the current invocation. Returns True when:
          - The session contains valid geographic coordinates (latitude is not
            None), OR
          - The user message contains one or more geographic reference keywords
            defined in GEO_KEYWORDS.
        Both conditions are evaluated independently (OR logic).
        ---
        Determina si Grounding con Google Maps debe activarse para la invocación
        actual. Devuelve True cuando:
          - La sesión contiene coordenadas geográficas válidas (latitude no es
            None), O
          - El mensaje del usuario contiene una o más palabras clave de referencia
            geográfica definidas en GEO_KEYWORDS.
        Ambas condiciones se evalúan de forma independiente (lógica OR).

        Args:
            session: Instancia de WhatsAppSession o None.
            user_message (str): Texto del mensaje entrante del usuario.

        Returns:
            bool: True si Maps Grounding debe activarse, False en caso contrario.
        """
        if session is not None and session.latitude is not None:
            return True
        message_lower = user_message.lower()
        return any(keyword in message_lower for keyword in cls.GEO_KEYWORDS)

    @classmethod
    def get_gemini_reply(
        cls,
        system_prompt: str,
        history: list,
        user_message: str,
        session=None,
    ) -> str:
        """
        Sends the user message to Gemini 2.5 Flash via Vertex AI, providing
        the dynamic system prompt and reconstructed session history as context.
        Returns the model's plain-text reply.

        When Maps Grounding is applicable (session has coordinates or user
        message contains geographic keywords), the call is made via a separate
        client instantiated with api_version="v1" and the GoogleMaps tool is
        injected into the GenerateContentConfig. If the session contains valid
        coordinates, they are passed via RetrievalConfig.lat_lng so that Gemini
        grounds its response against the client's actual position. The language
        code is set to "es-ES" for Grupo Álvarez's operational context.
        ---
        Envía el mensaje del usuario a Gemini 2.5 Flash vía Vertex AI,
        proporcionando el system prompt dinámico y el historial de sesión
        reconstruido como contexto. Devuelve la respuesta en texto plano del
        modelo.

        Cuando Maps Grounding es aplicable (la sesión tiene coordenadas o el
        mensaje contiene palabras clave geográficas), la llamada se realiza vía
        un cliente instanciado con api_version="v1" y el tool GoogleMaps se
        inyecta en GenerateContentConfig. Si la sesión contiene coordenadas
        válidas, se pasan vía RetrievalConfig.lat_lng para que Gemini ancle su
        respuesta a la posición real del cliente. El language_code se fija a
        "es-ES" para el contexto operacional de Grupo Álvarez.

        Args:
            system_prompt (str): System prompt dinámico construido por
                build_system_prompt().
            history (list): Historial de chat reconstruido por build_history().
            user_message (str): Texto del mensaje entrante del usuario.
            session (WhatsAppSession | None): Sesión activa. Se usa para
                determinar si activar Maps Grounding y para extraer coordenadas.

        Returns:
            str: Texto plano de la respuesta del modelo.
        """
        use_maps = cls._should_use_maps_grounding(session, user_message)

        if use_maps:
            # ------------------------------------------------------------------
            # Maps Grounding branch: api_version="v1" client + GoogleMaps tool.
            # Rama Maps Grounding: cliente con api_version="v1" + tool GoogleMaps.
            # ------------------------------------------------------------------
            logger.info(
                "# [WHATSAPP] Activando Maps Grounding para sesión %s — "
                "coordenadas: %s/%s — keywords: %s",
                session.pk if session else "sin-sesión",
                session.latitude if session else "N/A",
                session.longitude if session else "N/A",
                not (session is not None and session.latitude is not None),
            )

            client = _build_genai_client_maps()

            # Build tool_config: include lat/lng only when coordinates are
            # available in the session. Keyword-only activation uses the Maps
            # tool without explicit coordinates — Gemini infers location from
            # context.
            # Construir tool_config: incluir lat/lng solo cuando hay coordenadas
            # disponibles en la sesión. La activación solo por keywords usa el
            # tool Maps sin coordenadas explícitas — Gemini infiere ubicación
            # del contexto.
            if session is not None and session.latitude is not None:
                tool_config = ToolConfig(
                    retrieval_config=RetrievalConfig(
                        lat_lng=LatLng(
                            latitude=float(session.latitude),
                            longitude=float(session.longitude),
                        ),
                        language_code="es-ES",
                    )
                )
            else:
                tool_config = ToolConfig(
                    retrieval_config=RetrievalConfig(
                        language_code="es-ES",
                    )
                )

            chat = client.chats.create(
                model=cls.GEMINI_MODEL,
                config=genai_types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    tools=[genai_types.Tool(google_maps=GoogleMaps(enable_widget=False))],
                    tool_config=tool_config,
                ),
                history=history,
            )

        else:
            # ------------------------------------------------------------------
            # Standard branch: no Maps Grounding.
            # Rama estándar: sin Maps Grounding.
            # ------------------------------------------------------------------
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

    @classmethod
    def send_quick_reply(
        cls,
        from_number: str,
        to_number: str,
        content_sid: str,
        content_variables: dict,
    ) -> str:
        """
        Sends a WhatsApp quick-reply message using a pre-registered Twilio
        Content Template identified by content_sid. The template must exist
        in the Twilio account (created via Content Template Builder or Content
        API) and must NOT have been submitted for Meta approval, so it can be
        sent in-session without approval within the 24-hour window.

        content_variables is a dict mapping variable placeholders to their
        runtime values, e.g. {"1": "MiguelTxio"}. It is serialised to a JSON
        string before being passed to the Twilio Messages API, as required by
        the SDK.

        If messages.create() fails for any reason, the method raises the
        exception so the caller (_handle_alias_collection) can handle it and
        fall back to a plain-text reply via send_reply().

        Returns the Twilio message SID on success.
        ---
        Envía un mensaje de WhatsApp de respuesta rápida usando un Content
        Template de Twilio pre-registrado identificado por content_sid. El
        template debe existir en la cuenta de Twilio (creado vía Content
        Template Builder o Content API) y NO debe haber sido enviado a
        aprobación de Meta, para poder enviarse en sesión sin aprobación
        dentro de la ventana de 24 horas.

        content_variables es un dict que mapea los placeholders de variables
        a sus valores en tiempo de ejecución, p. ej. {"1": "MiguelTxio"}.
        Se serializa a cadena JSON antes de pasarse a la API de Mensajes de
        Twilio, tal como requiere el SDK.

        Si messages.create() falla por cualquier motivo, el método relanza
        la excepción para que el llamador (_handle_alias_collection) pueda
        gestionarla y caer a un reply de texto plano vía send_reply().

        Devuelve el SID del mensaje Twilio en caso de éxito.
        """
        import json

        twilio_client = _build_twilio_client()

        message = twilio_client.messages.create(
            from_=f"whatsapp:{from_number}",
            to=f"whatsapp:{to_number}",
            content_sid=content_sid,
            content_variables=json.dumps(content_variables),
        )
        logger.info(
            "# [WHATSAPP] Quick Reply enviado a %s — SID: %s",
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

# ---------------------------------------------------------------------------
# CAPTURE NOTIFICATION SERVICE
# Sends a structured IVR capture summary to the section's referent contact
# via WhatsApp using the ivr_capture_notification Meta-approved template.
# Envia un resumen estructurado de captura IVR al contacto referente de la
# seccion via WhatsApp usando el template aprobado por Meta ivr_capture_notification.
# ---------------------------------------------------------------------------

def send_capture_notification(
    call_data_capture,
    whatsapp_sender: str,
) -> bool:
    """
    Sends a WhatsApp notification to the referent contact of the section
    using the Meta-approved UTILITY template 'ivr_capture_notification'.
    The template variables are populated from the CallDataCapture instance:
      {{1}} section name, {{2}} captured name, {{3}} captured phone,
      {{4}} captured reason/motive.
    Updates CallDataCapture.notified_via_whatsapp and whatsapp_sent_at
    on successful delivery. Returns True on success, False on failure.
    This function is synchronous and designed to be called via
    asyncio.create_task(asyncio.to_thread(send_capture_notification, ...))
    from the async voice bridge context.
    ---
    Envia una notificacion WhatsApp al contacto referente de la seccion
    usando el template UTILITY aprobado por Meta 'ivr_capture_notification'.
    Las variables del template se rellenan desde la instancia CallDataCapture:
      {{1}} nombre de seccion, {{2}} nombre capturado, {{3}} telefono capturado,
      {{4}} motivo capturado.
    Actualiza CallDataCapture.notified_via_whatsapp y whatsapp_sent_at
    en caso de entrega exitosa. Devuelve True en exito, False en fallo.
    Esta funcion es sincrona y esta disenada para ser invocada mediante
    asyncio.create_task(asyncio.to_thread(send_capture_notification, ...))
    desde el contexto async del voice bridge.
    """
    from ivr_config.models import CallDataCapture as _CDC

    contact = call_data_capture.contact
    section = call_data_capture.section

    # Guard: contact must exist and have a phone number.
    # Guardia: el contacto debe existir y tener numero de telefono.
    if not contact or not contact.phone_number:
        logger.warning(
            "# [CAPTURE NOTIFY] CallDataCapture %s sin contacto o telefono. Abortando.",
            call_data_capture.pk,
        )
        return False

    # Resolve template from DB for the contact's company.
    # Resolver el template desde BD para la empresa del contacto.
    try:
        template = WhatsAppTemplate.objects.get(
            company=contact.company,
            name="ivr_capture_notification",
            is_active=True,
        )
    except WhatsAppTemplate.DoesNotExist:
        logger.error(
            "# [CAPTURE NOTIFY] Template ivr_capture_notification no encontrado "
            "para empresa %s. Abortando.",
            contact.company.name,
        )
        return False

    # Extract captured data fields with safe fallbacks.
    # Extraer campos de datos capturados con fallbacks seguros.
    captured = call_data_capture.captured_data or {}
    section_name    = section.name if section else "sin seccion"
    captured_name   = captured.get("nombre",   captured.get("name",   "No informado"))
    captured_phone  = captured.get("telefono", captured.get("phone",  "No informado"))
    captured_motive = captured.get("motivo",   captured.get("motive", "No informado"))

    # Build Twilio Content Template API payload.
    # Construir el payload de la API Content Template de Twilio.
    try:
        twilio_client = _build_twilio_client()
        message = twilio_client.messages.create(
            from_=f"whatsapp:{whatsapp_sender}",
            to=f"whatsapp:{contact.phone_number}",
            content_sid=template.content_sid,
            content_variables={
                "1": section_name,
                "2": captured_name,
                "3": captured_phone,
                "4": captured_motive,
            },
        )
        logger.info(
            "# [CAPTURE NOTIFY] Notificacion enviada a %s — SID: %s",
            contact.phone_number,
            message.sid,
        )
    except Exception as exc:
        logger.error(
            "# [CAPTURE NOTIFY] Error al enviar notificacion a %s: %s",
            contact.phone_number,
            exc,
        )
        return False

    # Mark capture as notified.
    # Marcar la captura como notificada.
    call_data_capture.notified_via_whatsapp = True
    call_data_capture.whatsapp_sent_at = now()
    call_data_capture.save(update_fields=["notified_via_whatsapp", "whatsapp_sent_at"])

    return True
