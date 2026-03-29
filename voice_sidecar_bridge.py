# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/voice_sidecar_bridge.py
import os
import json
import base64
import asyncio
import websockets
import django
from django.conf import settings

# 1. BOOTSTRAP DE DJANGO / DJANGO BOOTSTRAP
# Initialize Django environment for ORM and settings access.
# Inicializa el entorno de Django para acceso a modelos y configuración.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'enterprise_core.settings')
django.setup()

from vox_bridge.services import GeminiStreamService
from vox_bridge.models import CallInteraction

class UniversalVoiceBridge:
    """
    Asynchronous bridge for bidirectional audio streaming between Twilio Media Streams and Gemini 3.1.
    Handles the JSON-encapsulated Base64 audio protocol (G.711 mu-law).
    ---
    Puente asíncrono para streaming de audio bidireccional entre Twilio Media Streams y Gemini 3.1.
    Gestiona el protocolo de audio Base64 encapsulado en JSON (G.711 mu-law).
    """

    def __init__(self):
        """
        Initializes the AI service for real-time interaction.
        ---
        Inicializa el servicio de IA para interacción en tiempo real.
        """
        self.gemini_service = GeminiStreamService()
        self.stream_sid = None

    async def handle_connection(self, websocket):
        """
        Manages the lifecycle of the Twilio WebSocket connection and audio routing.
        ---
        Gestiona el ciclo de vida de la conexión WebSocket de Twilio y el enrutamiento de audio.
        """
        print("# [INFO] Nueva conexión de voz detectada desde Twilio.")
        
        try:
            async for message in websocket:
                # Twilio Media Streams always sends text (JSON) messages.
                # Twilio Media Streams siempre envía mensajes de texto (JSON).
                if isinstance(message, str):
                    try:
                        data = json.loads(message)
                        event = data.get('event')

                        if event == "connected":
                            print("# [EVENT] Protocolo de red establecido (Connected).")

                        elif event == "start":
                            self.stream_sid = data.get('start', {}).get('streamSid')
                            call_sid = data.get('start', {}).get('callSid')
                            print(f"# [EVENT] Stream iniciado. StreamSid: {self.stream_sid} | CallSid: {call_sid}")
                            
                            # Auditoría en Base de Datos: Actualizar interacción si existe
                            # Database Audit: Update interaction if exists
                            await self.log_call_start(call_sid, self.stream_sid)

                        elif event == "media":
                            # Extraction of Base64 payload from Twilio JSON
                            # Extracción del payload Base64 desde el JSON de Twilio
                            payload_b64 = data.get('media', {}).get('payload')
                            if payload_b64:
                                # Decode to raw bytes (PCMU / G.711 mu-law)
                                # Decodificar a bytes crudos (PCMU / G.711 mu-law)
                                audio_bytes = base64.b64decode(payload_b64)
                                
                                # Process through Gemini / Procesar a través de Gemini
                                response_audio = await self.gemini_service.process_audio_chunk(audio_bytes)
                                
                                if response_audio and self.stream_sid:
                                    # Encode Gemini response to Base64 for Twilio
                                    # Codificar respuesta de Gemini a Base64 para Twilio
                                    response_b64 = base64.b64encode(response_audio).decode('utf-8')
                                    
                                    # Wrap in Twilio's JSON structure
                                    # Encapsular en la estructura JSON de Twilio
                                    twilio_message = {
                                        "event": "media",
                                        "streamSid": self.stream_sid,
                                        "media": {
                                            "payload": response_b64
                                        }
                                    }
                                    await websocket.send(json.dumps(twilio_message))

                        elif event == "stop":
                            print(f"# [EVENT] Stream finalizado (Stop). StreamSid: {self.stream_sid}")
                            break

                    except json.JSONDecodeError:
                        print(f"# [WARNING] Mensaje de texto no válido (no JSON): {message}")
                
                elif isinstance(message, bytes):
                    # Warning: Twilio should not send raw binary. Log for debugging.
                    # Advertencia: Twilio no debería enviar binario crudo. Registrar para depuración.
                    print("# [DEBUG] Se recibió un mensaje binario inesperado.")

        except websockets.exceptions.ConnectionClosed:
            print("# [INFO] Conexión cerrada por Twilio.")
        except Exception as e:
            print(f"# [ERROR] CRÍTICO EN BRIDGE: {str(e)}")

    async def log_call_start(self, call_sid, stream_sid):
        """
        Updates the CallInteraction model with the StreamSid for traceability.
        ---
        Actualiza el modelo CallInteraction con el StreamSid para trazabilidad.
        """
        try:
            # Running ORM operations in a thread-safe way for async
            from asgiref.sync import sync_to_async
            
            @sync_to_async
            def update_model():
                interaction, created = CallInteraction.objects.get_or_create(call_sid=call_sid)
                interaction.stream_sid = stream_sid
                interaction.status = 'in-progress'
                interaction.save()
            
            await update_model()
        except Exception as e:
            print(f"# [DB ERROR] No se pudo actualizar la interacción: {str(e)}")

async def main():
    """
    Starts the asynchronous WebSocket server on port 8080.
    ---
    Inicia el servidor WebSocket asíncrono en el puerto 8080.
    """
    bridge = UniversalVoiceBridge()
    # Listen on all interfaces for task-based execution (PythonAnywhere)
    async with websockets.serve(bridge.handle_connection, "0.0.0.0", 8080):
        print("# [SUCCESS] EnterpriseBot: Bridge de Voz Activo en el puerto 8080 (Twilio Protocol)...")
        await asyncio.Future()  # Run forever

if __name__ == "__main__":
    # Ensure unbuffered output for PythonAnywhere logs
    asyncio.run(main())
