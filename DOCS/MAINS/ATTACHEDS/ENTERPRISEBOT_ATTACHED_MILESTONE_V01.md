# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/DOCS/MAINS/ATTACHEDS/ENTERPRISEBOT_ATTACHED_MILESTONE_V01.md
# ANEXO HITO 1: INFRAESTRUCTURA DE VOZ (ESTABILIZACIÓN CRÍTICA 3.1)
# ESTADO: EN PROGRESO
# FECHA ACTUALIZACIÓN: 2026-04-04

---

## 1. RESUMEN DE SESIÓN (2026-04-04)

### Problema de Partida
El sidecar bridge (voice_sidecar_bridge.py) intentaba importar una clase
GeminiStreamService que no existía en vox_bridge/services.py. La clase real
es VoiceOrchestrationService. Adicionalmente, test_bridge_connectivity.py
usaba send_client_content (inválido para Gemini 3.1 en conversación) y
end_of_turn=True (argumento no válido para envíos de texto en SDK 1.69.0),
causando error 1007 y cierre inmediato del WebSocket.

### Intervenciones Realizadas

1. test_bridge_connectivity.py:
   - Sustituido send_client_content(turns=..., turn_complete=True) por
     send_realtime_input(text=TEST_PROBE_TEXT).
   - Eliminado end_of_turn=True — argumento invalido para texto en SDK 1.69.0.
   - Comentarios inline sincronizados con la firma real del SDK.

2. voice_sidecar_bridge.py:
   - Reescrito por completo. Eliminada interfaz fantasma GeminiStreamService
     y toda la logica de setup_confirmed, reset_session_state,
     build_live_config, send_audio_frame, listen_to_ai.
   - Integrado VoiceOrchestrationService con su interfaz real:
     run_voice_session(ws), receive_twilio_audio(payload),
     terminate_session().
   - Preservada arquitectura aiohttp: POST /api/vox/inbound/ (TwiML) +
     GET /media (WebSocket upgrade).
   - Instanciacion de VoiceOrchestrationService fresca por llamada para
     aislamiento completo de estado entre llamadas consecutivas.

3. voice_orchestrator.py:
   - cleanup_ports ampliado con cierre de tunnel sessions via API cloud
     ngrok (https://api.ngrok.com) usando NGROK_API_KEY del .env.
   - Secuencia: GET /endpoints -> POST /tunnel_sessions/{id}/stop por
     cada sesion activa -> espera 3s de propagacion -> kill puertos locales.
   - Resuelto definitivamente ERR_NGROK_334.

4. vox_bridge/services.py:
   - Eliminado end_of_turn=True del bloque send_initial_greeting.
   - Comentarios inline sincronizados con la firma real del SDK 1.69.0.

### Resultado de Validacion Zero-Cost
Log canonico obtenido:
    [SDK] Handshake Gemini 3.1 (SetupComplete: True) VALIDADO
    RESULTADO: VALIDACION DE INFRAESTRUCTURA SUPERADA
    Audio recibido: 9604 bytes PCM 24kHz.

---

## 2. ESTADO TECNICO VALIDADO

- SDK: google-genai 1.69.0
- Modelo: gemini-3.1-flash-live-preview
- Protocolo Setup-First: Context manager async with client.aio.live.connect(...)
- Firma texto SDK 1.69.0: await session.send_realtime_input(text="...")
- Firma audio SDK 1.69.0: await session.send_realtime_input(audio=types.Blob(data=..., mime_type="audio/pcm;rate=16000"))
- Recepcion audio: response.server_content.model_turn.parts[n].inline_data.data
- Transcodificacion: mu-law 8kHz <-> PCM 16kHz <-> PCM 24kHz via audioop
- Infraestructura: ngrok v3 + aiohttp 8081 + Django 5.2.12 WSGI

---

## 3. HOJA DE RUTA PARA LA SIGUIENTE SESION (LEY SUPREMA)

### OBJETIVO
Validar el flujo de voz extremo a extremo con una llamada Twilio real:
Twilio -> ngrok -> sidecar bridge -> Gemini 3.1 Live -> audio de vuelta al llamante.

### ARQUITECTURA DE REFERENCIA (INMUTABLE)

Twilio Media Streams (G.711 mu-law 8kHz)
    WebSocket WSS
ngrok tunnel -> aiohttp puerto 8081
    POST /api/vox/inbound/  ->  TwiML con Connect/Stream url wss://{host}/media
    GET  /media             ->  WebSocket upgrade
UniversalVoiceBridge.handle_websocket_stream()
    instancia fresca por llamada
VoiceOrchestrationService
    run_voice_session(ws)
        async with gemini_client.aio.live.connect(
            model="gemini-3.1-flash-live-preview",
            config=LiveConnectConfig(
                response_modalities=["AUDIO"],
                system_instruction=Content(parts=[Part(text=SYSTEM_INSTRUCTION)])
            )
        ) as session:
            send_realtime_input(text=INITIAL_GREETING_TEXT)
            gather(
                _forward_twilio_audio_to_gemini(session),
                _receive_gemini_audio(session),
                _forward_gemini_audio_to_twilio(ws)
            )

### PASO 1: Verificacion de Configuracion Twilio

1. Confirmar que el webhook de voz entrante del numero Twilio apunta a:
   https://{ngrok_url}/api/vox/inbound/
   Metodo: HTTP POST.
2. Confirmar que las variables de entorno estan completas en .env:
   - TWILIO_ACCOUNT_SID
   - TWILIO_API_KEY_SID
   - TWILIO_API_KEY_SECRET
   - GEMINI_API_KEY
   - NGROK_API_KEY
3. Verificar que DOCS/SESSION/NGROK_URL.txt se escribe correctamente al
   arrancar el orquestador y que vox_bridge/views.py lo lee bien para
   construir la URL WSS del TwiML.

### PASO 2: Lanzamiento del Sistema

    cd /home/MiguelAeTxio/PROJECTS/EnterpriseBot
    python -m dotenv run python voice_orchestrator.py

Confirmar en consola:
    # [SUCCESS] TUNEL 2026 ACTIVO: https://{url}.ngrok-free.dev
    # [READY] Puente HIBRIDO (aiohttp) activo en puerto 8081.

### PASO 3: Configuracion del Webhook Twilio

En la consola de Twilio o via CLI:
    twilio phone-numbers:update {NUMERO} --voice-url https://{ngrok_url}/api/vox/inbound/

Verificar respuesta HTTP 200 y TwiML valido con:
    curl -s -X POST https://{ngrok_url}/api/vox/inbound/

Respuesta esperada:
    <?xml version="1.0" encoding="UTF-8"?>
    <Response><Connect><Stream url="wss://{ngrok_url}/media"/></Connect></Response>

### PASO 4: Llamada de Prueba y Validacion de Logs

Realizar llamada entrante al numero Twilio configurado.
Secuencia de logs esperada en consola del sidecar:

    # [HTTP POST] Peticion inicial de Twilio recibida. Generando TwiML.
    # [HTTP POST] TwiML generado. WSS target: wss://{url}/media
    # [WSS] Conexion WebSocket establecida en /media.
    # [EVENT] Stream iniciado -- streamSid: ... | callSid: ...
    [SDK] Handshake Gemini 3.1 (SetupComplete: True) VALIDADO. Sesion lista.
    [SESSION] Enviando saludo inicial a Gemini...
    [SESSION] Saludo inicial enviado correctamente. Lanzando corrutinas...
    [GEMINI-TX] Corrutina de envio de audio a Gemini iniciada.
    [GEMINI-RX] Corrutina de recepcion de audio de Gemini iniciada.
    [TWILIO-TX] Corrutina de envio de audio a Twilio iniciada.
    [GEMINI-RX] Fragmento de audio recibido de Gemini: XXXX bytes PCM 24kHz.
    [TWILIO-TX] Fragmento mu-law enviado a Twilio: XXX bytes.

### PASO 5: Diagnostico de Fallos Conocidos

FALLO: TwiML llega pero WebSocket no conecta.
CAUSA: ngrok no apunta a puerto 8081 o sidecar no esta escuchando.
ACCION: Verificar DOCS/SESSION/NGROK_URL.txt y puerto 8081 activo.

FALLO: WebSocket conecta pero Gemini falla en handshake.
CAUSA: GEMINI_API_KEY invalida o infraestructura Preview no disponible.
ACCION: Verificar clave en .env. El TTFT puede alcanzar 35s -- timeout minimo 60s.

FALLO: Audio llega a Gemini pero no vuelve a Twilio.
CAUSA: Fallo en transcodificacion PCM 24kHz -> mu-law 8kHz en _transcode_pcm24k_to_mulaw.
ACCION: Auditar _forward_gemini_audio_to_twilio -- verificar logs [TWILIO-TX].

FALLO: Audio llega distorsionado al llamante.
CAUSA: Fallo en la cadena de transcodificacion audioop.
ACCION: Auditar _transcode_mulaw_to_pcm16k y _transcode_pcm24k_to_mulaw en services.py.

