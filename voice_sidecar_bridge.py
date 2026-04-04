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
ARCHITECTURAL FIX APRIL 2026: The Gemini Live session context manager is now owned
by this bridge layer using the canonical SDK 1.69.0 pattern:
    async with service.client.aio.live.connect(
        model=service.model_id, config=service.build_live_config()
    ) as session
The previous anti-pattern of awaiting connect() before async with is eliminated.
reset_session_state() is called before each new connection to ensure per-call isolation.
---
Puente Híbrido Universal de EnterpriseBot (Estándar Abril 2026).
Usa exclusivamente aiohttp para gestionar el handshake dual de Twilio: POST (TwiML) y GET (WebSocket).
Esto elimina el error de 'método HTTP no soportado' separando responsabilidades vía enrutamiento.
CORRECCIÓN ARQUITECTÓNICA ABRIL 2026: El context manager de sesión Gemini Live es ahora
propiedad de esta capa bridge usando el patrón canónico del SDK 1.69.0:
    async with service.client.aio.live.connect(
        model=service.model_id, config=service.build_live_config()
    ) as session
El anti-patrón previo de awaiting connect() antes del async with queda eliminado.
reset_session_state() se llama antes de cada nueva conexión para garantizar el aislamiento por llamada.
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
    Owns the Gemini Live session lifecycle using the canonical SDK 1.69.0 async
    context manager pattern, ensuring correct Setup-First protocol execution.
    ---
    Puente núcleo usando aiohttp para streaming de voz de alta concurrencia.
    Es propietario del ciclo de vida de la sesión Gemini Live usando el patrón canónico
    de context manager asíncrono del SDK 1.69.0, asegurando la correcta ejecución
    del protocolo Setup-First.
    """

    def __init__(self):
        """
        Initializes a single GeminiStreamService instance shared across requests.
        reset_session_state() is called per-connection to ensure per-call isolation.
        ---
        Inicializa una única instancia de GeminiStreamService compartida entre peticiones.
        reset_session_state() se llama por conexión para garantizar el aislamiento por llamada.
        """
        self.gemini_service = GeminiStreamService()

    async def handle_twiml_post(self, request):
        """
        Handles initial POST from Twilio. Returns TwiML pointing to the WSS path.
        ---
        Gestiona el POST inicial de Twilio. Devuelve TwiML apuntando a la ruta WSS.
        """
        logger.info("# [HTTP POST] Recibida petición inicial de Twilio. Generando TwiML.")
        host = request.host
        # The WebSocket upgrade path is explicitly defined as /media.
        # La ruta de actualización WebSocket se define explícitamente como /media.
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
        Owns the Gemini Live session using the canonical SDK 1.69.0 async context manager.
        Calls reset_session_state() before each new connection to guarantee per-call
        isolation of DSP state and the Setup-First asyncio.Event.
        ---
        Procesa la actualización WebSocket para streaming de audio binario.
        Es propietario de la sesión Gemini Live usando el context manager asíncrono
        canónico del SDK 1.69.0. Llama a reset_session_state() antes de cada nueva
        conexión para garantizar el aislamiento por llamada del estado DSP y del
        asyncio.Event del protocolo Setup-First.
        """
        ws = web.WebSocketResponse()
        await ws.prepare(request)

        logger.info("# [WSS] Conexión de audio establecida en /media.")
        stream_sid = None

        # ✅ ARCHITECTURAL FIX APRIL 2026: Reset per-call state (DSP + setup_confirmed Event)
        # before opening a new Gemini Live session. This prevents a stale Event from bypassing
        # the Setup-First handshake on subsequent calls to the same service instance.
        # ---
        # ✅ CORRECCIÓN ARQUITECTÓNICA ABRIL 2026: Reiniciar el estado por llamada
        # (DSP + Event setup_confirmed) antes de abrir una nueva sesión Gemini Live.
        # Esto evita que un Event obsoleto omita el handshake Setup-First en llamadas
        # posteriores a la misma instancia del servicio.
        self.gemini_service.reset_session_state()

        try:
            # ✅ CANONICAL SDK 1.69.0 PATTERN (April 2026 official documentation):
            # The bridge owns the async context manager directly.
            # This replaces the previous anti-pattern:
            #     async with await self.gemini_service.connect() as google_session
            # which double-consumed the context manager before the server could send
            # setup_complete, causing the systematic handshake timeout.
            # ---
            # ✅ PATRÓN CANÓNICO SDK 1.69.0 (documentación oficial abril 2026):
            # El bridge es propietario del context manager asíncrono directamente.
            # Esto reemplaza el anti-patrón previo:
            #     async with await self.gemini_service.connect() as google_session
            # que consumía doblemente el context manager antes de que el servidor pudiera
            # enviar setup_complete, causando el timeout sistemático del handshake.
            config = self.gemini_service.build_live_config()

            async with self.gemini_service.client.aio.live.connect(
                model=self.gemini_service.model_id,
                config=config
            ) as google_session:

                logger.info("# [SDK] Sesión Gemini Live establecida. Esperando Setup-First.")

                async def stream_to_google():
                    """
                    Reads Twilio WebSocket events and forwards audio to Gemini Live.
                    Triggers send_initial_greeting on 'start' event after Setup-First confirmation.
                    ---
                    Lee los eventos WebSocket de Twilio y reenvía audio a Gemini Live.
                    Dispara send_initial_greeting en el evento 'start' tras la confirmación Setup-First.
                    """
                    nonlocal stream_sid
                    async for msg in ws:
                        if msg.type == web.WSMsgType.TEXT:
                            data = json.loads(msg.data)
                            event = data.get("event")

                            if event == "start":
                                # Extract stream and call identifiers from the Twilio start event.
                                # Extraer identificadores de stream y llamada del evento start de Twilio.
                                stream_sid = (
                                    data["start"].get("streamSid")
                                    or data["start"].get("stream_sid")
                                )
                                call_sid = (
                                    data["start"].get("callSid")
                                    or data["start"].get("call_sid")
                                )
                                logger.info(f"# [EVENT] Stream Activo: {stream_sid}")

                                # send_initial_greeting internally awaits self.setup_confirmed
                                # (set by listen_to_ai) before transmitting any data.
                                # This coroutine is launched as a background task to avoid
                                # blocking the Twilio event loop while waiting for the handshake.
                                # ---
                                # send_initial_greeting espera internamente self.setup_confirmed
                                # (activado por listen_to_ai) antes de transmitir cualquier dato.
                                # Esta corrutina se lanza como tarea en segundo plano para evitar
                                # bloquear el bucle de eventos de Twilio durante la espera del handshake.
                                asyncio.ensure_future(
                                    self.gemini_service.send_initial_greeting(
                                        google_session, call_sid
                                    )
                                )

                            elif event == "media":
                                # Audio frames are silently dropped by send_audio_frame if
                                # setup_confirmed is not yet set (Setup-First enforcement).
                                # ---
                                # Las tramas de audio son descartadas silenciosamente por
                                # send_audio_frame si setup_confirmed aún no está activo
                                # (imposición del protocolo Setup-First).
                                if stream_sid:
                                    await self.gemini_service.send_audio_frame(
                                        google_session, data["media"]["payload"]
                                    )

                            elif event == "stop":
                                logger.info("# [EVENT] Evento 'stop' recibido de Twilio.")
                                break

                        elif msg.type == web.WSMsgType.CLOSED:
                            logger.info("# [WSS] WebSocket cerrado por Twilio.")
                            break

                async def stream_from_google():
                    """
                    Receives audio responses from Gemini Live and forwards them to Twilio.
                    listen_to_ai sets setup_confirmed upon receiving setup_complete from the server.
                    ---
                    Recibe respuestas de audio de Gemini Live y las reenvía a Twilio.
                    listen_to_ai activa setup_confirmed al recibir setup_complete del servidor.
                    """
                    async for mu_law_payload in self.gemini_service.listen_to_ai(google_session):
                        if stream_sid and not ws.closed:
                            response = {
                                "event": "media",
                                "streamSid": stream_sid,
                                "media": {"payload": mu_law_payload}
                            }
                            await ws.send_str(json.dumps(response))

                # Both coroutines run concurrently:
                # - stream_from_google: receives server messages and sets setup_confirmed.
                # - stream_to_google: waits for start event, then launches greeting as background task.
                # This ordering guarantees listen_to_ai is already running when setup_complete arrives.
                # ---
                # Ambas corrutinas corren concurrentemente:
                # - stream_from_google: recibe mensajes del servidor y activa setup_confirmed.
                # - stream_to_google: espera el evento start y lanza el saludo como tarea en segundo plano.
                # Este orden garantiza que listen_to_ai ya está corriendo cuando llega setup_complete.
                await asyncio.gather(stream_to_google(), stream_from_google())

        except Exception as e:
            logger.error(f"# [ERROR] Fallo en el flujo de sesión: {str(e)}")
        finally:
            logger.info("# [WSS] Cerrando conexión WebSocket.")
            return ws


async def main():
    """
    Application entry point. Configures aiohttp routing and starts the TCP server.
    ---
    Punto de entrada de la aplicación. Configura el enrutamiento aiohttp e inicia el servidor TCP.
    """
    bridge = UniversalVoiceBridge()
    app = web.Application()

    # Separation of paths to avoid HTTP method conflicts between TwiML and WebSocket.
    # Separación de rutas para evitar conflictos de método HTTP entre TwiML y WebSocket.
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
