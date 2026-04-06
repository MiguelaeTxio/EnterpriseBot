# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/DOCS/MAINS/ATTACHEDS/ENTERPRISEBOT_ATTACHED_MILESTONE_V01.md

# ENTERPRISEBOT — ANEXO HITO V01
**Estado:** EN PROGRESO
**Título:** Validación E2E del Flujo de Voz Real: Twilio → ngrok → Gemini 2.5 Native Audio (Vertex AI)
**Fecha de última actualización:** 2026-04-06

---

## 1. OBJETIVO DEL HITO

Demostrar en una llamada telefónica real y completa que el pipeline IVR conversacional
bidireccional funciona end-to-end:

    Llamada outbound Twilio → ngrok → aiohttp WebSocket Bridge → Gemini 2.5 Live API (Vertex AI)

Alia (asistente virtual del Grupo Álvarez) debe:
1. Saludar al llamante al descolgar.
2. Escuchar la petición del llamante en castellano.
3. Responder con audio en tiempo real siguiendo el organigrama de atención.
4. Mantener una conversación multi-turno hasta que el llamante cuelgue.

---

## 2. ESTADO ACTUAL AL CIERRE DE SESIÓN 2026-04-06

### 2.1. Lo que funciona
- Llamada outbound disparada desde trigger_outbound_call.py.
- Handshake Gemini (SetupComplete: True) con Vertex AI y Service Account JSON.
- Autenticación Vertex AI con google.oauth2.service_account.Credentials.
- TwiML generado correctamente (HTTP 200).
- WebSocket Twilio conecta a /media en el bridge aiohttp (puerto 8081).
- ngrok tunnel estable con URL fija: https://deistical-rosalia-detonative.ngrok-free.dev
- Alia saluda correctamente — el primer turno (saludo inicial vía send_client_content)
  genera audio y se escucha en la llamada.
- **HITO VALIDADO 2026-04-06**: Pipeline E2E completo funcionando.
  Conversación multi-turno real validada: Alia saludó, el llamante pidió información
  sobre plataformas elevadoras, Alia respondió con el horario correcto del organigrama
  y cerró la llamada correctamente.
- Arquitectura de tres corrutinas + asyncio.Queue operativa y estable.
- Detección de actividad manual (VAD cliente) con máquina de estados RMS funcionando:
  activity_start y activity_end emitidos correctamente en cada turno del llamante.
- VAD servidor disabled=True correcto para telefonía (evita auto-interrupción por eco).

### 2.2. Aspectos pendientes de ajuste fino
- Los umbrales de detección de actividad (SILENCE_THRESHOLD_RMS,
  SILENCE_FRAMES_TO_END_ACTIVITY, SPEECH_FRAMES_TO_START_ACTIVITY) están
  operativos pero requieren validación bajo distintas condiciones de llamada
  (distintos dispositivos, entornos ruidosos, distintos hablantes).
- Valores actuales tras ajuste 2026-04-06:
    SILENCE_THRESHOLD_RMS = 200
    SILENCE_FRAMES_TO_END_ACTIVITY = 30
    SPEECH_FRAMES_TO_START_ACTIVITY = 10

### 2.3. Hipótesis investigadas y descartadas (histórico)
- thinking_level no soportado por Gemini 2.5 → corregido.
- speech_config ausente → añadido voz Aoede.
- audioStreamEnd no enviado tras turn_complete → añadido.
- Service Account sin rol Vertex AI User → verificado y correcto.
- Gemini API Preview inestable → migrado a Vertex AI GA.
- Arquitectura start_stream → deprecada, descartada.
- VAD deshabilitado sin señales manuales de actividad → causa raíz del turno 2 muerto,
  resuelto con activity_start / activity_end en _forward_twilio_audio_to_gemini.
- SPEECH_FRAMES_TO_START_ACTIVITY = 3 → disparaba sobre eco acústico del propio
  saludo de Alia, aumentado a 10 (~200ms).

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
| SDK Gemini | google-genai 1.69.0 |
| Voz | Aoede |
| VAD servidor | disabled=True (obligatorio para telefonía) |
| Detección actividad | RMS cliente — activity_start / activity_end manuales |

---

## 4. ARCHIVOS CLAVE MODIFICADOS EN ESTA SESIÓN

| Archivo | Cambio |
|---|---|
| vox_bridge/services.py | Añadidos imports struct y math. Añadidas constantes SILENCE_THRESHOLD_RMS, SILENCE_FRAMES_TO_END_ACTIVITY, SPEECH_FRAMES_TO_START_ACTIVITY. Reescrita _forward_twilio_audio_to_gemini con máquina de estados RMS y emisión de activity_start / activity_end. |

---

## 5. HOJA DE RUTA PARA LA SIGUIENTE SESIÓN

### OBJETIVO: Ajuste fino de umbrales de detección de actividad y validación en producción

#### 5.1. Contexto y Motivación

El pipeline E2E está validado y funcionando. La máquina de estados RMS en
_forward_twilio_audio_to_gemini emite correctamente activity_start y activity_end.
Los valores actuales de los umbrales son operativos pero han sido ajustados
empíricamente en condiciones de laboratorio (una llamada, un hablante, un dispositivo).

La siguiente sesión debe validar el comportamiento bajo distintas condiciones reales
y afinar los umbrales si fuera necesario.

#### 5.2. Pasos de Implementación

PASO 1 — Habilitar logging DEBUG en el bridge para ver los fragmentos de audio:

En voice_orchestrator.py o en la configuración de logging de Django, bajar el nivel
de log a DEBUG durante las pruebas. Esto permitirá ver en el log:
- Cada fragmento PCM enviado a Gemini con su RMS.
- Los fragmentos de audio recibidos de Gemini ([GEMINI-RX]).
- Los fragmentos mu-law enviados a Twilio ([TWILIO-TX]).

El log DEBUG tiene esta línea en _forward_twilio_audio_to_gemini:
    logger.debug(
        f"[GEMINI-TX] Fragmento PCM enviado a Gemini: {len(pcm_chunk)} bytes "
        f"| RMS: {rms:.1f} | Hablando: {is_speaking}"
    )

PASO 2 — Realizar llamadas de prueba con distintos perfiles:

- Llamada con pausa larga entre frases: ¿cierra el turno prematuramente?
- Llamada en entorno con ruido de fondo: ¿falsos positivos en activity_start?
- Llamada con hablante de voz suave: ¿SILENCE_THRESHOLD_RMS demasiado alto?
- Llamada con interrupción deliberada: ¿el barge-in funciona correctamente?

PASO 3 — Ajustar umbrales según observaciones:

Los tres parámetros a ajustar están en vox_bridge/services.py como constantes:

    SILENCE_THRESHOLD_RMS = 200
        Subir si hay falsos positivos por ruido de línea.
        Bajar si voces suaves no se detectan.

    SILENCE_FRAMES_TO_END_ACTIVITY = 30
        Subir si el turno se cierra prematuramente en pausas naturales del habla.
        Bajar si Gemini tarda demasiado en responder tras el fin del turno.

    SPEECH_FRAMES_TO_START_ACTIVITY = 10
        Subir si el eco acústico del propio audio de Alia sigue disparando
        activity_start espurios.
        Bajar si el llamante tarda demasiado en ser detectado al empezar a hablar.

PASO 4 — Evaluar audioStreamEnd tras turn_complete de Gemini:

El código actual envía audioStreamEnd tras cada turn_complete de Gemini.
Con VAD deshabilitado y activity_start/activity_end manuales, este audioStreamEnd
puede ser redundante o incluso interferir. Verificar en los logs DEBUG si su
presencia o ausencia afecta al comportamiento del turno siguiente.
Candidato a eliminar si las pruebas lo confirman.

PASO 5 — Actualizar la Directriz Técnica §4.1 del MASTER_DOCUMENT:

El modelo registrado en §4.1 sigue siendo gemini-3.1-flash-live-preview (incorrecto).
Actualizar a gemini-live-2.5-flash-native-audio mediante PMA en la siguiente sesión.

#### 5.3. Criterio de cierre del Hito 1

El Hito 1 se considera COMPLETADO cuando:
- Se hayan realizado al menos 3 llamadas de prueba con distintos perfiles.
- Los umbrales estén validados y documentados.
- No se produzcan auto-interrupciones espurias en ninguna prueba.
- La conversación multi-turno sea fluida y natural en todas las pruebas.

---

## 6. PAH — REGISTRO DE SESIÓN

**Título:** Refactorización arquitectural de vox_bridge/services.py: asyncio.Queue → activity_start/activity_end
**Descripción:** Sesión de diagnóstico y refactorización del pipeline de audio bidireccional.
Se identificó la causa raíz del turno 2 muerto: VAD servidor disabled=True sin señales
manuales de actividad. Se implementó máquina de estados RMS en _forward_twilio_audio_to_gemini
con emisión de activity_start y activity_end. Se validó el pipeline E2E con llamada real:
conversación multi-turno funcionando correctamente.
