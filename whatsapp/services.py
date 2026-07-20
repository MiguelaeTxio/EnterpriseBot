
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

        Excludes the current inbound turn when it is the most recent message
        in the session: every caller of this method persists the incoming
        WhatsAppMessage BEFORE building the history, and then sends that same
        turn again explicitly via chat.send_message(user_message). Without
        this exclusion, Gemini would receive the current user turn twice in a
        row (once from history, once from send_message) — bug detected in
        production on 2026-07-09 (S010, H17): Gemini reported the user's DNI
        as "written twice" during onboarding, when it had only been sent once.
        ---
        Reconstruye el historial de chat de Gemini desde todos los registros
        WhatsAppMessage pertenecientes a la sesión dada, ordenados cronológicamente.
        Devuelve una lista de objetos genai_types.Content compatible con
        client.chats.create(history=...).

        Excluye el turno entrante actual cuando es el mensaje más reciente de
        la sesión: todo llamador de este método persiste el WhatsAppMessage
        entrante ANTES de construir el historial, y luego reenvía ese mismo
        turno explícitamente vía chat.send_message(user_message). Sin esta
        exclusión, Gemini recibiría el turno actual del usuario dos veces
        seguidas (una desde el historial, otra desde send_message) — bug
        detectado en producción el 2026-07-09 (S010, H17): Gemini informó de
        que el DNI del usuario estaba "escrito dos veces" durante el
        onboarding, cuando en realidad solo se había enviado una vez.
        """
        history = []
        messages = list(session.messages.order_by("timestamp"))

        if messages and messages[-1].direction == WhatsAppMessage.DIRECTION_IN:
            messages = messages[:-1]

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

    @classmethod
    def send_template(
        cls,
        from_number: str,
        to_number: str,
        content_sid: str,
        content_variables: dict,
    ) -> str:
        """
        Sends a Meta-approved WhatsApp template message via the Twilio
        Messaging API. Used for out-of-session messages (renewal, breakdown
        card notification) that require a pre-approved Content Template.

        content_variables is a dict mapping variable placeholders to their
        runtime values, e.g. {"1": "Alejandro", "2": "Grupo Álvarez"}.
        It is serialised to a JSON string as required by the Twilio SDK.

        Returns the Twilio message SID on success.
        ---
        Envía un template de WhatsApp aprobado por Meta vía la API de
        Mensajería de Twilio. Usado para mensajes fuera de sesión (renewal,
        notificación de tarjeta de avería) que requieren un Content Template
        pre-aprobado.

        content_variables es un dict que mapea los placeholders de variables
        a sus valores en tiempo de ejecución, p. ej. {"1": "Alejandro"}.
        Se serializa a cadena JSON tal como requiere el SDK de Twilio.

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
            "# [WHATSAPP] Template enviado a %s — SID: %s",
            to_number,
            message.sid,
        )
        return message.sid

    @classmethod
    def send_breakdown_broadcast(
        cls,
        ticket,
        wa_sender: str,
    ) -> None:
        """
        Sends the breakdown_broadcast WhatsApp template to all active
        Contacts in the company that belong to a Section with
        ivr_breakdown_enabled=True, excluding the contact who reported
        the breakdown (ticket.contact).

        Variables for breakdown_broadcast:
            {{1}} recipient name
            {{2}} machine (machine_raw or machine code)
            {{3}} fault summary
            {{4}} location (base name or 'en ruta')

        Errors are logged and never re-raised — broadcast failure must
        never block the main breakdown flow.
        ---
        Envía la plantilla breakdown_broadcast por WhatsApp a todos los
        Contacts activos de la empresa que pertenezcan a una Section con
        ivr_breakdown_enabled=True, excluyendo al contacto que reportó
        la avería (ticket.contact).

        Los errores se registran y nunca se propagan — el fallo del
        broadcast nunca debe bloquear el flujo principal de avería.
        """
        import os as _os

        from ivr_config.models import (
            Contact as _Contact,
            SectionContact as _SC,
            Section as _Sec,
        )
        from whatsapp.models import WhatsAppTemplate as _WATpl

        try:
            tpl = _WATpl.objects.filter(
                company=ticket.company,
                name="breakdown_broadcast",
                is_active=True,
            ).first()
            if tpl is None:
                logger.warning(
                    "# [BROADCAST] Plantilla breakdown_broadcast no encontrada "
                    "para empresa pk=%s — broadcast omitido.",
                    ticket.company_id,
                )
                return

            # Resolve breakdown sections with broadcast enabled.
            # Resolver secciones con broadcast de averías habilitado.
            breakdown_sections = _Sec.objects.filter(
                company=ticket.company,
                is_active=True,
                ivr_breakdown_enabled=True,
            )
            if not breakdown_sections.exists():
                logger.info(
                    "# [BROADCAST] Sin secciones ivr_breakdown_enabled en "
                    "empresa pk=%s — broadcast omitido.",
                    ticket.company_id,
                )
                return

            # Collect recipients: Contacts in breakdown sections,
            # excluding the reporting contact and those without a phone.
            # Recopilar destinatarios: Contacts en secciones de avería,
            # excluyendo al contact que reporta y los sin teléfono.
            recipient_contacts = _Contact.objects.filter(
                company=ticket.company,
                is_internal=True,
                section_contacts__section__in=breakdown_sections,
            ).exclude(
                pk=ticket.contact_id,
            ).filter(
                phone_number__isnull=False,
            ).exclude(
                phone_number="",
            ).distinct()

            if not recipient_contacts.exists():
                logger.info(
                    "# [BROADCAST] Sin destinatarios para broadcast "
                    "ticket pk=%s — omitido.",
                    ticket.pk,
                )
                return

            # Build template variable values from ticket fields.
            # Construir valores de variables de plantilla desde el ticket.
            machine_label = (
                ticket.machine_raw
                or (ticket.machine.code if ticket.machine else "")
                or "desconocida"
            )
            fault_label = ticket.fault_summary or "sin descripción"
            location_label = ticket.location or "en ruta"

            sent_count = 0
            error_count = 0
            for recipient in recipient_contacts:
                try:
                    cls.send_template(
                        from_number=wa_sender,
                        to_number=recipient.phone_number,
                        content_sid=tpl.content_sid,
                        content_variables={
                            "1": recipient.name or "trabajador",
                            "2": machine_label,
                            "3": fault_label,
                            "4": location_label,
                        },
                    )
                    sent_count += 1
                except Exception as _exc:
                    error_count += 1
                    logger.error(
                        "# [BROADCAST] Error enviando broadcast a %s "
                        "(ticket pk=%s): %s",
                        recipient.phone_number,
                        ticket.pk,
                        _exc,
                    )

            logger.info(
                "# [BROADCAST] Broadcast ticket pk=%s completado — "
                "enviados=%d errores=%d.",
                ticket.pk,
                sent_count,
                error_count,
            )

        except Exception as exc:
            logger.error(
                "# [BROADCAST] Error inesperado en send_breakdown_broadcast "
                "ticket pk=%s: %s",
                ticket.pk,
                exc,
            )


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
    #
    # json.dumps() obligatorio (hallazgo real S025, mismo bug que en
    # document_management.alert_service.send_alert_now -- confirmado
    # contra la documentación actual de Twilio, error 21656: "Send
    # ContentVariables as a JSON string"). Esta función llama a
    # messages.create() DIRECTAMENTE en vez de pasar por
    # WhatsAppContentService.send_template()/send_quick_reply() (que sí
    # lo hacían bien, ver esos métodos más arriba en este mismo
    # archivo) -- por eso el bug pasó desapercibido hasta ahora: nunca
    # se detectó porque el except Exception de abajo lo capturaba en
    # silencio (solo quedaba en el log, nunca visible en el panel), y
    # nadie había comprobado en producción si esta notificación
    # concreta (tras captura de datos IVR) llegaba a enviarse de
    # verdad.
    import json

    try:
        twilio_client = _build_twilio_client()
        message = twilio_client.messages.create(
            from_=f"whatsapp:{whatsapp_sender}",
            to=f"whatsapp:{contact.phone_number}",
            content_sid=template.content_sid,
            content_variables=json.dumps({
                "1": section_name,
                "2": captured_name,
                "3": captured_phone,
                "4": captured_motive,
            }),
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


# ---------------------------------------------------------------------------
# OPERATOR ALBARAN NOTIFICATION SERVICE
# Sends the chat_session_renewal template to an operator's WhatsApp number
# to open the 24-hour session window. Queues the WorkOrderAssistanceUnit PKs
# in WhatsAppSession.pending_albaran_units so the opt_in webhook branch can
# deliver the albarán link once the operator responds.
# Envía el template chat_session_renewal al número WhatsApp del operario para
# abrir la ventana de sesión de 24 horas. Encola los PKs de
# WorkOrderAssistanceUnit en WhatsAppSession.pending_albaran_units para que
# la rama opt_in del webhook pueda entregar el enlace al albarán cuando el
# operario responda.
# ---------------------------------------------------------------------------

def send_operator_albaran_notification(
    unit_pk: int,
    whatsapp_sender: str,
) -> bool:
    """
    Sends the 'chat_session_renewal' WhatsApp template to the operator
    assigned to the given WorkOrderAssistanceUnit. The template opens the
    Meta 24-hour session window. The unit PK is queued in
    WhatsAppSession.pending_albaran_units so the albarán link is delivered
    automatically when the operator taps the opt_in button.

    Also marks WorkOrderAssistanceUnit.status as NOTIFIED and sets
    notified_at to the current timestamp.

    Returns True on successful Twilio dispatch, False on any failure.
    ---
    Envía el template WhatsApp 'chat_session_renewal' al operario asignado
    a la WorkOrderAssistanceUnit indicada. El template abre la ventana de
    sesión Meta de 24 horas. El PK de la unidad se encola en
    WhatsAppSession.pending_albaran_units para que el enlace al albarán se
    entregue automáticamente cuando el operario pulse el botón opt_in.

    También marca WorkOrderAssistanceUnit.status como NOTIFIED y establece
    notified_at con la marca de tiempo actual.

    Devuelve True en caso de despacho Twilio exitoso, False ante cualquier fallo.
    """
    from budgets.models import WorkOrderAssistanceUnit
    from .models import WhatsAppSession, WhatsAppTemplate

    # ── Resolve unit and operator phone ─────────────────────────────────────
    try:
        unit = WorkOrderAssistanceUnit.objects.select_related(
            "operator",
            "work_order__company",
        ).get(pk=unit_pk)
    except WorkOrderAssistanceUnit.DoesNotExist:
        logger.error(
            "# [ALBARAN NOTIFY] WorkOrderAssistanceUnit pk=%s no encontrada.",
            unit_pk,
        )
        return False

    operator        = unit.operator
    company         = unit.work_order.company
    operator_phone  = (operator.phone or "").strip()

    if not operator_phone:
        logger.error(
            "# [ALBARAN NOTIFY] Operario %s sin teléfono registrado. "
            "Unidad pk=%s. Abortando.",
            operator,
            unit_pk,
        )
        return False

    # ── Resolve chat_session_renewal template ────────────────────────────────
    try:
        template = WhatsAppTemplate.objects.get(
            company=company,
            name="chat_session_renewal",
            is_active=True,
        )
    except WhatsAppTemplate.DoesNotExist:
        logger.error(
            "# [ALBARAN NOTIFY] Template chat_session_renewal no encontrado "
            "para empresa %s. Abortando.",
            company.name,
        )
        return False

    # ── Send template via Twilio ─────────────────────────────────────────────
    try:
        twilio_client = _build_twilio_client()
        message = twilio_client.messages.create(
            from_=f"whatsapp:{whatsapp_sender}",
            to=f"whatsapp:{operator_phone}",
            content_sid=template.content_sid,
        )
        logger.info(
            "# [ALBARAN NOTIFY] Template enviado a operario %s (%s) — SID: %s",
            operator,
            operator_phone,
            message.sid,
        )
    except Exception as exc:
        logger.error(
            "# [ALBARAN NOTIFY] Error enviando template a %s: %s",
            operator_phone,
            exc,
        )
        return False

    # ── Queue unit PK in WhatsAppSession.pending_albaran_units ───────────────
    # Resolve or create the active session for this operator phone.
    # Resolver o crear la sesión activa para este teléfono de operario.
    session, _ = WhatsAppSession.objects.get_or_create(
        company=company,
        phone_number=operator_phone,
        is_active=True,
        defaults={},
    )
    pending = session.pending_albaran_units or []
    if unit_pk not in pending:
        pending.append(unit_pk)
    session.pending_albaran_units = pending
    session.save(update_fields=["pending_albaran_units"])

    # ── Mark unit as NOTIFIED ────────────────────────────────────────────────
    unit.status      = WorkOrderAssistanceUnit.STATUS_NOTIFIED
    unit.notified_at = now()
    unit.save(update_fields=["status", "notified_at"])

    logger.info(
        "# [ALBARAN NOTIFY] Unidad pk=%s marcada como NOTIFIED. "
        "pending_albaran_units sesión %s: %s",
        unit_pk,
        session.pk,
        pending,
    )
    return True

# ---------------------------------------------------------------------------
# BREAKDOWN AGENT SERVICE — H17 Paso 6
# Manages the WhatsApp breakdown conversation for internal Contacts.
# Resolves or creates a BreakdownTicket, builds the mechanic expert prompt,
# persists conversation turns in conversation_log, and parses TICKET_DATA
# markers from Gemini replies to populate ticket fields progressively.
# ---------------------------------------------------------------------------
# SERVICIO AGENTE DE AVERÍAS — H17 Paso 6
# Gestiona la conversación WhatsApp de avería para Contacts internos.
# Resuelve o crea un BreakdownTicket, construye el prompt de mecánico experto,
# persiste turnos en conversation_log y parsea marcadores TICKET_DATA de las
# respuestas de Gemini para poblar los campos del ticket progresivamente.
# ---------------------------------------------------------------------------

class BreakdownAgentService:
    """
    Stateless service that handles the full breakdown conversation pipeline
    for an internal Contact writing via WhatsApp. On each invocation it:
      1. Resolves the open BreakdownTicket for this contact or creates one.
      2. Builds the mechanic expert system prompt (Alia).
      3. Reconstructs conversation history from ticket.conversation_log.
      4. Sends the user message to Gemini and obtains a reply.
      5. Persists both turns in ticket.conversation_log.
      6. Parses [TICKET_DATA:{...}] markers to update ticket fields.
    ---
    Servicio sin estado que gestiona el pipeline completo de conversacion
    de averia para un Contact interno que escribe por WhatsApp.
    """

    GEMINI_MODEL = "gemini-2.5-flash"

    # Fault categories aligned with WorkOrderEntryLine.fault_category codes.
    # Categorias de averia alineadas con los codigos de WorkOrderEntryLine.
    FAULT_CATEGORIES = [
        "MECHANICAL", "ELECTRICAL_ELECTRONIC", "HYDRAULIC",
        "PNEUMATIC", "BODYWORK", "TYRES", "OTHER",
    ]

    @classmethod
    def get_or_create_ticket(cls, contact, company):
        """
        Returns the most recent open BreakdownTicket (OPEN or IN_PROGRESS)
        for the given contact and company. Creates a new OPEN ticket if none
        exists. Never returns PAUSED or CLOSED tickets — those are historical.
        ---
        Devuelve el BreakdownTicket abierto mas reciente (OPEN o IN_PROGRESS)
        para el contacto y empresa dados. Crea un nuevo ticket OPEN si no existe.
        Nunca devuelve tickets PAUSED o CLOSED — son historicos.
        """
        from chat.models import BreakdownTicket

        ticket = BreakdownTicket.objects.filter(
            contact=contact,
            company=company,
            status__in=[
                BreakdownTicket.STATUS_OPEN,
                BreakdownTicket.STATUS_IN_PROGRESS,
            ],
        ).order_by("-created_at").first()

        if ticket is None:
            from ivr_config.models import CompanyUser as _CU

            # Auto-assign if the contact is a workshop operator or boss.
            # Autoasignar si el contacto es operario o jefe de taller.
            company_user = getattr(contact, "company_user", None)
            auto_assign  = (
                company_user is not None
                and company_user.role in (
                    _CU.ROLE_WORKSHOP,
                    _CU.ROLE_WORKSHOPBOSS,
                )
            )

            ticket = BreakdownTicket.objects.create(
                company=company,
                contact=contact,
                origin=BreakdownTicket.ORIGIN_CHATBOT,
                status=(
                    BreakdownTicket.STATUS_IN_PROGRESS
                    if auto_assign
                    else BreakdownTicket.STATUS_OPEN
                ),
                assigned_to=company_user if auto_assign else None,
            )
            if auto_assign:
                logger.info(
                    "# [BREAKDOWN AGENT] Ticket pk=%s autoasignado a CU pk=%s"
                    " (IN_PROGRESS) — contacto %s",
                    ticket.pk, company_user.pk, contact.name,
                )
            else:
                logger.info(
                    "# [BREAKDOWN AGENT] Nuevo ticket creado para %s"
                    " — pk=%s code=%s",
                    contact.name, ticket.pk, ticket.ticket_date_code,
                )

            # H17 Paso 7 — Broadcast a secciones ivr_breakdown_enabled.
            # H17 Step 7 — Broadcast to ivr_breakdown_enabled sections.
            import os as _os_bd
            _wa_sender_bd = _os_bd.getenv("TWILIO_WHATSAPP_SENDER", "")
            if _wa_sender_bd:
                try:
                    WhatsAppChatService.send_breakdown_broadcast(
                        ticket=ticket,
                        wa_sender=_wa_sender_bd,
                    )
                except Exception as _bc_exc:
                    logger.error(
                        "# [BREAKDOWN AGENT] Error en broadcast WA "
                        "ticket pk=%s: %s",
                        ticket.pk,
                        _bc_exc,
                    )
            else:
                logger.warning(
                    "# [BREAKDOWN AGENT] TWILIO_WHATSAPP_SENDER no "
                    "configurado — broadcast omitido para ticket pk=%s.",
                    ticket.pk,
                )

        return ticket

    @classmethod
    def build_system_prompt(cls, contact, ticket, company) -> str:
        """
        Builds the mechanic expert system prompt for the breakdown agent.
        Alia acts as an expert mechanic specialised in heavy equipment
        (cranes, trucks, lifting platforms) and guides the internal contact
        through a structured fault declaration dialogue.

        The prompt instructs Gemini to:
          - Collect machine identification, fault description, fault location
            on the machine, physical location, and urgency level.
          - Append a [TICKET_DATA:{...}] marker when it has gathered enough
            information to populate the ticket fields.
          - Keep the conversation natural and concise.
        ---
        Construye el system prompt de mecanico experto para el agente de averias.
        """
        lines = [
            f"Eres Alia, mecanica experta de {company.name} especializada en "
            "maquinaria pesada: gruas, camiones, plataformas elevadoras y "
            "carretillas. Tu rol es recoger los datos de una averia de forma "
            "natural y eficiente.",
            "",
            f"Estas hablando con {contact.name}, trabajador interno de la empresa.",
            "",
            "OBJETIVO: Recoger los siguientes datos de la averia:",
            "1. Maquina o vehiculo afectado (modelo, matricula o codigo interno)",
            "2. Descripcion de la averia (que falla, como falla, desde cuando)",
            "3. Ubicacion de la averia en la maquina (zona especifica afectada)",
            "4. Ubicacion fisica actual de la maquina (base, ruta, lugar exacto)",
            "5. Nivel de urgencia (baja, media, alta o critica)",
            "",
            "INSTRUCCIONES:",
            "- Haz las preguntas de forma natural, no como un formulario.",
            "- Puedes agrupar varias preguntas en un mismo mensaje si tiene sentido.",
            "- Cuando tengas suficiente informacion para identificar la averia, "
            "resume los datos al trabajador y pide confirmacion.",
            "- Una vez confirmado, cierra el dialogo con un mensaje de confirmacion "
            "indicando el codigo del ticket.",
            "- Si el trabajador menciona que ya no hay averia o que fue un error, "
            "indicalo claramente.",
            "",
            "ESTADO ACTUAL DEL TICKET:",
            f"  Codigo: {ticket.ticket_date_code or 'pendiente de asignar'}",
            f"  Maquina: {ticket.machine_raw or 'no identificada aun'}",
            f"  Averia: {ticket.fault_summary or 'no descrita aun'}",
            f"  Ubicacion maquina: {ticket.fault_location or 'no indicada aun'}",
            f"  Ubicacion fisica: {ticket.location or 'no indicada aun'}",
            f"  Urgencia: {ticket.urgency or 'no indicada aun'}",
            "",
            "MARCADOR DE DATOS (uso interno — el trabajador no lo ve):",
            "Cuando hayas recopilado suficiente informacion, añade AL FINAL de tu "
            "respuesta — y SOLO al final — el siguiente marcador JSON:",
            '[TICKET_DATA:{"machine": "...", "fault": "...", '
            '"fault_location": "...", "location": "...", '
            '"urgency": "LOW|MEDIUM|HIGH|CRITICAL", "category": "...",'
            ' "reported_by": "nombre completo del conductor/maquinista o null"}]',
            "Categorias validas: MECHANICAL, ELECTRICAL_ELECTRONIC, HYDRAULIC, "
            "PNEUMATIC, BODYWORK, TYRES, OTHER.",
            "Solo incluye el marcador cuando los datos esten suficientemente "
            "completos. Omite campos que aun no esten claros.",
            "NUNCA muestres el marcador al trabajador — sera procesado internamente.",
        ]

        # If the contact is a manager/admin, ask who is operating the machine.
        # Si el contacto es jefe/admin, preguntar quién opera la máquina.
        from ivr_config.models import CompanyUser as _CU
        company_user = getattr(contact, "company_user", None)
        if (
            company_user is not None
            and company_user.role in (
                _CU.ROLE_WORKSHOPBOSS,
                _CU.ROLE_ADMIN,
            )
        ):
            lines.append("")
            lines.append(
                "CONDUCTOR O MAQUINISTA AFECTADO:"
            )
            lines.append(
                "Dado que el trabajador que reporta es responsable o "
                "administrador, preguntale quien es el conductor o maquinista "
                "que opera la maquina afectada. Incluye su nombre completo en "
                'el campo "reported_by" del marcador TICKET_DATA. '
                "Si el propio trabajador es quien opera la maquina, "
                "pon su nombre en reported_by igualmente. "
                "Si no es posible identificarlo, usa null."
            )

        return "\n".join(lines)

    @classmethod
    def build_history_from_log(cls, ticket) -> list:
        """
        Reconstructs Gemini chat history from ticket.conversation_log entries
        filtered to source='WHATSAPP'. Returns a list of genai_types.Content
        objects compatible with client.chats.create(history=...).
        ---
        Reconstruye el historial de chat de Gemini desde las entradas
        conversation_log del ticket filtradas a source='WHATSAPP'.
        """
        history = []
        for entry in (ticket.conversation_log or []):
            if entry.get("source") != "WHATSAPP":
                continue
            role = "user" if entry.get("role") == "USER" else "model"
            content = entry.get("content", "")
            if content:
                history.append(
                    genai_types.Content(
                        role=role,
                        parts=[genai_types.Part(text=content)],
                    )
                )
        return history

    @classmethod
    def append_log(cls, ticket, role: str, content: str, source: str = "WHATSAPP"):
        """
        Appends a single turn to ticket.conversation_log and saves the field.
        role: 'USER' | 'MODEL'
        source: 'WHATSAPP' | 'IVR' | 'SYSTEM'
        ---
        Anade un turno al conversation_log del ticket y guarda el campo.
        """
        import json as _json
        from django.utils.timezone import now as _now

        log = list(ticket.conversation_log or [])
        log.append({
            "timestamp": _now().isoformat(),
            "source":    source,
            "role":      role,
            "content":   content,
        })
        ticket.conversation_log = log
        ticket.save(update_fields=["conversation_log", "updated_at"])

    # Regex for TICKET_DATA marker emitted by Gemini.
    # Regex para el marcador TICKET_DATA emitido por Gemini.
    _TICKET_DATA_PATTERN = __import__("re").compile(
        r'\[TICKET_DATA:\s*(\{[^}]+\})\s*\]',
        __import__("re").IGNORECASE,
    )

    @classmethod
    def parse_and_apply_ticket_data(cls, reply_text: str, ticket) -> str:
        """
        Searches for a [TICKET_DATA:{...}] marker in the Gemini reply.
        If found:
          - Strips the marker from the visible reply text.
          - Updates ticket fields (machine_raw, fault_summary, fault_location,
            location, urgency, fault_category) with non-empty values.
          - Saves only the fields that changed.
        Returns the cleaned reply text (marker removed).
        ---
        Busca un marcador [TICKET_DATA:{...}] en la respuesta de Gemini.
        Si se encuentra, elimina el marcador del texto visible y actualiza
        los campos del ticket con los valores no vacios. Devuelve el texto limpio.
        """
        import json as _json

        match = cls._TICKET_DATA_PATTERN.search(reply_text)
        if not match:
            return reply_text

        # Strip marker from visible reply regardless of parse success.
        # Eliminar marcador del texto visible independientemente del exito del parseo.
        clean_text = cls._TICKET_DATA_PATTERN.sub("", reply_text).strip()

        try:
            data = _json.loads(match.group(1))
        except (_json.JSONDecodeError, AttributeError):
            logger.warning(
                "# [BREAKDOWN AGENT] Error parseando TICKET_DATA — raw: %s",
                match.group(1),
            )
            return clean_text

        updated_fields = []

        machine = (data.get("machine") or "").strip()
        if machine and machine != ticket.machine_raw:
            ticket.machine_raw = machine
            updated_fields.append("machine_raw")

        fault = (data.get("fault") or "").strip()
        if fault and fault != ticket.fault_summary:
            ticket.fault_summary = fault
            updated_fields.append("fault_summary")

        fault_location = (data.get("fault_location") or "").strip()
        if fault_location and fault_location != ticket.fault_location:
            ticket.fault_location = fault_location
            updated_fields.append("fault_location")

        location = (data.get("location") or "").strip()
        if location and location != ticket.location:
            ticket.location = location
            updated_fields.append("location")

        urgency = (data.get("urgency") or "").strip().upper()
        valid_urgencies = {
            "LOW", "MEDIUM", "HIGH", "CRITICAL",
        }
        if urgency in valid_urgencies and urgency != ticket.urgency:
            ticket.urgency = urgency
            updated_fields.append("urgency")

        category = (data.get("category") or "").strip().upper()
        if category in cls.FAULT_CATEGORIES and category != ticket.fault_category:
            ticket.fault_category = category
            updated_fields.append("fault_category")

        # Resolve reported_by from name string to Contact.
        # Resolver reported_by del nombre al Contact correspondiente.
        reported_by_name = (data.get("reported_by") or "").strip()
        if reported_by_name and reported_by_name.lower() != "null":
            from ivr_config.models import Contact as _Contact
            # Try exact match first, then icontains.
            # Primero coincidencia exacta, luego parcial.
            rb_contact = (
                _Contact.objects.filter(
                    company=ticket.company,
                    name__iexact=reported_by_name,
                ).first()
                or _Contact.objects.filter(
                    company=ticket.company,
                    name__icontains=reported_by_name,
                ).first()
            )
            if (
                rb_contact is not None
                and rb_contact != ticket.reported_by
            ):
                ticket.reported_by = rb_contact
                updated_fields.append("reported_by")
                logger.info(
                    "# [BREAKDOWN AGENT] reported_by resuelto a Contact pk=%s"
                    " '%s' para ticket pk=%s",
                    rb_contact.pk, rb_contact.name, ticket.pk,
                )
            elif rb_contact is None:
                logger.warning(
                    "# [BREAKDOWN AGENT] reported_by '%s' no encontrado"
                    " en empresa pk=%s — campo omitido.",
                    reported_by_name, ticket.company_id,
                )

        if updated_fields:
            updated_fields.append("updated_at")
            ticket.save(update_fields=updated_fields)
            logger.info(
                "# [BREAKDOWN AGENT] Ticket pk=%s actualizado: %s",
                ticket.pk,
                updated_fields,
            )

        return clean_text

    @classmethod
    def get_gemini_reply(
        cls,
        system_prompt: str,
        history: list,
        user_message: str,
    ) -> str:
        """
        Sends the user message to Gemini 2.5 Flash via Vertex AI using the
        breakdown agent system prompt and conversation history from the ticket
        log. Returns the plain-text reply (TICKET_DATA marker not yet stripped
        — caller handles that via parse_and_apply_ticket_data).
        ---
        Envia el mensaje del usuario a Gemini 2.5 Flash via Vertex AI usando
        el system prompt del agente de averias y el historial del ticket log.
        Devuelve el texto plano de la respuesta (el marcador TICKET_DATA aun
        no se elimina — el llamador lo gestiona via parse_and_apply_ticket_data).
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


# ---------------------------------------------------------------------------
# ONBOARDING SERVICE — H17 Paso 6
# Handles WhatsApp-driven employee onboarding for unknown phone numbers.
# Collects name, DNI and section via natural conversation, then creates
# CompanyUser + Contact + SectionContact automatically.
# ---------------------------------------------------------------------------
# SERVICIO DE ONBOARDING — H17 Paso 6
# Gestiona el onboarding de empleados via WhatsApp para numeros desconocidos.
# Recoge nombre, DNI y seccion mediante conversacion natural, luego crea
# CompanyUser + Contact + SectionContact automaticamente.
# ---------------------------------------------------------------------------

# Onboarding state persisted in WhatsAppSession.pending_broadcast_messages
# is NOT suitable for this purpose. We use a dedicated JSONField on the session
# via a light convention: the onboarding state is stored in the session's
# pending_albaran_units field as a sentinel value. Instead, we use the
# Contact.alias_onboarding_step / alias_onboarding_proposed fields on a
# *temporary* Contact record, OR we store the state in a simple in-DB
# approach: a dedicated OnboardingSession model would be ideal but requires
# a migration. For H17 Paso 6 we use a pragmatic approach: state is kept
# in WhatsAppSession.pending_broadcast_messages as a JSON sentinel with a
# "__onboarding__" key so it does not conflict with real broadcast messages.
#
# Convention: WhatsAppSession.pending_broadcast_messages may contain at most
# one entry with key "__onboarding__" whose value is the onboarding state dict:
# {
#   "__onboarding__": true,
#   "step": "NAME" | "LASTNAME" | "DNI" | "SECTION",
#   "first_name": "...",
#   "last_name1": "...",
#   "last_name2": "...",
#   "dni": "...",
#   "section_pk": null | int,
# }



_ONBOARDING_SENTINEL = "__onboarding__"


class OnboardingService:
    """
    Gemini-driven onboarding service for unknown WhatsApp numbers.
    Gemini manages the entire conversation naturally — no rigid state machine.
    When Gemini has collected and confirmed all required data it emits:
      [ONBOARDING_DATA:{"first_name":"...","last_name1":"...","last_name2":"...",
                        "dni":"...","section":"..."}]
    The webhook detects this marker, creates the user and sends confirmation.

    State stored in WhatsAppSession.pending_broadcast_messages:
      [{"__onboarding__": true}]  — minimal sentinel, no step tracking needed.

    Conversation history is reconstructed from WhatsAppSession.messages,
    identical to the generic chatbot pipeline.
    ---
    Servicio de onboarding dirigido por Gemini para numeros WhatsApp desconocidos.
    Gemini gestiona la conversacion completa de forma natural. Cuando tiene todos
    los datos confirmados emite el marcador ONBOARDING_DATA. El webhook lo detecta,
    crea el usuario y envia la confirmacion.
    """

    GEMINI_MODEL = "gemini-2.5-flash"

    # Regex to detect the ONBOARDING_DATA marker in Gemini replies.
    # Regex para detectar el marcador ONBOARDING_DATA en respuestas de Gemini.
    import re as _re_cls
    _ONBOARDING_DATA_PATTERN = _re_cls.compile(
        r'\[ONBOARDING_DATA:\s*(\{[^}]+\})\s*\]',
        _re_cls.IGNORECASE,
    )

    @classmethod
    def get_state(cls, session) -> dict | None:
        """Returns the onboarding sentinel dict or None."""
        for entry in (session.pending_broadcast_messages or []):
            if isinstance(entry, dict) and entry.get(_ONBOARDING_SENTINEL):
                return entry
        return None

    @classmethod
    def _set_state(cls, session):
        """Activates the onboarding sentinel on the session."""
        messages = [
            e for e in (session.pending_broadcast_messages or [])
            if not (isinstance(e, dict) and e.get(_ONBOARDING_SENTINEL))
        ]
        messages.append({_ONBOARDING_SENTINEL: True})
        session.pending_broadcast_messages = messages
        session.save(update_fields=["pending_broadcast_messages"])

    @classmethod
    def clear_state(cls, session):
        """Removes the onboarding sentinel from the session."""
        messages = [
            e for e in (session.pending_broadcast_messages or [])
            if not (isinstance(e, dict) and e.get(_ONBOARDING_SENTINEL))
        ]
        session.pending_broadcast_messages = messages
        session.save(update_fields=["pending_broadcast_messages"])

    @classmethod
    def build_system_prompt(cls, company) -> str:
        """
        Builds the Gemini system prompt for the onboarding conversation.
        Instructs Gemini to collect name, surnames, DNI and section naturally,
        confirm each piece of data with the user, and emit ONBOARDING_DATA
        when everything is confirmed.
        ---
        Construye el system prompt de Gemini para la conversacion de onboarding.
        """
        sections = list(company.sections.all().order_by("name"))
        section_list = "\n".join(f"  - {s.name}" for s in sections)

        bases = list(company.bases.all().order_by("name"))
        base_list = "\n".join(f"  - {b.name}" for b in bases)

        return (
            f"Eres el asistente de registro de nuevos empleados de {company.name}. "
            "Tu objetivo es registrar al trabajador en la plataforma de forma "
            "natural y amigable.\n\n"
            "DATOS QUE DEBES RECOGER (en cualquier orden, de forma conversacional):\n"
            "1. Nombre de pila\n"
            "2. Apellidos (primer apellido y segundo apellido)\n"
            "3. DNI completo con letra (p.ej. 12345678Z — acepta minúsculas, "
            "indícale que no importa)\n"
            f"4. Sección a la que pertenece. Secciones disponibles:\n{section_list}\n\n"
            f"5. Base a la que pertenece. Bases disponibles:\n{base_list}\n\n"
            "INSTRUCCIONES:\n"
            "- Recoge los datos de forma natural, no como un formulario.\n"
            "- Después de recoger cada dato, confírmalo con el usuario "
            "(p.ej. 'Tu nombre es Miguel Ángel, ¿correcto?').\n"
            "- Si el usuario corrige algún dato, acéptalo y confirma el nuevo valor.\n"
            "- Cuando tengas TODOS los datos confirmados, haz un resumen final "
            "y pregunta si todo es correcto antes de registrar.\n"
            "- Solo cuando el usuario confirme el resumen final, emite AL FINAL "
            "de tu respuesta — y SOLO al final, sin texto posterior — el marcador:\n"
            '[ONBOARDING_DATA:{"first_name":"...","last_name1":"...","last_name2":"...",'
            '"dni":"...","section":"...","base":"..."}]\n'
            "- El campo 'dni' debe estar en mayúsculas (tú lo conviertes).\n"
            "- El campo 'section' debe ser el nombre EXACTO de una de las secciones "
            "listadas arriba.\n"
            "- El campo 'base' debe ser el nombre EXACTO de una de las bases "
            "listadas arriba.\n"
            "- NUNCA muestres el marcador al usuario — será procesado internamente.\n"
            "- Si el usuario dice algo que no tiene que ver con el registro, "
            "redirige amablemente la conversación al proceso de alta.\n"
            "- Mantén un tono cálido, profesional y conciso."
        )

    @classmethod
    def start(cls, session, company) -> str:
        """
        Activates onboarding sentinel and returns the opening message
        via Gemini (first turn with empty history).
        ---
        Activa el sentinel de onboarding y devuelve el mensaje de apertura
        via Gemini (primer turno con historial vacio).
        """
        cls._set_state(session)
        logger.info(
            "# [ONBOARDING] Iniciado para sesion pk=%s empresa=%s",
            session.pk, company.name,
        )
        system_prompt = cls.build_system_prompt(company)
        # Seed Gemini with the trigger message already in history.
        # Sembrar Gemini con el mensaje trigger ya en el historial.
        history = WhatsAppChatService.build_history(session)
        try:
            reply = cls._get_gemini_reply(
                system_prompt=system_prompt,
                history=history,
                user_message="",  # Gemini opens the conversation.
            )
        except Exception as exc:
            logger.error("# [ONBOARDING] Error Gemini inicio: %s", exc)
            reply = (
                f"Bienvenido/a a {company.name}. Voy a registrarte en la "
                "plataforma. ¿Cuál es tu nombre completo?"
            )
        return reply

    @classmethod
    def handle(cls, session, company, body: str) -> str:
        """
        Processes an inbound message during an active onboarding conversation.
        Sends the full session history + body to Gemini and returns the reply.
        If Gemini emits [ONBOARDING_DATA:{...}], creates the user and returns
        the confirmation message (marker stripped from visible reply).
        ---
        Procesa un mensaje entrante durante un onboarding activo.
        """
        import json as _json

        system_prompt = cls.build_system_prompt(company)
        history = WhatsAppChatService.build_history(session)

        try:
            raw_reply = cls._get_gemini_reply(
                system_prompt=system_prompt,
                history=history,
                user_message=body,
            )
        except Exception as exc:
            logger.error("# [ONBOARDING] Error Gemini handle: %s", exc)
            return (
                "Lo sentimos, ha habido un problema. "
                "Por favor, inténtalo de nuevo."
            )

        # Check for ONBOARDING_DATA marker.
        # Comprobar marcador ONBOARDING_DATA.
        match = cls._ONBOARDING_DATA_PATTERN.search(raw_reply)
        if match:
            # Strip marker from visible reply.
            # Eliminar marcador del texto visible.
            visible_reply = cls._ONBOARDING_DATA_PATTERN.sub(
                "", raw_reply
            ).strip()

            try:
                data = _json.loads(match.group(1))
            except (_json.JSONDecodeError, AttributeError):
                logger.warning(
                    "# [ONBOARDING] Error parseando ONBOARDING_DATA: %s",
                    match.group(1),
                )
                return visible_reply or raw_reply

            # Create user and return confirmation.
            # Crear usuario y devolver confirmacion.
            confirmation = cls._create_user(session, company, data)
            # Return Gemini's summary text + our confirmation message.
            # Devolver texto de resumen de Gemini + mensaje de confirmacion.
            if visible_reply:
                return f"{visible_reply}\n\n{confirmation}"
            return confirmation

        return raw_reply

    @classmethod
    def _get_gemini_reply(
        cls,
        system_prompt: str,
        history: list,
        user_message: str,
    ) -> str:
        """Invokes Gemini 2.5 Flash with the onboarding prompt and history."""
        client = _build_genai_client()
        chat = client.chats.create(
            model=cls.GEMINI_MODEL,
            config=genai_types.GenerateContentConfig(
                system_instruction=system_prompt,
            ),
            history=history,
        )
        # If user_message is empty, send a trigger so Gemini opens naturally.
        # Si user_message esta vacio, enviar trigger para que Gemini abra.
        msg = user_message if user_message else "Hola, quiero registrarme."
        response = chat.send_message(msg)
        return response.text

    @classmethod
    def _create_user(cls, session, company, data: dict) -> str:
        """
        Creates DjangoUser + CompanyUser + Contact + SectionContact from the
        data dict emitted by Gemini. Returns the confirmation message.
        ---
        Crea DjangoUser + CompanyUser + Contact + SectionContact desde el dict
        emitido por Gemini. Devuelve el mensaje de confirmacion.
        """
        from django.contrib.auth.models import User as DjangoUser
        from ivr_config.models import (
            CompanyUser as _CU,
            Contact as _Contact,
            SectionContact as _SC,
            Section as _S,
        )
        import unicodedata
        import re as _re

        first_name  = (data.get("first_name") or "").strip()
        last_name1  = (data.get("last_name1") or "").strip()
        last_name2  = (data.get("last_name2") or "").strip()
        dni         = (data.get("dni") or "").strip().upper()
        section_name = (data.get("section") or "").strip()
        base_name    = (data.get("base") or "").strip()

        # Resolve section — exact match first, then partial.
        # Resolver seccion — coincidencia exacta primero, luego parcial.
        section = _S.objects.filter(
            company=company, name=section_name,
        ).first()
        if section is None:
            section = _S.objects.filter(
                company=company,
                name__icontains=section_name,
            ).first()
        if section is None:
            cls.clear_state(session)
            logger.error(
                "# [ONBOARDING] Seccion '%s' no encontrada para empresa %s",
                section_name, company.name,
            )
            return (
                "Ha ocurrido un error al identificar la sección. "
                "Por favor, contacta con el administrador."
            )

        # Resolve base — same pattern as section (exact match first, then
        # partial). Added S018 at Miguel Ángel's explicit request: the
        # WhatsApp onboarding must ask for the base, same as it already
        # asks for the section — see hr_calendar's CompanyUser.base
        # (H24), which needs this to resolve which labor calendar
        # (Base.labor_calendar) applies to each new employee.
        # ---
        # Resolver base — mismo patrón que sección (coincidencia exacta
        # primero, luego parcial). Añadido en S018 a petición explícita
        # de Miguel Ángel: el onboarding de WhatsApp debe preguntar la
        # base, igual que ya pregunta la sección — ver
        # CompanyUser.base de hr_calendar (H24), que necesita esto para
        # resolver qué calendario laboral (Base.labor_calendar) aplica a
        # cada empleado nuevo.
        from budgets.models import Base as _Base
        base = _Base.objects.filter(
            company=company, name=base_name,
        ).first()
        if base is None:
            base = _Base.objects.filter(
                company=company,
                name__icontains=base_name,
            ).first()
        if base is None:
            cls.clear_state(session)
            logger.error(
                "# [ONBOARDING] Base '%s' no encontrada para empresa %s",
                base_name, company.name,
            )
            return (
                "Ha ocurrido un error al identificar la base. "
                "Por favor, contacta con el administrador."
            )

        # Determine role from the section's own configuration — never infer
        # it from the section name. Section.default_role is the single
        # source of truth for the role assigned on WhatsApp onboarding.
        # Determinar el rol desde la configuración propia de la sección —
        # nunca inferirlo del nombre. Section.default_role es la única
        # fuente de verdad para el rol asignado en el alta por WhatsApp.
        role = section.default_role

        # Build username.
        def _normalize(s: str) -> str:
            return "".join(
                c for c in unicodedata.normalize("NFD", s)
                if unicodedata.category(c) != "Mn"
            ).lower()

        def _clean(s: str) -> str:
            return _re.sub(r"[^a-z0-9.]", "", s)

        fn  = _normalize(first_name)
        ln1 = _normalize(last_name1)
        ln2 = _normalize(last_name2)

        base_username = _clean(f"{fn}.{ln1}") if ln1 else _clean(fn)
        username = base_username

        if DjangoUser.objects.filter(username=username).exists() and ln2:
            alt = _clean(f"{fn}.{ln2}")
            if not DjangoUser.objects.filter(username=alt).exists():
                username = alt
            else:
                suffix = 2
                while DjangoUser.objects.filter(
                    username=f"{base_username}{suffix}"
                ).exists():
                    suffix += 1
                username = f"{base_username}{suffix}"

        # Derive password from last 4 numeric digits of DNI.
        dni_digits = _re.sub(r"[^0-9]", "", dni)
        password   = dni_digits[-4:] if len(dni_digits) >= 4 else dni_digits.zfill(4)

        try:
            django_user = DjangoUser.objects.create_user(
                username=username,
                password=password,
                first_name=first_name,
                last_name=f"{last_name1} {last_name2}".strip(),
                is_active=True,
                is_staff=False,
            )
            company_user = _CU.objects.create(
                company=company,
                user=django_user,
                role=role,
                base=base,
                is_active=True,
                must_change_password=False,
                dni=dni,
            )
            contact = _Contact.objects.create(
                company=company,
                name=f"{first_name} {last_name1} {last_name2}".strip(),
                phone_number=session.phone_number,
                is_internal=True,
                company_user=company_user,
            )
            _SC.objects.create(
                section=section,
                contact=contact,
                priority=99,
            )
            cls.clear_state(session)

            role_label = dict(_CU.ROLE_CHOICES).get(role, role)
            panel_url = (
                "https://enterprisebot-miguelaetxio.pythonanywhere.com"
                "/panel/users/"
            )

            logger.info(
                "# [ONBOARDING] Usuario creado: username=%s role=%s "
                "seccion=%s phone=%s",
                username, role, section.name, session.phone_number,
            )

            return (
                f"✅ ¡Listo! Tu cuenta ha sido creada en {company.name}.\n\n"
                f"👤 Usuario: *{username}*\n"
                f"🔑 Contraseña: *{password}*\n"
                f"📋 Rol: {role_label}\n"
                f"🏢 Sección: {section.name}\n"
                f"🏠 Base: {base.name}\n\n"
                f"🔗 Accede al panel aquí: {panel_url}\n\n"
                "Guarda estos datos. Si necesitas ayuda para acceder o "
                "tienes cualquier problema con tu cuenta, escríbeme aquí mismo. "
                "Y si tienes alguna avería que reportar, también puedes "
                "hacerlo por este chat."
            )

        except Exception as exc:
            logger.error(
                "# [ONBOARDING] Error creando usuario sesion pk=%s: %s",
                session.pk, exc,
            )
            cls.clear_state(session)
            return (
                "Ha ocurrido un error al crear tu cuenta. "
                "Por favor, contacta con el administrador de la plataforma."
            )


