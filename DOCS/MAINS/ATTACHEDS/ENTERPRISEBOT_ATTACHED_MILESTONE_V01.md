# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/DOCS/MAINS/ATTACHEDS/ENTERPRISEBOT_ATTACHED_MILESTONE_V01.md

# Anexo de Hito V01 — Validación de Infraestructura de Voz en Tiempo Real
# Proyecto: EnterpriseBot
# Estado: COMPLETADO
# Fecha de cierre: 2026-04-07

---

## 1. Visión General del Hito

Validación completa del pipeline de voz en tiempo real:
Twilio → ngrok → aiohttp (Sidecar Bridge) → Gemini Live → Twilio.
Incluye transcodificación bidireccional mu-law/PCM, VAD cliente RMS
e integración con Gemini Live 2.5 Flash Native Audio en Vertex AI.
Validación E2E con llamada real superada.

---

## 2. Arquitectura Técnica

### 2.1. Pipeline de voz

```
Twilio Media Streams (mu-law 8kHz)
    ↓ WebSocket
ngrok (túnel HTTP/WS)
    ↓
aiohttp Sidecar Bridge (puerto 8081)
    ↓ transcodificación
Gemini Live 2.5 Flash Native Audio — Vertex AI (PCM 16kHz / 24kHz)
    ↑ audio respuesta
Twilio (mu-law 8kHz)
```

### 2.2. Componentes clave

- **`voice_sidecar_bridge.py`** — Puente aiohttp con doble handshake
  HTTP/WebSocket. Fix `asyncio.get_running_loop()` (Python 3.10+).
  stdout/stderr redirigidos a `/home/MiguelAeTxio/SWAP/bridge.log`.
- **`vox_bridge/services.py`** — SYSTEM_INSTRUCTION + INITIAL_GREETING_TEXT
  de Alia. Migración Vertex AI. VAD cliente RMS.
- **`voice_orchestrator.py`** — Limpieza túneles ngrok cloud, apertura
  túnel HTTP, lanzamiento del bridge con redirección de logs.
- **`.env`** — `DJANGO_SETTINGS_MODULE` añadido para correcta herencia
  en subprocesos.

### 2.3. Modelo de IA

- **Modelo:** `gemini-live-2.5-flash-native-audio`
- **Plataforma:** Vertex AI (`us-central1`)
- **Autenticación:** Service Account JSON (`GCP_CREDENTIALS_PATH` en `.env`)
- **Voice:** `Aoede` (femenina, IVR)
- **VAD servidor:** `disabled=True` (obligatorio para telefonía)
- **Greeting:** `send_client_content(turns=..., turn_complete=True)`

### 2.4. Transcodificación

Pipeline bidireccional via `audioop`:
- Entrada Twilio: mu-law 8kHz → PCM 16kHz → Gemini Live
- Salida Gemini: PCM 24kHz → mu-law 8kHz → Twilio

### 2.5. VAD cliente (RMS con histéresis)

| Constante | Valor | Observación |
|---|---|---|
| `SILENCE_THRESHOLD_RMS` | `200` | Pendiente calibración con números ES |
| `SPEECH_FRAMES_TO_START_ACTIVITY` | `10` | ~200ms — filtra eco acústico |
| `SILENCE_FRAMES_TO_END_ACTIVITY` | `30` | ~600ms — margen inter-frase |

**NOTA:** Calibración fina pendiente para cuando se dispongan de los
números de teléfono españoles aprobados por Twilio (entrega estimada
1-3 días desde 2026-04-07). Valores actuales funcionales pero no
optimizados para líneas españolas.

### 2.6. Documentación satélite (en servidor)

| Archivo | Contenido |
|---|---|
| `V01DOC_ARCH_VOICE_INFRASTRUCTURE.md` | Arquitectura completa del Sidecar Bridge |
| `V01DOC_API_HANDSHAKE_PROTOCOL.md` | Protocolo de handshake con Gemini Live |
| `V01DOC_TRANSCODING_ENGINE_SPECS.md` | Especificaciones del motor de transcodificación |

Ruta: `DOCS/MAINS/ATTACHEDS/DOCS_ATTACHED_2_ANNEX_V01/`

---

## 3. Hoja de Ruta

### Sesión 1 — Construcción de Infraestructura Base
- Estado: COMPLETADO (S001)

### Sesión 2 — Estabilización, Migración y Validación E2E
- Estado: COMPLETADO (S002)

---

## 4. Registro de Sesiones

| Sesión | Fecha | Resumen |
|---|---|---|
| S001 | 2026-04-07 | Sidecar Bridge aiohttp. Transcodificación mu-law/PCM. Integración Gemini Live SDK 1.69.0. voice_orchestrator.py. Constelación documental V01 (3 satélites). |
| S002 | 2026-04-07 | Migración Vertex AI (gemini-live-2.5-flash-native-audio). Fix greeting send_client_content. VAD cliente RMS con histéresis. Fix get_running_loop(). Fix deadlock pipes (bridge.log). DJANGO_SETTINGS_MODULE en .env. Validación E2E con llamada real superada. |

---

## 5. Hoja de Ruta para la Siguiente Sesion

### Criterios de reapertura

Este hito puede reabrirse únicamente para:

1. **Calibración de umbrales VAD** tras pruebas con números españoles.
2. **Regresión de infraestructura** que afecte al pipeline A2A.

En ningún caso debe reabrirse para trabajo de nuevas funcionalidades —
ese trabajo corresponde a hitos posteriores.
