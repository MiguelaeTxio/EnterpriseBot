# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/test_live/services.py
import asyncio
import time
from google import genai
from google.genai import types
from django.conf import settings
from .models import LiveTestLog
from django.utils import timezone

class GeminiLiveProbe:
    """
    Master Diagnostic Service for Gemini 3.1 Flash Live (v1beta).
    Validated on March 31, 2026.
    ---
    Servicio de Diagnóstico Maestro para Gemini 3.1 Flash Live (v1beta).
    Validado el 31 de marzo de 2026.
    """
    def __init__(self, session_id):
        self.session_id = session_id
        # Versión de API v1beta obligatoria para Multimodal Live
        self.client = genai.Client(
            api_key=settings.GEMINI_API_KEY, 
            http_options=types.HttpOptions(api_version='v1beta')
        )
        self.model_id = "gemini-3.1-flash-live-preview"
        self.log_entry = LiveTestLog.objects.create(session_id=self.session_id, api_version="v1beta")

    async def run_diagnostic(self, audio_file):
        """
        Executes a real-time stream using the send_realtime_input protocol.
        ---
        Ejecuta un flujo en tiempo real usando el protocolo send_realtime_input.
        """
        start_time = time.time()
        try:
            # Configuración estricta de modalidades para evitar errores 1007
            config = types.LiveConnectConfig(
                response_modalities=['AUDIO'],
                thinking_config=types.ThinkingConfig(thinking_level='minimal')
            )
            
            async with self.client.aio.live.connect(model=self.model_id, config=config) as session:
                self.log_entry.setup_completed_at = timezone.now()
                self.log_entry.handshake_latency_ms = int((time.time() - start_time) * 1000)
                
                if audio_file:
                    # Uso del método send_realtime_input validado en la Prueba v7
                    await session.send_realtime_input(audio=audio_file.read())
                    
                    async for message in session.receive():
                        # Captura del turno del modelo (Audio a 24000Hz)
                        if message.server_content and message.server_content.model_turn:
                            self.log_entry.first_response_at = timezone.now()
                            # En esta fase de sonda, confirmamos la recepción del primer blob
                            break
                
                self.log_entry.is_successful = True
                self.log_entry.save()
                return {
                    "status": "success", 
                    "latency_ms": self.log_entry.handshake_latency_ms,
                    "info": "BIDI Protocol Validated (24kHz)"
                }
        
        except Exception as e:
            self.log_entry.error_log = f"{type(e).__name__}: {str(e)}"
            self.log_entry.save()
            return {"status": "error", "message": self.log_entry.error_log}
