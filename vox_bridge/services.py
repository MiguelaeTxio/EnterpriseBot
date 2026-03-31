# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/vox_bridge/services.py
import os
import logging
import asyncio
import audioop
import base64
from django.conf import settings
from google import genai
from google.genai import types

# Standard industrial logging
# Registro industrial estándar
logger = logging.getLogger("VoxServices")

class GeminiStreamService:
    """
    Synchronous State Orchestrator for Gemini 3.1 Flash Live.
    Enforces a strict "Setup-then-Data" policy to avoid 1011 Protocol errors.
    ---
    Orquestador de estado síncrono para Gemini 3.1 Flash Live.
    Impone una política estricta de "Setup-luego-Datos" para evitar errores de protocolo 1011.
    """

    def __init__(self):
        self.client = genai.Client(
            api_key=settings.GEMINI_API_KEY,
            http_options={"api_version": "v1beta"}
        )
        self.model_id = "models/gemini-3.1-flash-live-preview"
        self.state_in = None
        self.state_out = None
        self.frames_in = 0
        self.frames_out = 0
        
        # Forced European Codec for Ireland Route
        self.codec = "pcma"
        
        # ✅ Barrier: Must wait for Google's confirmation
        self.setup_confirmed = asyncio.Event()

    async def connect(self):
        """
        Establishes connection and sends the initial configuration frame via SDK.
        ---
        Establece la conexión y envía el frame de configuración inicial vía SDK.
        """
        config = types.LiveConnectConfig(
            system_instruction=types.Content(
                parts=[
                    types.Part(
                        text=(
                            "Eres EnterpriseBot. Responde de forma muy concisa en CASTELLANO de España. "
                            "Tu tono es profesional. Saluda al usuario inmediatamente."
                        )
                    )
                ]
            ),
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Puck")
                )
            )
        )
        # The SDK handles the first SETUP frame internally here
        return self.client.aio.live.connect(model=self.model_id, config=config)

    async def send_initial_greeting(self, session):
        """
        Blocks until setup_complete is received, then injects the first conversational turn.
        ---
        Bloquea hasta recibir setup_complete, luego inyecta el primer turno conversacional.
        """
        try:
            logger.info("# [SDK] Waiting for setup_complete barrier...")
            # Increased timeout for PythonAnywhere stability
            await asyncio.wait_for(self.setup_confirmed.wait(), timeout=15.0)
            
            greeting = types.LiveClientRealtimeInput(
                text="Hola, soy EnterpriseBot. ¿En qué puedo ayudarte?"
            )
            await session.send(input=greeting, end_of_turn=True)
            logger.info("# [SDK] Session ACTIVE. Greeting injected.")
        except asyncio.TimeoutError:
            logger.error("# [SDK FATAL] Google did not confirm setup. Handshake failed.")
        except Exception as e:
            logger.error(f"# [SDK GREET] Error: {str(e)}")

    def _transcode_twilio_to_gemini(self, b64_data: str) -> bytes:
        try:
            raw_audio = base64.b64decode(b64_data)
            # Forced A-law for Spanish destination
            pcm_8k = audioop.alaw2lin(raw_audio, 2)
            pcm_16k, self.state_in = audioop.ratecv(pcm_8k, 2, 1, 8000, 16000, self.state_in)
            self.frames_in += 1
            return pcm_16k
        except Exception as e:
            logger.error(f"# [DSP IN] Error: {str(e)}")
            return b""

    def _transcode_gemini_to_twilio(self, pcm_bytes: bytes) -> str:
        try:
            pcm_8k, self.state_out = audioop.ratecv(pcm_bytes, 2, 1, 16000, 8000, self.state_out)
            data_8k = audioop.lin2alaw(pcm_8k, 2)
            self.frames_out += 1
            return base64.b64encode(data_8k).decode("utf-8")
        except Exception as e:
            logger.error(f"# [DSP OUT] Error: {str(e)}")
            return ""

    async def send_audio_frame(self, session, b64_data: str):
        # 🛡️ PROTECTIVE BARRIER: Do not flood Google with audio before setup
        if not self.setup_confirmed.is_set():
            return

        pcm_frame = self._transcode_twilio_to_gemini(b64_data)
        if pcm_frame:
            payload = types.LiveClientRealtimeInput(
                audio=types.Blob(data=pcm_frame, mime_type="audio/L16;rate=16000")
            )
            await session.send(input=payload)
            if self.frames_in % 20 == 0:
                logger.info(f"# [UPSTREAM] Packets sent: {self.frames_in}")

    async def listen_to_ai(self, session):
        try:
            async for message in session.receive():
                # Detect the system message that unlocks the session
                if message.setup_complete:
                    logger.info("# [SDK] setup_complete received. Unlocking session.")
                    self.setup_confirmed.set()
                
                if message.server_content and message.server_content.model_turn:
                    for part in message.server_content.model_turn.parts:
                        if part.inline_data:
                            payload = self._transcode_gemini_to_twilio(part.inline_data.data)
                            if payload:
                                if self.frames_out % 10 == 0:
                                    logger.info(f"# [DOWNSTREAM] IA Frames: {self.frames_out}")
                                yield payload
                elif message.server_content and message.server_content.interrupted:
                    logger.warning("# [SDK] IA Interrupted.")
        except Exception as e:
            logger.error(f"# [SDK LISTEN] Error: {str(e)}")
