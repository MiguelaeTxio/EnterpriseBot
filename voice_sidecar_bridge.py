# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/voice_sidecar_bridge.py
import os
import json
import asyncio
import logging
import signal
from aiohttp import web
import django

"""
EnterpriseBot Universal Hybrid Bridge (Standard April 2026).
Exclusively uses aiohttp to handle Twilio's POST (TwiML) and GET (WebSocket) dual handshake.
This eliminates the 'unsupported HTTP method' error by separating concerns via routing.
---
Puente Híbrido Universal de EnterpriseBot (Estándar Abril 2026).
Usa exclusivamente aiohttp para gestionar el handshake dual de Twilio: POST (TwiML) y GET (WebSocket).
Esto elimina el error de 'método HTTP no soportado' separando responsabilidades vía enrutamiento.
"""

# Django Environment Initialization / Inicialización del Entorno Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "enterprise_core.settings")
django.setup()

from vox_bridge.services import GeminiStreamService

# Advanced Logging Configuration / Configuración de Registro Avanzada
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s # [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("VoiceSidecar")

class UniversalVoiceBridge:
    """
    Core Bridge using aiohttp for high-concurrency voice streaming.
    ---
    Puente núcleo usando aiohttp para streaming de voz de alta concurrencia.
    """
    def __init__(self):
        self.gemini_service = GeminiStreamService()

    async def handle_twiml_post(self, request):
        """
        Handles initial POST from Twilio. Returns TwiML pointing to the WSS path.
        ---
        Gestiona el POST inicial de Twilio. Devuelve TwiML apuntando a la ruta WSS.
        """
        logger.info("# [HTTP POST] Recibida petición inicial de Twilio. Generando TwiML.")
        host = request.host
        # The WebSocket upgrade path is explicitly defined as /media
        wss_url = f"wss://{host}/media"
        
        twiml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Response>'
            '    <Connect>'
            f'        <Stream url="{wss_url}" />'
            '    </Connect>'
            '</Response>'
        )
        return web.Response(text=twiml, content_type='text/xml')

    async def handle_websocket_stream(self, request):
        """
        Processes the WebSocket upgrade for binary audio streaming.
        ---
        Procesa la actualización WebSocket para streaming de audio binario.
        """
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        
        logger.info("# [WSS] Conexión de audio establecida en /media.")
        stream_sid = None

        try:
            # AI Session Initialization / Inicialización de la sesión de IA
            async with await self.gemini_service.connect() as google_session:
                logger.info("# [SDK] Handshake de Gemini 2.0 Flash completado.")

                async def stream_to_google():
                    nonlocal stream_sid
                    async for msg in ws:
                        if msg.type == web.WSMsgType.TEXT:
                            data = json.loads(msg.data)
                            event = data.get("event")
                            
                            if event == "start":
                                stream_sid = data["start"].get("streamSid") or data["start"].get("stream_sid")
                                call_sid = data["start"].get("callSid") or data["start"].get("call_sid")
                                logger.info(f"# [EVENT] Stream Activo: {stream_sid}")
                                await self.gemini_service.send_initial_greeting(google_session, call_sid)
                                
                            elif event == "media":
                                if stream_sid:
                                    await self.gemini_service.send_audio_frame(google_session, data["media"]["payload"])
                                    
                            elif event == "stop":
                                break
                        elif msg.type == web.WSMsgType.CLOSED:
                            break

                async def stream_from_google():
                    async for mu_law_payload in self.gemini_service.listen_to_ai(google_session):
                        if stream_sid and not ws.closed:
                            response = {
                                "event": "media",
                                "streamSid": stream_sid,
                                "media": {"payload": mu_law_payload}
                            }
                            await ws.send_str(json.dumps(response))

                await asyncio.gather(stream_to_google(), stream_from_google())

        except Exception as e:
            logger.error(f"# [ERROR] Fallo en el flujo: {str(e)}")
        finally:
            logger.info("# [WSS] Cerrando conexión.")
            return ws

async def main():
    bridge = UniversalVoiceBridge()
    app = web.Application()
    
    # Separation of paths to avoid method conflicts
    app.router.add_post('/api/vox/inbound/', bridge.handle_twiml_post)
    app.router.add_get('/media', bridge.handle_websocket_stream)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 8081)
    
    logger.info("# [READY] Puente HÍBRIDO (aiohttp) activo en puerto 8081.")
    await site.start()
    
    stop_event = asyncio.Event()
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop_event.set)
    await stop_event.wait()
    await runner.cleanup()

if __name__ == "__main__":
    asyncio.run(main())
