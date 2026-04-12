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
# CallFlow missing). Contains the original hardcoded Grupo Álvarez / Alia
# persona definition as a safety net to prevent silent call failures.
# Instrucción de sistema de fallback usada cuando build_live_config() no puede
# cargar la configuración dinámica desde la base de datos (p. ej. número no
# configurado, CallFlow ausente). Contiene la definición original hardcodeada
# de la persona Grupo Álvarez / Alia como red de seguridad para evitar fallos
# silenciosos en llamadas.
SYSTEM_INSTRUCTION_FALLBACK = (
    "Eres Alia, la asistente virtual del Grupo Álvarez. "
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
# of Alia's own playback being captured by the handset microphone. At 3 frames
# (~60ms) the detector was firing on the model's own audio output, causing
# spurious activity_start signals that triggered Gemini self-interruptions.
# Número de frames de voz consecutivos requeridos para abrir una ventana de
# actividad. Aumentado de 3 a 10 el 2026-04-06 (~200ms) para filtrar el eco
# acústico de la reproducción del propio audio de Alia capturado por el
# micrófono del auricular. Con 3 frames (~60ms) el detector disparaba sobre
# la propia salida de audio del modelo, causando señales activity_start
# espurias que provocaban auto-interrupciones de Gemini.
SPEECH_FRAMES_TO_START_ACTIVITY = 15


# Fallback initial greeting used when build_live_config() fails to load
# the dynamic configuration from the database. Contains the original hardcoded
# Alia / Grupo Álvarez greeting as a safety net.
# Saludo inicial de fallback usado cuando build_live_config() no puede cargar
# la configuración dinámica desde la base de datos. Contiene el saludo original
# hardcodeado de Alia / Grupo Álvarez como red de seguridad.
INITIAL_GREETING_FALLBACK = (
    "El llamante acaba de contestar la llamada. "
    "Salúdale presentándote como Alia, asistente virtual del Grupo Álvarez, "
    "con el siguiente mensaje exacto, sin añadir ni modificar nada: "
    "'Hola, me llamo Alia, soy la asistente virtual del Grupo Álvarez. "
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

    def __init__(self, twilio_number: str = ""):
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
        # This project uses Twilio API Key authentication (SID + Secret) rather
        # than the legacy Auth Token approach. This is the recommended method for
        # server-side applications as of Twilio CLI 6.2.4.
        # Este proyecto usa autenticación por API Key de Twilio (SID + Secret) en
        # lugar del enfoque heredado con Auth Token. Este es el método recomendado
        # para aplicaciones de servidor a partir de Twilio CLI 6.2.4.
        twilio_account_sid = os.getenv("TWILIO_ACCOUNT_SID")
        twilio_api_key_sid = os.getenv("TWILIO_API_KEY_SID")
        twilio_api_key_secret = os.getenv("TWILIO_API_KEY_SECRET")

        if not all([twilio_account_sid, twilio_api_key_sid, twilio_api_key_secret]):
            logger.error(
                "[INIT] Credenciales de Twilio incompletas. Se requieren: "
                "TWILIO_ACCOUNT_SID, TWILIO_API_KEY_SID, TWILIO_API_KEY_SECRET."
            )
            raise EnvironmentError(
                "Twilio credentials are incomplete. Cannot initialise VoiceOrchestrationService."
            )
        self.twilio_client = TwilioClient(
            twilio_api_key_sid,
            twilio_api_key_secret,
            twilio_account_sid
        )
        logger.info("[INIT] Cliente Twilio REST inicializado correctamente.")

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
        self.system_instruction: str = SYSTEM_INSTRUCTION_FALLBACK
        self.initial_greeting_text: str = INITIAL_GREETING_FALLBACK

        logger.info(
            f"[INIT] VoiceOrchestrationService inicializado. "
            f"Número: '{twilio_number}'. "
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
            ) = await sync_to_async(build_live_config)(self.twilio_number)
            logger.info(
                f"[CONFIG] Configuración IVR dinámica cargada correctamente "
                f"para el número '{self.twilio_number}'."
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
                        voice_name="Aoede"
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
                            logger.info("[GEMINI-TX] activity_end enviado correctamente.")
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
    # SESSION CONTROL / CONTROL DE SESIÓN
    # -----------------------------------------------------------------------

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
