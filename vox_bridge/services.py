# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/vox_bridge/services.py
import os
import logging
import asyncio
import audioop
import base64
from django.conf import settings
from google import genai
from google.genai import types

"""
EnterpriseBot Gemini Live Stream Service: High-Precision DSP and AI Orchestration.
Linguistic Fix: Forced Spanish via SpeechConfig language_code (April 2026 Production).
Codec Fix: Switched to mu-law (PCMU) and 16kHz for Gemini 2.0 Flash GA.
---
Servicio de Streaming Gemini Live de EnterpriseBot: Orquestación de IA y DSP de Alta Precisión.
Corrección Lingüística: Castellano forzado vía language_code en SpeechConfig (Estándar Abril 2026).
Corrección de Codec: Cambio a mu-law (PCMU) y 16kHz para Gemini 2.0 Flash GA.
"""

logger = logging.getLogger("VoxServices")

class GeminiStreamService:
    """
    Orchestrator for bidirectional voice interaction between Twilio and Gemini.
    ---
    Orquestador para la interacción de voz bidireccional entre Twilio y Gemini.
    """
    def __init__(self):
        # ✅ SDK 2.0 GA: api_version is now a direct parameter
        self.client = genai.Client(
            api_key=settings.GEMINI_API_KEY,
            api_version="v1"
        )
        self.model_id = "models/gemini-2.0-flash-live"
        self.state_in = None
        self.state_out = None
        self.frames_in = 0
        self.frames_out = 0
        self.setup_confirmed = asyncio.Event()

    async def connect(self):
        """
        Establishes connection using the Aoede voice and mandatory es-ES language code.
        ---
        Establece la conexión usando la voz Aoede y el código de idioma obligatorio es-ES.
        """
        # ✅ APRIL 2026 MANDATORY: Hierarchical SpeechConfig for phonetic recognition
        speech_config = types.SpeechConfig(
            language_code="es-ES",
            voice_config=types.VoiceConfig(
                voice_name="Aoede"
            )
        )

        config = types.LiveConnectConfig(
            system_instruction=types.Content(
                parts=[
                    types.Part(
                        text=(
                            "Eres EnterpriseBot. HABLA SIEMPRE EN CASTELLANO DE ESPAÑA. "
                            "Tu función es asistir al usuario en tiempo real. "
                            "MANTÉN LA ESCUCHA SIEMPRE ACTIVA. No te despidas ni cierres la sesión "
                            "a menos que el usuario lo pida. Sé breve y profesional."
                        )
                    )
                ]
            ),
            response_modalities=["AUDIO"],
            speech_config=speech_config
        )
        logger.info("# [SDK] Iniciando sesión LIVE (v1) con localización es-ES.")
        return self.client.aio.live.connect(model=self.model_id, config=config)

    async def send_initial_greeting(self, session):
        """
        Sends the greeting WITHOUT turn_complete to ensure the microphone stays open.
        ---
        Envía el saludo SIN turn_complete para asegurar que el micrófono permanezca abierto.
        """
        try:
            logger.info("# [SDK] Esperando setup_complete para inyección de saludo...")
            await asyncio.wait_for(self.setup_confirmed.wait(), timeout=15.0)
            
            # ✅ end_of_turn=False keeps the session in listening mode (SDK 1.69.0 syntax).
            greeting = types.LiveClientRealtimeInput(
                text="Hola, soy EnterpriseBot. ¿En qué puedo ayudarte?"
            )
            await session.send(input=greeting, end_of_turn=False) 
            logger.info("# [SDK] Saludo inyectado. Turno mantenido en ESCUCHA ACTIVA.")
        except asyncio.TimeoutError:
            logger.error("# [SDK FATAL] Time-out en Handshake. Revisa conectividad regional.")
        except Exception as e:
            logger.error(f"# [SDK GREET] Error: {str(e)}")

    def _transcode_twilio_to_gemini(self, b64_data: str) -> bytes:
        """
        Transcodes Twilio mu-law audio to PCM 16-bit for Gemini Input.
        ---
        Transcodifica audio mu-law de Twilio a PCM 16-bit para la entrada de Gemini.
        """
        try:
            raw_audio = base64.b64decode(b64_data)
            # ✅ APRIL 2026 FIX: Twilio Media Streams uses mu-law (PCMU)
            pcm_8k = audioop.ulaw2lin(raw_audio, 2)
            # ✅ Gemini 2.0 Flash GA expects 16kHz input
            pcm_16k, self.state_in = audioop.ratecv(pcm_8k, 2, 1, 8000, 16000, self.state_in)
            self.frames_in += 1
            return pcm_16k
        except Exception as e:
            logger.error(f"# [DSP IN] Error: {str(e)}")
            return b""

    def _transcode_gemini_to_twilio(self, pcm_bytes: bytes) -> str:
        """
        Transcodes Gemini PCM audio to mu-law for Twilio Output.
        ---
        Transcodifica audio PCM de Gemini a mu-law para la salida de Twilio.
        """
        try:
            # ✅ APRIL 2026 FIX: Gemini 2.0 Flash GA returns 16kHz (Factor 0.5)
            pcm_8k, self.state_out = audioop.ratecv(pcm_bytes, 2, 1, 16000, 8000, self.state_out)
            # ✅ APRIL 2026 FIX: Convert to mu-law for Twilio
            data_8k = audioop.lin2ulaw(pcm_8k, 2)
            self.frames_out += 1
            return base64.b64encode(data_8k).decode("utf-8")
        except Exception as e:
            logger.error(f"# [DSP OUT] Error: {str(e)}")
            return ""

    async def send_audio_frame(self, session, b64_data: str):
        """
        Processes and sends an audio frame from Twilio to the Gemini session.
        ---
        Procesa y envía una trama de audio desde Twilio a la sesión de Gemini.
        """
        if not self.setup_confirmed.is_set():
            return

        pcm_frame = self._transcode_twilio_to_gemini(b64_data)
        if pcm_frame:
            payload = types.LiveClientRealtimeInput(
                audio=types.Blob(data=pcm_frame, mime_type="audio/L16;rate=16000")
            )
            await session.send(input=payload)
            if self.frames_in % 100 == 0:
                logger.info(f"# [UPSTREAM] Frames processed: {self.frames_in}")

    async def listen_to_ai(self, session):
        """
        Listens for server messages and yields transcode audio payloads.
        ---
        Escucha mensajes del servidor y genera payloads de audio transcodificados.
        """
        try:
            async for message in session.receive():
                if message.setup_complete:
                    logger.info("# [SDK] setup_complete recibido. Sesión LIVE (es-ES) sincronizada.")
                    self.setup_confirmed.set()
                
                if message.server_content and message.server_content.model_turn:
                    for part in message.server_content.model_turn.parts:
                        if part.inline_data:
                            payload = self._transcode_gemini_to_twilio(part.inline_data.data)
                            if payload:
                                yield payload
                elif message.server_content and message.server_content.interrupted:
                    logger.warning("# [SDK] IA Interrumpida (Barge-in detected).")
        except Exception as e:
            logger.error(f"# [SDK LISTEN] Error en recepción de IA: {str(e)}")
