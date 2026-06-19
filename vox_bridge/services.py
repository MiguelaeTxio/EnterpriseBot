# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/vox_bridge/services.py
"""
Core orchestration service for the EnterpriseBot voice bridge.

This module implements the stateful, bidirectional audio pipeline between
Twilio Media Streams (G.711 mu-law/A-law, 8kHz) and the Gemini 3.1 Live API
(PCM Linear 16-bit, 16kHz). It manages the full lifecycle of a real-time
voice session: WebSocket connection from Twilio, audio transcoding via the
sidecar bridge, streaming to Gemini Live, and audio response playback back
to the caller.

Architecture (Server-to-Server, WSGI/PythonAnywhere):
    Twilio <--G.711 mulaw/alaw 8kHz--> Django WebSocket View
    Django WebSocket View <--PCM 16kHz--> VoiceOrchestrationService
    VoiceOrchestrationService <--PCM 16kHz--> Gemini 3.1 Live API

Setup-First Protocol (SDK 1.69.0 Compliant):
    The Gemini Live session is established exclusively via the
    `async with client.aio.live.connect(...)` context manager. Entry into
    this context manager guarantees that the WebSocket handshake with
    Google's infrastructure is complete and the session is ready to receive
    data. No explicit setup_complete event polling is required or supported
    by the SDK. The initial greeting is sent immediately upon context entry.
---
Servicio de orquestación principal para el puente de voz de EnterpriseBot.

Este módulo implementa el pipeline de audio bidireccional y con estado entre
Twilio Media Streams (G.711 mu-law/A-law, 8kHz) y la API Gemini 3.1 Live
(PCM Linear 16-bit, 16kHz). Gestiona el ciclo de vida completo de una sesión
de voz en tiempo real: conexión WebSocket desde Twilio, transcodificación de
audio vía el sidecar bridge, streaming a Gemini Live, y reproducción de la
respuesta de audio de vuelta al llamante.

Arquitectura (Servidor a Servidor, WSGI/PythonAnywhere):
    Twilio <--G.711 mulaw/alaw 8kHz--> Vista WebSocket de Django
    Vista WebSocket de Django <--PCM 16kHz--> VoiceOrchestrationService
    VoiceOrchestrationService <--PCM 16kHz--> API Gemini 3.1 Live

Protocolo Setup-First (Conforme a SDK 1.69.0):
    La sesión de Gemini Live se establece exclusivamente a través del
    context manager `async with client.aio.live.connect(...)`. La entrada
    en este context manager garantiza que el handshake WebSocket con la
    infraestructura de Google está completo y la sesión está lista para
    recibir datos. No se requiere ni está soportado por el SDK el sondeo
    de ningún evento setup_complete explícito. El saludo inicial se envía
    de forma inmediata tras la entrada al context manager.
"""

import asyncio
import base64
import json
import logging
import math
import os
import struct
import time

from google import genai
from google.genai import types
from twilio.rest import Client as TwilioClient

# ---------------------------------------------------------------------------
# LOGGING CONFIGURATION / CONFIGURACIÓN DE LOGGING
# ---------------------------------------------------------------------------
# Module-level logger for structured, traceable output throughout the service.
# Logger de módulo para salida estructurada y trazable a lo largo del servicio.
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# CONSTANTS / CONSTANTES
# ---------------------------------------------------------------------------

# Gemini Live 2.5 Flash Native Audio — GA stable model on Vertex AI.
# Migrated from gemini-3.1-flash-live-preview (Gemini API Preview) on 2026-04-05
# due to Preview infrastructure instability causing silent audio generation failures.
# gemini-live-2.5-flash-native-audio is GA on Vertex AI with no published
# deprecation date and production-grade SLA guarantees.
# Gemini Live 2.5 Flash Native Audio — modelo GA estable en Vertex AI.
# Migrado desde gemini-3.1-flash-live-preview (Gemini API Preview) el 2026-04-05
# debido a inestabilidad de la infraestructura Preview que causaba fallos silenciosos
# en la generación de audio. gemini-live-2.5-flash-native-audio es GA en Vertex AI
# sin fecha de deprecación publicada y con garantías SLA de producción.
GEMINI_MODEL = "gemini-live-2.5-flash-native-audio"

# Fallback system instruction used when build_live_config() fails to load
# the dynamic configuration from the database (e.g. number not configured,
# CallFlow missing). Contains the original hardcoded Grupo Álvarez / María
# persona definition as a safety net to prevent silent call failures.
# Instrucción de sistema de fallback usada cuando build_live_config() no puede
# cargar la configuración dinámica desde la base de datos (p. ej. número no
# configurado, CallFlow ausente). Contiene la definición original hardcodeada
# de la persona Grupo Álvarez / María como red de seguridad para evitar fallos
# silenciosos en llamadas.
SYSTEM_INSTRUCTION_FALLBACK = (
    "Eres María, la asistente virtual del Grupo Álvarez. "
    "Atiendes llamadas de voz en tiempo real. "
    "Tu tono es profesional, cálido y conciso. "
    "Habla siempre en castellano, salvo que el llamante se dirija a ti en otro idioma. "
    "\n\n"
    "ORGANIGRAMA DE ATENCIÓN:\n"
    "\n"
    "1. ELEVACIÓN (alquiler de plataformas elevadoras):\n"
    "   Si el llamante pregunta por el departamento de Elevación o por el alquiler "
    "de plataformas elevadoras, infórmale de que el horario de atención es de lunes "
    "a viernes de 8:00 a 18:00 horas, y despídete amablemente.\n"
    "\n"
    "2. ASISTENCIA (rescate de vehículos pesados):\n"
    "   Si el llamante pregunta por el departamento de Asistencia o por el rescate "
    "de vehículos pesados, infórmale de que el servicio está disponible las 24 horas "
    "del día, los 7 días de la semana, y despídete amablemente.\n"
    "\n"
    "3. PREGUNTA POR ALGUIEN CON APELLIDO ÁLVAREZ:\n"
    "   Si el llamante pregunta por cualquier persona cuyo apellido sea Álvarez, "
    "indícale que en estos momentos está reunida. "
    "Ofrécete a tomar nota del recado. "
    "Pídele su nombre y, una vez que te lo facilite, confirma que transmitirás el "
    "mensaje y despídete amablemente.\n"
    "\n"
    "4. PREGUNTA POR ALGUIEN SIN APELLIDO ÁLVAREZ:\n"
    "   Si el llamante pregunta por una persona cuyo apellido NO es Álvarez, "
    "pregúntale el motivo de su llamada y redirígele según su respuesta conforme "
    "a las categorías anteriores (Elevación o Asistencia). "
    "Si el motivo no encaja en ninguna categoría, pasa a la regla 5.\n"
    "\n"
    "5. MOTIVO AMBIGUO O SIN CATEGORÍA:\n"
    "   Si el motivo de la llamada no encaja en ninguna de las categorías anteriores, "
    "indícale al llamante que un comercial se pondrá en contacto con él a la mayor "
    "brevedad posible. "
    "Solicítale sus datos de contacto (nombre y número de teléfono) y, "
    "una vez recogidos, despídete amablemente.\n"
    "\n"
    "REGLAS GENERALES:\n"
    "- Nunca inventes información que no figure en este organigrama.\n"
    "- Nunca menciones que eres una inteligencia artificial salvo que el llamante "
    "te lo pregunte directamente.\n"
    "- Mantén siempre un tono sereno y profesional, independientemente del tono "
    "del llamante.\n"
    "- Sé concisa: no des explicaciones innecesarias.\n"
)

# Timeout values aligned with the V01 roadmap directive:
# The Preview infrastructure of Gemini 3.1 Live has a documented TTFT
# (Time to First Token) of up to 35 seconds. All asyncio.wait_for calls
# must therefore use a minimum of 60 seconds to avoid false-positive timeouts.
# Valores de timeout alineados con la directiva de la hoja de ruta V01:
# La infraestructura Preview de Gemini 3.1 Live tiene un TTFT (Time to First
# Token) documentado de hasta 35 segundos. Todas las llamadas asyncio.wait_for
# deben usar un mínimo de 60 segundos para evitar timeouts de falso positivo.
TIMEOUT_SESSION_CONNECT_SECONDS = 60.0
TIMEOUT_INITIAL_GREETING_SECONDS = 60.0
TIMEOUT_AUDIO_RECEIVE_SECONDS = 60.0
TIMEOUT_CALL_COMPLETION_SECONDS = 60.0

# Audio format specification for Twilio ↔ Gemini Live bridge.
# Especificación de formato de audio para el puente Twilio ↔ Gemini Live.
GEMINI_AUDIO_MIME_TYPE = "audio/pcm;rate=16000"
GEMINI_OUTPUT_SAMPLE_RATE = 24000  # Hz — Gemini Live output is always 24kHz PCM
TWILIO_INPUT_SAMPLE_RATE = 8000   # Hz — Twilio G.711 mu-law/A-law is always 8kHz
TWILIO_OUTPUT_SAMPLE_RATE = 8000  # Hz — Twilio expects 8kHz mu-law back

# ---------------------------------------------------------------------------
# ACTIVITY DETECTION CONSTANTS / CONSTANTES DE DETECCIÓN DE ACTIVIDAD
# ---------------------------------------------------------------------------

# RMS energy threshold below which a PCM frame is considered silence.
# Twilio G.711 mu-law decoded to PCM 16-bit yields values in [-32768, 32767].
# 200 RMS (~-44 dBFS) is a conservative threshold that reliably separates
# background line noise from actual speech in telephony conditions.
# Umbral de energía RMS por debajo del cual un frame PCM se considera silencio.
# El mu-law G.711 de Twilio decodificado a PCM 16-bit da valores en [-32768, 32767].
# 200 RMS (~-44 dBFS) es un umbral conservador que separa de forma fiable el
# ruido de línea de fondo del habla real en condiciones de telefonía.
SILENCE_THRESHOLD_RMS = 300

# Number of consecutive silent frames required to close an activity window.
# At Twilio's 8kHz mu-law encoding, each media event carries ~20ms of audio,
# so 30 frames ≈ 600ms of silence before activity_end is sent.
# Increased from 20 to 30 on 2026-04-06 to give the caller more inter-phrase
# margin and avoid premature activity_end during natural speech pauses.
# Número de frames silenciosos consecutivos requeridos para cerrar una ventana
# de actividad. Con la codificación mu-law a 8kHz de Twilio, cada evento media
# lleva ~20ms de audio, por lo que 30 frames ≈ 600ms de silencio antes de que
# se envíe activity_end.
# Aumentado de 20 a 30 el 2026-04-06 para dar más margen al llamante entre
# frases y evitar activity_end prematuro durante pausas naturales del habla.
SILENCE_FRAMES_TO_END_ACTIVITY = 50

# Number of consecutive speech frames required to open an activity window.
# Increased from 3 to 10 on 2026-04-06 (~200ms) to filter out acoustic echo
# of María's own playback being captured by the handset microphone. At 3 frames
# (~60ms) the detector was firing on the model's own audio output, causing
# spurious activity_start signals that triggered Gemini self-interruptions.
# Número de frames de voz consecutivos requeridos para abrir una ventana de
# actividad. Aumentado de 3 a 10 el 2026-04-06 (~200ms) para filtrar el eco
# acústico de la reproducción del propio audio de María capturado por el
# micrófono del auricular. Con 3 frames (~60ms) el detector disparaba sobre
# la propia salida de audio del modelo, causando señales activity_start
# espurias que provocaban auto-interrupciones de Gemini.
SPEECH_FRAMES_TO_START_ACTIVITY = 15


# Fallback voice name used when build_live_config() fails to load the dynamic
# configuration. 'Aoede' is the canonical IVR voice for EnterpriseBot.
# Nombre de voz de fallback usado cuando build_live_config() no puede cargar
# la configuración dinámica. 'Aoede' es la voz IVR canónica de EnterpriseBot.
VOICE_NAME_FALLBACK = "Aoede"

# Fallback initial greeting used when build_live_config() fails to load
# the dynamic configuration from the database. Contains the original hardcoded
# María / Grupo Álvarez greeting as a safety net.
# Saludo inicial de fallback usado cuando build_live_config() no puede cargar
# la configuración dinámica desde la base de datos. Contiene el saludo original
# hardcodeado de María / Grupo Álvarez como red de seguridad.
INITIAL_GREETING_FALLBACK = (
    "El llamante acaba de contestar la llamada. "
    "Salúdale presentándote como María, asistente virtual del Grupo Álvarez, "
    "con el siguiente mensaje exacto, sin añadir ni modificar nada: "
    "'Hola, me llamo María, soy la asistente virtual del Grupo Álvarez. "
    "¿En qué puedo ayudarle?'"
)


# ---------------------------------------------------------------------------
# VOICE ORCHESTRATION SERVICE / SERVICIO DE ORQUESTACIÓN DE VOZ
# ---------------------------------------------------------------------------

class VoiceOrchestrationService:
    """
    Manages the full lifecycle of a real-time voice session between a Twilio
    caller and the Gemini 3.1 Live API.

    Responsibilities:
        - Initialising the Gemini GenAI client with the project API key.
        - Initialising the Twilio REST client for outbound call control.
        - Establishing the Gemini Live session via the SDK context manager,
          which guarantees the Setup-First protocol (SDK 1.69.0 compliant).
        - Sending the initial greeting text immediately upon session entry.
        - Concurrently: forwarding inbound PCM audio from Twilio to Gemini,
          and receiving PCM audio responses from Gemini to forward back to Twilio.
        - Handling graceful shutdown and error recovery.
    ---
    Gestiona el ciclo de vida completo de una sesión de voz en tiempo real entre
    un llamante de Twilio y la API Gemini 3.1 Live.

    Responsabilidades:
        - Inicializar el cliente Gemini GenAI con la clave de API del proyecto.
        - Inicializar el cliente REST de Twilio para el control de llamadas salientes.
        - Establecer la sesión Gemini Live mediante el context manager del SDK,
          que garantiza el protocolo Setup-First (conforme a SDK 1.69.0).
        - Enviar el texto del saludo inicial de forma inmediata al entrar en la sesión.
        - De forma concurrente: reenviar el audio PCM entrante de Twilio a Gemini,
          y recibir las respuestas de audio PCM de Gemini para reenviarlas a Twilio.
        - Gestionar el apagado elegante y la recuperación de errores.
    """

    def __init__(self, twilio_number: str = "", caller_number: str = ""):
        """
        Initialises the service by loading credentials from environment variables,
        constructing the Gemini and Twilio client instances, and resolving the
        dynamic IVR configuration for the inbound call via build_live_config().

        If build_live_config() raises any exception (e.g. the Twilio number is
        not yet registered in the database, or has no active CallFlow assigned),
        the service falls back silently to the hardcoded SYSTEM_INSTRUCTION_FALLBACK
        and INITIAL_GREETING_FALLBACK constants, logging the failure at ERROR level
        so it is visible in the PythonAnywhere error log for diagnosis.

        Args:
            twilio_number (str): The Twilio E.164 number that received the inbound
                                 call (e.g. '+12603466780'). Passed by InboundCallView
                                 from request.POST.get('To', ''). Defaults to empty
                                 string, which will trigger the fallback path.
            caller_number (str): The caller's E.164 number (From field). Used by
                                 build_live_config() to verify the caller against the
                                 BlockedCaller registry. Defaults to empty string,
                                 which skips the blocked caller check.

        Gemini client: Vertex AI service account JSON — GCP_CREDENTIALS_PATH.
        Twilio client: TWILIO_ACCOUNT_SID + TWILIO_API_KEY_SID +
                       TWILIO_API_KEY_SECRET (API Key auth, not Auth Token auth).
        ---
        Inicializa el servicio cargando las credenciales desde las variables de
        entorno, construyendo las instancias de los clientes Gemini y Twilio, y
        resolviendo la configuración IVR dinámica para la llamada entrante mediante
        build_live_config().

        Si build_live_config() lanza cualquier excepción (p. ej. el número Twilio
        aún no está registrado en la base de datos, o no tiene ningún CallFlow
        activo asignado), el servicio cae silenciosamente al fallback de las
        constantes hardcodeadas SYSTEM_INSTRUCTION_FALLBACK e INITIAL_GREETING_FALLBACK,
        registrando el fallo a nivel ERROR para que sea visible en el log de errores
        de PythonAnywhere para su diagnóstico.

        Args:
            twilio_number (str): El número Twilio E.164 que recibió la llamada
                                 entrante (p. ej. '+12603466780'). Pasado por
                                 InboundCallView desde request.POST.get('To', '').
                                 Por defecto cadena vacía, que activará el fallback.
            caller_number (str): El número E.164 del llamante (campo From). Usado
                                 por build_live_config() para verificar al llamante
                                 contra el registro de BlockedCaller. Por defecto
                                 cadena vacía, que omite la comprobación de bloqueo.

        Cliente Gemini: Service account JSON de Vertex AI — GCP_CREDENTIALS_PATH.
        Cliente Twilio: TWILIO_ACCOUNT_SID + TWILIO_API_KEY_SID +
                        TWILIO_API_KEY_SECRET (autenticación por API Key, no Auth Token).
        """
        # --- Gemini Client Initialisation / Inicialización del Cliente Gemini ---
        # The GenAI client is instantiated once per service instance and reused
        # across all session lifecycle methods. The API key is sourced exclusively
        # from the GEMINI_API_KEY environment variable loaded by Django's settings.py.
        # El cliente GenAI se instancia una vez por instancia de servicio y se
        # reutiliza en todos los métodos del ciclo de vida de la sesión.
        # VERTEX AI AUTHENTICATION — SERVICE ACCOUNT JSON:
        # Authentication uses a Google Cloud service account JSON key file.
        # The path is sourced from GCP_CREDENTIALS_PATH in the project .env.
        # The client is initialised with vertexai=True, project and location
        # from GOOGLE_CLOUD_PROJECT and GOOGLE_CLOUD_LOCATION env vars.
        # This replaces the Gemini Developer API key authentication used
        # with gemini-3.1-flash-live-preview (migrated 2026-04-05).
        #
        # AUTENTICACIÓN VERTEX AI — SERVICE ACCOUNT JSON:
        # La autenticación usa un fichero JSON de cuenta de servicio de Google Cloud.
        # La ruta se obtiene de GCP_CREDENTIALS_PATH en el .env del proyecto.
        # El cliente se inicializa con vertexai=True, proyecto y ubicación
        # desde las variables GOOGLE_CLOUD_PROJECT y GOOGLE_CLOUD_LOCATION.
        # Reemplaza la autenticación por API Key de Gemini Developer API usada
        # con gemini-3.1-flash-live-preview (migrado 2026-04-05).
        from google.oauth2.service_account import Credentials as GCPCredentials

        gcp_credentials_path = os.getenv("GCP_CREDENTIALS_PATH")
        gcp_project = os.getenv("GOOGLE_CLOUD_PROJECT")
        gcp_location = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")

        if not all([gcp_credentials_path, gcp_project]):
            logger.error(
                "[INIT] Credenciales Vertex AI incompletas. Se requieren: "
                "GCP_CREDENTIALS_PATH, GOOGLE_CLOUD_PROJECT."
            )
            raise EnvironmentError(
                "Vertex AI credentials are incomplete. "
                "Cannot initialise VoiceOrchestrationService."
            )

        gcp_credentials = GCPCredentials.from_service_account_file(
            gcp_credentials_path,
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        self.gemini_client = genai.Client(
            vertexai=True,
            project=gcp_project,
            location=gcp_location,
            credentials=gcp_credentials
        )
        logger.info(
            f"[INIT] Cliente Gemini GenAI (Vertex AI) inicializado correctamente. "
            f"Proyecto: {gcp_project} | Ubicación: {gcp_location}"
        )

        # --- Twilio Client Initialisation / Inicialización del Cliente Twilio ---
        # Uses IE1 regional API Key credentials (SID + Secret) with edge="dublin"
        # and region="ie1" so that all REST API calls target the Ireland data center
        # where Spanish numbers (+34) are processed. Using US1 credentials or
        # omitting edge/region causes HTTP 404 when updating or querying calls that
        # were created in IE1, because call records only exist in their origin region.
        # Note: specifying only region= without edge= routes to US1 — both parameters
        # must always be provided together per Twilio SDK documentation.
        # Deadline: api.ie1.twilio.com stops working on 2026-04-28 — the SDK approach
        # with edge+region is the correct migration path.
        # ---
        # Usa credenciales de API Key regional IE1 (SID + Secret) con edge="dublin"
        # y region="ie1" para que todas las llamadas REST API apunten al centro de datos
        # de Irlanda donde se procesan los números españoles (+34). Usar credenciales
        # US1 u omitir edge/region provoca HTTP 404 al actualizar o consultar llamadas
        # creadas en IE1, ya que los registros de llamada solo existen en su región de origen.
        # Nota: especificar solo region= sin edge= enruta a US1 — ambos parámetros deben
        # proporcionarse siempre juntos según la documentación del SDK de Twilio.
        # Fecha límite: api.ie1.twilio.com deja de funcionar el 2026-04-28 — el enfoque
        # SDK con edge+region es la ruta de migración correcta.
        twilio_account_sid    = os.getenv("TWILIO_ACCOUNT_SID")
        twilio_api_key_sid    = os.getenv("TWILIO_API_KEY_SID_IE1")
        twilio_api_key_secret = os.getenv("TWILIO_API_KEY_SECRET_IE1")

        if not all([twilio_account_sid, twilio_api_key_sid, twilio_api_key_secret]):
            logger.error(
                "[INIT] Credenciales de Twilio IE1 incompletas. Se requieren: "
                "TWILIO_ACCOUNT_SID, TWILIO_API_KEY_SID_IE1, TWILIO_API_KEY_SECRET_IE1."
            )
            raise EnvironmentError(
                "Twilio IE1 credentials are incomplete. Cannot initialise VoiceOrchestrationService."
            )
        self.twilio_client = TwilioClient(
            twilio_api_key_sid,
            twilio_api_key_secret,
            twilio_account_sid,
            edge="dublin",
            region="ie1",
        )
        logger.info(
            "[INIT] Cliente Twilio REST inicializado correctamente. "
            "Región: IE1 | Edge: dublin."
        )

        # --- Session State / Estado de Sesión ---
        # Queue for inbound audio chunks arriving from Twilio via the WebSocket view.
        # The queue decouples the Django WebSocket receiver from the Gemini sender
        # coroutine, preventing back-pressure from blocking the WebSocket handler.
        # Cola para los fragmentos de audio entrantes que llegan desde Twilio a través
        # de la vista WebSocket. La cola desacopla el receptor WebSocket de Django de
        # la corrutina emisora de Gemini, evitando que la contrapresión bloquee el
        # manejador WebSocket.
        self.audio_input_queue: asyncio.Queue = asyncio.Queue()

        # Queue for outbound audio chunks to be sent back to Twilio.
        # PCM 24kHz responses from Gemini are placed here by the listener coroutine
        # and consumed by the Twilio sender coroutine.
        # Cola para los fragmentos de audio salientes que se enviarán de vuelta a Twilio.
        # Las respuestas PCM 24kHz de Gemini se colocan aquí por la corrutina escuchadora
        # y son consumidas por la corrutina emisora de Twilio.
        self.audio_output_queue: asyncio.Queue = asyncio.Queue()

        # Flag to signal all coroutines to terminate gracefully.
        # Flag para señalizar a todas las corrutinas que terminen de forma elegante.
        self.session_active: bool = False
        self._pending_transfer_section_id: int | None = None

        # Stream SID assigned by Twilio for this Media Stream session.
        # This value is populated via set_stream_sid() when the Twilio 'start'
        # event is received, and must be included in every outbound 'media' message
        # to comply with the Twilio Media Streams bidirectional protocol.
        # SID del stream asignado por Twilio para esta sesión de Media Stream.
        # Este valor se rellena mediante set_stream_sid() cuando se recibe el evento
        # 'start' de Twilio, y debe incluirse en cada mensaje 'media' saliente para
        # cumplir con el protocolo bidireccional de Twilio Media Streams.
        self.stream_sid: str = ""

        # --- Dynamic IVR Configuration / Configuración IVR Dinámica ---
        # ARCHITECTURE NOTE (2026-04-11 — SynchronousOnlyOperation fix):
        # build_live_config() executes synchronous Django ORM queries. Calling
        # it here from __init__() would raise SynchronousOnlyOperation because
        # __init__() is invoked from inside handle_websocket_stream(), which is
        # an async coroutine running in the aiohttp event loop.
        #
        # Solution: store twilio_number and initialise system_instruction /
        # initial_greeting_text with the hardcoded fallback values here so the
        # service is always in a consistent, callable state after __init__().
        # The real dynamic configuration is loaded asynchronously at the very
        # start of run_voice_session() using:
        #     await sync_to_async(build_live_config)(self.twilio_number)
        # This executes the ORM queries in a dedicated thread pool thread,
        # fully satisfying Django's async safety requirements.
        #
        # NOTA DE ARQUITECTURA (2026-04-11 — corrección SynchronousOnlyOperation):
        # build_live_config() ejecuta queries ORM síncronas de Django. Llamarla
        # aquí desde __init__() lanzaría SynchronousOnlyOperation porque __init__()
        # se invoca desde dentro de handle_websocket_stream(), que es una corrutina
        # async ejecutándose en el bucle de eventos de aiohttp.
        #
        # Solución: almacenar twilio_number e inicializar system_instruction /
        # initial_greeting_text con los valores de fallback hardcodeados aquí para
        # que el servicio esté siempre en un estado consistente y llamable tras
        # __init__(). La configuración dinámica real se carga de forma asíncrona al
        # inicio de run_voice_session() usando:
        #     await sync_to_async(build_live_config)(self.twilio_number)
        # Esto ejecuta las queries ORM en un hilo dedicado del pool de hilos,
        # satisfaciendo completamente los requisitos de seguridad async de Django.
        self.twilio_number: str = twilio_number
        self.caller_number: str = caller_number
        self.system_instruction: str = SYSTEM_INSTRUCTION_FALLBACK
        self.initial_greeting_text: str = INITIAL_GREETING_FALLBACK
        # voice_name is resolved dynamically in run_voice_session() via
        # build_live_config(). Fallback to 'Aoede' until then.
        # voice_name se resuelve dinámicamente en run_voice_session() vía
        # build_live_config(). Fallback a 'Aoede' hasta entonces.
        self.voice_name: str = VOICE_NAME_FALLBACK

        # section_callflow_map maps Section.pk → CallFlow instance for all
        # active sections that have an active CallFlow assigned (Estrategia B).
        # Populated in run_voice_session() from the 4th element of the tuple
        # returned by build_live_config(). Empty dict until then — the fallback
        # path (build_live_config() failure) leaves it as {} and the session
        # continues without section-level routing capability.
        # section_callflow_map mapea Section.pk → instancia de CallFlow para
        # todas las secciones activas con CallFlow activo asignado (Estrategia B).
        # Se puebla en run_voice_session() desde el 4º elemento de la tupla
        # retornada por build_live_config(). Dict vacío hasta entonces — la
        # ruta de fallback (fallo de build_live_config()) lo deja como {} y
        # la sesión continúa sin capacidad de enrutamiento por sección.
        self.section_callflow_map: dict = {}

        # general_call_flow stores the CallFlow instance linked to the PhoneNumber
        # (the welcome/routing flow). Populated in run_voice_session() from
        # build_live_config(). Required by _activate_fallback_section() to
        # resolve the fallback_section FK of the general flow.
        # general_call_flow almacena la instancia de CallFlow vinculada al PhoneNumber
        # (el flujo de bienvenida/enrutamiento). Se puebla en run_voice_session()
        # desde build_live_config(). Necesario por _activate_fallback_section() para
        # resolver el FK fallback_section del flujo general.
        self.general_call_flow = None

        logger.info(
            f"[INIT] VoiceOrchestrationService inicializado. "
            f"Número destino: '{twilio_number}' | Número llamante: '{caller_number}'. "
            "Configuración IVR dinámica se cargará al inicio de run_voice_session()."
        )

    # -----------------------------------------------------------------------
    # SESSION LIFECYCLE / CICLO DE VIDA DE LA SESIÓN
    # -----------------------------------------------------------------------

    async def run_voice_session(self, twilio_websocket) -> None:
        """
        Entry point for a complete voice session lifecycle.

        This method establishes the Gemini Live session using the SDK's
        async context manager, which implements the Setup-First protocol
        automatically: the session object is fully negotiated and ready to
        use upon entry into the `async with` block. No polling for
        setup_complete events is necessary.

        Upon session entry:
            1. The initial greeting text is sent immediately to Gemini,
               triggering the model to produce the opening spoken response.
            2. Three concurrent coroutines are launched via asyncio.gather:
               - _forward_twilio_audio_to_gemini: reads from audio_input_queue
                 and streams PCM chunks to Gemini Live.
               - _receive_gemini_audio: reads from session.receive() and
                 places PCM audio chunks into audio_output_queue.
               - _forward_gemini_audio_to_twilio: reads from audio_output_queue
                 and sends mu-law encoded audio back through the Twilio WebSocket.

        Args:
            twilio_websocket: The active WebSocket connection to Twilio Media Streams.
        ---
        Punto de entrada para el ciclo de vida completo de una sesión de voz.

        Este método establece la sesión Gemini Live usando el context manager
        asíncrono del SDK, que implementa el protocolo Setup-First de forma
        automática: el objeto de sesión está completamente negociado y listo
        para usar al entrar en el bloque `async with`. No es necesario sondear
        eventos setup_complete.

        Al entrar en la sesión:
            1. El texto del saludo inicial se envía inmediatamente a Gemini,
               indicando al modelo que produzca la respuesta hablada de apertura.
            2. Tres corrutinas concurrentes se lanzan mediante asyncio.gather:
               - _forward_twilio_audio_to_gemini: lee de audio_input_queue
                 y transmite fragmentos PCM a Gemini Live.
               - _receive_gemini_audio: lee de session.receive() y coloca
                 fragmentos de audio PCM en audio_output_queue.
               - _forward_gemini_audio_to_twilio: lee de audio_output_queue
                 y envía audio codificado mu-law de vuelta a través del
                 WebSocket de Twilio.

        Args:
            twilio_websocket: La conexión WebSocket activa con Twilio Media Streams.
        """
        self.session_active = True
        logger.info(
            "[SESSION] Iniciando sesión de voz. Conectando con Gemini 3.1 Live API..."
        )

        # --- Async Dynamic IVR Configuration Load / Carga Asíncrona de Config IVR ---
        # build_live_config() performs synchronous Django ORM queries. It is
        # wrapped with sync_to_async() so it executes in a dedicated thread pool
        # thread, fully satisfying Django's async safety requirements (Django 5.2.x).
        # On success, self.system_instruction and self.initial_greeting_text are
        # updated with the real database values for this call. On any exception
        # (number not in DB, no active CallFlow, DB unreachable), the fallback
        # constants set in __init__() are preserved and the session continues.
        #
        # build_live_config() realiza queries ORM síncronas de Django. Se envuelve
        # con sync_to_async() para que se ejecute en un hilo dedicado del pool de
        # hilos, satisfaciendo completamente los requisitos de seguridad async de
        # Django (Django 5.2.x). Si tiene éxito, self.system_instruction y
        # self.initial_greeting_text se actualizan con los valores reales de la
        # base de datos para esta llamada. Ante cualquier excepción (número no en
        # BD, sin CallFlow activo, BD inaccesible), las constantes de fallback
        # establecidas en __init__() se preservan y la sesión continúa.
        try:
            from asgiref.sync import sync_to_async
            from ivr_config.services import build_live_config
            (
                self.system_instruction,
                self.initial_greeting_text,
                self.voice_name,
                self.section_callflow_map,
                self.general_call_flow,
            ) = await sync_to_async(build_live_config)(
                self.twilio_number,
                self.caller_number,
            )
            logger.info(
                f"[CONFIG] Configuración IVR dinámica cargada correctamente "
                f"para el número '{self.twilio_number}' "
                f"(llamante: '{self.caller_number}'). "
                f"Secciones con flujo propio: {len(self.section_callflow_map)}."
            )
        except Exception as config_exc:
            logger.error(
                f"[CONFIG] No se pudo cargar la configuración dinámica para "
                f"'{self.twilio_number}': {type(config_exc).__name__}: {config_exc}. "
                "Usando SYSTEM_INSTRUCTION_FALLBACK e INITIAL_GREETING_FALLBACK."
            )
            # Fallback values were already set in __init__() — no reassignment needed.
            # Los valores de fallback ya fueron establecidos en __init__() — no se
            # necesita reasignación.

        # Build the tools list before the LiveConnectConfig constructor.
        # LiveConnectConfig is a Pydantic BaseModel and only accepts explicit
        # keyword arguments — the *(...) unpacking operator is NOT valid inside
        # a Pydantic constructor. Tools are built conditionally here and passed
        # as the tools= keyword argument.
        #
        # Construir la lista de tools ANTES del constructor de LiveConnectConfig.
        # LiveConnectConfig es un BaseModel de Pydantic y solo acepta keyword
        # arguments explícitos — el operador de desempaquetado *(...) NO es válido
        # dentro de un constructor Pydantic. Las tools se construyen condicionalmente
        # aquí y se pasan como keyword argument tools=.
        if self.section_callflow_map:
            live_tools = [
                types.Tool(
                    function_declarations=[
                        # TOOL 1: route_to_section — Estrategia B, Paso 38
                        # María invoca esta función cuando identifica la sección destino.
                        # El handler recarga el system_instruction con el CallFlow de sección.
                        # TOOL 1: route_to_section — Estrategia B, Step 38
                        # María invokes this when it identifies the target section.
                        # The handler reloads system_instruction with the section CallFlow.
                        types.FunctionDeclaration(
                            name="route_to_section",
                            description=(
                                "Invoca esta función en cuanto identifiques con certeza "
                                "la sección a la que pertenece la llamada. "
                                "Proporciona el section_id de la sección correspondiente "
                                "según la tabla IDENTIFICADORES DE SECCIÓN del "
                                "system_instruction. "
                                "Solo invoca esta función una vez por llamada."
                            ),
                            parameters={
                                "type": "object",
                                "properties": {
                                    "section_id": {
                                        "type": "integer",
                                        "description": (
                                            "El identificador numérico de la sección "
                                            "destino, según la tabla "
                                            "IDENTIFICADORES DE SECCIÓN."
                                        ),
                                    }
                                },
                                "required": ["section_id"],
                            },
                        ),
                        # TOOL 2: transfer_to_section_contact — Paso 39
                        # María invoca esta función cuando está lista para transferir
                        # la llamada al responsable de la sección identificada.
                        # El handler cierra el Media Stream y ejecuta Dial Conference.
                        # TOOL 2: transfer_to_section_contact — Step 39
                        # María invokes this when ready to transfer the call to the
                        # section responsible. Handler closes Media Stream + Dial Conference.
                        types.FunctionDeclaration(
                            name="transfer_to_section_contact",
                            description=(
                                "Invoca esta función cuando estés listo para transferir "
                                "la llamada al responsable de la sección. "
                                "Antes de invocarla, informa al llamante de que le vas "
                                "a transferir y que espere un momento. "
                                "Proporciona el section_id de la sección destino. "
                                "Solo invoca esta función una vez por llamada."
                            ),
                            parameters={
                                "type": "object",
                                "properties": {
                                    "section_id": {
                                        "type": "integer",
                                        "description": (
                                            "El identificador numérico de la sección "
                                            "cuyo responsable debe recibir la transferencia."
                                        ),
                                    }
                                },
                                "required": ["section_id"],
                            },
                        ),
                        # TOOL 3: submit_captured_data — Paso 7 (Hito 5)
                        # María invoca esta función cuando ha recogido todos los
                        # datos requeridos por el DataCaptureSet activo de la sección,
                        # ya sea por inferencia del contexto o por pregunta directa.
                        # El handler persiste un CallDataCapture y dispara la
                        # notificación WhatsApp al contacto referente de la sección.
                        # TOOL 3: submit_captured_data — Step 7 (Milestone 5)
                        # María invokes this when all required DataCaptureSet fields
                        # have been collected, either inferred from context or asked.
                        # Handler persists a CallDataCapture and fires WhatsApp notification.
                        types.FunctionDeclaration(
                            name="submit_captured_data",
                            description=(
                                "Invoca esta función cuando hayas recogido todos los "
                                "datos indicados en las instrucciones de captura de la "
                                "sección. Infiere los datos del contexto natural de la "
                                "conversación — no vuelvas a preguntar datos que el "
                                "llamante ya haya mencionado. "
                                "Proporciona todos los campos capturados en el parámetro "
                                "captured_fields como un objeto clave-valor. "
                                "Solo invoca esta función una vez por sección."
                            ),
                            parameters={
                                "type": "object",
                                "properties": {
                                    "section_id": {
                                        "type": "integer",
                                        "description": (
                                            "El identificador numérico de la sección "
                                            "para la que se han capturado los datos."
                                        ),
                                    },
                                    "captured_fields": {
                                        "type": "object",
                                        "description": (
                                            "Diccionario clave-valor con todos los datos "
                                            "capturados durante la conversación. "
                                            "Las claves deben coincidir con los nombres "
                                            "de campo indicados en las instrucciones "
                                            "de captura de la sección."
                                        ),
                                        "additionalProperties": True,
                                    },
                                },
                                "required": ["section_id", "captured_fields"],
                            },
                        ),
                        # TOOL 4: report_breakdown — Avería interna de flota (H03)
                        # María invoca esta función cuando ha recogido todos los
                        # datos de la avería del chófer y ha recibido confirmación
                        # expresa. Crea un BreakdownTicket en BD e invita al chófer
                        # a enviar su ubicación por WhatsApp si no está en una base.
                        # TOOL 4: report_breakdown — Internal fleet breakdown (H03)
                        # María invokes this when all breakdown data has been collected
                        # and the caller has confirmed. Creates a BreakdownTicket in DB.
                        types.FunctionDeclaration(
                            name="report_breakdown",
                            description=(
                                "Invoca esta función ÚNICAMENTE cuando el llamante haya "
                                "confirmado expresamente todos los datos de la avería. "
                                "No la invoques hasta tener: código de máquina, descripción "
                                "de la avería y confirmación del llamante. "
                                "Solo se invoca una vez por llamada."
                            ),
                            parameters={
                                "type": "object",
                                "properties": {
                                    "machine_code": {
                                        "type": "string",
                                        "description": (
                                            "Código de la máquina tal como lo ha indicado "
                                            "el llamante (p. ej. 'G12', 'B43')."
                                        ),
                                    },
                                    "fault_summary": {
                                        "type": "string",
                                        "description": (
                                            "Descripción breve de la avería, en las palabras "
                                            "del llamante."
                                        ),
                                    },
                                    "fault_location": {
                                        "type": "string",
                                        "description": (
                                            "Ubicación exacta de la avería en la máquina "
                                            "(p. ej. 'rueda delantera lado conductor'). "
                                            "Vacío si no se especificó."
                                        ),
                                    },
                                    "urgency_inferred": {
                                        "type": "string",
                                        "enum": ["BAJA", "MEDIA", "ALTA", "CRITICA"],
                                        "description": (
                                            "Urgencia inferida por el agente según la "
                                            "conversación. NUNCA preguntar directamente "
                                            "al llamante — inferir de si la máquina puede "
                                            "moverse, circular, tiene luces, etc."
                                        ),
                                    },
                                    "caller_name": {
                                        "type": "string",
                                        "description": (
                                            "Nombre del chófer o llamante, si se ha "
                                            "identificado durante la conversación."
                                        ),
                                    },
                                    "caller_phone_reported": {
                                        "type": "string",
                                        "description": (
                                            "Teléfono de contacto facilitado verbalmente "
                                            "por el llamante, si difiere del número de llamada "
                                            "o si llamó desde un teléfono ajeno."
                                        ),
                                    },
                                    "at_base": {
                                        "type": "boolean",
                                        "description": (
                                            "True si el chófer ha confirmado estar en una "
                                            "base conocida de la empresa."
                                        ),
                                    },
                                    "base_name": {
                                        "type": "string",
                                        "description": (
                                            "Nombre de la base si at_base=True. "
                                            "Vacío en caso contrario."
                                        ),
                                    },
                                },
                                "required": [
                                    "machine_code",
                                    "fault_summary",
                                    "urgency_inferred",
                                    "at_base",
                                ],
                            },
                        ),
                        # TOOL 5: submit_call_summary — Resumen final de llamada (H03)
                        # María invoca esta función al despedirse del llamante, siempre,
                        # independientemente del resultado (ticket, transferencia, info).
                        # Persiste un InboundCallLog con todos los datos capturados.
                        # TOOL 5: submit_call_summary — End-of-call summary (H03)
                        # María invokes this on farewell, always, regardless of outcome.
                        # Persists an InboundCallLog with all captured data.
                        types.FunctionDeclaration(
                            name="submit_call_summary",
                            description=(
                                "Invoca esta función SIEMPRE al finalizar la llamada, "
                                "justo antes de despedirte del llamante. "
                                "Registra un resumen de la conversación en el sistema. "
                                "Es obligatoria en todas las llamadas sin excepción."
                            ),
                            parameters={
                                "type": "object",
                                "properties": {
                                    "caller_name": {
                                        "type": "string",
                                        "description": (
                                            "Nombre del llamante si se identificó "
                                            "durante la conversación. Vacío si no."
                                        ),
                                    },
                                    "caller_phone_reported": {
                                        "type": "string",
                                        "description": (
                                            "Teléfono facilitado verbalmente por el "
                                            "llamante, si difiere del CLI o si llamó "
                                            "desde teléfono ajeno. Vacío si no aplica."
                                        ),
                                    },
                                    "call_reason": {
                                        "type": "string",
                                        "description": (
                                            "Motivo principal de la llamada en una "
                                            "frase breve."
                                        ),
                                    },
                                    "call_type": {
                                        "type": "string",
                                        "enum": [
                                            "BREAKDOWN",
                                            "TRANSFER",
                                            "INFO",
                                            "OTHER",
                                        ],
                                        "description": (
                                            "Tipo de llamada: BREAKDOWN si avería "
                                            "interna de flota, TRANSFER si se "
                                            "transfirió, INFO si solo informativa, "
                                            "OTHER en cualquier otro caso."
                                        ),
                                    },
                                    "outcome": {
                                        "type": "string",
                                        "enum": [
                                            "TICKET_CREATED",
                                            "TRANSFERRED",
                                            "INFO_GIVEN",
                                            "ABANDONED",
                                            "OTHER",
                                        ],
                                        "description": "Resultado final de la llamada.",
                                    },
                                    "raw_summary": {
                                        "type": "string",
                                        "description": (
                                            "Resumen libre de la conversación en 2-4 "
                                            "frases: quién llamó, por qué, qué se "
                                            "resolvió y cualquier dato relevante."
                                        ),
                                    },
                                },
                                "required": [
                                    "call_reason",
                                    "call_type",
                                    "outcome",
                                    "raw_summary",
                                ],
                            },
                        ),
                    ]
                )
            ]
            logger.info(
                "[SESSION] Tools registradas: route_to_section, "
                "transfer_to_section_contact, submit_captured_data, "
                "report_breakdown, submit_call_summary."
            )
        else:
            live_tools = None
            logger.info(
                "[SESSION] Sin secciones cualificadas — no se registran tools."
            )

        # Build the Gemini Live session configuration.
        # The response modality is AUDIO — we want raw PCM audio back, not text.
        # The system instruction defines the IVR agent's persona.
        # Construir la configuración de la sesión Gemini Live.
        # La modalidad de respuesta es AUDIO — queremos PCM sin procesar de vuelta,
        # no texto. La instrucción de sistema define la persona del agente IVR.
        live_config = types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            system_instruction=types.Content(
                parts=[types.Part(text=self.system_instruction)]
            ),
            # SPEECH CONFIG — VOICE REQUIRED FOR NATIVE AUDIO MODEL:
            # gemini-live-2.5-flash-native-audio requires an explicit voice
            # in speech_config to guarantee audio generation. Without it the
            # model may generate silence or text instead of audio.
            # Voice 'Aoede' is a female voice suitable for IVR telephony.
            # Language is selected automatically from system_instruction content.
            # Source: googleapis/python-genai issue #1725 + Live API capabilities
            # guide, verified 2026-04-05.
            #
            # SPEECH CONFIG — VOZ OBLIGATORIA PARA MODELO DE AUDIO NATIVO:
            # gemini-live-2.5-flash-native-audio requiere una voz explícita en
            # speech_config para garantizar la generación de audio. Sin ella el
            # modelo puede generar silencio o texto en lugar de audio.
            # La voz 'Aoede' es una voz femenina adecuada para telefonía IVR.
            # El idioma se selecciona automáticamente del contenido del system_instruction.
            # Fuente: issue #1725 de googleapis/python-genai + guía de capacidades
            # de Live API, verificado 2026-04-05.
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name=self.voice_name
                    )
                )
            ),
            # THINKING CONFIG: Not supported by gemini-live-2.5-flash-native-audio.
            # Gemini 2.5 models use thinkingBudget (token count) instead of
            # thinkingLevel. Omitting thinking_config uses the model default,
            # which is optimised for low latency in native audio sessions.
            # Source: Vertex AI Live API capabilities guide, verified 2026-04-05.
            # THINKING CONFIG: No soportado por gemini-live-2.5-flash-native-audio.
            # Los modelos Gemini 2.5 usan thinkingBudget (número de tokens) en lugar
            # de thinkingLevel. Omitir thinking_config usa el valor por defecto del
            # modelo, optimizado para baja latencia en sesiones de audio nativo.
            # Fuente: guía de capacidades de Live API en Vertex AI, verificado 2026-04-05.
            # TOOLS — passed as explicit keyword argument (Pydantic-safe pattern).
            # live_tools is None when section_callflow_map is empty — Pydantic
            # accepts None for optional list fields and omits them from the payload.
            # TOOLS — pasadas como keyword argument explícito (patrón seguro para Pydantic).
            # live_tools es None cuando section_callflow_map está vacío — Pydantic
            # acepta None para campos de lista opcionales y los omite del payload.
            tools=live_tools,
            # REALTIME INPUT CONFIG — VAD DISABLED FOR TELEPHONY:
            # Server-side automatic VAD must be disabled for telephony
            # bridges. In a phone call, the outbound audio played to the
            # caller is captured by the handset microphone and returned
            # as acoustic echo into the inbound audio stream. With VAD
            # enabled, Gemini interprets this echo as user speech,
            # immediately fires an 'interrupted' signal, cancels the
            # ongoing audio generation, and drains the output queue —
            # producing total silence on the caller's end.
            # Disabling VAD removes this echo-triggered self-interruption.
            # Standard pattern per Gemini Live API guide (2026-03-26).
            # CONFIGURACIÓN DE ENTRADA EN TIEMPO REAL — VAD DESHABILITADO
            # PARA TELEFONÍA:
            # El VAD automático del servidor debe deshabilitarse en puentes
            # de telefonía. En una llamada telefónica, el audio de salida
            # reproducido al llamante es capturado por el micrófono del
            # auricular y devuelto como eco acústico al flujo de audio
            # entrante. Con el VAD habilitado, Gemini interpreta este eco
            # como voz del usuario, activa inmediatamente una señal
            # 'interrupted', cancela la generación de audio en curso y
            # vacía la cola de salida — produciendo silencio total en el
            # lado del llamante.
            # Deshabilitar el VAD elimina esta auto-interrupción por eco.
            # Patrón estándar según la guía de Live API (2026-03-26).
            realtime_input_config=types.RealtimeInputConfig(
                automatic_activity_detection=types.AutomaticActivityDetection(
                    disabled=True
                )
            ),
        )

        try:
            # SETUP-FIRST PROTOCOL (SDK 1.69.0 COMPLIANT):
            # The async context manager `client.aio.live.connect()` performs the
            # full WebSocket handshake with Google's Live API infrastructure.
            # By the time execution reaches the first line inside the `async with`
            # block, the session is fully established and ready to accept data.
            # There is no need for — and the SDK does not expose — an explicit
            # setup_complete event in the session.receive() stream.
            #
            # PROTOCOLO SETUP-FIRST (CONFORME A SDK 1.69.0):
            # El context manager asíncrono `client.aio.live.connect()` realiza el
            # handshake WebSocket completo con la infraestructura de Live API de Google.
            # En el momento en que la ejecución alcanza la primera línea dentro del
            # bloque `async with`, la sesión está completamente establecida y lista
            # para aceptar datos. No hay necesidad de — y el SDK no expone — ningún
            # evento setup_complete explícito en el flujo session.receive().
            async with self.gemini_client.aio.live.connect(
                model=GEMINI_MODEL,
                config=live_config
            ) as session:

                logger.info(
                    "[SDK] Handshake Gemini 3.1 (SetupComplete: True) VALIDADO. "
                    "Sesión lista para recibir datos."
                )

                # STEP 1: Send the initial greeting immediately upon session entry.
                # This is safe because the context manager guarantees the session
                # is ready. The correct SDK 1.69.0 signature for text input is:
                #     await session.send_realtime_input(text="...")
                # The end_of_turn argument is NOT valid for text sends in SDK 1.69.0
                # and causes a 1007 invalid argument error that closes the WebSocket.
                # PASO 1: Enviar el saludo inicial de forma inmediata al entrar en la sesión.
                # Esto es seguro porque el context manager garantiza que la sesión
                # está lista. La firma correcta del SDK 1.69.0 para entrada de texto es:
                #     await session.send_realtime_input(text="...")
                # El argumento end_of_turn NO es válido para envíos de texto en SDK 1.69.0
                # y provoca un error 1007 invalid argument que cierra el WebSocket.
                logger.info(
                    "[SESSION] Enviando saludo inicial a Gemini..."
                )
                # GREETING TRIGGER — send_client_content FOR GEMINI 2.5:
                # Unlike Gemini 3.1 (where send_client_content was restricted
                # to initial history seeding), Gemini 2.5 supports
                # send_client_content with turn_complete=True to send text
                # and trigger an immediate audio response from the model.
                # This is the documented pattern for Vertex AI Live API
                # with gemini-live-2.5-flash-native-audio.
                # Source: Vertex AI configure-gemini-capabilities guide,
                # verified 2026-04-05.
                #
                # TRIGGER DE SALUDO — send_client_content PARA GEMINI 2.5:
                # A diferencia de Gemini 3.1 (donde send_client_content estaba
                # restringido al sembrado de historial inicial), Gemini 2.5
                # soporta send_client_content con turn_complete=True para enviar
                # texto y disparar una respuesta de audio inmediata del modelo.
                # Este es el patrón documentado para Live API en Vertex AI
                # con gemini-live-2.5-flash-native-audio.
                # Fuente: guía configure-gemini-capabilities de Vertex AI,
                # verificado 2026-04-05.
                await asyncio.wait_for(
                    session.send_client_content(
                        turns=types.Content(
                            role="user",
                            parts=[types.Part(text=self.initial_greeting_text)]
                        ),
                        turn_complete=True
                    ),
                    timeout=TIMEOUT_INITIAL_GREETING_SECONDS
                )
                logger.info(
                    "[SESSION] Saludo inicial enviado correctamente "
                    "(send_client_content Gemini 2.5). "
                    "Lanzando corrutinas concurrentes..."
                )

                # STEP 2: Launch all three concurrent coroutines.
                # asyncio.gather runs them concurrently and propagates the first
                # exception raised. return_exceptions=False means any coroutine
                # failure will cancel the others and propagate to this level.
                # PASO 2: Lanzar las tres corrutinas concurrentes.
                # asyncio.gather las ejecuta de forma concurrente y propaga la primera
                # excepción lanzada. return_exceptions=False significa que cualquier
                # fallo de una corrutina cancelará las otras y propagará a este nivel.
                # return_exceptions=True prevents a single coroutine failure
                # from cancelling its siblings. Each coroutine handles its own
                # errors internally; gather collects results/exceptions without
                # propagating them upward. This is essential for the outer
                # while self.session_active loop to remain stable across
                # multiple Gemini turns and interruption events.
                # return_exceptions=True evita que el fallo de una corrutina
                # cancele a sus hermanas. Cada corrutina gestiona sus propios
                # errores internamente; gather recopila resultados/excepciones
                # sin propagarlas hacia arriba. Esto es esencial para que el
                # bucle externo while self.session_active permanezca estable
                # a través de múltiples turnos e interrupciones de Gemini.
                gather_results = await asyncio.gather(
                    self._forward_twilio_audio_to_gemini(session),
                    self._receive_gemini_audio(session),
                    self._forward_gemini_audio_to_twilio(twilio_websocket),
                    return_exceptions=True
                )
                # Log any exceptions collected by gather for full traceability.
                # Registrar cualquier excepción recopilada por gather para
                # trazabilidad completa.
                coroutine_names = [
                    "_forward_twilio_audio_to_gemini",
                    "_receive_gemini_audio",
                    "_forward_gemini_audio_to_twilio",
                ]
                for coro_name, result in zip(coroutine_names, gather_results):
                    if isinstance(result, Exception):
                        logger.error(
                            f"[SESSION] Excepción en corrutina '{coro_name}': "
                            f"{type(result).__name__}: {result}"
                        )

        except asyncio.TimeoutError:
            logger.error(
                "[SESSION] Timeout al intentar conectar o enviar el saludo inicial "
                f"a Gemini Live (límite: {TIMEOUT_INITIAL_GREETING_SECONDS}s). "
                "La infraestructura Preview puede estar experimentando alta latencia."
            )
        except Exception as exc:
            logger.error(
                f"[SESSION] Error inesperado en la sesión de voz: {exc}",
                exc_info=True
            )
        finally:
            self.session_active = False
            logger.info("[SESSION] Sesión de voz finalizada.")

    # -----------------------------------------------------------------------
    # INBOUND AUDIO PIPELINE / PIPELINE DE AUDIO ENTRANTE
    # -----------------------------------------------------------------------

    async def receive_twilio_audio(self, raw_payload: str) -> None:
        """
        Public interface for the Django WebSocket view to deliver inbound audio.

        The WebSocket view calls this method each time a Twilio Media Streams
        'media' event arrives. The raw base64-encoded mu-law audio payload is
        decoded, transcoded to PCM 16kHz by the sidecar bridge, and placed onto
        the audio_input_queue for the Gemini sender coroutine to consume.

        Args:
            raw_payload (str): The raw JSON string from the Twilio WebSocket event.
        ---
        Interfaz pública para que la vista WebSocket de Django entregue audio entrante.

        La vista WebSocket llama a este método cada vez que llega un evento 'media'
        de Twilio Media Streams. El payload de audio mu-law codificado en base64 se
        decodifica, se transcodifica a PCM 16kHz mediante el sidecar bridge, y se
        coloca en audio_input_queue para que la corrutina emisora de Gemini lo consuma.

        Args:
            raw_payload (str): La cadena JSON bruta del evento WebSocket de Twilio.
        """
        try:
            data = json.loads(raw_payload)
            if data.get("event") != "media":
                # Non-media events (start, stop, mark) are acknowledged but not
                # forwarded to Gemini.
                # Los eventos no-media (start, stop, mark) se reconocen pero no
                # se reenvían a Gemini.
                logger.debug(f"[TWILIO-RX] Evento no-media recibido: {data.get('event')}")
                return

            # Extract the base64-encoded mu-law audio chunk from the Twilio payload.
            # Extraer el fragmento de audio mu-law codificado en base64 del payload de Twilio.
            mulaw_b64 = data["media"]["payload"]
            mulaw_bytes = base64.b64decode(mulaw_b64)

            # Transcode mu-law 8kHz → PCM 16kHz via audioop sidecar.
            # This is the mandatory conversion for Gemini Live compatibility.
            # Transcodificar mu-law 8kHz → PCM 16kHz mediante el sidecar audioop.
            # Esta es la conversión obligatoria para la compatibilidad con Gemini Live.
            pcm_16khz_bytes = self._transcode_mulaw_to_pcm16k(mulaw_bytes)

            # Place the PCM chunk onto the queue. The queue is non-blocking here;
            # if the consumer is slow, chunks accumulate in memory. For a production
            # system a bounded queue with overflow handling would be appropriate.
            # Colocar el fragmento PCM en la cola. La cola no es bloqueante aquí;
            # si el consumidor es lento, los fragmentos se acumulan en memoria.
            # Para un sistema de producción sería apropiada una cola acotada con
            # gestión de desbordamiento.
            await self.audio_input_queue.put(pcm_16khz_bytes)

        except (json.JSONDecodeError, KeyError) as exc:
            logger.warning(
                f"[TWILIO-RX] Payload de Twilio malformado o con clave ausente: {exc}"
            )
        except Exception as exc:
            logger.error(
                f"[TWILIO-RX] Error inesperado al procesar audio entrante de Twilio: {exc}",
                exc_info=True
            )

    async def _forward_twilio_audio_to_gemini(self, session) -> None:
        """
        Coroutine: continuously reads PCM 16kHz audio from audio_input_queue,
        detects speech activity via RMS energy analysis, and streams audio to
        the active Gemini Live session using the official send_realtime_input
        pattern with explicit activity_start / activity_end signals.

        Activity Management (VAD disabled=True):
            When server-side VAD is disabled (mandatory for telephony to prevent
            acoustic echo self-interruption), the client MUST signal manually when
            the user starts and stops speaking. Without these signals Gemini never
            knows a new caller turn has begun and produces no response after turn 1.

            The detection algorithm:
                - Computes RMS energy of each PCM frame.
                - Speech confirmed: SPEECH_FRAMES_TO_START_ACTIVITY consecutive
                  frames above SILENCE_THRESHOLD_RMS → emit activity_start.
                - Silence confirmed: SILENCE_FRAMES_TO_END_ACTIVITY consecutive
                  frames below SILENCE_THRESHOLD_RMS → emit activity_end.
                - Audio is streamed continuously regardless of activity state;
                  the signals bracket the speech segment for Gemini's turn logic.

        This coroutine runs concurrently with _receive_gemini_audio and
        _forward_gemini_audio_to_twilio for the duration of the session.
        It terminates when session_active is set to False and the queue is drained.
        ---
        Corrutina: lee continuamente audio PCM 16kHz de audio_input_queue,
        detecta actividad de voz mediante análisis de energía RMS, y transmite
        el audio a la sesión Gemini Live activa usando el patrón oficial
        send_realtime_input con señales explícitas activity_start / activity_end.

        Gestión de Actividad (VAD disabled=True):
            Cuando el VAD del servidor está deshabilitado (obligatorio para telefonía
            para evitar la auto-interrupción por eco acústico), el cliente DEBE señalizar
            manualmente cuándo el usuario empieza y termina de hablar. Sin estas señales
            Gemini nunca sabe que ha comenzado un nuevo turno del llamante y no produce
            respuesta tras el turno 1.

            El algoritmo de detección:
                - Calcula la energía RMS de cada frame PCM.
                - Voz confirmada: SPEECH_FRAMES_TO_START_ACTIVITY frames consecutivos
                  por encima de SILENCE_THRESHOLD_RMS → emitir activity_start.
                - Silencio confirmado: SILENCE_FRAMES_TO_END_ACTIVITY frames consecutivos
                  por debajo de SILENCE_THRESHOLD_RMS → emitir activity_end.
                - El audio se transmite continuamente independientemente del estado de
                  actividad; las señales delimitan el segmento de voz para la lógica
                  de turnos de Gemini.

        Esta corrutina se ejecuta de forma concurrente con _receive_gemini_audio y
        _forward_gemini_audio_to_twilio durante la duración de la sesión.
        Termina cuando session_active se establece en False y la cola se vacía.
        """
        logger.info("[GEMINI-TX] Corrutina de envío de audio a Gemini iniciada.")

        # --- Activity Detection State / Estado de Detección de Actividad ---
        # Tracks whether an activity_start has been sent to Gemini and not yet
        # closed with activity_end. Essential to avoid duplicate signals.
        # Rastrea si se ha enviado un activity_start a Gemini que aún no ha sido
        # cerrado con activity_end. Esencial para evitar señales duplicadas.
        is_speaking: bool = False

        # Consecutive frame counters for hysteresis:
        #   - speech_frame_count: frames above threshold since last silence.
        #   - silence_frame_count: frames below threshold since last speech.
        # Contadores de frames consecutivos para histéresis:
        #   - speech_frame_count: frames por encima del umbral desde el último silencio.
        #   - silence_frame_count: frames por debajo del umbral desde la última voz.
        speech_frame_count: int = 0
        silence_frame_count: int = 0

        try:
            while self.session_active:
                try:
                    # Wait for a PCM 16kHz chunk from the input queue.
                    # The chunk was already transcoded from mu-law 8kHz by
                    # receive_twilio_audio before being enqueued.
                    # Esperar un fragmento PCM 16kHz de la cola de entrada.
                    # El fragmento ya fue transcodificado desde mu-law 8kHz por
                    # receive_twilio_audio antes de ser encolado.
                    pcm_chunk = await asyncio.wait_for(
                        self.audio_input_queue.get(),
                        timeout=TIMEOUT_AUDIO_RECEIVE_SECONDS
                    )
                except asyncio.TimeoutError:
                    # No audio in the timeout window — normal inter-utterance silence.
                    # If an activity window is open, the extended silence should
                    # close it to avoid Gemini waiting indefinitely for activity_end.
                    # Sin audio en la ventana de timeout — silencio normal entre turnos.
                    # Si hay una ventana de actividad abierta, el silencio extendido
                    # debe cerrarla para evitar que Gemini espere indefinidamente.
                    if is_speaking:
                        logger.info(
                            "[GEMINI-TX] Silencio extendido detectado (timeout de cola). "
                            "Cerrando ventana de actividad con activity_end..."
                        )
                        try:
                            await session.send_realtime_input(
                                activity_end=types.ActivityEnd()
                            )
                            logger.info("[GEMINI-TX] activity_end enviado (timeout de cola).")
                        except Exception as ae_exc:
                            logger.warning(
                                f"[GEMINI-TX] Error al enviar activity_end por timeout: {ae_exc}"
                            )
                        is_speaking = False
                        speech_frame_count = 0
                        silence_frame_count = 0
                    continue

                # -----------------------------------------------------------
                # RMS ENERGY COMPUTATION / CÁLCULO DE ENERGÍA RMS
                # -----------------------------------------------------------
                # PCM 16kHz audio is 16-bit signed little-endian (2 bytes/sample).
                # struct.unpack reads the raw bytes as an array of signed shorts.
                # El audio PCM 16kHz es signed little-endian de 16-bit (2 bytes/muestra).
                # struct.unpack lee los bytes brutos como un array de shorts con signo.
                num_samples = len(pcm_chunk) // 2
                if num_samples == 0:
                    self.audio_input_queue.task_done()
                    continue

                samples = struct.unpack(f"<{num_samples}h", pcm_chunk[:num_samples * 2])
                rms = math.sqrt(sum(s * s for s in samples) / num_samples)

                # -----------------------------------------------------------
                # ACTIVITY STATE MACHINE / MÁQUINA DE ESTADOS DE ACTIVIDAD
                # -----------------------------------------------------------
                if rms >= SILENCE_THRESHOLD_RMS:
                    # Frame with speech energy detected.
                    # Frame con energía de voz detectada.
                    silence_frame_count = 0
                    speech_frame_count += 1

                    if not is_speaking and speech_frame_count >= SPEECH_FRAMES_TO_START_ACTIVITY:
                        # Sufficient consecutive speech frames — open activity window.
                        # Suficientes frames consecutivos de voz — abrir ventana de actividad.
                        logger.info(
                            f"[GEMINI-TX] Voz detectada ({speech_frame_count} frames). "
                            "Enviando activity_start a Gemini..."
                        )
                        try:
                            await session.send_realtime_input(
                                activity_start=types.ActivityStart()
                            )
                            # LATENCY-P5: Timestamp when next caller turn starts.
                            # Measures inter-turn gap: from Gemini turn_complete to next
                            # caller speech. Confirms whether VAD thresholds add delay
                            # before Gemini can start processing the next utterance.
                            # LATENCIA-P5: Marca cuando el siguiente turno del llamante comienza.
                            # Mide el intervalo entre turnos: desde turn_complete de Gemini
                            # hasta la siguiente voz del llamante. Confirma si los umbrales VAD
                            # añaden retardo antes de que Gemini pueda procesar el siguiente turno.
                            _t_next_start = time.monotonic()
                            logger.info(
                                f"[LATENCY-P5] activity_start siguiente turno — "
                                f"t={_t_next_start:.3f}s"
                            )
                            logger.info("[GEMINI-TX] activity_start enviado correctamente.")
                        except Exception as as_exc:
                            logger.warning(
                                f"[GEMINI-TX] Error al enviar activity_start: {as_exc}"
                            )
                        is_speaking = True
                else:
                    # Frame with silence energy detected.
                    # Frame con energía de silencio detectada.
                    speech_frame_count = 0
                    silence_frame_count += 1

                    if is_speaking and silence_frame_count >= SILENCE_FRAMES_TO_END_ACTIVITY:
                        # Sufficient consecutive silence frames — close activity window.
                        # Suficientes frames consecutivos de silencio — cerrar ventana.
                        logger.info(
                            f"[GEMINI-TX] Silencio detectado ({silence_frame_count} frames). "
                            "Enviando activity_end a Gemini..."
                        )
                        try:
                            await session.send_realtime_input(
                                activity_end=types.ActivityEnd()
                            )
                            # LATENCY-P1: Timestamp when activity_end is sent.
                            # Marks the end of the detected caller speech turn.
                            # Also stored on self for cross-coroutine TTFT calculation (P2).
                            # LATENCIA-P1: Marca de tiempo al enviar activity_end.
                            # Marca el fin del turno de voz detectado del llamante.
                            # Se almacena en self para el cálculo de TTFT entre corrutinas (P2).
                            _t_activity_end = time.monotonic()
                            self._t_last_activity_end = _t_activity_end
                            self._t_first_audio_logged = False  # reset for next turn
                            logger.info(
                                "[LATENCY-P1] activity_end enviado — "
                                f"t={_t_activity_end:.3f}s"
                            )
                        except Exception as ae_exc:
                            logger.warning(
                                f"[GEMINI-TX] Error al enviar activity_end: {ae_exc}"
                            )
                        is_speaking = False
                        silence_frame_count = 0

                # -----------------------------------------------------------
                # AUDIO FORWARDING / REENVÍO DE AUDIO
                # -----------------------------------------------------------
                # Audio is sent to Gemini regardless of activity state.
                # The activity signals bracket the speech for turn logic;
                # the audio stream must be continuous to avoid buffer gaps.
                # El audio se envía a Gemini independientemente del estado de actividad.
                # Las señales de actividad delimitan la voz para la lógica de turnos;
                # el stream de audio debe ser continuo para evitar huecos en el buffer.
                await session.send_realtime_input(
                    audio=types.Blob(
                        data=pcm_chunk,
                        mime_type=GEMINI_AUDIO_MIME_TYPE
                    )
                )
                logger.debug(
                    f"[GEMINI-TX] Fragmento PCM enviado a Gemini: "
                    f"{len(pcm_chunk)} bytes | RMS: {rms:.1f} | "
                    f"Hablando: {is_speaking}"
                )
                self.audio_input_queue.task_done()

        except Exception as exc:
            logger.error(
                f"[GEMINI-TX] Error en la corrutina de envío a Gemini: {exc}",
                exc_info=True
            )
        finally:
            # If the session ends while an activity window is open, close it cleanly
            # to avoid leaving Gemini in a waiting state.
            # Si la sesión termina con una ventana de actividad abierta, cerrarla
            # limpiamente para evitar dejar a Gemini en estado de espera.
            if is_speaking:
                try:
                    await session.send_realtime_input(
                        activity_end=types.ActivityEnd()
                    )
                    logger.info(
                        "[GEMINI-TX] activity_end enviado en finally (cierre de sesión)."
                    )
                except Exception:
                    pass
            logger.info("[GEMINI-TX] Corrutina de envío de audio a Gemini finalizada.")

    # -----------------------------------------------------------------------
    # OUTBOUND AUDIO PIPELINE / PIPELINE DE AUDIO SALIENTE
    # -----------------------------------------------------------------------

    async def _receive_gemini_audio(self, session) -> None:
        """
        Coroutine: continuously reads responses from the Gemini Live session
        and places audio chunks onto audio_output_queue for delivery to Twilio.

        Iterates over session.receive() which yields LiveServerMessage objects.
        Audio data is found in response.server_content.model_turn.parts[n].inline_data.
        Interruption signals from Gemini (VAD-driven) are handled by flushing
        the output queue to stop playback immediately.
        ---
        Corrutina: lee continuamente las respuestas de la sesión Gemini Live y
        coloca fragmentos de audio en audio_output_queue para su entrega a Twilio.

        Itera sobre session.receive() que produce objetos LiveServerMessage.
        Los datos de audio se encuentran en
        response.server_content.model_turn.parts[n].inline_data.
        Las señales de interrupción de Gemini (dirigidas por VAD) se gestionan
        vaciando la cola de salida para detener la reproducción de forma inmediata.
        """
        logger.info("[GEMINI-RX] Corrutina de recepción de audio de Gemini iniciada.")
        try:
            # OUTER LOOP: The google-genai SDK's session.receive() async iterator
            # is exhausted and terminates after each `turn_complete` or `interrupted`
            # signal from Gemini (documented in googleapis/python-genai issue #1224).
            # To maintain continuous listening across multiple turns, we re-enter
            # the iterator on each exhaustion by wrapping it in this outer while loop.
            # BUCLE EXTERNO: El iterador asíncrono session.receive() del SDK
            # google-genai se agota y termina tras cada señal `turn_complete` o
            # `interrupted` de Gemini (documentado en el issue #1224 de
            # googleapis/python-genai). Para mantener la escucha continua a través
            # de múltiples turnos, re-entramos en el iterador en cada agotamiento
            # envolviendo el bucle interno en este while externo.
            while self.session_active:
                async for response in session.receive():

                # --- Interruption Handling / Gestión de Interrupciones ---
                # If Gemini's VAD detects the user is speaking while the model
                # is responding, it sends an interrupted signal. We must flush
                # the output queue immediately to stop sending stale audio to Twilio.
                # Si el VAD de Gemini detecta que el usuario está hablando mientras
                # el modelo está respondiendo, envía una señal de interrupción.
                # Debemos vaciar la cola de salida inmediatamente para dejar de
                # enviar audio obsoleto a Twilio.
                    if (
                        response.server_content
                        and response.server_content.interrupted is True
                    ):
                        logger.info(
                            "[GEMINI-RX] Señal de interrupción recibida de Gemini. "
                            "Vaciando cola de audio de salida..."
                        )
                        # Drain the output queue to discard buffered audio from the
                        # interrupted response.
                        # Vaciar la cola de salida para descartar el audio en buffer
                        # de la respuesta interrumpida.
                        while not self.audio_output_queue.empty():
                            try:
                                self.audio_output_queue.get_nowait()
                                self.audio_output_queue.task_done()
                            except asyncio.QueueEmpty:
                                break
                        continue

                    # --- Tool Call Handler — route_to_section (Estrategia B, Paso 38) ---
                    # Gemini invokes route_to_section() when it identifies the caller's
                    # intended section. We capture the tool_call, execute the section
                    # reload, and respond with tool_response so the model can continue.
                    # Gemini invoca route_to_section() cuando identifica la sección
                    # destino del llamante. Capturamos el tool_call, ejecutamos la
                    # recarga de sección y respondemos con tool_response para que
                    # el modelo pueda continuar.
                    if response.tool_call:
                        for fn_call in response.tool_call.function_calls:
                            if fn_call.name == "route_to_section":
                                section_id = int(fn_call.args.get("section_id", -1))
                                logger.info(
                                    f"[ESTRATEGIA-B] tool_call route_to_section recibido. "
                                    f"section_id={section_id}. "
                                    "Ejecutando _reload_session_for_section()..."
                                )
                                success = await self._reload_session_for_section(
                                    session, section_id
                                )
                                # Respond to Gemini with the tool result so it can
                                # continue the conversation with the new context.
                                # Responder a Gemini con el resultado de la tool para
                                # que continúe la conversación con el nuevo contexto.
                                try:
                                    await session.send_client_content(
                                        turns=types.Content(
                                            role="tool",
                                            parts=[
                                                types.Part(
                                                    function_response=types.FunctionResponse(
                                                        name="route_to_section",
                                                        response={
                                                            "success": success,
                                                            "section_id": section_id,
                                                        },
                                                    )
                                                )
                                            ],
                                        ),
                                        turn_complete=True,
                                    )
                                    logger.info(
                                        f"[ESTRATEGIA-B] tool_response route_to_section "
                                        f"enviado correctamente (success={success})."
                                    )
                                except Exception as tr_exc:
                                    logger.error(
                                        f"[ESTRATEGIA-B] Error al enviar tool_response: "
                                        f"{type(tr_exc).__name__}: {tr_exc}",
                                        exc_info=True,
                                    )
                            elif fn_call.name == "submit_captured_data":
                                # --- Tool Call Handler: submit_captured_data (Paso 7, Hito 5) ---
                                # Persist CallDataCapture and fire WhatsApp notification.
                                # Persistir CallDataCapture y disparar notificación WhatsApp.
                                _section_id_cap = int(fn_call.args.get("section_id", -1))
                                _captured_fields = fn_call.args.get("captured_fields", {})
                                logger.info(
                                    f"[PASO-7] tool_call submit_captured_data recibido. "
                                    f"section_id={_section_id_cap} | "
                                    f"campos={list(_captured_fields.keys())}"
                                )
                                try:
                                    from django.utils.timezone import now as _now
                                    from ivr_config.models import (
                                        CallDataCapture as _CDC,
                                        Section as _Section,
                                        Contact as _Contact,
                                    )
                                    from whatsapp.services import send_capture_notification
                                    from asgiref.sync import sync_to_async

                                    # Resolve section and referent contact from DB.
                                    # Resolver sección y contacto referente desde BD.
                                    def _persist_capture():
                                        section_obj = _Section.objects.filter(
                                            pk=_section_id_cap
                                        ).first()
                                        contact_obj = None
                                        if section_obj:
                                            sc = section_obj.section_contacts.order_by(
                                                "priority"
                                            ).select_related("contact").first()
                                            if sc:
                                                contact_obj = sc.contact
                                        cdc = _CDC.objects.create(
                                            call_sid=self.call_sid,
                                            call_flow=self.general_call_flow,
                                            section=section_obj,
                                            contact=contact_obj,
                                            captured_data=_captured_fields,
                                        )
                                        logger.info(
                                            f"[PASO-7] CallDataCapture persistido — "
                                            f"pk={cdc.pk} | "
                                            f"section={section_obj} | "
                                            f"contact={contact_obj}"
                                        )
                                        return cdc

                                    cdc_instance = await sync_to_async(_persist_capture)()

                                    # Fire WhatsApp notification asynchronously.
                                    # No se espera confirmación — el transfer no
                                    # debe bloquearse por el envío WhatsApp.
                                    # Disparar notificación WhatsApp de forma asíncrona.
                                    # No se espera confirmación — la transferencia
                                    # no debe bloquearse por el envío WhatsApp.
                                    _wa_sender = os.getenv(
                                        "TWILIO_WHATSAPP_SENDER", ""
                                    )
                                    if _wa_sender:
                                        asyncio.create_task(
                                            asyncio.to_thread(
                                                send_capture_notification,
                                                cdc_instance,
                                                _wa_sender,
                                            )
                                        )
                                        logger.info(
                                            "[PASO-7] Tarea WhatsApp notification "
                                            "disparada de forma asíncrona."
                                        )
                                    else:
                                        logger.warning(
                                            "[PASO-7] TWILIO_WHATSAPP_SENDER no "
                                            "configurado — notificación WhatsApp omitida."
                                        )
                                except Exception as cap_exc:
                                    logger.error(
                                        f"[PASO-7] Error al persistir CallDataCapture "
                                        f"o disparar notificación: "
                                        f"{type(cap_exc).__name__}: {cap_exc}",
                                        exc_info=True,
                                    )

                                # Respond to Gemini with tool_response.
                                # Responder a Gemini con tool_response.
                                try:
                                    await session.send_client_content(
                                        turns=types.Content(
                                            role="tool",
                                            parts=[
                                                types.Part(
                                                    function_response=types.FunctionResponse(
                                                        name="submit_captured_data",
                                                        response={
                                                            "success": True,
                                                            "section_id": _section_id_cap,
                                                        },
                                                    )
                                                )
                                            ],
                                        ),
                                        turn_complete=True,
                                    )
                                    logger.info(
                                        "[PASO-7] tool_response submit_captured_data "
                                        "enviado correctamente."
                                    )
                                except Exception as tr_cap_exc:
                                    logger.error(
                                        f"[PASO-7] Error al enviar tool_response "
                                        f"submit_captured_data: "
                                        f"{type(tr_cap_exc).__name__}: {tr_cap_exc}",
                                        exc_info=True,
                                    )

                            elif fn_call.name == "report_breakdown":
                                # --- Tool Call Handler: report_breakdown (H03) ---
                                # Creates a BreakdownTicket in DB via ORM (same
                                # process — no HTTP round-trip needed).
                                # Crea un BreakdownTicket en BD vía ORM (mismo
                                # proceso — sin round-trip HTTP necesario).
                                _machine_code     = str(fn_call.args.get("machine_code", "")).strip()
                                _fault_summary    = str(fn_call.args.get("fault_summary", "")).strip()
                                _fault_location   = str(fn_call.args.get("fault_location", "")).strip()
                                _urgency          = str(fn_call.args.get("urgency_inferred", "MEDIA")).strip()
                                _caller_name      = str(fn_call.args.get("caller_name", "")).strip()
                                _caller_phone     = str(fn_call.args.get("caller_phone_reported", "")).strip()
                                _at_base          = bool(fn_call.args.get("at_base", False))
                                _base_name        = str(fn_call.args.get("base_name", "")).strip()
                                logger.info(
                                    f"[H03-BREAKDOWN] tool_call report_breakdown recibido — "
                                    f"máquina='{_machine_code}' | urgencia='{_urgency}' | "
                                    f"at_base={_at_base}"
                                )
                                _breakdown_ticket_code = None
                                try:
                                    from asgiref.sync import sync_to_async as _s2a
                                    from ivr_config.models import Section as _Sec
                                    from chat.models import BreakdownTicket as _BT

                                    # Map urgency string → BreakdownTicket urgency choices.
                                    # Mapear cadena de urgencia → choices de BreakdownTicket.
                                    _urgency_map = {
                                        "BAJA":    _BT.URGENCY_LOW,
                                        "MEDIA":   _BT.URGENCY_MEDIUM,
                                        "ALTA":    _BT.URGENCY_HIGH,
                                        "CRITICA": _BT.URGENCY_CRITICAL,
                                    }
                                    _urgency_val = _urgency_map.get(
                                        _urgency.upper(), _BT.URGENCY_MEDIUM
                                    )

                                    def _create_breakdown():
                                        # Resolve breakdown-enabled section for this company.
                                        # Resolver la sección habilitada para averías de esta empresa.
                                        from ivr_config.models import PhoneNumber as _PN
                                        try:
                                            _pn = _PN.objects.select_related("company").get(
                                                number=self.twilio_number, is_active=True
                                            )
                                            _company = _pn.company
                                        except Exception:
                                            _company = None

                                        _section = None
                                        if _company:
                                            _section = _Sec.objects.filter(
                                                company=_company,
                                                is_active=True,
                                                ivr_breakdown_enabled=True,
                                            ).first()

                                        # Resolve MachineAsset from machine_code.
                                        # Resolver MachineAsset desde machine_code.
                                        _machine = None
                                        try:
                                            from fleet.models import MachineAsset as _MA
                                            _machine = (
                                                _MA.objects.filter(code__iexact=_machine_code).first()
                                                or _MA.objects.filter(code__iexact=_machine_code.upper()).first()
                                            )
                                        except Exception as ma_exc:
                                            logger.warning(
                                                f"[H03-BREAKDOWN] No se pudo resolver "
                                                f"MachineAsset '{_machine_code}': {ma_exc}"
                                            )

                                        # reported_by is FK to Contact — pass None for IVR calls
                                        # (caller is not necessarily a registered Contact).
                                        # Caller identity is captured in fault_summary prefix.
                                        # reported_by es FK a Contact — pasar None para llamadas IVR
                                        # (el llamante no es necesariamente un Contact registrado).
                                        # La identidad del llamante se captura en el prefijo de fault_summary.
                                        _caller_prefix = ""
                                        if _caller_name:
                                            _caller_prefix = f"[Chófer: {_caller_name}] "
                                        elif self.caller_number:
                                            _caller_prefix = f"[Tel: {self.caller_number}] "
                                        ticket = _BT.objects.create(
                                            section=_section,
                                            machine=_machine,
                                            machine_raw=_machine_code,
                                            fault_summary=_caller_prefix + _fault_summary,
                                            fault_location=_fault_location,
                                            status=_BT.STATUS_OPEN,
                                            origin=_BT.ORIGIN_IVR,
                                            urgency=_urgency_val,
                                            reported_by=None,
                                        )
                                        logger.info(
                                            f"[H03-BREAKDOWN] BreakdownTicket creado — "
                                            f"pk={ticket.pk} | "
                                            f"code='{ticket.ticket_date_code}' | "
                                            f"máquina='{_machine_code}' | "
                                            f"sección={_section}"
                                        )
                                        return ticket

                                    _ticket = await _s2a(_create_breakdown)()
                                    _breakdown_ticket_code = _ticket.ticket_date_code

                                except Exception as bd_exc:
                                    logger.error(
                                        f"[H03-BREAKDOWN] Error al crear BreakdownTicket: "
                                        f"{type(bd_exc).__name__}: {bd_exc}",
                                        exc_info=True,
                                    )

                                # Respond to Gemini with tool_response including ticket code.
                                # Responder a Gemini con tool_response incluyendo el código del ticket.
                                try:
                                    await session.send_client_content(
                                        turns=types.Content(
                                            role="tool",
                                            parts=[
                                                types.Part(
                                                    function_response=types.FunctionResponse(
                                                        name="report_breakdown",
                                                        response={
                                                            "success": _breakdown_ticket_code is not None,
                                                            "ticket_code": _breakdown_ticket_code or "",
                                                            "location_needed": not _at_base,
                                                        },
                                                    )
                                                )
                                            ],
                                        ),
                                        turn_complete=True,
                                    )
                                    logger.info(
                                        f"[H03-BREAKDOWN] tool_response report_breakdown "
                                        f"enviado (ticket={_breakdown_ticket_code}, "
                                        f"location_needed={not _at_base})."
                                    )
                                except Exception as tr_bd_exc:
                                    logger.error(
                                        f"[H03-BREAKDOWN] Error al enviar tool_response: "
                                        f"{type(tr_bd_exc).__name__}: {tr_bd_exc}",
                                        exc_info=True,
                                    )

                            elif fn_call.name == "submit_call_summary":
                                # --- Tool Call Handler: submit_call_summary (H03) ---
                                # Persists InboundCallLog at end of every call.
                                # Persiste InboundCallLog al final de cada llamada.
                                _cs_caller_name   = str(fn_call.args.get("caller_name", "")).strip()
                                _cs_caller_phone  = str(fn_call.args.get("caller_phone_reported", "")).strip()
                                _cs_call_reason   = str(fn_call.args.get("call_reason", "")).strip()
                                _cs_call_type     = str(fn_call.args.get("call_type", "OTHER")).strip()
                                _cs_outcome       = str(fn_call.args.get("outcome", "OTHER")).strip()
                                _cs_raw_summary   = str(fn_call.args.get("raw_summary", "")).strip()
                                logger.info(
                                    f"[H03-SUMMARY] tool_call submit_call_summary — "
                                    f"tipo='{_cs_call_type}' | outcome='{_cs_outcome}'"
                                )
                                try:
                                    from asgiref.sync import sync_to_async as _s2a_cs
                                    from ivr_config.models import InboundCallLog as _ICL
                                    from ivr_config.models import Section as _SecCS

                                    def _persist_summary():
                                        from ivr_config.models import PhoneNumber as _PN2
                                        _company2 = None
                                        _section2 = None
                                        try:
                                            _pn2 = _PN2.objects.select_related("company").get(
                                                number=self.twilio_number, is_active=True
                                            )
                                            _company2 = _pn2.company
                                        except Exception:
                                            pass

                                        import django.utils.timezone as _tz
                                        _ICL.objects.create(
                                            company=_company2,
                                            call_sid=getattr(self, "call_sid", ""),
                                            twilio_number=self.twilio_number or "",
                                            caller_number=self.caller_number or "",
                                            started_at=getattr(self, "call_started_at", _tz.now()),
                                            caller_name=_cs_caller_name,
                                            caller_phone_reported=_cs_caller_phone,
                                            call_reason=_cs_call_reason,
                                            call_type=_cs_call_type,
                                            outcome=_cs_outcome,
                                            raw_summary=_cs_raw_summary,
                                            section=_section2,
                                        )
                                        logger.info(
                                            f"[H03-SUMMARY] InboundCallLog creado — "
                                            f"caller='{_cs_caller_name or self.caller_number}' | "
                                            f"tipo='{_cs_call_type}' | outcome='{_cs_outcome}'"
                                        )

                                    await _s2a_cs(_persist_summary)()

                                except Exception as cs_exc:
                                    logger.error(
                                        f"[H03-SUMMARY] Error al crear InboundCallLog: "
                                        f"{type(cs_exc).__name__}: {cs_exc}",
                                        exc_info=True,
                                    )

                                # Respond to Gemini so it can proceed with farewell.
                                # Responder a Gemini para que pueda continuar con la despedida.
                                try:
                                    await session.send_client_content(
                                        turns=types.Content(
                                            role="tool",
                                            parts=[
                                                types.Part(
                                                    function_response=types.FunctionResponse(
                                                        name="submit_call_summary",
                                                        response={"success": True},
                                                    )
                                                )
                                            ],
                                        ),
                                        turn_complete=True,
                                    )
                                    logger.info("[H03-SUMMARY] tool_response submit_call_summary enviado.")
                                except Exception as cs_tr_exc:
                                    logger.error(
                                        f"[H03-SUMMARY] Error al enviar tool_response: "
                                        f"{type(cs_tr_exc).__name__}: {cs_tr_exc}",
                                        exc_info=True,
                                    )

                            elif fn_call.name == "transfer_to_section_contact":
                                section_id = int(fn_call.args.get("section_id", -1))
                                logger.info(
                                    f"[PASO-39] tool_call transfer_to_section_contact "
                                    f"recibido. section_id={section_id}. "
                                    "Iniciando secuencia de transferencia con drenado de audio."
                                )
                                # Send the tool_response to Gemini FIRST so the session
                                # protocol is satisfied before we block on the audio drain.
                                # With function calling, Gemini Live does NOT send
                                # turn_complete after a tool_call event — the tool_call
                                # IS the end of the model turn. Therefore the deferred
                                # turn_complete approach does not work here. Instead we
                                # send the tool_response immediately and then drain the
                                # audio_output_queue + apply a fixed safety pause before
                                # calling _execute_transfer() which sets session_active=False.
                                # Enviar el tool_response a Gemini PRIMERO para que el
                                # protocolo de sesión quede satisfecho antes de bloquear
                                # en el drenado de audio. Con function calling, Gemini Live
                                # NO envía turn_complete tras un evento tool_call — el
                                # tool_call ES el fin del turno del modelo. Por tanto el
                                # enfoque de deferido hasta turn_complete no funciona aquí.
                                # En su lugar enviamos el tool_response inmediatamente y
                                # luego drenamos audio_output_queue + aplicamos una pausa
                                # fija antes de llamar a _execute_transfer() que establece
                                # session_active=False.
                                try:
                                    await session.send_client_content(
                                        turns=types.Content(
                                            role="tool",
                                            parts=[
                                                types.Part(
                                                    function_response=types.FunctionResponse(
                                                        name="transfer_to_section_contact",
                                                        response={
                                                            "success": True,
                                                            "section_id": section_id,
                                                        },
                                                    )
                                                )
                                            ],
                                        ),
                                        turn_complete=True,
                                    )
                                    logger.info(
                                        f"[PASO-39] tool_response transfer_to_section_contact "
                                        f"enviado antes del drenado de audio."
                                    )
                                except Exception as tr_pre_exc:
                                    logger.error(
                                        f"[PASO-39] Error al enviar tool_response previo: "
                                        f"{type(tr_pre_exc).__name__}: {tr_pre_exc}",
                                        exc_info=True,
                                    )
                                # Drain the audio output queue so María finishes speaking
                                # before the Gemini Live session is terminated.
                                # Drenar la cola de salida para que María termine de hablar
                                # antes de que la sesión Gemini Live se termine.
                                _drain_timeout  = 8.0
                                _drain_elapsed  = 0.0
                                _drain_interval = 0.05
                                while (
                                    not self.audio_output_queue.empty()
                                    and _drain_elapsed < _drain_timeout
                                ):
                                    await asyncio.sleep(_drain_interval)
                                    _drain_elapsed += _drain_interval
                                # Fixed safety pause to allow last dequeued fragments
                                # to finish transmitting to Twilio.
                                # Pausa fija para que los últimos fragmentos desencollados
                                # terminen de transmitirse a Twilio.
                                await asyncio.sleep(3.5)
                                logger.info(
                                    f"[PASO-39] Audio drenado ({_drain_elapsed:.2f}s) + "
                                    "pausa completada. Ejecutando _execute_transfer()."
                                )
                                transfer_success = await self._execute_transfer(section_id)
                                logger.info(
                                    f"[PASO-39] _execute_transfer() completado "
                                    f"(success={transfer_success})."
                                )
                            else:
                                logger.warning(
                                    f"[GEMINI-RX] tool_call desconocido recibido: "
                                    f"'{fn_call.name}'. Se ignora."
                                )
                        continue

                    # --- Audio Response Extraction / Extracción de Respuesta de Audio ---
                    if not response.server_content:
                        continue
                    if not response.server_content.model_turn:
                        continue

                    for part in response.server_content.model_turn.parts:
                        if part.inline_data and part.inline_data.data:
                            # Raw PCM 24kHz audio bytes from Gemini Live output.
                            # These must be transcoded to mu-law 8kHz before sending
                            # back to Twilio.
                            # Bytes de audio PCM 24kHz sin procesar de la salida de Gemini Live.
                            # Deben transcodificarse a mu-law 8kHz antes de enviarlos
                            # de vuelta a Twilio.
                            pcm_24khz_bytes = part.inline_data.data
                            # LATENCY-P2: Timestamp of first audio chunk from Gemini.
                            # Measures TTFT (Time To First Token) from activity_end to
                            # first audio byte. Calculated only on the first chunk per turn.
                            # LATENCIA-P2: Marca del primer chunk de audio de Gemini.
                            # Mide TTFT desde activity_end hasta el primer byte de audio.
                            # Se calcula solo en el primer chunk de cada turno.
                            if not getattr(self, '_t_first_audio_logged', False):
                                _t_first_audio = time.monotonic()
                                _t_activity_end_ref = getattr(self, '_t_last_activity_end', None)
                                if _t_activity_end_ref:
                                    logger.info(
                                        f"[LATENCY-P2] Primer chunk PCM de Gemini recibido — "
                                        f"t={_t_first_audio:.3f}s | "
                                        f"TTFT desde activity_end: "
                                        f"{_t_first_audio - _t_activity_end_ref:.3f}s"
                                    )
                                else:
                                    logger.info(
                                        f"[LATENCY-P2] Primer chunk PCM de Gemini recibido — "
                                        f"t={_t_first_audio:.3f}s (sin ref activity_end)"
                                    )
                                self._t_first_audio_logged = True
                            await self.audio_output_queue.put(pcm_24khz_bytes)
                            logger.debug(
                                f"[GEMINI-RX] Fragmento de audio recibido de Gemini: "
                                f"{len(pcm_24khz_bytes)} bytes PCM 24kHz."
                            )

                    # Log turn completion and send audioStreamEnd to flush
                    # cached audio on the server side. This is MANDATORY when
                    # using automatic VAD: after Gemini finishes speaking, the
                    # audio stream from Twilio is effectively paused (the caller
                    # has been listening, not speaking). Without audioStreamEnd,
                    # the server VAD gets stuck waiting for the end of the
                    # caller's 'utterance' and never triggers a new response.
                    # Source: Vertex AI Live API reference + Google AI Developers
                    # Forum 'Turn 1 works, Turn 2 dies' pattern, verified 2026-04-05.
                    #
                    # Registrar fin de turno y enviar audioStreamEnd para vaciar
                    # el audio en caché del lado del servidor. Esto es OBLIGATORIO
                    # con VAD automático: tras que Gemini termina de hablar, el
                    # stream de audio de Twilio está efectivamente pausado (el
                    # llamante ha estado escuchando, no hablando). Sin audioStreamEnd,
                    # el VAD del servidor queda bloqueado esperando el fin del
                    # 'turno' del llamante y nunca dispara una nueva respuesta.
                    # Fuente: referencia Live API Vertex AI + foro Google AI
                    # Developers patrón 'Turn 1 works, Turn 2 dies', 2026-04-05.
                    if response.server_content and response.server_content.turn_complete:
                        # LATENCY-P4: Timestamp at turn_complete — total Gemini turn duration.
                        # LATENCIA-P4: Marca en turn_complete — duración total del turno Gemini.
                        _t_turn_complete = time.monotonic()
                        _t_activity_end_ref = getattr(self, '_t_last_activity_end', None)
                        if _t_activity_end_ref:
                            logger.info(
                                f"[LATENCY-P4] turn_complete de Gemini recibido — "
                                f"t={_t_turn_complete:.3f}s | "
                                f"Duración total del turno desde activity_end: "
                                f"{_t_turn_complete - _t_activity_end_ref:.3f}s"
                            )
                        else:
                            logger.info(
                                f"[LATENCY-P4] turn_complete de Gemini recibido — "
                                f"t={_t_turn_complete:.3f}s (sin ref activity_end)"
                            )
                        # Reset per-turn flags for the next turn.
                        # Reiniciar flags de turno para el siguiente turno.
                        self._t_first_twilio_logged = False
                        logger.info("[GEMINI-RX] Turno de Gemini completado. "
                                    "Enviando audioStreamEnd para flush del VAD...")
                        try:
                            await session.send_realtime_input(
                                audio_stream_end=True
                            )
                            logger.info(
                                "[GEMINI-RX] audioStreamEnd enviado correctamente. "
                                "VAD listo para escuchar al llamante."
                            )
                        except Exception as ase_exc:
                            logger.warning(
                                f"[GEMINI-RX] Error al enviar audioStreamEnd: {ase_exc}"
                            )

                        # Execute a deferred transfer if one was registered by the
                        # transfer_to_section_contact tool_call handler above.
                        # At this point all audio fragments of the current turn have
                        # been enqueued in audio_output_queue, so María has finished
                        # speaking her farewell phrase. We add a short fixed pause to
                        # allow _forward_gemini_audio_to_twilio to dequeue and transmit
                        # the last fragments before session_active is set to False.
                        # Ejecutar la transferencia diferida si fue registrada por el
                        # handler de tool_call transfer_to_section_contact arriba.
                        # En este punto todos los fragmentos de audio del turno actual
                        # han sido encolados en audio_output_queue, por lo que María ha
                        # terminado de pronunciar su frase de despedida. Añadimos una


        except Exception as exc:
            logger.error(
                f"[GEMINI-RX] Error en la corrutina de recepción de Gemini: {exc}",
                exc_info=True
            )
        finally:
            logger.info("[GEMINI-RX] Corrutina de recepción de audio de Gemini finalizada.")

    async def _forward_gemini_audio_to_twilio(self, twilio_websocket) -> None:
        """
        Coroutine: reads PCM 24kHz audio from audio_output_queue, transcodes
        it to G.711 mu-law 8kHz, and sends it back to Twilio via the WebSocket.

        Audio is encoded as a Twilio Media Streams 'media' event with the
        base64-encoded mu-law payload embedded in the JSON message structure.
        ---
        Corrutina: lee audio PCM 24kHz de audio_output_queue, lo transcodifica
        a G.711 mu-law 8kHz, y lo envía de vuelta a Twilio a través del WebSocket.

        El audio se codifica como un evento 'media' de Twilio Media Streams con
        el payload mu-law codificado en base64 embebido en la estructura de
        mensaje JSON.
        """
        logger.info("[TWILIO-TX] Corrutina de envío de audio a Twilio iniciada.")
        try:
            while self.session_active:
                try:
                    pcm_24khz_chunk = await asyncio.wait_for(
                        self.audio_output_queue.get(),
                        timeout=TIMEOUT_AUDIO_RECEIVE_SECONDS
                    )
                except asyncio.TimeoutError:
                    logger.debug(
                        "[TWILIO-TX] Timeout esperando audio de Gemini. "
                        "Continuando..."
                    )
                    continue

                # Transcode PCM 24kHz → mu-law 8kHz for Twilio compatibility.
                # Transcodificar PCM 24kHz → mu-law 8kHz para compatibilidad con Twilio.
                mulaw_chunk = self._transcode_pcm24k_to_mulaw(pcm_24khz_chunk)

                # LATENCY-P3: Timestamp of first mu-law chunk sent to Twilio.
                # Measures output pipeline delay: queue wait + transcode time.
                # LATENCIA-P3: Marca del primer chunk mu-law enviado a Twilio.
                # Mide la latencia del pipeline de salida: espera en cola + transcodificación.
                if not getattr(self, '_t_first_twilio_logged', False):
                    _t_first_twilio = time.monotonic()
                    _t_activity_end_ref = getattr(self, '_t_last_activity_end', None)
                    if _t_activity_end_ref:
                        logger.info(
                            f"[LATENCY-P3] Primer chunk mu-law enviado a Twilio — "
                            f"t={_t_first_twilio:.3f}s | "
                            f"Latencia total desde activity_end: "
                            f"{_t_first_twilio - _t_activity_end_ref:.3f}s"
                        )
                    else:
                        logger.info(
                            f"[LATENCY-P3] Primer chunk mu-law enviado a Twilio — "
                            f"t={_t_first_twilio:.3f}s (sin ref activity_end)"
                        )
                    self._t_first_twilio_logged = True

                # Encode the mu-law bytes as base64 for the Twilio JSON payload.
                # Codificar los bytes mu-law como base64 para el payload JSON de Twilio.
                mulaw_b64 = base64.b64encode(mulaw_chunk).decode("utf-8")

                # Build the Twilio Media Streams 'media' event message.
                # The 'streamSid' field at the root level is MANDATORY for
                # bidirectional Media Streams. Its absence causes Twilio to
                # silently discard the audio and emit Warning 31951.
                # Construir el mensaje de evento 'media' de Twilio Media Streams.
                # El campo 'streamSid' en el nivel raíz es OBLIGATORIO para
                # Media Streams bidireccionales. Su ausencia hace que Twilio
                # descarte silenciosamente el audio y emita el Warning 31951.
                twilio_media_message = json.dumps({
                    "event": "media",
                    "streamSid": self.stream_sid,
                    "media": {
                        "payload": mulaw_b64
                    }
                })

                # Send the encoded audio back to the caller via the Twilio WebSocket.
                # Enviar el audio codificado de vuelta al llamante a través del
                # WebSocket de Twilio.
                await twilio_websocket.send_str(twilio_media_message)
                logger.debug(
                    f"[TWILIO-TX] Fragmento mu-law enviado a Twilio: "
                    f"{len(mulaw_chunk)} bytes."
                )
                self.audio_output_queue.task_done()

        except Exception as exc:
            logger.error(
                f"[TWILIO-TX] Error en la corrutina de envío a Twilio: {exc}",
                exc_info=True
            )
        finally:
            logger.info("[TWILIO-TX] Corrutina de envío de audio a Twilio finalizada.")

    # -----------------------------------------------------------------------
    # AUDIO TRANSCODING HELPERS / HELPERS DE TRANSCODIFICACIÓN DE AUDIO
    # -----------------------------------------------------------------------

    def _transcode_mulaw_to_pcm16k(self, mulaw_bytes: bytes) -> bytes:
        """
        Transcodes G.711 mu-law 8kHz (Twilio input format) to PCM 16-bit 16kHz
        (Gemini Live input format).

        Process:
            1. Decode mu-law to PCM 16-bit 8kHz using audioop.ulaw2lin.
            2. Upsample from 8kHz to 16kHz using audioop.ratecv.

        Args:
            mulaw_bytes (bytes): Raw G.711 mu-law encoded audio at 8kHz.

        Returns:
            bytes: Raw PCM 16-bit little-endian audio at 16kHz.
        ---
        Transcodifica G.711 mu-law 8kHz (formato de entrada de Twilio) a PCM
        16-bit 16kHz (formato de entrada de Gemini Live).

        Proceso:
            1. Decodificar mu-law a PCM 16-bit 8kHz usando audioop.ulaw2lin.
            2. Sobremuestrear de 8kHz a 16kHz usando audioop.ratecv.

        Args:
            mulaw_bytes (bytes): Audio G.711 mu-law sin procesar a 8kHz.

        Returns:
            bytes: Audio PCM 16-bit little-endian sin procesar a 16kHz.
        """
        import audioop

        # Step 1: Decode mu-law to linear PCM 16-bit at 8kHz.
        # audioop.ulaw2lin(fragment, width) — width=2 means 16-bit samples.
        # Paso 1: Decodificar mu-law a PCM lineal 16-bit a 8kHz.
        # audioop.ulaw2lin(fragmento, ancho) — ancho=2 significa muestras de 16-bit.
        pcm_8khz = audioop.ulaw2lin(mulaw_bytes, 2)

        # Step 2: Upsample from 8kHz to 16kHz.
        # audioop.ratecv(fragment, width, nchannels, inrate, outrate, state)
        # nchannels=1 (mono), state=None (no previous conversion state).
        # Paso 2: Sobremuestrear de 8kHz a 16kHz.
        # audioop.ratecv(fragmento, ancho, ncanales, tasa_entrada, tasa_salida, estado)
        # ncanales=1 (mono), estado=None (sin estado de conversión previo).
        pcm_16khz, _ = audioop.ratecv(
            pcm_8khz, 2, 1,
            TWILIO_INPUT_SAMPLE_RATE,
            16000,
            None
        )

        return pcm_16khz

    def _transcode_pcm24k_to_mulaw(self, pcm_24khz_bytes: bytes) -> bytes:
        """
        Transcodes PCM 16-bit 24kHz (Gemini Live output format) to G.711
        mu-law 8kHz (Twilio output format).

        Process:
            1. Downsample from 24kHz to 8kHz using audioop.ratecv.
            2. Encode PCM 16-bit 8kHz to mu-law using audioop.lin2ulaw.

        Args:
            pcm_24khz_bytes (bytes): Raw PCM 16-bit little-endian audio at 24kHz.

        Returns:
            bytes: Raw G.711 mu-law encoded audio at 8kHz.
        ---
        Transcodifica PCM 16-bit 24kHz (formato de salida de Gemini Live) a
        G.711 mu-law 8kHz (formato de salida de Twilio).

        Proceso:
            1. Submuestrear de 24kHz a 8kHz usando audioop.ratecv.
            2. Codificar PCM 16-bit 8kHz a mu-law usando audioop.lin2ulaw.

        Args:
            pcm_24khz_bytes (bytes): Audio PCM 16-bit little-endian sin procesar a 24kHz.

        Returns:
            bytes: Audio G.711 mu-law sin procesar a 8kHz.
        """
        import audioop

        # Step 1: Downsample from 24kHz to 8kHz.
        # Paso 1: Submuestrear de 24kHz a 8kHz.
        pcm_8khz, _ = audioop.ratecv(
            pcm_24khz_bytes, 2, 1,
            GEMINI_OUTPUT_SAMPLE_RATE,
            TWILIO_OUTPUT_SAMPLE_RATE,
            None
        )

        # Step 2: Encode linear PCM 16-bit to mu-law.
        # audioop.lin2ulaw(fragment, width) — width=2 means 16-bit samples.
        # Paso 2: Codificar PCM lineal 16-bit a mu-law.
        # audioop.lin2ulaw(fragmento, ancho) — ancho=2 significa muestras de 16-bit.
        mulaw_bytes = audioop.lin2ulaw(pcm_8khz, 2)

        return mulaw_bytes

    # -----------------------------------------------------------------------
    # ESTRATEGIA B — IN-SESSION SECTION ROUTING
    # ESTRATEGIA B — ENRUTAMIENTO POR SECCIÓN EN SESIÓN
    # -----------------------------------------------------------------------

    async def _reload_session_for_section(
        self,
        session,
        section_pk: int,
    ) -> bool:
        """
        Reloads the Gemini Live session with the specific CallFlow assigned
        to the section identified by section_pk (Estrategia B — Step 37.B).

        This method is called once the IVR agent (María) has identified the
        caller's intended section and a routing trigger has been detected.
        It injects a new system_instruction into the active Gemini Live session
        via send_client_content(), replacing the general welcome flow with the
        section-specific conversational flow.

        The injection uses the 'user' role so that Gemini treats the new
        instruction as a high-priority context update and immediately applies
        it to subsequent audio generation. The session WebSocket is NOT
        reconnected — this is an in-session instruction swap.

        Args:
            session: The active Gemini Live session object obtained from
                     `async with client.aio.live.connect(...)`.
            section_pk (int): The primary key of the Section whose CallFlow
                              should be loaded and injected.

        Returns:
            bool: True if the injection was completed successfully.
                  False if section_pk is not in section_callflow_map, the
                  CallFlow has no system_instruction, or any exception occurs
                  during the send_client_content() call.
        ---
        Recarga la sesión de Gemini Live con el CallFlow específico asignado
        a la sección identificada por section_pk (Estrategia B — Paso 37.B).

        Este método se invoca una vez que el agente IVR (María) ha identificado
        la sección destino del llamante y se ha detectado un disparador de
        enrutamiento. Inyecta un nuevo system_instruction en la sesión Gemini
        Live activa mediante send_client_content(), reemplazando el flujo
        general de bienvenida por el flujo conversacional específico de la
        sección.

        La inyección usa el rol 'user' para que Gemini trate la nueva
        instrucción como una actualización de contexto de alta prioridad y la
        aplique de forma inmediata a la generación de audio subsiguiente.
        El WebSocket de sesión NO se reconecta — es un swap de instrucción
        en sesión activa.

        Args:
            session: El objeto de sesión Gemini Live activo obtenido de
                     `async with client.aio.live.connect(...)`.
            section_pk (int): La clave primaria de la Section cuyo CallFlow
                              debe cargarse e inyectarse.

        Returns:
            bool: True si la inyección se completó correctamente.
                  False si section_pk no está en section_callflow_map, el
                  CallFlow no tiene system_instruction, o se produce cualquier
                  excepción durante la llamada a send_client_content().
        """
        # Guard: verify the section has a registered CallFlow in the map.
        # Guardia: verificar que la sección tiene un CallFlow registrado en el mapa.
        call_flow = self.section_callflow_map.get(section_pk)
        if call_flow is None:
            logger.warning(
                f"[ESTRATEGIA-B] section_pk={section_pk} no encontrado en "
                f"section_callflow_map ({list(self.section_callflow_map.keys())}). "
                "No se puede reinyectar instrucción de sección."
            )
            return False

        # Guard: verify the CallFlow has a non-empty system_instruction.
        # Guardia: verificar que el CallFlow tiene system_instruction no vacío.
        new_system_instruction = (call_flow.system_instruction or "").strip()
        if not new_system_instruction:
            logger.warning(
                f"[ESTRATEGIA-B] El CallFlow '{call_flow.name}' (id={call_flow.pk}) "
                f"de la sección (pk={section_pk}) tiene system_instruction vacío. "
                "No se puede reinyectar instrucción de sección."
            )
            return False

        logger.info(
            f"[ESTRATEGIA-B] Reinyectando system_instruction de sección "
            f"(pk={section_pk}, CallFlow='{call_flow.name}') en sesión Gemini Live activa."
        )

        try:
            # Inject the section-specific system_instruction into the live session.
            # The 'user' role causes Gemini to treat this as a high-priority
            # context update applied immediately to subsequent audio generation.
            # Inyectar el system_instruction específico de la sección en la sesión
            # live. El rol 'user' hace que Gemini lo trate como una actualización
            # de contexto de alta prioridad aplicada de inmediato a la generación
            # de audio subsiguiente.
            await session.send_client_content(
                turns=types.Content(
                    role="user",
                    parts=[types.Part(text=new_system_instruction)],
                ),
                turn_complete=False,
            )

            # Update the stored system_instruction to reflect the active context.
            # Actualizar el system_instruction almacenado para reflejar el contexto activo.
            self.system_instruction = new_system_instruction

            logger.info(
                f"[ESTRATEGIA-B] Reinyección completada correctamente para "
                f"sección pk={section_pk} (CallFlow='{call_flow.name}'). "
                f"Longitud nuevo system_instruction: {len(new_system_instruction)} caracteres."
            )
            return True

        except Exception as exc:
            logger.error(
                f"[ESTRATEGIA-B] Error durante send_client_content() para sección "
                f"pk={section_pk}: {type(exc).__name__}: {exc}. "
                "La sesión continúa con el system_instruction anterior.",
                exc_info=True,
            )
            return False

    async def _activate_fallback_section(
        self,
        session,
        general_call_flow,
    ) -> bool:
        """
        Activates the fallback section routing when no qualifying section can
        attend the caller (Estrategia B — Step 37.B).

        This method is called when all active sections with a call_flow assigned
        are unavailable (e.g. all closed by schedule), or when no section intent
        was detected. It injects the system_instruction of the CallFlow associated
        with the fallback_section of the general CallFlow into the active Gemini
        Live session, instructing the agent to route the call to the designated
        human responsible.

        If the general CallFlow has no fallback_section configured, the method
        logs a warning and returns False — the session continues with the current
        general system_instruction.

        Args:
            session: The active Gemini Live session object.
            general_call_flow: The general CallFlow instance loaded at session
                               start (linked to the PhoneNumber via
                               PhoneNumber.call_flow). Its fallback_section FK
                               is the source of the fallback routing target.

        Returns:
            bool: True if the fallback injection was completed successfully.
                  False if no fallback_section is configured, its CallFlow has
                  no system_instruction, or any exception occurs.
        ---
        Activa el enrutamiento de sección fallback cuando ninguna sección
        cualificada puede atender al llamante (Estrategia B — Paso 37.B).

        Este método se invoca cuando todas las secciones activas con call_flow
        asignado están no disponibles (p. ej. todas cerradas por horario), o
        cuando no se detectó intención de sección. Inyecta el system_instruction
        del CallFlow asociado a la fallback_section del CallFlow general en la
        sesión Gemini Live activa, instruyendo al agente a derivar la llamada
        al responsable humano designado.

        Si el CallFlow general no tiene fallback_section configurada, el método
        registra una advertencia y devuelve False — la sesión continúa con el
        system_instruction general actual.

        Args:
            session: El objeto de sesión Gemini Live activo.
            general_call_flow: La instancia de CallFlow general cargada al inicio
                               de la sesión (vinculada al PhoneNumber mediante
                               PhoneNumber.call_flow). Su FK fallback_section es
                               la fuente del destino de enrutamiento fallback.

        Returns:
            bool: True si la inyección fallback se completó correctamente.
                  False si no hay fallback_section configurada, su CallFlow no
                  tiene system_instruction, o se produce cualquier excepción.
        """
        # Guard: verify that general_call_flow was supplied.
        # Guardia: verificar que se ha suministrado general_call_flow.
        if general_call_flow is None:
            logger.warning(
                "[ESTRATEGIA-B] _activate_fallback_section() invocado sin "
                "general_call_flow. No se puede activar fallback."
            )
            return False

        # Guard: verify that a fallback_section is assigned to the general CallFlow.
        # Guardia: verificar que hay fallback_section asignada al CallFlow general.
        fallback_section = getattr(general_call_flow, "fallback_section", None)
        if fallback_section is None:
            logger.warning(
                f"[ESTRATEGIA-B] El CallFlow general '{general_call_flow.name}' "
                f"(id={general_call_flow.pk}) no tiene fallback_section configurada. "
                "La sesión continúa con el system_instruction general actual."
            )
            return False

        # Obtain the CallFlow of the fallback section via the section_callflow_map.
        # If the fallback section is not in the map (no call_flow assigned or
        # inactive), log a warning and return False.
        # Obtener el CallFlow de la sección fallback mediante section_callflow_map.
        # Si la sección fallback no está en el mapa (sin call_flow asignado o
        # inactiva), registrar advertencia y devolver False.
        fallback_call_flow = self.section_callflow_map.get(fallback_section.pk)
        if fallback_call_flow is None:
            logger.warning(
                f"[ESTRATEGIA-B] La fallback_section '{fallback_section.name}' "
                f"(pk={fallback_section.pk}) no está en section_callflow_map. "
                "Puede que no tenga CallFlow activo asignado. "
                "La sesión continúa con el system_instruction general actual."
            )
            return False

        # Guard: verify that the fallback CallFlow has a non-empty system_instruction.
        # Guardia: verificar que el CallFlow fallback tiene system_instruction no vacío.
        fallback_instruction = (fallback_call_flow.system_instruction or "").strip()
        if not fallback_instruction:
            logger.warning(
                f"[ESTRATEGIA-B] El CallFlow fallback '{fallback_call_flow.name}' "
                f"(id={fallback_call_flow.pk}) tiene system_instruction vacío. "
                "La sesión continúa con el system_instruction general actual."
            )
            return False

        logger.info(
            f"[ESTRATEGIA-B] Activando fallback hacia sección "
            f"'{fallback_section.name}' (pk={fallback_section.pk}), "
            f"CallFlow='{fallback_call_flow.name}' (id={fallback_call_flow.pk})."
        )

        try:
            # Inject the fallback system_instruction into the active live session.
            # Inyectar el system_instruction fallback en la sesión live activa.
            await session.send_client_content(
                turns=types.Content(
                    role="user",
                    parts=[types.Part(text=fallback_instruction)],
                ),
                turn_complete=True,
            )

            # Update the stored system_instruction to the fallback context.
            # Actualizar el system_instruction almacenado al contexto fallback.
            self.system_instruction = fallback_instruction

            logger.info(
                f"[ESTRATEGIA-B] Fallback activado correctamente hacia "
                f"'{fallback_section.name}'. "
                f"Longitud system_instruction fallback: {len(fallback_instruction)} caracteres."
            )
            return True

        except Exception as exc:
            logger.error(
                f"[ESTRATEGIA-B] Error durante send_client_content() en fallback "
                f"hacia '{fallback_section.name}': {type(exc).__name__}: {exc}. "
                "La sesión continúa con el system_instruction general actual.",
                exc_info=True,
            )
            return False

    # -----------------------------------------------------------------------
    # SESSION CONTROL / CONTROL DE SESIÓN
    # -----------------------------------------------------------------------

    def set_call_sid(self, call_sid: str) -> None:
        """
        Stores the Twilio Call SID for this Media Stream session.

        Called by voice_sidecar_bridge.py immediately after service instantiation
        when the Twilio 'start' event is received. Required by _execute_transfer()
        to update the live call via Twilio REST API when the
        transfer_to_section_contact tool is invoked by María.
        ---
        Almacena el Call SID de Twilio para esta sesión de Media Stream.

        Invocado desde voice_sidecar_bridge.py inmediatamente tras instanciar el
        servicio al recibir el evento 'start' de Twilio. Necesario por
        _execute_transfer() para actualizar la llamada en curso vía REST API de
        Twilio cuando María invoca la tool transfer_to_section_contact.

        Args:
            call_sid (str): The Twilio Call SID from the 'start' event.
                            / El Call SID de Twilio del evento 'start'.
        """
        self.call_sid = call_sid
        logger.info(
            f"[SESSION] Call SID de Twilio almacenado correctamente: {call_sid}"
        )

    async def _execute_transfer(self, section_id: int) -> bool:
        """
        Initiates a resilient multi-contact call transfer to the highest-priority
        Contact assigned to the given section via SectionContact.priority (Paso 39).

        The caller is placed into a named Twilio Conference room and hears hold
        music (HoldMusicView) while the bridge places an outbound call to the
        first contact ordered by SectionContact.priority ASC. A TransferAttempt
        record is persisted in the database before any Twilio API call so that
        TransferStatusView can correlate the action webhook with the correct
        session state and contact index.

        Contact selection criteria:
            - Ordered by SectionContact.priority ASC (lower = higher preference).
            - contact_index=0 is always the first attempt.
            - Contacts without a phone_number are excluded at query time.
            - is_internal is NOT a filter criterion — external contacts are valid
              transfer targets (e.g. an external admin managing supplier relations).

        Args:
            section_id (int): Section pk whose contact receives the transfer.

        Returns:
            bool: True if transfer initiated. False on error or missing data.
        ---
        Inicia una transferencia de llamada resiliente multi-contacto al Contact de mayor
        prioridad asignado a la sección dada vía SectionContact.priority (Paso 39).

        El llamante se coloca en una sala Twilio Conference con nombre y escucha música
        de espera (HoldMusicView) mientras el bridge realiza una llamada saliente al
        primer contacto ordenado por SectionContact.priority ASC. Se persiste un registro
        TransferAttempt en la base de datos antes de cualquier llamada a la API de Twilio
        para que TransferStatusView pueda correlacionar el webhook action con el estado
        de sesión correcto y el índice de contacto.

        Criterios de selección de contacto:
            - Ordenados por SectionContact.priority ASC (menor = mayor preferencia).
            - contact_index=0 es siempre el primer intento.
            - Los contactos sin phone_number se excluyen en tiempo de consulta.
            - is_internal NO es criterio de filtro — los contactos externos son destinos
              de transferencia válidos (p. ej. un administrador externo que gestiona
              relaciones con proveedores).

        Args:
            section_id (int): pk de la Section cuyo contacto recibe la transferencia.

        Returns:
            bool: True si la transferencia se inició. False en error o datos ausentes.
        """
        # Guard: call_sid must be set.
        # Guardia: call_sid debe estar establecido.
        if not self.call_sid:
            logger.error(
                "[PASO-39] _execute_transfer() invocado sin call_sid. "
                "No se puede ejecutar la transferencia."
            )
            return False

        # Guard: section_id must be in map.
        # Guardia: section_id debe estar en el mapa.
        if section_id not in self.section_callflow_map:
            logger.error(
                f"[PASO-39] section_id={section_id} no encontrado en "
                "section_callflow_map. No se puede ejecutar la transferencia."
            )
            return False

        # Resolve the prioritised contact list for this section via SectionContact.
        # Contacts without phone_number are excluded — they cannot receive calls.
        # is_internal is NOT a filter criterion per Paso 39 design decision.
        # Resolver la lista de contactos priorizada para esta sección vía SectionContact.
        # Los contactos sin phone_number se excluyen — no pueden recibir llamadas.
        # is_internal NO es criterio de filtro según la decisión de diseño del Paso 39.
        try:
            from asgiref.sync import sync_to_async
            from ivr_config.models import (
                Section         as _Section,
                SectionContact  as _SectionContact,
                TransferAttempt as _TransferAttempt,
            )

            section_obj = await sync_to_async(
                lambda: _Section.objects.get(pk=section_id)
            )()

            # Fetch contacts ordered by priority ASC, excluding those without phone.
            # Obtener contactos ordenados por priority ASC, excluyendo los sin teléfono.
            section_contacts = await sync_to_async(
                lambda: list(
                    _SectionContact.objects.select_related("contact")
                    .filter(section_id=section_id)
                    .exclude(contact__phone_number="")
                    .order_by("priority", "contact__name")
                )
            )()

            if not section_contacts:
                logger.error(
                    f"[PASO-39] Sección pk={section_id} sin contactos con teléfono. "
                    "No se puede ejecutar la transferencia."
                )
                return False

            # Select the first contact (index 0 — highest priority).
            # Seleccionar el primer contacto (índice 0 — mayor prioridad).
            first_sc      = section_contacts[0]
            contact       = first_sc.contact
            contact_phone = contact.phone_number
            section_name  = section_obj.name

        except Exception as db_exc:
            logger.error(
                f"[PASO-39] Error al resolver contactos de sección pk={section_id}: "
                f"{type(db_exc).__name__}: {db_exc}",
                exc_info=True,
            )
            return False

        logger.info(
            f"[PASO-39] Iniciando transferencia — sección: '{section_name}' "
            f"| contacto: '{contact.name}' ({contact_phone}) "
            f"| call_sid: {self.call_sid} | contact_index: 0"
        )

        # Conference room name — unique per call SID.
        # Nombre de la sala de conferencia — único por call SID.
        conference_name = f"EnterpriseBot-{self.call_sid}"

        # Base URL — read from shared ngrok session file.
        # URL base — leída del archivo de sesión ngrok compartido.
        try:
            ngrok_file = (
                "/home/MiguelAeTxio/PROJECTS/EnterpriseBot/DOCS/SESSION/NGROK_URL.txt"
            )
            with open(ngrok_file, "r") as _f:
                base_url = _f.read().strip().rstrip("/")
        except Exception:
            base_url = "https://enterprisebot.ngrok-free.app"
            logger.warning(
                "[PASO-39] No se pudo leer NGROK_URL.txt. "
                f"Usando base_url por defecto: {base_url}"
            )

        action_url = f"https://enterprisebot-miguelaetxio.pythonanywhere.com/api/vox/transfer_status/{self.call_sid}/"

        # TwiML for the caller: enter Conference and hear hold music.
        # TwiML para el llamante: entrar en la Conference y escuchar música de espera.
        caller_twiml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Response>'
            f'<Dial action="{action_url}" method="POST" timeout="30">'
            '<Conference '
            'startConferenceOnEnter="false" endConferenceOnExit="true" '
            f'beep="false">{conference_name}</Conference>'
            '</Dial>'
            '</Response>'
        )

        # TwiML for the contact: join same Conference when they answer.
        # TwiML para el contacto: unirse a la misma Conference al contestar.
        contact_twiml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Response>'
            '<Say voice="alice" language="es-ES">'
            'Llamada entrante de centralita. '
            'Le estamos conectando con el llamante.'
            '</Say>'
            f'<Dial><Conference startConferenceOnEnter="true" '
            f'endConferenceOnExit="false" beep="false">'
            f'{conference_name}</Conference></Dial>'
            '</Response>'
        )

        try:
            # Step 1: Persist TransferAttempt in DB BEFORE any Twilio API call.
            # This record is the state bridge between this process and the
            # TransferStatusView webhook — Twilio provides no session context
            # in the action webhook POST, so the DB is the only viable mechanism.
            # Paso 1: Persistir TransferAttempt en BD ANTES de cualquier llamada a la API de Twilio.
            # Este registro es el puente de estado entre este proceso y el webhook
            # TransferStatusView — Twilio no proporciona contexto de sesión en el
            # POST del webhook action, por lo que la BD es el único mecanismo viable.
            await sync_to_async(
                lambda: _TransferAttempt.objects.create(
                    call_sid=self.call_sid,
                    section=section_obj,
                    twilio_number=self.twilio_number,
                    caller_number=self.caller_number,
                    contact_index=0,
                    status=_TransferAttempt.STATUS_PENDING,
                )
            )()
            logger.info(
                f"[PASO-39] TransferAttempt creado en BD — "
                f"call_sid={self.call_sid} | contact_index=0."
            )

            # Step 2: Update the caller's live call with Conference TwiML.
            # Paso 2: Actualizar la llamada en curso del llamante con TwiML de Conference.
            self.twilio_client.calls(self.call_sid).update(twiml=caller_twiml)
            logger.info(
                f"[PASO-39] Llamada {self.call_sid} actualizada con Conference TwiML. "
                f"Sala: '{conference_name}'."
            )

            # Step 3: Terminate Gemini Live session — Media Stream ends.
            # Caller is now in Conference hearing hold music.
            # Paso 3: Terminar la sesión Gemini Live — el Media Stream termina.
            # El llamante está ahora en la Conference escuchando música de espera.
            self.session_active = False
            logger.info(
                "[PASO-39] Sesión Gemini Live terminada. "
                "El llamante está en la Conference escuchando música de espera."
            )

            # Step 4: Place outbound call to the first section contact.
            # Register ContactStatusView as statusCallback to detect whether
            # the contact actually answered (DialCallStatus on the caller
            # <Dial><Conference> action URL is always 'answered' — unsuitable
            # for outcome detection per Twilio documentation, 2026).
            # Paso 4: Realizar llamada saliente al primer contacto de la sección.
            # Registrar ContactStatusView como statusCallback para detectar si
            # el contacto realmente contestó (DialCallStatus en el action URL
            # del <Dial><Conference> del llamante siempre es 'answered' —
            # no apto para detección de resultado según documentación Twilio, 2026).
            contact_status_url = (
                "https://enterprisebot-miguelaetxio.pythonanywhere.com"
                f"/api/vox/contact_status/{self.call_sid}/"
            )
            outbound_call = self.twilio_client.calls.create(
                to=contact_phone,
                from_=self.twilio_number,
                twiml=contact_twiml,
                status_callback=contact_status_url,
                status_callback_event=["completed", "no-answer", "busy",
                                       "failed", "canceled"],
                status_callback_method="POST",
            )
            logger.info(
                f"[PASO-39] Llamada saliente iniciada hacia '{contact.name}' "
                f"({contact_phone}). OutboundCallSid: {outbound_call.sid}. "
                f"StatusCallback registrado en: {contact_status_url}"
            )
            return True

        except Exception as twilio_exc:
            logger.error(
                f"[PASO-39] Error durante la transferencia: "
                f"{type(twilio_exc).__name__}: {twilio_exc}",
                exc_info=True,
            )
            # Restore Gemini session if the transfer failed before the conference
            # was established so the caller is not left in silence.
            # Restaurar la sesión Gemini si la transferencia falló antes de establecer
            # la conference para que el llamante no quede en silencio.
            self.session_active = True
            return False

    def set_stream_sid(self, stream_sid: str) -> None:
        """
        Stores the Twilio Stream SID for the current Media Stream session.

        This method must be called by the Django WebSocket view immediately
        upon receiving the Twilio 'start' event. The stored SID is then
        embedded in every outbound 'media' event message to comply with the
        Twilio Media Streams bidirectional protocol. Omitting it causes
        Warning 31951 and silent audio discard on Twilio's side.
        ---
        Almacena el Stream SID de Twilio para la sesión de Media Stream actual.

        Este método debe ser invocado por la vista WebSocket de Django de forma
        inmediata al recibir el evento 'start' de Twilio. El SID almacenado se
        embebe en cada mensaje de evento 'media' saliente para cumplir con el
        protocolo bidireccional de Twilio Media Streams. Su omisión provoca el
        Warning 31951 y el descarte silencioso del audio en el lado de Twilio.

        Args:
            stream_sid (str): The Twilio Stream SID from the 'start' event.
                              / El Stream SID de Twilio del evento 'start'.
        """
        self.stream_sid = stream_sid
        logger.info(
            f"[SESSION] Stream SID de Twilio almacenado correctamente: {stream_sid}"
        )

    def terminate_session(self) -> None:
        """
        Signals all active coroutines to terminate gracefully by setting
        the session_active flag to False.

        This method is called by the Django WebSocket view when the Twilio
        'stop' event is received, indicating the caller has hung up.
        ---
        Señaliza a todas las corrutinas activas que terminen de forma elegante
        estableciendo el flag session_active en False.

        Este método es llamado por la vista WebSocket de Django cuando se recibe
        el evento 'stop' de Twilio, indicando que el llamante ha colgado.
        """
        logger.info(
            "[SESSION] terminate_session() invocado. "
            "Señalizando fin de sesión a todas las corrutinas..."
        )
        self.session_active = False
