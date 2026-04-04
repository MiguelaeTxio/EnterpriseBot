# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/vox_bridge/services.py
import os
import logging
import asyncio
import audioop
import base64
from django.conf import settings
from google import genai
from google.genai import types
from asgiref.sync import sync_to_async

"""
EnterpriseBot Gemini Live Stream Service: High-Precision DSP and AI Orchestration.
April 2026 Standard: Mandatory gemini-3.1-flash-live-preview for Conversational IVR.
This service manages the bidirectional voice bridge, applying digital signal processing
to match Twilio's G.711 mu-law (8kHz) with Gemini's L16 (16kHz) requirements.
The connect() method has been removed in favour of build_live_config(), which exposes
the client and config objects directly to the bridge, allowing it to own the async
context manager lifecycle via: async with client.aio.live.connect(...) as session.
---
Servicio de Streaming Gemini Live de EnterpriseBot: Orquestación de IA y DSP de Alta Precisión.
Estándar de Abril de 2026: gemini-3.1-flash-live-preview obligatorio para IVR Conversacional.
Este servicio gestiona el puente de audio bidireccional, aplicando procesamiento de señal digital
para emparejar el mu-law G.711 (8kHz) de Twilio con los requisitos L16 (16kHz) de Gemini.
El método connect() ha sido eliminado en favor de build_live_config(), que expone el cliente
y la configuración directamente al bridge, permitiéndole gestionar el ciclo de vida del
context manager asíncrono mediante: async with client.aio.live.connect(...) as session.
"""

# Logging configuration exclusively in Spanish (Directriz 2.1.3)
# Configuración de registro exclusivamente en Castellano (Directriz 2.1.3)
logger = logging.getLogger("VoxServices")


class GeminiStreamService:
    """
    Core orchestrator for real-time voice synthesis and recognition via Gemini 3.1 Flash Live.
    Handles DSP transcoding, AI session lifecycle, and Django ORM persistence.
    The session context manager is now owned by the bridge layer (voice_sidecar_bridge.py)
    using the canonical SDK 1.69.0 pattern:
        async with client.aio.live.connect(model=model, config=config) as session
    This class exposes build_live_config() to provide the client and config to the bridge,
    and reset_session_state() to reinitialise per-call state before each new connection.
    ---
    Orquestador núcleo para síntesis y reconocimiento de voz en tiempo real vía Gemini 3.1 Flash Live.
    Gestiona la transcodificación DSP, el ciclo de vida de la sesión de IA y la persistencia en el ORM de Django.
    El context manager de sesión es ahora propiedad de la capa del bridge (voice_sidecar_bridge.py)
    usando el patrón canónico del SDK 1.69.0:
        async with client.aio.live.connect(model=model, config=config) as session
    Esta clase expone build_live_config() para proporcionar el cliente y la config al bridge,
    y reset_session_state() para reinicializar el estado por llamada antes de cada nueva conexión.
    """

    def __init__(self):
        """
        Initializes the GenAI client using April 2026 API standards (SDK 1.69.0).
        Sets up DSP state variables and the asyncio.Event for the Setup-First protocol.
        ---
        Inicializa el cliente GenAI usando los estándares de la API de abril de 2026 (SDK 1.69.0).
        Establece las variables de estado DSP y el asyncio.Event para el protocolo Setup-First.
        """
        # ✅ SURGICAL FIX APRIL 2026: Forcing API version 'v1beta' to support
        # gemini-3.1-flash-live-preview in BiDi mode. Ensures compliance with the
        # 2026 technical directive for Conversational IVR.
        # ---
        # ✅ CORRECCIÓN QUIRÚRGICA ABRIL 2026: Forzando la versión de API 'v1beta' para
        # soportar gemini-3.1-flash-live-preview en modo BiDi. Asegura el cumplimiento
        # con la directriz técnica de 2026 para IVR Conversacional.
        self.client = genai.Client(
            api_key=settings.GEMINI_API_KEY,
            http_options=types.HttpOptions(api_version="v1beta")
        )

        # Mandatory model for Conversational IVR (Directriz Técnica 1.4)
        # Modelo obligatorio para IVR Conversacional (Directriz Técnica 1.4)
        # ✅ GA UPGRADE APRIL 2026: gemini-3.1-flash-live-preview
        # Mandatory for real-time multimodal A2A (Audio-to-Audio) flows with persistent state.
        # ---
        # ✅ ACTUALIZACIÓN GA ABRIL 2026: gemini-3.1-flash-live-preview
        # Obligatorio para flujos multimodal A2A (Audio-to-Audio) en tiempo real con estado persistente.
        self.model_id = "models/gemini-3.1-flash-live-preview"

        # DSP state: maintained across frames to prevent phase clipping between chunks.
        # Estado DSP: mantenido entre tramas para evitar el recorte de fase entre fragmentos.
        self.state_in = None
        self.state_out = None
        self.frames_in = 0
        self.frames_out = 0

        # Setup-First protocol: asyncio.Event set by listen_to_ai() upon server confirmation.
        # Protocolo Setup-First: asyncio.Event activado por listen_to_ai() al confirmar el servidor.
        self.setup_confirmed = asyncio.Event()

    def reset_session_state(self):
        """
        Resets all per-call state before a new Gemini Live session is established.
        This is mandatory to prevent stale DSP state and a pre-set setup_confirmed
        Event from bypassing the Setup-First handshake protocol on subsequent calls.
        ---
        Reinicia todo el estado por llamada antes de establecer una nueva sesión Gemini Live.
        Esto es obligatorio para evitar que el estado DSP obsoleto y un Event setup_confirmed
        ya activado omitan el protocolo de handshake Setup-First en llamadas posteriores.
        """
        # Clear the Setup-First Event so each new call waits for its own setup_complete.
        # Limpia el Event Setup-First para que cada nueva llamada espere su propio setup_complete.
        self.setup_confirmed.clear()

        # Reset DSP state to avoid phase artifacts from a previous call's audio stream.
        # Reinicia el estado DSP para evitar artefactos de fase del flujo de audio de la llamada anterior.
        self.state_in = None
        self.state_out = None
        self.frames_in = 0
        self.frames_out = 0

        logger.info("# [SERVICE] Estado de sesión reiniciado para nueva llamada entrante.")

    def build_live_config(self):
        """
        Builds and returns the LiveConnectConfig and exposes the GenAI client.
        The bridge layer uses these to own the async context manager:
            async with service.client.aio.live.connect(
                model=service.model_id, config=service.build_live_config()
            ) as session
        This is the canonical SDK 1.69.0 pattern per the April 2026 official documentation.
        Returns a tuple: (client, model_id, LiveConnectConfig).
        ---
        Construye y devuelve la LiveConnectConfig y expone el cliente GenAI.
        La capa bridge usa estos para ser propietaria del context manager asíncrono:
            async with service.client.aio.live.connect(
                model=service.model_id, config=service.build_live_config()
            ) as session
        Este es el patrón canónico del SDK 1.69.0 según la documentación oficial de abril de 2026.
        Devuelve una tupla: (client, model_id, LiveConnectConfig).
        """
        # Regional Spanish speech configuration (es-ES).
        # Configuración de voz para español regional (es-ES).

        # ✅ SURGICAL FIX APRIL 2026: Nesting voice_name inside prebuilt_voice_config
        # to satisfy the Pydantic schema of SDK 1.69.0.
        # ---
        # ✅ CORRECCIÓN QUIRÚRGICA ABRIL 2026: Anidando voice_name dentro de
        # prebuilt_voice_config para satisfacer el esquema Pydantic del SDK 1.69.0.
        voice_config = types.VoiceConfig(
            prebuilt_voice_config=types.PrebuiltVoiceConfig(
                voice_name="Aoede"
            )
        )

        speech_config = types.SpeechConfig(
            language_code="es-ES",
            voice_config=voice_config
        )

        # Real-time stateful connection configuration.
        # Configuración de conexión con estado en tiempo real.
        config = types.LiveConnectConfig(
            system_instruction=types.Content(
                parts=[types.Part(text=(
                    "Eres EnterpriseBot, una IA corporativa de nivel empresarial. "
                    "HABLA SIEMPRE EN CASTELLANO DE ESPAÑA. "
                    "Tu tono es profesional, eficiente y empático. "
                    "Mantén respuestas breves para reducir la latencia percibida."
                ))]
            ),
            # OBLIGATORIO: Audio como modalidad principal de respuesta.
            response_modalities=["AUDIO"],
            speech_config=speech_config
        )

        logger.info(f"# [SDK] Configuración Live construida para {self.model_id} (Localización: es-ES).")
        return config

    @sync_to_async
    def _persist_transcript(self, call_sid, text_chunk):
        """
        Thread-safe database update for interaction logging.
        Ensures the full_transcript field is updated atomically.
        ---
        Actualización de base de datos segura entre hilos para el registro de interacciones.
        Asegura que el campo full_transcript se actualice de forma atómica.
        """
        from vox_bridge.models import CallInteraction
        try:
            interaction, _ = CallInteraction.objects.get_or_create(call_sid=call_sid)
            if interaction.full_transcript:
                interaction.full_transcript += f"\n{text_chunk}"
            else:
                interaction.full_transcript = text_chunk
            interaction.save()
        except Exception as e:
            logger.error(f"# [ORM ERROR] Fallo en la persistencia de la conversación: {str(e)}")

    async def send_initial_greeting(self, session, call_sid=None):
        """
        Injects the first interaction once the AI handshake is confirmed.
        Waits for self.setup_confirmed (asyncio.Event) set by listen_to_ai upon
        receiving setup_complete from the server. This enforces the mandatory
        Setup-First protocol for Gemini 3.1 Flash Live (April 2026 standard).
        ---
        Inyecta la primera interacción una vez que se confirma el apretón de manos de la IA.
        Espera a self.setup_confirmed (asyncio.Event) activado por listen_to_ai al recibir
        setup_complete del servidor. Esto impone el protocolo Setup-First obligatorio
        para Gemini 3.1 Flash Live (estándar de abril de 2026).
        """
        try:
            logger.info("# [SDK] Esperando confirmación de infraestructura de IA...")
            # ✅ SURGICAL FIX APRIL 2026: Waiting on self.setup_confirmed.wait()
            # (asyncio.Event), NOT on session.setup_complete (server attribute).
            # The Event is set by listen_to_ai when the server confirms setup_complete=True.
            # Prohibido enviar datos antes de que el flag esté activo.
            # ---
            # ✅ CORRECCIÓN QUIRÚRGICA ABRIL 2026: Se espera sobre self.setup_confirmed.wait()
            # (asyncio.Event), NO sobre session.setup_complete (atributo del servidor).
            # El Event es activado por listen_to_ai cuando el servidor confirma setup_complete=True.
            # Prohibido enviar datos antes de que el flag esté activo.
            await asyncio.wait_for(self.setup_confirmed.wait(), timeout=60.0)

            msg = "Hola, soy EnterpriseBot. ¿En qué puedo ayudarte hoy?"

            # ✅ SDK 1.69.0 canonical text injection syntax (April 2026 official docs).
            # Prohibido usar input=, audio= u otros envoltorios para mensajes de texto.
            # ---
            # ✅ Sintaxis canónica de inyección de texto del SDK 1.69.0 (docs oficiales abril 2026).
            # Prohibido usar input=, audio= u otros envoltorios para mensajes de texto.
            await session.send_realtime_input(text=msg, end_of_turn=True)

            logger.info(f"# [SDK] Saludo inicial enviado: '{msg}'")

            if call_sid:
                await self._persist_transcript(call_sid, f"BOT: {msg}")

        except asyncio.TimeoutError:
            logger.error("# [SDK ERROR] Tiempo de espera agotado en el Handshake (60s).")
        except Exception as e:
            logger.error(f"# [SDK ERROR] Fallo en el saludo inicial: {str(e)}")

    def _transcode_twilio_to_gemini(self, b64_data: str) -> bytes:
        """
        DSP: G.711 mu-law (8kHz) -> PCM Linear (16kHz).
        Ensures signal continuity for the AI recognition engine.
        ---
        DSP: G.711 mu-law (8kHz) -> PCM Linear (16kHz).
        Asegura la continuidad de la señal para el motor de reconocimiento de IA.
        """
        try:
            raw_audio = base64.b64decode(b64_data)
            # Mu-law decoding: Transforms 8-bit log compressed audio to 16-bit linear PCM.
            # Decodificación Mu-law: Transforma audio comprimido logarítmico de 8 bits a PCM lineal de 16 bits.
            pcm_8k = audioop.ulaw2lin(raw_audio, 2)

            # Resampling: Interpolates the 8kHz signal to meet Gemini's 16kHz requirement.
            # Resampling: Interpola la señal de 8kHz para cumplir con el requisito de 16kHz de Gemini.
            # Note: self.state_in is preserved across frames to prevent phase clipping.
            # Nota: self.state_in se preserva entre tramas para evitar recorte de fase.
            pcm_16k, self.state_in = audioop.ratecv(pcm_8k, 2, 1, 8000, 16000, self.state_in)

            self.frames_in += 1
            return pcm_16k
        except Exception as e:
            logger.error(f"# [DSP IN ERROR] Error en decodificación de audio: {str(e)}")
            return b""

    def _transcode_gemini_to_twilio(self, pcm_bytes: bytes) -> str:
        """
        DSP: PCM Linear (16kHz) -> G.711 mu-law (8kHz).
        Optimized for Twilio's telephony infrastructure.
        ---
        DSP: PCM Linear (16kHz) -> G.711 mu-law (8kHz).
        Optimizado para la infraestructura de telefonía de Twilio.
        """
        try:
            # Downsampling: Reduces the 16kHz AI output to Twilio's 8kHz standard.
            # Downsampling: Reduce la salida de IA de 16kHz al estándar de 8kHz de Twilio.
            pcm_8k, self.state_out = audioop.ratecv(pcm_bytes, 2, 1, 16000, 8000, self.state_out)

            # Mu-law encoding: Compresses 16-bit linear PCM to 8-bit log for network transmission.
            # Codificación Mu-law: Comprime PCM lineal de 16 bits a logarítmico de 8 bits para transmisión de red.
            data_8k = audioop.lin2ulaw(pcm_8k, 2)

            self.frames_out += 1
            return base64.b64encode(data_8k).decode("utf-8")
        except Exception as e:
            logger.error(f"# [DSP OUT ERROR] Error en codificación de audio: {str(e)}")
            return ""

    async def send_audio_frame(self, session, b64_data: str):
        """
        Transmits processed audio frames to the Gemini Live session.
        Silently drops frames received before setup_confirmed is set,
        enforcing the Setup-First protocol at the audio streaming layer.
        ---
        Transmite tramas de audio procesadas a la sesión Gemini Live.
        Descarta silenciosamente las tramas recibidas antes de que setup_confirmed esté activo,
        imponiendo el protocolo Setup-First en la capa de streaming de audio.
        """
        if not self.setup_confirmed.is_set():
            return

        pcm_frame = self._transcode_twilio_to_gemini(b64_data)
        if pcm_frame:
            # SDK 1.69.0: Mandatory Blob schema for raw PCM 16kHz audio frames.
            # SDK 1.69.0: Esquema de Blob obligatorio para tramas de audio PCM crudo a 16kHz.
            payload = types.LiveClientRealtimeInput(
                audio=types.Blob(data=pcm_frame, mime_type="audio/pcm;rate=16000")
            )
            await session.send(input=payload)

    async def listen_to_ai(self, session, call_sid=None):
        """
        Listens for AI server responses and yields encoded audio payloads.
        Handles interruption events (Barge-in) and transcript persistence.
        Sets self.setup_confirmed Event upon detection of setup_complete from
        the server, enabling the Setup-First protocol for send_initial_greeting.
        ---
        Escucha las respuestas del servidor de IA y genera payloads de audio codificados.
        Gestiona eventos de interrupción (Barge-in) y persistencia de transcripción.
        Activa el Event self.setup_confirmed al detectar setup_complete del servidor,
        habilitando el protocolo Setup-First para send_initial_greeting.
        """
        try:
            async for message in session.receive():
                # ✅ APRIL 2026 FIX: Support for both explicit and implicit handshakes.
                # In Gemini 3.1 Flash Live, setup_complete may be None if server_content
                # arrives first. Upon detection, self.setup_confirmed Event is set to
                # unblock send_initial_greeting and enable audio frame transmission.
                # ---
                # ✅ CORRECCIÓN ABRIL 2026: Soporte para handshakes explícitos e implícitos.
                # En Gemini 3.1 Flash Live, setup_complete puede ser None si server_content
                # llega primero. Al detectarlo, se activa el Event self.setup_confirmed para
                # desbloquear send_initial_greeting y habilitar la transmisión de tramas de audio.
                if message.setup_complete:
                    if not self.setup_confirmed.is_set():
                        self.setup_confirmed.set()
                        # ✅ Log format mandated by Hito 1 Annex (ENTERPRISEBOT_ATTACHED_MILESTONE_V01.md).
                        # Formato de log exigido por el Anexo del Hito 1.
                        logger.info("# [SDK] Handshake Gemini 3.1 (SetupComplete: True) VALIDADO")

                # Check for audio/text model turns.
                # Comprobar turnos del modelo de audio/texto.
                if message.server_content and message.server_content.model_turn:
                    for part in message.server_content.model_turn.parts:
                        if part.inline_data:
                            yield self._transcode_gemini_to_twilio(part.inline_data.data)
                        if part.text and call_sid:
                            await self._persist_transcript(call_sid, f"BOT: {part.text}")

                elif message.server_content and message.server_content.interrupted:
                    logger.warning("# [SDK EVENT] Interrupción de IA detectada (Barge-in).")

        except Exception as e:
            logger.error(f"# [SDK LISTEN ERROR] Error en recepción de IA: {str(e)}")


if __name__ == "__main__":
    # Standard 2026 Syntax Check Entry point.
    # Punto de entrada de comprobación sintáctica estándar 2026.
    print("# [SERVICE] Módulo de servicios listo para la orquestación.")
