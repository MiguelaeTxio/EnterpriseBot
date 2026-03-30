# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/voice_sidecar_bridge.py
import os
import json
import base64
import asyncio
import websockets
import django
from django.conf import settings

# 1. BOOTSTRAP DE DJANGO
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'enterprise_core.settings')
django.setup()

from vox_bridge.services import GeminiStreamService
from vox_bridge.models import CallInteraction

class UniversalVoiceBridge:
    """
    Simplified bridge for direct binary passthrough.
    ---
    Puente simplificado para el paso directo de binarios.
    """
    def __init__(self):
        self.gemini_service = GeminiStreamService()
        self.stream_sid = None

    async def handle_connection(self, websocket):
        print("# [INFO] Connection established. Monitoring traffic...", flush=True)
        try:
            async for message in websocket:
                if isinstance(message, str):
                    data = json.loads(message)
                    event = data.get('event')

                    if event == "start":
                        self.stream_sid = data.get('start', {}).get('streamSid')
                        call_sid = data.get('start', {}).get('callSid')
                        print(f"# [EVENT] Stream started: {self.stream_sid}", flush=True)
                        await self.log_call_start(call_sid, self.stream_sid)
                        
                        # PROACTIVE GREETING
                        greeting_audio = await self.gemini_service.get_initial_greeting()
                        if greeting_audio:
                            payload = base64.b64encode(greeting_audio).decode('utf-8')
                            await websocket.send(json.dumps({
                                "event": "media",
                                "streamSid": self.stream_sid,
                                "media": {"payload": payload}
                            }))
                            print("# [STREAM] Greeting payload sent.", flush=True)

                    elif event == "media":
                        payload_b64 = data.get('media', {}).get('payload')
                        if payload_b64:
                            # Direct passthrough to AI / Paso directo a la IA
                            audio_bytes = base64.b64decode(payload_b64)
                            response_audio = await self.gemini_service.process_audio_chunk(audio_bytes)
                            
                            if response_audio and self.stream_sid:
                                response_b64 = base64.b64encode(response_audio).decode('utf-8')
                                await websocket.send(json.dumps({
                                    "event": "media",
                                    "streamSid": self.stream_sid,
                                    "media": {"payload": response_b64}
                                }))
                                print("# [STREAM] AI Response sent.", flush=True)

                    elif event == "stop":
                        print("# [EVENT] Call stopped.", flush=True)
                        break
        except Exception as e:
            print(f"# [CRITICAL] Bridge loop error: {str(e)}", flush=True)

    async def log_call_start(self, call_sid, stream_sid):
        from asgiref.sync import sync_to_async
        @sync_to_async
        def update_model():
            interaction, _ = CallInteraction.objects.get_or_create(call_sid=call_sid)
            interaction.stream_sid = stream_sid
            interaction.status = 'in-progress'
            interaction.save()
        await update_model()

async def main():
    bridge = UniversalVoiceBridge()
    async with websockets.serve(bridge.handle_connection, "0.0.0.0", 8080):
        print("# [SUCCESS] Bridge active on port 8080. Awaiting Twilio...", flush=True)
        await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())
