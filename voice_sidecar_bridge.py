# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/voice_sidecar_bridge.py
import os
import json
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
    Asynchronous bridge for bidirectional audio streaming between CPaaS (Voximplant) and Gemini 3.1.
    Handles both binary frames (raw audio) and JSON metadata.
    ---
    Puente asíncrono para streaming de audio bidireccional entre CPaaS (Voximplant) y Gemini 3.1.
    Gestiona tanto tramas binarias (audio crudo) como metadatos JSON.
    """

    def __init__(self):
        """
        Initializes the AI service for real-time interaction.
        ---
        Inicializa el servicio de IA para interacción en tiempo real.
        """
        self.gemini_service = GeminiStreamService()

    async def handle_connection(self, websocket):
        """
        Manages the lifecycle of the WebSocket connection and audio routing.
        ---
        Gestiona el ciclo de vida de la conexión WebSocket y el enrutamiento de audio.
        """
        print("# Nueva conexión de voz detectada (Protocolo Voximplant/Telnyx).")
        
        try:
            async for message in websocket:
                if isinstance(message, bytes):
                    # BINARY AUDIO: Direct pipe to Gemini Multimodal
                    # AUDIO BINARIO: Enlace directo a Gemini Multimodal
                    response_audio = await self.gemini_service.process_audio_chunk(message)
                    
                    if response_audio:
                        # Return audio to user's headset / Devolver audio al auricular del usuario
                        await websocket.send(response_audio)
                
                elif isinstance(message, str):
                    # METADATA: Log signaling or setup data
                    # METADATOS: Registrar señalización o datos de configuración
                    try:
                        data = json.loads(message)
                        print(f"# Señalización recibida: {data.get('event', 'unknown')}")
                    except json.JSONDecodeError:
                        print(f"# Mensaje de texto (no JSON): {message}")

        except websockets.exceptions.ConnectionClosed:
            print("# Conexión cerrada por el cliente remoto.")
        except Exception as e:
            print(f"# ERROR CRÍTICO EN BRIDGE: {str(e)}")

async def main():
    """
    Starts the asynchronous WebSocket server on port 8080.
    ---
    Inicia el servidor WebSocket asíncrono en el puerto 8080.
    """
    bridge = UniversalVoiceBridge()
    # Listen on all interfaces for task-based execution
    async with websockets.serve(bridge.handle_connection, "0.0.0.0", 8080):
        print("# EnterpriseBot: Bridge de Voz Activo en el puerto 8080 (Modo Universal)...")
        await asyncio.Future()  # Run forever

if __name__ == "__main__":
    # Ensure unbuffered output for PythonAnywhere logs
    asyncio.run(main())
