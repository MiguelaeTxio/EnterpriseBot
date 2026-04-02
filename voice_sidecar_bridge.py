# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/voice_sidecar_bridge.py
import os
import json
import asyncio
import logging
import signal
import websockets
import django
from django.conf import settings

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "enterprise_core.settings")
django.setup()

from vox_bridge.services import GeminiStreamService

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s # [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("VoiceSidecar")

class UniversalVoiceBridge:
    """
    WebSocket bridge between Twilio and Gemini Live.
    ---
    Puente WebSocket entre Twilio y Gemini Live.
    """
    def __init__(self):
        self.gemini_service = GeminiStreamService()
        self.stream_sid = None

    async def handle_connection(self, twilio_ws):
        logger.info("# [CONN] Incoming Twilio Stream.")
        try:
            # Connect using the internal SDK setup mechanism
            async with await self.gemini_service.connect() as google_session:
                logger.info("# [CONN] Socket open. Handshaking...")

                # Launch concurrent duplex tasks
                uplink = asyncio.create_task(self.stream_to_google(twilio_ws, google_session))
                downlink = asyncio.create_task(self.stream_from_google(twilio_ws, google_session))
                
                # ✅ APRIL 2026 FIX: Mandatory delay for Twilio buffer stabilization
                await asyncio.sleep(0.5)
                await self.gemini_service.send_initial_greeting(google_session)

                await asyncio.wait([uplink, downlink], return_when=asyncio.FIRST_COMPLETED)
                for task in [uplink, downlink]:
                    task.cancel()
                logger.info("# [CONN] Interaction finished.")

        except Exception as e:
            logger.error(f"# [CRITICAL] Orchestration Failure: {str(e)}")

    async def stream_to_google(self, twilio_ws, google_session):
        async for message in twilio_ws:
            data = json.loads(message)
            event = data.get("event")
            if event == "start":
                self.stream_sid = data["start"]["streamSid"]
                logger.info(f"# [EVENT] Start SID: {self.stream_sid}")
            elif event == "media":
                if self.stream_sid:
                    await self.gemini_service.send_audio_frame(
                        google_session, data["media"]["payload"]
                    )
            elif event == "stop":
                logger.info("# [EVENT] Stop received.")
                break

    async def stream_from_google(self, twilio_ws, google_session):
        async for mu_law_payload in self.gemini_service.listen_to_ai(google_session):
            if self.stream_sid:
                response = {
                    "event": "media",
                    "streamSid": self.stream_sid,
                    "media": {"payload": mu_law_payload}
                }
                await twilio_ws.send(json.dumps(response))

async def main():
    bridge = UniversalVoiceBridge()
    stop_signal = asyncio.Future()
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: stop_signal.set_result(None))

    async with websockets.serve(bridge.handle_connection, "0.0.0.0", 8081):
        logger.info("# [READY] Sidecar Bridge operational on port 8081.")
        await stop_signal

if __name__ == "__main__":
    asyncio.run(main())
