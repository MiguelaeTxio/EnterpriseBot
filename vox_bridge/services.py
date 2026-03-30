# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/vox_bridge/services.py
import os
import logging
import asyncio
from django.conf import settings
from google import genai
from google.genai import types

"""
Service for real-time multimodal audio streaming using Gemini 3.1 Pro.
Correction: Updated SDK method signature for send_message.
---
Servicio para el streaming de audio multimodal en tiempo real usando Gemini 3.1 Pro.
Corrección: Firma del método send_message actualizada para el SDK.
"""

logger = logging.getLogger(__name__)

class GeminiStreamService:
    def __init__(self):
        """
        Initializes the GenAI Client.
        """
        self.client = genai.Client(api_key=settings.GEMINI_API_KEY)
        self.model_id = "gemini-3.1-pro-preview"
        
        system_instruction = (
            "You are EnterpriseBot, a professional enterprise voice assistant. "
            "Respond always in ENGLISH. Be concise. "
            "You are in a live phone call, speak naturally."
        )

        self.session = self.client.chats.create(
            model=self.model_id,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction
            )
        )
        print("# [AI SERVICE] Gemini session initialized (SDK Sync).", flush=True)

    async def get_initial_greeting(self) -> bytes:
        """
        Generates initial greeting using correct SDK signature.
        """
        try:
            def get_greeting():
                # FIX: In google-genai SDK, prompt is positional or uses 'message' keyword
                return self.session.send_message(
                    message="Please introduce yourself briefly as EnterpriseBot and ask how you can help.",
                    config=types.GenerateContentConfig(response_mime_type="audio/wav")
                )
            response = await asyncio.to_thread(get_greeting)
            return response.audio_bytes if response.audio_bytes else b""
        except Exception as e:
            logger.error(f"# [GREETING ERROR] {str(e)}")
            return b""

    async def process_audio_chunk(self, audio_data: bytes) -> bytes:
        """
        Processes audio chunk using correct SDK signature.
        """
        try:
            def get_gemini_response():
                # FIX: Use 'message' instead of 'contents' for part-based input
                return self.session.send_message(
                    message=[types.Part.from_bytes(data=audio_data, mime_type="audio/x-mulaw")],
                    config=types.GenerateContentConfig(response_mime_type="audio/wav")
                )
            response = await asyncio.to_thread(get_gemini_response)
            return response.audio_bytes if response.audio_bytes else b""
        except Exception as e:
            logger.error(f"# [AI ERROR] {str(e)}")
            return b""
