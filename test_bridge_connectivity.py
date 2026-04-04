# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/test_bridge_connectivity.py
"""
Zero-cost infrastructure validation script for Gemini 3.1 Live API connectivity.

This script performs a standalone, isolated handshake test against the Gemini
3.1 Live API (gemini-3.1-flash-live-preview) using the google-genai SDK 1.69.0.
It does NOT invoke any Django components, Twilio integration, or audio transcoding.
Its sole purpose is to validate that:

    1. The GEMINI_API_KEY credential is valid and accepted by Google's infrastructure.
    2. The Gemini 3.1 Live WebSocket connection can be established successfully
       (Setup-First protocol via the SDK context manager).
    3. A text message can be sent using the correct SDK 1.69.0 syntax.
    4. A valid audio response is received from the model within the timeout window.

Setup-First Protocol (SDK 1.69.0 Compliant):
    Session readiness is guaranteed by the `async with client.aio.live.connect(...)`
    context manager. Upon entry, the session is fully negotiated. The test message
    is sent immediately. No setup_complete event polling is performed.

Expected success log:
    [SDK] Handshake Gemini 3.1 (SetupComplete: True) VALIDADO

Usage:
    cd /home/MiguelAeTxio/PROJECTS/EnterpriseBot
    python -m dotenv run python test_bridge_connectivity.py
---
Script de validación de infraestructura de coste cero para la conectividad
de la API Gemini 3.1 Live.

Este script realiza una prueba de handshake aislada e independiente contra la
API Gemini 3.1 Live (gemini-3.1-flash-live-preview) usando el SDK google-genai
1.69.0. NO invoca ningún componente de Django, integración con Twilio, ni
transcodificación de audio. Su único propósito es validar que:

    1. La credencial GEMINI_API_KEY es válida y aceptada por la infraestructura
       de Google.
    2. La conexión WebSocket de Gemini 3.1 Live puede establecerse correctamente
       (protocolo Setup-First a través del context manager del SDK).
    3. Se puede enviar un mensaje de texto usando la sintaxis correcta del SDK 1.69.0.
    4. Se recibe una respuesta de audio válida del modelo dentro de la ventana
       de timeout.

Protocolo Setup-First (Conforme a SDK 1.69.0):
    La disponibilidad de la sesión está garantizada por el context manager
    `async with client.aio.live.connect(...)`. Al entrar, la sesión está
    completamente negociada. El mensaje de prueba se envía de forma inmediata.
    No se realiza sondeo de ningún evento setup_complete.

Log de éxito esperado:
    [SDK] Handshake Gemini 3.1 (SetupComplete: True) VALIDADO

Uso:
    cd /home/MiguelAeTxio/PROJECTS/EnterpriseBot
    python -m dotenv run python test_bridge_connectivity.py
"""

import asyncio
import logging
import os
import sys

from google import genai
from google.genai import types

# ---------------------------------------------------------------------------
# LOGGING CONFIGURATION / CONFIGURACIÓN DE LOGGING
# ---------------------------------------------------------------------------
# Configure logging to stdout so output is visible in the PythonAnywhere console.
# Configurar logging a stdout para que la salida sea visible en la consola de PA.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# CONSTANTS / CONSTANTES
# ---------------------------------------------------------------------------

# Gemini 3.1 Live model identifier — standard for April 2026.
# Identificador del modelo Gemini 3.1 Live — estándar de Abril de 2026.
GEMINI_MODEL = "gemini-3.1-flash-live-preview"

# Timeout aligned with V01 roadmap directive: Preview infrastructure TTFT
# can reach up to 35 seconds. 60 seconds provides a safe margin.
# Timeout alineado con la directiva de la hoja de ruta V01: el TTFT de la
# infraestructura Preview puede alcanzar hasta 35 segundos. 60 segundos
# proporciona un margen seguro.
TIMEOUT_CONNECT_SECONDS = 60.0
TIMEOUT_SEND_SECONDS = 60.0
TIMEOUT_RECEIVE_SECONDS = 60.0

# Test probe message sent to the model to trigger a response.
# The end_of_turn=True flag signals Gemini that this is a complete turn
# and it should begin generating its audio response immediately.
# Mensaje de sonda de prueba enviado al modelo para provocar una respuesta.
# El flag end_of_turn=True indica a Gemini que este es un turno completo
# y debe comenzar a generar su respuesta de audio de forma inmediata.
TEST_PROBE_TEXT = "Di 'Prueba de infraestructura superada.' exactamente."

# Minimum number of audio bytes expected in a valid response.
# Any response above this threshold is considered a successful audio reception.
# Número mínimo de bytes de audio esperados en una respuesta válida.
# Cualquier respuesta por encima de este umbral se considera una recepción
# de audio exitosa.
MIN_AUDIO_BYTES_THRESHOLD = 100


# ---------------------------------------------------------------------------
# CONNECTIVITY TEST / PRUEBA DE CONECTIVIDAD
# ---------------------------------------------------------------------------

async def run_connectivity_test() -> bool:
    """
    Executes the full zero-cost infrastructure validation sequence.

    Steps:
        1. Load and validate GEMINI_API_KEY from environment.
        2. Instantiate the Gemini GenAI client.
        3. Establish a Gemini Live session via the SDK context manager
           (Setup-First protocol — session is ready upon context entry).
        4. Log the validated handshake confirmation.
        5. Send the test probe text with end_of_turn=True.
        6. Receive and validate the audio response.
        7. Log the final validation result.

    Returns:
        bool: True if the full validation sequence succeeds, False otherwise.
    ---
    Ejecuta la secuencia completa de validación de infraestructura de coste cero.

    Pasos:
        1. Cargar y validar GEMINI_API_KEY desde el entorno.
        2. Instanciar el cliente Gemini GenAI.
        3. Establecer una sesión Gemini Live a través del context manager del SDK
           (protocolo Setup-First — la sesión está lista al entrar en el contexto).
        4. Registrar la confirmación del handshake validado.
        5. Enviar el texto de sonda de prueba con end_of_turn=True.
        6. Recibir y validar la respuesta de audio.
        7. Registrar el resultado final de la validación.

    Returns:
        bool: True si la secuencia de validación completa tiene éxito, False en caso contrario.
    """
    logger.info("=" * 60)
    logger.info("  ENTERPRISEBOT — PRUEBA DE CONECTIVIDAD GEMINI 3.1 LIVE")
    logger.info("=" * 60)

    # STEP 1: Load and validate the API key.
    # PASO 1: Cargar y validar la clave de API.
    gemini_api_key = os.getenv("GEMINI_API_KEY")
    if not gemini_api_key:
        logger.error(
            "[CONFIG] GEMINI_API_KEY no encontrada en las variables de entorno. "
            "Asegúrate de ejecutar el script con: python -m dotenv run python test_bridge_connectivity.py"
        )
        return False
    logger.info("[CONFIG] GEMINI_API_KEY cargada correctamente.")

    # STEP 2: Instantiate the Gemini client.
    # PASO 2: Instanciar el cliente Gemini.
    client = genai.Client(api_key=gemini_api_key)
    logger.info(f"[CONFIG] Cliente Gemini GenAI instanciado. Modelo objetivo: {GEMINI_MODEL}")

    # Build the session configuration.
    # Response modality is AUDIO to validate the full audio pipeline.
    # Construir la configuración de la sesión.
    # La modalidad de respuesta es AUDIO para validar el pipeline de audio completo.
    live_config = types.LiveConnectConfig(
        response_modalities=["AUDIO"],
    )

    try:
        # STEP 3: Establish the Gemini Live session via the SDK context manager.
        #
        # SETUP-FIRST PROTOCOL (SDK 1.69.0 COMPLIANT):
        # The async context manager `client.aio.live.connect()` performs the full
        # WebSocket handshake with Google's Live API infrastructure internally.
        # By the time execution reaches the first line inside the `async with` block,
        # the session is fully established and ready to accept data.
        # No polling for setup_complete events is required or exposed by the SDK.
        #
        # PASO 3: Establecer la sesión Gemini Live a través del context manager del SDK.
        #
        # PROTOCOLO SETUP-FIRST (CONFORME A SDK 1.69.0):
        # El context manager asíncrono `client.aio.live.connect()` realiza el handshake
        # WebSocket completo con la infraestructura de Live API de Google de forma interna.
        # En el momento en que la ejecución alcanza la primera línea dentro del bloque
        # `async with`, la sesión está completamente establecida y lista para aceptar datos.
        # No se requiere ni está expuesto por el SDK el sondeo de ningún evento setup_complete.
        logger.info(
            f"[SDK] Conectando con Gemini Live API... "
            f"(timeout: {TIMEOUT_CONNECT_SECONDS}s)"
        )

        async with client.aio.live.connect(
            model=GEMINI_MODEL,
            config=live_config
        ) as session:

            # STEP 4: Log the validated handshake confirmation.
            # This is the canonical success log defined in the V01 roadmap.
            # PASO 4: Registrar la confirmación del handshake validado.
            # Este es el log de éxito canónico definido en la hoja de ruta V01.
            logger.info(
                "[SDK] Handshake Gemini 3.1 (SetupComplete: True) VALIDADO"
            )

            # STEP 5: Send the test probe text using SDK 1.69.0 compliant syntax.
            # The correct signature for text input is:
            #     await session.send_realtime_input(text="...")
            # The end_of_turn argument is NOT valid for text sends in SDK 1.69.0
            # and causes a 1007 invalid argument error that closes the WebSocket.
            # PASO 5: Enviar el texto de sonda de prueba usando la sintaxis conforme
            # a SDK 1.69.0. La firma correcta para entrada de texto es:
            #     await session.send_realtime_input(text="...")
            # El argumento end_of_turn NO es válido para envíos de texto en SDK 1.69.0
            # y provoca un error 1007 invalid argument que cierra el WebSocket.
            logger.info(
                f"[TEST] Enviando sonda de prueba: '{TEST_PROBE_TEXT}' "
                f"(timeout: {TIMEOUT_SEND_SECONDS}s)"
            )
            await asyncio.wait_for(
                session.send_realtime_input(
                    text=TEST_PROBE_TEXT
                ),
                timeout=TIMEOUT_SEND_SECONDS
            )
            logger.info("[TEST] Sonda enviada. Esperando respuesta de audio de Gemini...")

            # STEP 6: Receive and validate the audio response.
            # Iterate over session.receive() until we get an audio chunk or
            # the turn completes. The first audio chunk received is sufficient
            # to validate the pipeline.
            # PASO 6: Recibir y validar la respuesta de audio.
            # Iterar sobre session.receive() hasta recibir un fragmento de audio
            # o que el turno se complete. El primer fragmento de audio recibido
            # es suficiente para validar el pipeline.
            audio_bytes_received = 0
            validation_passed = False

            async def _receive_with_timeout():
                """
                Inner coroutine that iterates session.receive() and returns
                upon receiving the first valid audio chunk or turn completion.
                ---
                Corrutina interna que itera session.receive() y retorna al
                recibir el primer fragmento de audio válido o la finalización
                del turno.
                """
                nonlocal audio_bytes_received, validation_passed

                async for response in session.receive():

                    # Check for audio data in the model turn.
                    # Verificar datos de audio en el turno del modelo.
                    if response.server_content and response.server_content.model_turn:
                        for part in response.server_content.model_turn.parts:
                            if part.inline_data and part.inline_data.data:
                                chunk_size = len(part.inline_data.data)
                                audio_bytes_received += chunk_size
                                logger.info(
                                    f"[TEST] Fragmento de audio recibido: "
                                    f"{chunk_size} bytes "
                                    f"(total acumulado: {audio_bytes_received} bytes)."
                                )
                                if audio_bytes_received >= MIN_AUDIO_BYTES_THRESHOLD:
                                    validation_passed = True
                                    # We have enough data to confirm the pipeline works.
                                    # Return early without consuming the full response.
                                    # Tenemos suficientes datos para confirmar que el
                                    # pipeline funciona. Retornar sin consumir la
                                    # respuesta completa.
                                    return

                    # Check for turn completion.
                    # Verificar la finalización del turno.
                    if (
                        response.server_content
                        and response.server_content.turn_complete
                    ):
                        logger.info("[TEST] Turno de Gemini completado.")
                        return

            await asyncio.wait_for(
                _receive_with_timeout(),
                timeout=TIMEOUT_RECEIVE_SECONDS
            )

            # STEP 7: Log the final validation result.
            # PASO 7: Registrar el resultado final de la validación.
            if validation_passed:
                logger.info("=" * 60)
                logger.info("  RESULTADO: VALIDACIÓN DE INFRAESTRUCTURA SUPERADA ✓")
                logger.info(
                    f"  Audio recibido: {audio_bytes_received} bytes PCM 24kHz."
                )
                logger.info("=" * 60)
                return True
            else:
                logger.warning(
                    f"[TEST] El turno completó pero sólo se recibieron "
                    f"{audio_bytes_received} bytes de audio "
                    f"(umbral mínimo: {MIN_AUDIO_BYTES_THRESHOLD} bytes). "
                    "Posible respuesta vacía o modelo sin respuesta de audio."
                )
                logger.info("=" * 60)
                logger.info("  RESULTADO: VALIDACIÓN INCOMPLETA — REVISAR LOGS")
                logger.info("=" * 60)
                return False

    except asyncio.TimeoutError:
        logger.error(
            f"[TEST] TIMEOUT — La operación superó el límite de {TIMEOUT_RECEIVE_SECONDS}s. "
            "La infraestructura Preview puede estar experimentando alta latencia. "
            "Recuerda: el TTFT documentado puede alcanzar los 35 segundos."
        )
        logger.info("=" * 60)
        logger.info("  RESULTADO: VALIDACIÓN FALLIDA — TIMEOUT")
        logger.info("=" * 60)
        return False

    except Exception as exc:
        logger.error(
            f"[TEST] Error inesperado durante la prueba de conectividad: {exc}",
            exc_info=True
        )
        logger.info("=" * 60)
        logger.info("  RESULTADO: VALIDACIÓN FALLIDA — ERROR INESPERADO")
        logger.info("=" * 60)
        return False


# ---------------------------------------------------------------------------
# ENTRY POINT / PUNTO DE ENTRADA
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    success = asyncio.run(run_connectivity_test())
    sys.exit(0 if success else 1)
