# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/test_bridge_locally.py
import asyncio
import aiohttp
import json
import logging

"""
Twilio Mock Emulator (April 2026).
Validates the Hybrid Bridge handshake (POST + WSS) and AI connectivity at zero cost.
---
Emulador Mock de Twilio (Abril 2026).
Valida el handshake del Puente Híbrido (POST + WSS) y la conectividad de IA a coste cero.
"""

logging.basicConfig(level=logging.INFO, format='# [SIM] %(message)s')
logger = logging.getLogger("TwilioMock")

async def simulate_interaction():
    # Targets the local bridge on port 8081.
    base_url = "http://127.0.0.1:8081"
    
    async with aiohttp.ClientSession() as session:
        logger.info("Paso 1: Iniciando HTTP POST Handshake (TwiML Request)...")
        async with session.post(f"{base_url}/api/vox/inbound/") as resp:
            if resp.status == 200:
                twiml = await resp.text()
                logger.info(f"ÉXITO: TwiML recibido. Handshake HTTP OK.")
            else:
                logger.error(f"FALLO: El Bridge respondió con status {resp.status}")
                return

        logger.info("Paso 2: Intentando Upgrade a WebSocket (/media)...")
        try:
            async with session.ws_connect(f"{base_url}/media") as ws:
                logger.info("ÉXITO: Conexión WebSocket establecida.")
                
                # Sending the initial 'start' event as Twilio would.
                start_payload = {
                    "event": "start",
                    "start": {
                        "streamSid": "test_stream_001",
                        "callSid": "test_call_001",
                        "accountSid": "test_account"
                    }
                }
                await ws.send_str(json.dumps(start_payload))
                logger.info("Evento 'start' enviado. Esperando respuesta de Gemini 2.0 Flash...")

                # Await AI response (Media or Text) with 15s timeout.
                try:
                    msg = await asyncio.wait_for(ws.receive(), timeout=15.0)
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        data = json.loads(msg.data)
                        if data.get("event") == "media":
                            logger.info("!!! ÉXITO TOTAL !!!: Payload de audio recibido de la IA.")
                            logger.info("La anidación de VoiceConfig es correcta y el Bridge es estable.")
                        else:
                            logger.warning(f"Recibido evento inesperado: {data.get('event')}")
                except asyncio.TimeoutError:
                    logger.error("FALLO: La IA no respondió. Posible error interno en Services.")
        except Exception as e:
            logger.error(f"FALLO: Error en la conexión WS: {str(e)}")

if __name__ == "__main__":
    asyncio.run(simulate_interaction())
