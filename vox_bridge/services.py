# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/vox_bridge/services.py
import os
import logging
from django.conf import settings
from google import genai
from google.genai import types

logger = logging.getLogger(__name__)

class GeminiStreamService:
    """
    Service for real-time multimodal audio streaming using Gemini 3.1 Pro.
    ---
    Servicio para el streaming de audio multimodal en tiempo real usando Gemini 3.1 Pro.
    """
    def __init__(self):
        self.client = genai.Client(api_key=settings.GEMINI_API_KEY)
        self.model_id = "gemini-3.1-pro-preview"
        # Inicialización de sesión de chat persistente / Persistent chat session init
        self.session = self.client.chats.create(model=self.model_id)

    async def process_audio_chunk(self, audio_data: bytes) -> bytes:
        """
        Sends an audio chunk to Gemini and returns the synthesized voice response.
        ---
        Envía un fragmento de audio a Gemini y devuelve la respuesta de voz sintetizada.
        """
        try:
            # Lógica de streaming multimodal (SDK 2026)
            # En esta versión simplificada devolvemos el audio procesado
            response = self.session.send_message(
                contents=[types.Part.from_bytes(data=audio_data, mime_type="audio/x-mulaw")],
                config=types.GenerateContentConfig(response_mime_type="audio/wav")
            )
            return response.audio_bytes # Asumiendo salida de audio directa
        except Exception as e:
            logger.error(f"Error en stream de Gemini: {str(e)}")
            return b""
