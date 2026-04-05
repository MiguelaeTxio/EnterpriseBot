# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/DOCS/MAINS/ATTACHEDS/ENTERPRISEBOT_ATTACHED_MILESTONE_V01.md

# ENTERPRISEBOT — ANEXO HITO V01
**Estado:** EN PROGRESO
**Título:** Validación E2E del Flujo de Voz Real: Twilio → ngrok → Gemini 2.5 Native Audio (Vertex AI)
**Fecha de última actualización:** 2026-04-05

---

## 1. OBJETIVO DEL HITO

Demostrar en una llamada telefónica real y completa que el pipeline IVR conversacional
bidireccional funciona end-to-end:
```
Llamada outbound Twilio → ngrok → aiohttp WebSocket Bridge → Gemini 2.5 Live API (Vertex AI)
```

Alia (asistente virtual del Grupo Álvarez) debe:
1. Saludar al llamante al descolgar.
2. Escuchar la petición del llamante en castellano.
3. Responder con audio en tiempo real siguiendo el organigrama de atención.
4. Mantener una conversación multi-turno hasta que el llamante cuelgue.

---

## 2. ESTADO ACTUAL AL CIERRE DE SESIÓN 2026-04-05

### 2.1. Lo que funciona
- Llamada outbound disparada desde trigger_outbound_call.py.
- Handshake Gemini (SetupComplete: True) con Vertex AI y Service Account JSON.
- Autenticación Vertex AI con google.oauth2.service_account.Credentials.
- TwiML generado correctamente (HTTP 200).
- WebSocket Twilio conecta a /media en el bridge aiohttp (puerto 8081).
- ngrok tunnel estable con URL fija: https://deistical-rosalia-detonative.ngrok-free.dev
- Alia saluda correctamente — el primer turno (saludo inicial vía send_client_content) genera audio y se escucha en la llamada.

### 2.2. Lo que NO funciona
- Turno 2 completamente muerto: cuando el llamante habla tras el saludo de Alia,
  Gemini no genera ninguna respuesta. El log muestra cero fragmentos [GEMINI-RX]
  entre el fin del saludo y el evento stop de Twilio.
- El log de INFO no muestra ningún evento media de Twilio (se loguean en DEBUG),
  por lo que no se puede confirmar visualmente si el audio del llamante llega a la cola.
- La arquitectura de tres corrutinas + asyncio.Queue no ha podido ser validada
  en el turno 2 con ningún modelo Gemini Live probado.

### 2.3. Hipótesis investigadas y descartadas
- thinking_level no soportado por Gemini 2.5 → corregido.
- speech_config ausente → añadido voz Aoede.
- audioStreamEnd no enviado tras turn_complete → añadido.
- Service Account sin rol Vertex AI User → verificado y correcto.
- Gemini API Preview inestable → migrado a Vertex AI GA.

### 2.4. Hipótesis activa — Causa Raíz Probable
La investigación en foros confirma que la arquitectura actual de tres corrutinas
con asyncio.Queue es propensa a problemas de sincronización en el turno 2.

La arquitectura documentada por Google (Christopher Brox, Google Cloud) y
probada en producción para exactamente este caso de uso usa
session.start_stream(stream=async_generator, mime_type='audio/pcm') —
un patrón radicalmente diferente donde el generador asíncrono de Twilio alimenta
directamente el stream de Gemini, eliminando las colas y la sincronización manual.

---

## 3. STACK TÉCNICO CONFIRMADO

| Componente | Valor |
|---|---|
| Modelo Gemini | gemini-live-2.5-flash-native-audio |
| Auth | Vertex AI — Service Account JSON |
| GCP Project | gen-lang-client-0961484137 |
| GCP Location | us-central1 |
| Service Account | enterprisebot-vertex@gen-lang-client-0961484137.iam.gserviceaccount.com |
| Credenciales | /home/MiguelAeTxio/PROJECTS/EnterpriseBot/gcp_credentials.json |
| Twilio número | +12603466780 |
| Número destino demo | +34688360595 |
| ngrok URL | https://deistical-rosalia-detonative.ngrok-free.dev |
| Bridge | aiohttp 3.13.5 — puerto 8081 |
| Framework | Django 5.2.12 |
| SDK Gemini | google-genai (instalado en venv) |
| Voz | Aoede |

---

## 4. ARCHIVOS CLAVE MODIFICADOS EN ESTA SESIÓN

| Archivo | Cambio |
|---|---|
| .env | Añadidas variables GOOGLE_CLOUD_PROJECT, GOOGLE_CLOUD_LOCATION, GCP_CREDENTIALS_PATH |
| vox_bridge/services.py | Migración completa Gemini API → Vertex AI; eliminado thinking_config; añadido speech_config voz Aoede; send_client_content para saludo; audioStreamEnd tras turn_complete |
| gcp_credentials.json | Subido al servidor (Service Account JSON) |

---

## 5. HOJA DE RUTA PARA LA SIGUIENTE SESIÓN

### OBJETIVO ÚNICO: Refactorizar vox_bridge/services.py con arquitectura start_stream

#### 5.1. Contexto y Motivación

La arquitectura actual usa tres corrutinas independientes con asyncio.Queue:
- _forward_twilio_audio_to_gemini(session) — consume la cola y envía audio a Gemini.
- _receive_gemini_audio(session) — recibe audio de Gemini y lo pone en otra cola.
- _forward_gemini_audio_to_twilio(twilio_websocket) — consume la segunda cola y envía audio a Twilio.

Esta arquitectura introduce sincronización manual propensa a fallos en el turno 2.

La arquitectura probada usa:

    async with self.client.aio.live.connect(model=self.model_id, config=self.config) as session:
        async for response in session.start_stream(stream=self.twilio_audio_stream(), mime_type='audio/pcm'):
            if data := response.data:
                # enviar audio a Twilio

Donde twilio_audio_stream() es un generador asíncrono que:
1. Lee mensajes del WebSocket de Twilio.
2. Extrae el payload base64.
3. Decodifica de mu-law 8kHz a PCM 16kHz.
4. Hace yield del PCM.

#### 5.2. Pasos de Implementación

PASO 1 — Antes de tocar código: Actualizar web y verificar si session.start_stream
sigue disponible en la versión actual del SDK google-genai instalada en el venv:

    python -m dotenv run python -c "from google.genai import live; print(dir(live))"

Y verificar la versión del SDK:

    python -m dotenv run pip show google-genai

PASO 2 — Leer el archivo actual completo antes de proponer ningún PMA:

    sftp MiguelAeTxio@ssh.pythonanywhere.com
    get /home/MiguelAeTxio/PROJECTS/EnterpriseBot/vox_bridge/services.py "/sdcard/Download/temp_01"
    !cat "/sdcard/Download/temp_01" > "/sdcard/Download/file00.txt"
    !rm "/sdcard/Download/temp_01"
    exit

PASO 3 — Refactorizar vox_bridge/services.py mediante PMA:

La nueva arquitectura de run_voice_session debe:

1. Mantener el __init__ y VoiceOrchestrationService tal como están.
2. Mantener el LiveConnectConfig con speech_config, system_instruction, Aoede.
3. Eliminar las tres corrutinas _forward_twilio_audio_to_gemini,
   _receive_gemini_audio, _forward_gemini_audio_to_twilio.
4. Eliminar asyncio.Queue y asyncio.gather.
5. Implementar twilio_audio_stream() como generador asíncrono que consume
   self._audio_input_queue (que el sidecar sigue llenando sin cambios).
6. Implementar run_voice_session con start_stream.
7. Mantener receive_twilio_audio, terminate_session y set_stream_sid sin cambios.

#### 5.3. Conversión de audio a verificar

El audio de salida de Gemini es PCM 24kHz. Twilio espera mu-law 8kHz base64.
La conversión actual usa audioop y debe mantenerse en el nuevo flujo:

    data, _ = audioop.ratecv(audio_data, 2, 1, 24000, 8000, None)
    mulaw = audioop.lin2ulaw(data, 2)
    encoded = base64.b64encode(mulaw).decode('utf-8')

#### 5.4. Refuerzo de Skills obligatorio al cierre de la refactorización

Reforzar la skill session-standards añadiendo la Directriz 4.4 de forma explícita:
"OBLIGATORIO actualizar web antes de cualquier implementación con APIs externas,
incluyendo Google Gemini, Twilio y cualquier SDK de terceros."
Esta directriz fue violada en múltiples ocasiones durante la sesión 2026-04-05,
causando horas de trabajo perdido.

---

## 6. PAH — REGISTRO DE SESIÓN

**Título:** Validación E2E del Flujo de Voz Real: Twilio → ngrok → Gemini 3.1 Live
**Descripción:** Sesión de migración Gemini API Preview → Vertex AI GA, depuración
exhaustiva del pipeline de audio bidireccional IVR. Se resolvieron múltiples bloqueantes
de configuración (Vertex AI, Service Account, thinking_config, speech_config) pero
el turno 2 del pipeline de audio sigue sin funcionar. Identificada la causa raíz probable
y definida la hoja de ruta de refactorización arquitectural para la siguiente sesión.

