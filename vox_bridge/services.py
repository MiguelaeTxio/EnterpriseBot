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
Linguistic Fix: Forced Spanish via SpeechConfig language_code (March 2026 Standard).
---
Servicio de Streaming Gemini Live de EnterpriseBot: Orquestación de IA y DSP de Alta Precisión.
Corrección Lingüística: Castellano forzado vía language_code en SpeechConfig (Estándar Marzo 2026).
"""

logger = logging.getLogger("VoxServices")

class GeminiStreamService:
    def __init__(self):
        # Client initialized with v1beta as per official online documentation
        self.client = genai.Client(
            api_key=settings.GEMINI_API_KEY,
            http_options={"api_version": "v1beta"}
        )
        self.model_id = "models/gemini-3.1-flash-live-preview"
        self.state_in = None
        self.state_out = None
        self.frames_in = 0
        self.frames_out = 0
        self.setup_confirmed = asyncio.Event()

    async def connect(self):
        """
        Establishes connection using the Kore voice and mandatory es-ES language code.
        ---
        Establece la conexión usando la voz Kore y el código de idioma obligatorio es-ES.
        """
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
            speech_config=types.SpeechConfig(
                # ✅ MARCH 2026 MANDATORY: Specific language code for the live session
                language_code="es-ES",
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        # ✅ Kore: High-definition Multilingual Voice (2026 Standard)
                        voice_name="Kore"
                    )
                )
            )
        )
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
            
            # ✅ DO NOT send turn_complete=True. This keeps the session in listening mode.
            greeting = types.LiveClientRealtimeInput(
                text="Hola, soy EnterpriseBot. ¿En qué puedo ayudarte?"
            )
            await session.send(input=greeting) 
            logger.info("# [SDK] Saludo inyectado. Turno mantenido en ESCUCHA ACTIVA.")
        except asyncio.TimeoutError:
            logger.error("# [SDK FATAL] Time-out en Handshake. Revisa conectividad regional.")
        except Exception as e:
            logger.error(f"# [SDK GREET] Error: {str(e)}")

    def _transcode_twilio_to_gemini(self, b64_data: str) -> bytes:
        try:
            raw_audio = base64.b64decode(b64_data)
            # A-law (Ireland IE1) to PCM 16-bit
            pcm_8k = audioop.alaw2lin(raw_audio, 2)
            # Resampling to 16kHz for Gemini Input
            pcm_16k, self.state_in = audioop.ratecv(pcm_8k, 2, 1, 8000, 16000, self.state_in)
            self.frames_in += 1
            return pcm_16k
        except Exception as e:
            logger.error(f"# [DSP IN] Error: {str(e)}")
            return b""

    def _transcode_gemini_to_twilio(self, pcm_bytes: bytes) -> str:
        try:
            # Resampling from 24kHz (Gemini Output) to 8kHz (Twilio)
            pcm_8k, self.state_out = audioop.ratecv(pcm_bytes, 2, 1, 24000, 8000, self.state_out)
            # PCM to A-law (Europe Standard)
            data_8k = audioop.lin2alaw(pcm_8k, 2)
            self.frames_out += 1
            return base64.b64encode(data_8k).decode("utf-8")
        except Exception as e:
            logger.error(f"# [DSP OUT] Error: {str(e)}")
            return ""

    async def send_audio_frame(self, session, b64_data: str):
        # Barrier protection
        if not self.setup_confirmed.is_set():
            return

        pcm_frame = self._transcode_twilio_to_gemini(b64_data)
        if pcm_frame:
            payload = types.LiveClientRealtimeInput(
                audio=types.Blob(data=pcm_frame, mime_type="audio/L16;rate=16000")
            )
            await session.send(input=payload)
            if self.frames_in % 50 == 0:
                logger.info(f"# [UPSTREAM] Audio Frames flow: {self.frames_in}")

    async def listen_to_ai(self, session):
        try:
            async for message in session.receive():
                if message.setup_complete:
                    logger.info("# [SDK] setup_complete recibido. Sesión LIVE sincronizada.")
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
