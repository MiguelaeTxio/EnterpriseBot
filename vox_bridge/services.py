# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/vox_bridge/services.py
import os
import logging
import asyncio
from django.conf import settings
from google import genai
from google.genai import types

"""
Service for real-time bi-directional voice streaming using Gemini 3.1 Live API.
FINAL AUDIT MARCH 2026: Direct Blob in media_chunks, No Part wrappers for audio.
"""

logger = logging.getLogger(__name__)

class GeminiStreamService:
    def __init__(self):
        self.client = genai.Client(
            api_key=settings.GEMINI_API_KEY,
            http_options={"api_version": "v1alpha"}
        )
        self.model_id = "gemini-3.1-flash-live-preview"
        self.session = None

    async def connect(self):
        config = types.LiveConnectConfig(
            system_instruction=types.Content(
                parts=[types.Part(text="""Eres EnterpriseBot, asistente de voz. 
                Responde SIEMPRE en CASTELLANO de España. Sé profesional y directo. 
                Estás en una llamada telefónica, evita respuestas largas.""")]
            ),
            response_modalities=["AUDIO"]
        )
        self.session = self.client.aio.live.connect(model=self.model_id, config=config)
        return self.session

    async def send_initial_greeting(self, session):
        try:
            # turns -> list[Content] -> parts -> list[Part] (Correct for text)
            content = types.Content(
                parts=[types.Part(text="Preséntate como EnterpriseBot y saluda en castellano.")]
            )
            await session.send(input=types.LiveClientContent(turns=[content]))
            logger.info("# [AI SERVICE] Greeting sent.")
        except Exception as e:
            logger.error(f"# [GREETING ERROR] {str(e)}")

    async def send_audio_frame(self, session, audio_pcm_bytes: bytes):
        try:
            # SDK 2026: media_chunks MUST be list[Blob]. Wrappers like Part cause 1007.
            runtime_input = types.LiveClientRealtimeInput(
                media_chunks=[types.Blob(data=audio_pcm_bytes, mime_type="audio/pcm")]
            )
            await session.send(input=runtime_input)
        except Exception as e:
            logger.error(f"# [AI STREAM ERROR] {str(e)}")
