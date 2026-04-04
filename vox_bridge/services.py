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
import os

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

# Gemini 3.1 Live model identifier — standard for April 2026.
# Identificador del modelo Gemini 3.1 Live — estándar de Abril de 2026.
GEMINI_MODEL = "gemini-3.1-flash-live-preview"

# System instruction that defines the IVR agent's persona and behaviour.
# This prompt is injected at session setup time and governs all interactions.
# Instrucción de sistema que define la persona y comportamiento del agente IVR.
# Este prompt se inyecta en el momento de configuración de la sesión y rige
# todas las interacciones.
SYSTEM_INSTRUCTION = (
    "Eres un asistente de voz empresarial de EnterpriseBot. "
    "Responde de forma concisa, clara y profesional. "
    "Estás atendiendo una llamada de voz en tiempo real. "
    "Habla en castellano a menos que el usuario se dirija a ti en otro idioma."
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

# Initial greeting text sent to Gemini immediately after session establishment.
# This text triggers the model to produce the opening spoken response to the caller.
# Texto del saludo inicial enviado a Gemini inmediatamente tras el establecimiento
# de la sesión. Este texto indica al modelo que produzca la respuesta hablada de
# apertura para el llamante.
INITIAL_GREETING_TEXT = (
    "El usuario ha contestado la llamada. "
    "Salúdale de forma breve y profesional y pregúntale en qué puedes ayudarle."
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

    def __init__(self):
        """
        Initialises the service by loading credentials from environment variables
        and constructing the Gemini and Twilio client instances.

        Gemini client: uses GEMINI_API_KEY from the project .env file.
        Twilio client: uses TWILIO_ACCOUNT_SID + TWILIO_API_KEY_SID +
                       TWILIO_API_KEY_SECRET (API Key auth, not Auth Token auth).
        ---
        Inicializa el servicio cargando las credenciales desde las variables de
        entorno y construyendo las instancias de los clientes Gemini y Twilio.

        Cliente Gemini: usa GEMINI_API_KEY del archivo .env del proyecto.
        Cliente Twilio: usa TWILIO_ACCOUNT_SID + TWILIO_API_KEY_SID +
                        TWILIO_API_KEY_SECRET (autenticación por API Key, no Auth Token).
        """
        # --- Gemini Client Initialisation / Inicialización del Cliente Gemini ---
        # The GenAI client is instantiated once per service instance and reused
        # across all session lifecycle methods. The API key is sourced exclusively
        # from the GEMINI_API_KEY environment variable loaded by Django's settings.py.
        # El cliente GenAI se instancia una vez por instancia de servicio y se
        # reutiliza en todos los métodos del ciclo de vida de la sesión.
        gemini_api_key = os.getenv("GEMINI_API_KEY")
        if not gemini_api_key:
            # This is a fatal configuration error — the service cannot operate
            # without a valid API key.
            # Este es un error de configuración fatal — el servicio no puede operar
            # sin una clave de API válida.
            logger.error(
                "[INIT] GEMINI_API_KEY no encontrada en las variables de entorno. "
                "El servicio no puede inicializarse."
            )
            raise EnvironmentError(
                "GEMINI_API_KEY is not set. Cannot initialise VoiceOrchestrationService."
            )
        self.gemini_client = genai.Client(api_key=gemini_api_key)
        logger.info("[INIT] Cliente Gemini GenAI inicializado correctamente.")

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

        logger.info("[INIT] VoiceOrchestrationService inicializado completamente.")

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

        # Build the Gemini Live session configuration.
        # The response modality is AUDIO — we want raw PCM audio back, not text.
        # The system instruction defines the IVR agent's persona.
        # Construir la configuración de la sesión Gemini Live.
        # La modalidad de respuesta es AUDIO — queremos PCM sin procesar de vuelta,
        # no texto. La instrucción de sistema define la persona del agente IVR.
        live_config = types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            system_instruction=types.Content(
                parts=[types.Part(text=SYSTEM_INSTRUCTION)]
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
                await asyncio.wait_for(
                    session.send_realtime_input(
                        text=INITIAL_GREETING_TEXT
                    ),
                    timeout=TIMEOUT_INITIAL_GREETING_SECONDS
                )
                logger.info(
                    "[SESSION] Saludo inicial enviado correctamente. "
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
                await asyncio.gather(
                    self._forward_twilio_audio_to_gemini(session),
                    self._receive_gemini_audio(session),
                    self._forward_gemini_audio_to_twilio(twilio_websocket),
                    return_exceptions=False
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
        Coroutine: continuously reads PCM audio from audio_input_queue and
        streams it to the active Gemini Live session.

        This coroutine runs concurrently with _receive_gemini_audio and
        _forward_gemini_audio_to_twilio for the duration of the session.
        It terminates when session_active is set to False and the queue
        is drained.
        ---
        Corrutina: lee continuamente audio PCM de audio_input_queue y lo transmite
        a la sesión Gemini Live activa.

        Esta corrutina se ejecuta de forma concurrente con _receive_gemini_audio y
        _forward_gemini_audio_to_twilio durante la duración de la sesión.
        Termina cuando session_active se establece en False y la cola se vacía.
        """
        logger.info("[GEMINI-TX] Corrutina de envío de audio a Gemini iniciada.")
        try:
            while self.session_active:
                try:
                    # Wait for a PCM chunk with a generous timeout to avoid
                    # spinning on an empty queue.
                    # Esperar un fragmento PCM con un timeout generoso para evitar
                    # girar en una cola vacía.
                    pcm_chunk = await asyncio.wait_for(
                        self.audio_input_queue.get(),
                        timeout=TIMEOUT_AUDIO_RECEIVE_SECONDS
                    )
                except asyncio.TimeoutError:
                    # No audio arrived in the timeout window. If session is still
                    # active this is normal silence; log and continue.
                    # No llegó audio en la ventana de timeout. Si la sesión sigue
                    # activa esto es silencio normal; loguear y continuar.
                    logger.debug(
                        "[GEMINI-TX] Timeout esperando audio de Twilio (silencio normal). "
                        "Continuando..."
                    )
                    continue

                # Send the PCM chunk to Gemini Live using the SDK 1.69.0 compliant
                # audio sending syntax with types.Blob.
                # Enviar el fragmento PCM a Gemini Live usando la sintaxis de envío
                # de audio conforme a SDK 1.69.0 con types.Blob.
                await session.send_realtime_input(
                    audio=types.Blob(
                        data=pcm_chunk,
                        mime_type=GEMINI_AUDIO_MIME_TYPE
                    )
                )
                logger.debug(
                    f"[GEMINI-TX] Fragmento PCM enviado a Gemini: {len(pcm_chunk)} bytes."
                )
                self.audio_input_queue.task_done()

        except Exception as exc:
            logger.error(
                f"[GEMINI-TX] Error en la corrutina de envío a Gemini: {exc}",
                exc_info=True
            )
        finally:
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

                # Log turn completion for traceability.
                # Registrar la finalización del turno para trazabilidad.
                if response.server_content.turn_complete:
                    logger.info("[GEMINI-RX] Turno de Gemini completado.")

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
                # Construir el mensaje de evento 'media' de Twilio Media Streams.
                twilio_media_message = json.dumps({
                    "event": "media",
                    "media": {
                        "payload": mulaw_b64
                    }
                })

                # Send the encoded audio back to the caller via the Twilio WebSocket.
                # Enviar el audio codificado de vuelta al llamante a través del
                # WebSocket de Twilio.
                await twilio_websocket.send(twilio_media_message)
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
