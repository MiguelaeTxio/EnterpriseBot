# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/vox_bridge/services.py

import os
import logging
import asyncio
import audioop
import base64
from django.conf import settings
from google import genai
from google.genai import types

logger = logging.getLogger(__name__)


class GeminiStreamService:
    """
    Stateful orchestrator for Gemini Live A2A (Audio-to-Audio) interactions.
    Updated for SDK v1.68.0+ (March 2026 compliant).
    """

    def __init__(self):
        self.client = genai.Client(
            api_key=settings.GEMINI_API_KEY,
            http_options={"api_version": "v1alpha"}
        )

        self.model_id = "models/gemini-3.1-flash-live-preview"

        # DSP states
        self.state_in = None   # mu-law -> PCM
        self.state_out = None  # PCM -> mu-law

    async def connect(self):
        """
        Establish Gemini Live session (March 2026 compliant).
        """

        config = types.LiveConnectConfig(
            system_instruction=types.Content(
                parts=[
                    types.Part(
                        text=(
                            "Eres EnterpriseBot, asistente de voz profesional. "
                            "Responde siempre en CASTELLANO de España. "
                            "Sé breve y natural."
                        )
                    )
                ]
            ),

            # ✅ NUEVA FORMA (sin GenerationConfig)
            response_modalities=["AUDIO"],

            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name="Puck"
                    )
                )
            )
        )

        return self.client.aio.live.connect(
            model=self.model_id,
            config=config
        )

    def _transcode_twilio_to_gemini(self, mu_law_base64: str) -> bytes:
        """
        DSP: 8kHz 8-bit mu-law -> 16kHz 16-bit PCM Linear.
        """
        try:
            raw_mu_law = base64.b64decode(mu_law_base64)

            pcm_linear_8k = audioop.ulaw2lin(raw_mu_law, 2)

            pcm_linear_16k, self.state_in = audioop.ratecv(
                pcm_linear_8k,
                2,
                1,
                8000,
                16000,
                self.state_in
            )

            return pcm_linear_16k

        except Exception as e:
            logger.error(f"# [DSP IN] Error: {str(e)}")
            return b""

    def _transcode_gemini_to_twilio(self, pcm_bytes: bytes) -> str:
        """
        DSP: 16kHz 16-bit PCM Linear -> 8kHz 8-bit mu-law.
        """
        try:
            pcm_8k, self.state_out = audioop.ratecv(
                pcm_bytes,
                2,
                1,
                24000,
                8000,
                self.state_out
            )

            mu_law_data = audioop.lin2ulaw(pcm_8k, 2)

            return base64.b64encode(mu_law_data).decode("utf-8")

        except Exception as e:
            logger.error(f"# [DSP OUT] Error: {str(e)}")
            return ""

    async def send_audio_frame(self, session, mu_law_base64: str):
        """
        Send audio frame to Gemini (strict Blob format).
        """
        try:
            pcm_frame = self._transcode_twilio_to_gemini(mu_law_base64)

            if pcm_frame:
                runtime_input = types.LiveClientRealtimeInput(
                    audio=types.Blob(
                        data=pcm_frame,
                        mime_type="audio/pcm"
                    )
                )

                await session.send(input=runtime_input)

        except Exception as e:
            logger.error(f"# [SDK SEND] Error: {str(e)}")

    async def listen_to_ai(self, session):
        """
        Async generator to receive AI audio stream.
        """
        try:
            # ✅ FIX CRÍTICO AQUÍ
            async for message in session.receive():

                if (
                    message.server_content
                    and message.server_content.model_turn
                ):
                    for part in message.server_content.model_turn.parts:
                        if part.inline_data:
                            mu_law_payload = self._transcode_gemini_to_twilio(
                                part.inline_data.data
                            )

                            if mu_law_payload:
                                yield mu_law_payload

                # Barge-in detection
                if (
                    message.server_content
                    and message.server_content.interrupted
                ):
                    logger.warning(
                        "# [SDK] Barge-in detected: AI stopping response."
                    )
                    break

        except Exception as e:
            logger.error(f"# [SDK LISTEN] Error: {str(e)}")