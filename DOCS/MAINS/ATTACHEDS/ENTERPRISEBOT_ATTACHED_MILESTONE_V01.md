# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/DOCS/MAINS/ATTACHEDS/ENTERPRISEBOT_ATTACHED_MILESTONE_V01.md

# ENTERPRISEBOT — ANEXO HITO V01 — VALIDACIÓN DE INFRAESTRUCTURA DE VOZ
**Estado:** COMPLETADO
**Fecha de cierre:** 2026-04-07

---

## SECCIÓN 1 — RESUMEN DE LOGROS TOTALES DEL HITO

### Sesión 1 — Construcción de Infraestructura Base
1. **Implementación del Sidecar Bridge:** Puente aiohttp en puerto 8081 con separación
   de responsabilidades HTTP/WebSocket (doble handshake).
2. **Transcodificación bidireccional:** Pipeline mu-law 8kHz ↔ PCM 16kHz ↔ PCM 24kHz
   via `audioop` operativo y validado.
3. **Integración Gemini Live:** Handshake con Google GenAI SDK 1.69.0 vía context manager
   `async with client.aio.live.connect(...)` confirmado y estable.
4. **Orquestador de voz:** `voice_orchestrator.py` gestiona el ciclo de vida completo:
   limpieza de túneles ngrok cloud, apertura de túnel HTTP, lanzamiento del bridge.
5. **Constelación Documental Satélite V01** generada:
   - `ARCH_VOICE_INFRASTRUCTURE.md`
   - `API_HANDSHAKE_PROTOCOL.md`
   - `TRANSCODING_ENGINE_SPECS.md`

### Sesión 2 — Estabilización, Migración y Validación E2E
1. **Migración a Vertex AI:** Abandono de `gemini-3.1-flash-live-preview` (Preview,
   inestable) y migración a `gemini-live-2.5-flash-native-audio` (GA, Vertex AI).
   Autenticación via Service Account JSON (`gcp_credentials.json`).
2. **Corrección del saludo inicial:** Migración de `send_realtime_input(text=...)` a
   `send_client_content(turns=..., turn_complete=True)` — patrón correcto para
   Gemini 2.5 en Vertex AI.
3. **VAD cliente implementado:** Máquina de estados RMS con histéresis:
   - `SILENCE_THRESHOLD_RMS = 200`
   - `SPEECH_FRAMES_TO_START_ACTIVITY = 10` (~200ms)
   - `SILENCE_FRAMES_TO_END_ACTIVITY = 30` (~600ms)
4. **Fix Python 3.10+:** `asyncio.get_event_loop()` → `asyncio.get_running_loop()`
   en `voice_sidecar_bridge.py`.
5. **Fix deadlock de pipes:** Bridge relanzado con stdout/stderr redirigidos a
   `/home/MiguelAeTxio/SWAP/bridge.log` desacoplando descriptores del orquestador.
6. **`DJANGO_SETTINGS_MODULE` en `.env`:** Variable añadida para correcta herencia
   en subprocesos.
7. **Validación E2E con llamada real:** Alia responde correctamente en castellano.
   Pipeline Twilio → ngrok → aiohttp → Gemini Live → Twilio validado end-to-end.

---

## SECCIÓN 2 — ESTADO TÉCNICO AL CIERRE

### Modelo de IA activo
- **Modelo:** `gemini-live-2.5-flash-native-audio`
- **Plataforma:** Vertex AI (`us-central1`)
- **Autenticación:** Service Account JSON (`GCP_CREDENTIALS_PATH` en `.env`)
- **Voice:** `Aoede` (femenina, IVR)
- **VAD servidor:** `disabled=True` (obligatorio para telefonía)
- **Greeting:** `send_client_content(turn_complete=True)`

### Umbrales VAD cliente (pendientes de calibración fina)
| Constante | Valor | Observación |
|---|---|---|
| `SILENCE_THRESHOLD_RMS` | `200` | Pendiente calibración con números ES |
| `SPEECH_FRAMES_TO_START_ACTIVITY` | `10` | ~200ms — filtra eco acústico |
| `SILENCE_FRAMES_TO_END_ACTIVITY` | `30` | ~600ms — margen inter-frase |

**NOTA:** La calibración fina del VAD queda pendiente para cuando se dispongan
de los números de teléfono españoles aprobados por Twilio (entrega estimada 1-3 días
desde 2026-04-07). Los valores actuales son funcionales pero no están optimizados
para líneas españolas.

### Archivos clave modificados en este hito
| Archivo | Cambio |
|---|---|
| `vox_bridge/services.py` | SYSTEM_INSTRUCTION + INITIAL_GREETING_TEXT de Alia; migración Vertex AI; VAD cliente |
| `voice_sidecar_bridge.py` | `get_running_loop()` fix |
| `voice_orchestrator.py` | Redirección stdout/stderr bridge a `bridge.log` |
| `.env` | `DJANGO_SETTINGS_MODULE` añadido |

---

## SECCIÓN 3 — CRITERIOS DE REAPERTURA

Este hito puede reabrirse únicamente para:
1. **Calibración de umbrales VAD** tras pruebas con números españoles.
2. **Regresión de infraestructura** que afecte al pipeline A2A.

En ningún caso debe reabrirse para trabajo de nuevas funcionalidades —
ese trabajo corresponde a hitos posteriores.

---

## SECCIÓN 4 — PAH — REGISTRO DE SESIÓN
**Título:** Calibración de VAD por RMS y Cierre del Hito 1
**Descripción:** Sesión dedicada a la calibración del sistema de detección de actividad
de voz (VAD) basado en RMS en vox_bridge/services.py. Se auditaron los valores de RMS
observados en sesiones anteriores (rango 8.0–485.0) para ajustar los umbrales de
activity_start y activity_end, eliminando falsos positivos por ruido de línea. Se
implementó un mecanismo de histéresis o conteo de frames para estabilizar la transición
del flag Hablando. Tras la calibración, se realizaron pruebas de validación de latencia
(TTFT) y se procedió al cierre formal del Hito 1 marcándolo como COMPLETADO en el Master
Document.
