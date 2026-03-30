# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/voice_sidecar_bridge.py
import os
import json
import base64
import asyncio
import websockets
import django
import audioop
from django.conf import settings

# 1. BOOTSTRAP DE DJANGO
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "enterprise_core.settings")
django.setup()

from vox_bridge.services import GeminiStreamService

class UniversalVoiceBridge:
    def __init__(self):
        self.gemini_service = GeminiStreamService()
        self.stream_sid = None
        self.state = {"ulaw_state": None, "pcm_state": None}

    async def handle_connection(self, twilio_ws):
        print("# [INFO] Twilio Connection established.", flush=True)
        try:
            async with await self.gemini_service.connect() as google_session:
                print("# [INFO] Gemini Live Session connected.", flush=True)
                await asyncio.gather(
                    self.stream_to_google(twilio_ws, google_session),
                    self.stream_from_google(twilio_ws, google_session)
                )
        except Exception as e:
            print(f"# [CRITICAL] Session Error: {str(e)}", flush=True)

    async def stream_to_google(self, twilio_ws, google_session):
        try:
            async for message in twilio_ws:
                data = json.loads(message)
                if data.get("event") == "start":
                    self.stream_sid = data["start"]["streamSid"]
                    print(f"# [EVENT] Stream started: {self.stream_sid}", flush=True)
                    await self.gemini_service.send_initial_greeting(google_session)
                elif data.get("event") == "media" and self.stream_sid:
                    payload = base64.b64decode(data["media"]["payload"])
                    pcm_data = audioop.ulaw2lin(payload, 2)
                    resampled_pcm, self.state["ulaw_state"] = audioop.ratecv(
                        pcm_data, 2, 1, 8000, 16000, self.state["ulaw_state"]
                    )
                    await self.gemini_service.send_audio_frame(google_session, resampled_pcm)
        except Exception as e:
            print(f"# [ERROR] Uplink: {str(e)}", flush=True)

    async def stream_from_google(self, twilio_ws, google_session):
        try:
            async for response in google_session:
                if response.server_content and response.server_content.model_turn:
                    for part in response.server_content.model_turn.parts:
                        if part.inline_data:
                            # Transcode 24kHz -> 8kHz mulaw
                            resampled, self.state["pcm_state"] = audioop.ratecv(
                                part.inline_data.data, 2, 1, 24000, 8000, self.state["pcm_state"]
                            )
                            mulaw_data = audioop.lin2ulaw(resampled, 2)
                            await twilio_ws.send(json.dumps({
                                "event": "media",
                                "streamSid": self.stream_sid,
                                "media": {"payload": base64.b64encode(mulaw_data).decode("utf-8")}
                            }))
        except Exception as e:
            print(f"# [ERROR] Downlink: {str(e)}", flush=True)

async def main():
    bridge = UniversalVoiceBridge()
    async with websockets.serve(bridge.handle_connection, "0.0.0.0", 8081):
        print("# [SUCCESS] Bridge active on port 8081.", flush=True)
        await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())
