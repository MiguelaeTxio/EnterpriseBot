# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/voice_sidecar_bridge.py

import os
import json
import asyncio
import logging
import websockets
import django
from django.conf import settings

# 1. DJANGO BOOTSTRAP
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "enterprise_core.settings")
django.setup()

from vox_bridge.services import GeminiStreamService

# Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s # [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("VoiceSidecar")


class UniversalVoiceBridge:
    def __init__(self):
        self.gemini_service = GeminiStreamService()
        self.stream_sid = None

    async def handle_connection(self, twilio_ws):
        logger.info("# [CONN] New connection request from Twilio.")

        try:
            async with await self.gemini_service.connect() as google_session:
                logger.info("# [CONN] Gemini Live session fully established.")

                # ⚠️ FIX IMPORTANTE: manejar cancelación correcta
                uplink = asyncio.create_task(
                    self.stream_to_google(twilio_ws, google_session)
                )
                downlink = asyncio.create_task(
                    self.stream_from_google(twilio_ws, google_session)
                )

                done, pending = await asyncio.wait(
                    [uplink, downlink],
                    return_when=asyncio.FIRST_COMPLETED
                )

                # Cancelar lo que quede vivo
                for task in pending:
                    task.cancel()

        except websockets.exceptions.ConnectionClosed:
            logger.warning("# [CONN] Twilio WebSocket closed.")
        except Exception as e:
            logger.error(f"# [CRITICAL] Session Orchestration Error: {str(e)}")

    async def stream_to_google(self, twilio_ws, google_session):
        try:
            async for message in twilio_ws:
                data = json.loads(message)
                event = data.get("event")

                if event == "start":
                    self.stream_sid = data["start"]["streamSid"]
                    call_sid = data["start"]["callSid"]

                    logger.info(
                        f"# [EVENT] Media Stream Started. SID: {self.stream_sid} | Call: {call_sid}"
                    )

                elif event == "media":
                    if not self.stream_sid:
                        continue

                    payload_b64 = data["media"]["payload"]

                    await self.gemini_service.send_audio_frame(
                        google_session,
                        payload_b64
                    )

                elif event == "stop":
                    logger.info(
                        f"# [EVENT] Media Stream Stopped. SID: {self.stream_sid}"
                    )
                    break

        except Exception as e:
            logger.error(f"# [UPLINK ERROR] {str(e)}")

    async def stream_from_google(self, twilio_ws, google_session):
        try:
            async for mu_law_payload in self.gemini_service.listen_to_ai(google_session):

                if not self.stream_sid:
                    continue

                response_event = {
                    "event": "media",
                    "streamSid": self.stream_sid,  # ✅ FIX: camelCase correcto
                    "media": {
                        "payload": mu_law_payload
                    }
                }

                await twilio_ws.send(json.dumps(response_event))

        except Exception as e:
            logger.error(f"# [DOWNLINK ERROR] {str(e)}")


async def main():
    bridge = UniversalVoiceBridge()

    port = 8081

    async with websockets.serve(
        bridge.handle_connection,
        "0.0.0.0",
        port,
        ping_interval=20,
        ping_timeout=20
    ):
        logger.info(f"# [READY] EnterpriseBot Bridge listening on port {port}")
        await asyncio.Future()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("# [EXIT] Sidecar Bridge terminated by user.")