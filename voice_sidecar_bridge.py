# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/voice_sidecar_bridge.py
"""
EnterpriseBot Universal Hybrid Bridge (Standard April 2026).

Uses aiohttp exclusively to handle Twilio's dual HTTP handshake:
    - POST /api/vox/inbound/  → TwiML response pointing to the WSS stream path.
    - GET  /media             → WebSocket upgrade for binary audio streaming.

This separation of concerns eliminates the 'unsupported HTTP method' conflict
that arises when a single route attempts to serve both HTTP and WebSocket traffic.

Session lifecycle ownership:
    This bridge layer delegates the complete Gemini Live session lifecycle to
    VoiceOrchestrationService.run_voice_session(). The service internally owns
    the canonical SDK 1.69.0 async context manager:

        async with client.aio.live.connect(model=..., config=...) as session

    Entry into that context manager guarantees the WebSocket handshake with
    Google's infrastructure is complete and the session is ready to accept data.
    No setup_complete event polling is performed anywhere in this stack.

Inbound audio delivery:
    Each Twilio 'media' event is forwarded to
    VoiceOrchestrationService.receive_twilio_audio() which decodes the
    base64 mu-law payload, transcodes it to PCM 16kHz, and places it onto
    the internal asyncio.Queue consumed by the Gemini sender coroutine.

Session termination:
    The Twilio 'stop' event triggers VoiceOrchestrationService.terminate_session(),
    which sets session_active = False, causing all concurrent coroutines to drain
    and exit gracefully.

Usage:
    Launched by voice_orchestrator.py as a subprocess:
        python voice_sidecar_bridge.py
---
Puente Híbrido Universal de EnterpriseBot (Estándar Abril 2026).

Usa aiohttp exclusivamente para gestionar el doble handshake HTTP de Twilio:
    - POST /api/vox/inbound/  → Respuesta TwiML apuntando a la ruta WSS de stream.
    - GET  /media             → Actualización WebSocket para streaming de audio binario.

Esta separación de responsabilidades elimina el conflicto de 'método HTTP no soportado'
que surge cuando una sola ruta intenta servir tanto tráfico HTTP como WebSocket.

Propiedad del ciclo de vida de la sesión:
    Esta capa bridge delega el ciclo de vida completo de la sesión Gemini Live en
    VoiceOrchestrationService.run_voice_session(). El servicio es internamente
    propietario del context manager asíncrono canónico del SDK 1.69.0:

        async with client.aio.live.connect(model=..., config=...) as session

    La entrada en ese context manager garantiza que el handshake WebSocket con la
    infraestructura de Google está completo y la sesión está lista para aceptar datos.
    No se realiza sondeo de ningún evento setup_complete en ningún punto de esta pila.

Entrega de audio entrante:
    Cada evento 'media' de Twilio se reenvía a
    VoiceOrchestrationService.receive_twilio_audio(), que decodifica el payload
    mu-law en base64, lo transcodifica a PCM 16kHz y lo coloca en la
    asyncio.Queue interna consumida por la corrutina emisora de Gemini.

Terminación de sesión:
    El evento 'stop' de Twilio activa VoiceOrchestrationService.terminate_session(),
    que establece session_active = False, haciendo que todas las corrutinas
    concurrentes drenen y salgan de forma elegante.

Uso:
    Lanzado por voice_orchestrator.py como subproceso:
        python voice_sidecar_bridge.py
"""

import asyncio
import json
import logging
import os
import signal

import django
from aiohttp import web

# ---------------------------------------------------------------------------
# DJANGO ENVIRONMENT INITIALIZATION / INICIALIZACIÓN DEL ENTORNO DJANGO
# ---------------------------------------------------------------------------
# Must be performed before any Django model or app import.
# Debe realizarse antes de cualquier importación de modelo o app de Django.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "enterprise_core.settings")
django.setup()

from vox_bridge.services import VoiceOrchestrationService

# ---------------------------------------------------------------------------
# LOGGING CONFIGURATION / CONFIGURACIÓN DE LOGGING
# ---------------------------------------------------------------------------
# Structured logging with timestamp and level for PythonAnywhere console output.
# Logging estructurado con marca de tiempo y nivel para la salida de consola
# de PythonAnywhere.
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s # [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("VoiceSidecar")


# ---------------------------------------------------------------------------
# UNIVERSAL VOICE BRIDGE / PUENTE DE VOZ UNIVERSAL
# ---------------------------------------------------------------------------

class UniversalVoiceBridge:
    """
    Core bridge using aiohttp for high-concurrency voice streaming between
    Twilio Media Streams and the Gemini 3.1 Live API.

    Responsibilities:
        - Serve TwiML via HTTP POST to instruct Twilio to open a Media Stream.
        - Accept the WebSocket upgrade from Twilio via HTTP GET.
        - Instantiate a fresh VoiceOrchestrationService per call to guarantee
          complete per-call isolation of asyncio queues and session state.
        - Delegate the full Gemini Live session lifecycle to
          VoiceOrchestrationService.run_voice_session(), which internally owns
          the SDK 1.69.0 canonical async context manager.
        - Forward each incoming Twilio 'media' event to
          VoiceOrchestrationService.receive_twilio_audio() for decoding and
          transcoding before queuing to the Gemini sender coroutine.
        - Signal session termination to VoiceOrchestrationService via
          terminate_session() upon receiving the Twilio 'stop' event.
    ---
    Puente núcleo usando aiohttp para streaming de voz de alta concurrencia entre
    Twilio Media Streams y la API Gemini 3.1 Live.

    Responsabilidades:
        - Servir TwiML vía HTTP POST para instruir a Twilio a abrir un Media Stream.
        - Aceptar la actualización WebSocket de Twilio vía HTTP GET.
        - Instanciar un VoiceOrchestrationService fresco por llamada para garantizar
          el aislamiento completo por llamada de las colas asyncio y el estado de sesión.
        - Delegar el ciclo de vida completo de la sesión Gemini Live en
          VoiceOrchestrationService.run_voice_session(), que internamente es propietario
          del context manager asíncrono canónico del SDK 1.69.0.
        - Reenviar cada evento 'media' entrante de Twilio a
          VoiceOrchestrationService.receive_twilio_audio() para decodificación y
          transcodificación antes de encolar en la corrutina emisora de Gemini.
        - Señalizar la terminación de sesión a VoiceOrchestrationService vía
          terminate_session() al recibir el evento 'stop' de Twilio.
    """

    async def handle_twiml_post(self, request: web.Request) -> web.Response:
        """
        Handles the initial HTTP POST from Twilio when a call is connected.

        Reads the active ngrok public URL from the shared session file
        (DOCS/SESSION/NGROK_URL.txt) and returns a TwiML <Connect><Stream>
        response pointing Twilio to the WSS WebSocket endpoint at /media.

        DESTINATION NUMBER CAPTURE (2026-04-11):
            The Twilio Media Streams WebSocket 'start' event does NOT carry
            the destination phone number ('To') in its payload — confirmed by
            the DEBUG-P28 diagnostic. The number is exclusively available here,
            in the initial HTTP POST body sent by Twilio before the WebSocket
            is opened. It is captured and stored in self._pending_twilio_number
            so handle_websocket_stream() can pass it to VoiceOrchestrationService
            when instantiating the service upon receiving the 'start' event.

        Args:
            request (web.Request): The incoming aiohttp HTTP request from Twilio.

        Returns:
            web.Response: A TwiML XML response with Content-Type text/xml.
        ---
        Gestiona el HTTP POST inicial de Twilio cuando una llamada se conecta.

        Lee la URL pública activa de ngrok desde el archivo de sesión compartido
        (DOCS/SESSION/NGROK_URL.txt) y devuelve una respuesta TwiML <Connect><Stream>
        apuntando a Twilio al endpoint WebSocket WSS en /media.

        CAPTURA DEL NÚMERO DESTINO (2026-04-11):
            El evento 'start' del WebSocket de Twilio Media Streams NO transporta
            el número de teléfono destino ('To') en su payload — confirmado por
            el diagnóstico DEBUG-P28. El número está disponible exclusivamente aquí,
            en el body del POST HTTP inicial enviado por Twilio antes de abrir el
            WebSocket. Se captura y almacena en self._pending_twilio_number para
            que handle_websocket_stream() pueda pasarlo a VoiceOrchestrationService
            al instanciar el servicio al recibir el evento 'start'.

        Args:
            request (web.Request): La petición HTTP aiohttp entrante de Twilio.

        Returns:
            web.Response: Una respuesta XML TwiML con Content-Type text/xml.
        """
        logger.info("# [HTTP POST] Petición inicial de Twilio recibida. Generando TwiML.")

        # --- Capture destination phone number from POST body ---
        # Twilio sends the call parameters as application/x-www-form-urlencoded.
        # The 'To' field contains the E.164 number that received the inbound call.
        # This is the only point in the Media Streams pipeline where this number
        # is available — it does NOT appear in the WebSocket 'start' event payload.
        # --- Capturar número de teléfono destino del body del POST ---
        # Twilio envía los parámetros de la llamada como application/x-www-form-urlencoded.
        # El campo 'To' contiene el número E.164 que recibió la llamada entrante.
        # Este es el único punto del pipeline de Media Streams donde este número
        # está disponible — NO aparece en el payload del evento 'start' del WebSocket.
        try:
            post_data = await request.post()
            twilio_number = post_data.get("To", "")
            if twilio_number:
                logger.info(
                    f"# [HTTP POST] Número destino capturado del POST: {twilio_number}"
                )
            else:
                logger.warning(
                    "# [HTTP POST] Campo 'To' ausente en el body del POST de Twilio. "
                    "VoiceOrchestrationService usará configuración de fallback."
                )
        except Exception as post_exc:
            logger.error(
                f"# [HTTP POST] Error al leer body del POST: {post_exc}. "
                "Usando cadena vacía como número destino."
            )
            twilio_number = ""

        # Store the captured number so handle_websocket_stream() can access it
        # when the WebSocket 'start' event arrives for this call.
        # Almacenar el número capturado para que handle_websocket_stream() pueda
        # acceder a él cuando llegue el evento 'start' del WebSocket para esta llamada.
        self._pending_twilio_number = twilio_number

        # Derive the WSS URL from the request host header so that the TwiML
        # always points to the correct tunnel regardless of the ngrok session.
        # The /media path is the registered WebSocket upgrade endpoint.
        # Derivar la URL WSS desde la cabecera host de la petición para que el
        # TwiML siempre apunte al túnel correcto independientemente de la sesión ngrok.
        # La ruta /media es el endpoint de actualización WebSocket registrado.
        host = request.host
        wss_url = f"wss://{host}/media"

        twiml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            "<Response>"
            "    <Connect>"
            f'        <Stream url="{wss_url}" />'
            "    </Connect>"
            "</Response>"
        )

        logger.info(f"# [HTTP POST] TwiML generado. WSS target: {wss_url}")
        return web.Response(text=twiml, content_type="text/xml")

    async def handle_websocket_stream(self, request: web.Request) -> web.WebSocketResponse:
        """
        Handles the WebSocket upgrade request from Twilio Media Streams.

        A fresh VoiceOrchestrationService is instantiated per call to guarantee
        complete isolation of asyncio.Queue state and session_active flag between
        consecutive calls handled by the same bridge process.

        The Gemini Live session lifecycle is delegated entirely to
        VoiceOrchestrationService.run_voice_session(), launched as a concurrent
        asyncio Task alongside the Twilio event reader loop.

        Twilio event handling:
            'start'  — stores streamSid on the service via set_stream_sid()
                       (mandatory for Twilio bidirectional Media Streams protocol)
                       and logs stream and call SIDs for traceability.
            'media'  — forwards the raw JSON payload to receive_twilio_audio()
                       for mu-law decoding and PCM transcoding.
            'stop'   — calls terminate_session() and breaks the reader loop.

        Args:
            request (web.Request): The incoming aiohttp WebSocket upgrade request.

        Returns:
            web.WebSocketResponse: The prepared WebSocket response object.
        ---
        Gestiona la petición de actualización WebSocket de Twilio Media Streams.

        Se instancia un VoiceOrchestrationService fresco por llamada para garantizar
        el aislamiento completo del estado asyncio.Queue y el flag session_active entre
        llamadas consecutivas gestionadas por el mismo proceso bridge.

        El ciclo de vida de la sesión Gemini Live se delega completamente en
        VoiceOrchestrationService.run_voice_session(), lanzado como una Task asyncio
        concurrente junto al bucle lector de eventos de Twilio.

        Gestión de eventos de Twilio:
            'start'  — almacena el streamSid en el servicio mediante set_stream_sid()
                       (obligatorio para el protocolo bidireccional de Twilio Media
                       Streams) y registra los SIDs de stream y llamada para
                       trazabilidad.
            'media'  — reenvía el payload JSON bruto a receive_twilio_audio()
                       para decodificación mu-law y transcodificación PCM.
            'stop'   — llama a terminate_session() y rompe el bucle lector.

        Args:
            request (web.Request): La petición de actualización WebSocket aiohttp entrante.

        Returns:
            web.WebSocketResponse: El objeto de respuesta WebSocket preparado.
        """
        ws = web.WebSocketResponse()
        await ws.prepare(request)

        logger.info("# [WSS] Conexión WebSocket establecida en /media.")

        # SERVICE INSTANTIATION DEFERRED TO 'start' EVENT:
        # VoiceOrchestrationService requires the Twilio 'To' number (E.164) to
        # load the dynamic IVR configuration via build_live_config(). This number
        # is only available in the Twilio 'start' WebSocket event payload, not at
        # WebSocket upgrade time. Therefore, both the service instantiation and the
        # voice_task launch are deferred until the 'start' event is received.
        # voice_task is initialised to None here and assigned inside the 'start'
        # handler; all subsequent event handlers guard against voice_task being None.
        #
        # INSTANCIACIÓN DEL SERVICIO DIFERIDA AL EVENTO 'start':
        # VoiceOrchestrationService requiere el número Twilio 'To' (E.164) para
        # cargar la configuración IVR dinámica mediante build_live_config(). Este
        # número solo está disponible en el payload del evento WebSocket 'start' de
        # Twilio, no en el momento de la actualización WebSocket. Por tanto, tanto
        # la instanciación del servicio como el lanzamiento de voice_task se difieren
        # hasta que se recibe el evento 'start'. voice_task se inicializa a None aquí
        # y se asigna dentro del manejador de 'start'; todos los manejadores de eventos
        # posteriores protegen contra voice_task siendo None.
        service: VoiceOrchestrationService | None = None
        voice_task: asyncio.Task | None = None

        try:
            # Twilio WebSocket event reader loop.
            # Bucle lector de eventos WebSocket de Twilio.
            async for msg in ws:

                if msg.type == web.WSMsgType.TEXT:
                    data = json.loads(msg.data)
                    event = data.get("event")

                    if event == "start":
                        # Extract stream and call identifiers from the Twilio
                        # 'start' event payload. Both camelCase (streamSid,
                        # callSid) and snake_case variants are checked for
                        # forward compatibility with Twilio API changes.
                        # Extraer los identificadores de stream y llamada del
                        # payload del evento 'start' de Twilio. Se comprueban
                        # tanto las variantes camelCase (streamSid, callSid)
                        # como snake_case para compatibilidad futura con cambios
                        # en la API de Twilio.
                        start_payload = data.get("start", {})

                        stream_sid = (
                            start_payload.get("streamSid")
                            or start_payload.get("stream_sid")
                        )
                        call_sid = (
                            start_payload.get("callSid")
                            or start_payload.get("call_sid")
                        )

                        # DESTINATION NUMBER RESOLUTION (2026-04-11 — Paso 28 closed):
                        # The Twilio Media Streams 'start' event does NOT carry the
                        # destination number ('To') in its payload — confirmed by the
                        # DEBUG-P28 diagnostic. The number was captured from the initial
                        # HTTP POST body in handle_twiml_post() and stored in
                        # self._pending_twilio_number. It is consumed here once and
                        # reset to empty string to prevent stale values leaking into
                        # subsequent calls handled by the same bridge process.
                        #
                        # RESOLUCIÓN DEL NÚMERO DESTINO (2026-04-11 — Paso 28 cerrado):
                        # El evento 'start' de Twilio Media Streams NO transporta el
                        # número destino ('To') en su payload — confirmado por el
                        # diagnóstico DEBUG-P28. El número fue capturado del body del
                        # POST HTTP inicial en handle_twiml_post() y almacenado en
                        # self._pending_twilio_number. Se consume aquí una única vez y
                        # se resetea a cadena vacía para evitar que valores obsoletos
                        # contaminen llamadas posteriores gestionadas por el mismo proceso.
                        twilio_number = getattr(self, "_pending_twilio_number", "")
                        self._pending_twilio_number = ""

                        if twilio_number:
                            logger.info(
                                f"# [EVENT] Número Twilio receptor resuelto desde "
                                f"POST HTTP: {twilio_number}"
                            )
                        else:
                            logger.warning(
                                "# [EVENT] Número Twilio destino no disponible "
                                "(campo 'To' ausente en el POST inicial). "
                                "VoiceOrchestrationService usará la configuración "
                                "de fallback hardcodeada (SYSTEM_INSTRUCTION_FALLBACK)."
                            )

                        # Instantiate a fresh VoiceOrchestrationService per call,
                        # passing the resolved Twilio number so that build_live_config()
                        # can load the dynamic IVR configuration from the database.
                        # Each call gets its own asyncio.Queue instances and a clean
                        # session_active flag, preventing state bleed between consecutive
                        # calls handled by the same bridge process.
                        # Instanciar un VoiceOrchestrationService fresco por llamada,
                        # pasando el número Twilio resuelto para que build_live_config()
                        # pueda cargar la configuración IVR dinámica desde la base de datos.
                        # Cada llamada obtiene sus propias instancias de asyncio.Queue y
                        # un flag session_active limpio, evitando contaminación de estado
                        # entre llamadas consecutivas gestionadas por el mismo proceso bridge.
                        service = VoiceOrchestrationService(twilio_number=twilio_number)

                        # Launch run_voice_session as a concurrent asyncio Task.
                        # This task owns the Gemini Live session lifecycle via the SDK
                        # context manager and runs concurrently with the Twilio event
                        # reader loop below.
                        # Lanzar run_voice_session como una Task asyncio concurrente.
                        # Esta tarea es propietaria del ciclo de vida de la sesión Gemini
                        # Live mediante el context manager del SDK y se ejecuta
                        # concurrentemente con el bucle lector de eventos de Twilio.
                        voice_task = asyncio.ensure_future(service.run_voice_session(ws))

                        # Store the streamSid on the service instance.
                        # This is MANDATORY for the Twilio Media Streams bidirectional
                        # protocol: every outbound 'media' message must include 'streamSid'
                        # at the root level. Omitting it causes Warning 31951 and silent
                        # audio discard on Twilio's side.
                        # Almacenar el streamSid en la instancia del servicio.
                        # Esto es OBLIGATORIO para el protocolo bidireccional de Twilio
                        # Media Streams: cada mensaje 'media' saliente debe incluir
                        # 'streamSid' en el nivel raíz. Su omisión provoca el Warning
                        # 31951 y el descarte silencioso del audio en el lado de Twilio.
                        if stream_sid:
                            service.set_stream_sid(stream_sid)
                        else:
                            logger.warning(
                                "# [EVENT] Evento 'start' recibido sin streamSid. "
                                "Los mensajes 'media' salientes no incluirán streamSid "
                                "y podrían ser descartados por Twilio (Warning 31951)."
                            )

                        logger.info(
                            f"# [EVENT] Stream iniciado — streamSid: {stream_sid} | "
                            f"callSid: {call_sid}"
                        )

                    elif event == "media":
                        # Forward the raw JSON payload to the service for mu-law
                        # decoding, PCM transcoding, and queuing to Gemini.
                        # Guard against receiving 'media' before 'start' (should not
                        # happen per Twilio protocol but defensive programming applies).
                        # Reenviar el payload JSON bruto al servicio para decodificación
                        # mu-law, transcodificación PCM y encolado a Gemini.
                        # Proteger contra la recepción de 'media' antes de 'start' (no
                        # debería ocurrir según el protocolo de Twilio, pero aplica
                        # programación defensiva).
                        if service is not None:
                            await service.receive_twilio_audio(msg.data)
                        else:
                            logger.warning(
                                "# [EVENT] Evento 'media' recibido antes del evento "
                                "'start'. Fragmento de audio descartado."
                            )

                    elif event == "stop":
                        # The caller has hung up. Signal the service to terminate
                        # all concurrent coroutines gracefully.
                        # El llamante ha colgado. Señalizar al servicio para que
                        # termine todas las corrutinas concurrentes de forma elegante.
                        logger.info("# [EVENT] Evento 'stop' recibido de Twilio.")
                        if service is not None:
                            service.terminate_session()
                        break

                    else:
                        # Log unhandled event types for diagnostic traceability.
                        # Registrar tipos de eventos no gestionados para trazabilidad diagnóstica.
                        logger.debug(f"# [EVENT] Evento no gestionado recibido: {event}")

                elif msg.type == web.WSMsgType.CLOSED:
                    logger.info("# [WSS] WebSocket cerrado por Twilio.")
                    if service is not None:
                        service.terminate_session()
                    break

                elif msg.type == web.WSMsgType.ERROR:
                    logger.error(
                        f"# [WSS] Error en el WebSocket de Twilio: {ws.exception()}"
                    )
                    if service is not None:
                        service.terminate_session()
                    break

        except Exception as exc:
            logger.error(
                f"# [WSS] Error inesperado en el bucle de eventos de Twilio: {exc}",
                exc_info=True,
            )
            if service is not None:
                service.terminate_session()

        finally:
            # Ensure the voice task is cancelled if the WebSocket closes before
            # the session completes naturally. Guard against voice_task being None
            # in the edge case where the WebSocket closes before 'start' is received.
            # Asegurar que la tarea de voz se cancela si el WebSocket se cierra antes
            # de que la sesión se complete de forma natural. Proteger contra voice_task
            # siendo None en el caso extremo de que el WebSocket se cierre antes de
            # recibir el evento 'start'.
            if voice_task is not None and not voice_task.done():
                voice_task.cancel()
                try:
                    await voice_task
                except asyncio.CancelledError:
                    logger.info("# [WSS] Tarea de sesión de voz cancelada correctamente.")

            logger.info("# [WSS] Conexión WebSocket finalizada.")

        return ws


# ---------------------------------------------------------------------------
# APPLICATION ENTRY POINT / PUNTO DE ENTRADA DE LA APLICACIÓN
# ---------------------------------------------------------------------------

async def main() -> None:
    """
    Application entry point. Configures aiohttp routing and starts the TCP server
    on port 8081.

    Routes:
        POST /api/vox/inbound/  → handle_twiml_post
        GET  /media             → handle_websocket_stream

    Signal handling:
        SIGINT and SIGTERM trigger a clean shutdown via asyncio.Event.
    ---
    Punto de entrada de la aplicación. Configura el enrutamiento aiohttp e inicia
    el servidor TCP en el puerto 8081.

    Rutas:
        POST /api/vox/inbound/  → handle_twiml_post
        GET  /media             → handle_websocket_stream

    Gestión de señales:
        SIGINT y SIGTERM activan un apagado limpio vía asyncio.Event.
    """
    bridge = UniversalVoiceBridge()
    app = web.Application()

    # Separation of HTTP method concerns via distinct route paths.
    # This eliminates the 'unsupported HTTP method' error that occurs when a
    # single route attempts to serve both POST (TwiML) and GET (WebSocket) traffic.
    # Separación de responsabilidades de método HTTP mediante rutas distintas.
    # Esto elimina el error de 'método HTTP no soportado' que ocurre cuando una
    # sola ruta intenta servir tanto tráfico POST (TwiML) como GET (WebSocket).
    app.router.add_post("/api/vox/inbound/", bridge.handle_twiml_post)
    app.router.add_get("/media", bridge.handle_websocket_stream)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 8081)
    await site.start()

    logger.info("# [READY] Puente HÍBRIDO (aiohttp) activo en puerto 8081.")

    # Graceful shutdown via OS signal handling.
    # Apagado elegante mediante gestión de señales del SO.
    stop_event = asyncio.Event()
    # PYTHON 3.10+ FIX: asyncio.get_event_loop() is deprecated inside a coroutine
    # launched by asyncio.run() — it may return a different loop or block indefinitely.
    # asyncio.get_running_loop() is the correct call inside a running coroutine.
    # CORRECCIÓN PYTHON 3.10+: asyncio.get_event_loop() está deprecado dentro de una
    # corrutina lanzada por asyncio.run() — puede devolver un loop diferente o bloquearse
    # indefinidamente. asyncio.get_running_loop() es la llamada correcta dentro de una
    # corrutina en ejecución.
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop_event.set)

    await stop_event.wait()
    logger.info("# [SHUTDOWN] Señal de apagado recibida. Limpiando recursos...")
    await runner.cleanup()
    logger.info("# [SHUTDOWN] Puente detenido correctamente.")


if __name__ == "__main__":
    asyncio.run(main())
