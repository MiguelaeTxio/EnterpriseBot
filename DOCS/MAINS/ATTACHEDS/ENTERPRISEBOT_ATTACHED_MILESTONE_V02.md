# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/DOCS/MAINS/ATTACHEDS/ENTERPRISEBOT_ATTACHED_MILESTONE_V02.md

# Anexo de Hito V02 — Validación y Aislamiento de Diagnóstico (test_live)
# Proyecto: EnterpriseBot
# Fecha: 2026-03-31

---

## 1. Visión General del Hito

Creación de la app Django `test_live` como sonda de diagnóstico aislada.
Objetivo: validar la audibilidad de Gemini Live (v1beta) mediante una
interfaz web "Walkie-Talkie", eliminando las variables de red de Twilio
y ngrok para aislar el handshake con la API de Google.

---

## 2. Arquitectura Técnica

### 2.1. App Django `test_live`

- **URL base:** `/test/walkie-talkie/`
- **App registrada** en `INSTALLED_APPS` de `settings.py`.
- **Rutas:** `path('test/', include('test_live.urls'))` en el core.

### 2.2. Backend

- **`test_live/services.py`** — `GeminiLiveProbe`:
  - SDK `google-genai` v1.68.0+.
  - Endpoint API: `v1beta`.
  - Audio format: PCM Linear 16-bit a 16000Hz.
  - Primer frame: `LiveConnectConfig`.
  - `asyncio.Event` que bloquea el flujo hasta recibir `setup_complete`.
  - `self.is_api_ready` (booleano para control de UI).
- **Modelos:** `LiveTestLog` para auditar latencias de handshake.
- **Vistas:** `ProcessAudioView` — recibe blobs de audio vía POST,
  devuelve respuesta binaria de la IA.

### 2.3. Frontend — Walkie-Talkie

- **Template:** `walkie_talkie.html`
- **Lógica JS:** `MediaRecorder` API para captura de audio
  (`audio/webm` o `audio/ogg`, conversión a `L16;rate=16000`
  en backend si es necesario).
- **Botonería:**
  1. `INICIAR SESIÓN` — dispara el handshake con Google.
  2. `HABLAR` (Hold to Talk) — captura y envía el audio al soltar.
  3. `DETENER` — cierra el socket de Google limpiamente.
- **Mime-Type:** `audio/L16;rate=16000`.

---

## 3. Hoja de Ruta

### Tarea 1 — Registro e Inicialización
- Estado: PENDIENTE

### Tarea 2 — Implementación de la Sonda (v1beta)
- Estado: PENDIENTE

### Tarea 3 — Construcción del Interfaz de Audio
- Estado: PENDIENTE

---

## 4. Registro de Sesiones

| Sesión | Fecha | Resumen |
|---|---|---|
| — | — | Sin sesiones registradas aún. |

---

## 5. Hoja de Ruta para la Siguiente Sesion

### Tarea 1 — Registro e Inicialización
1. Ejecutar `python manage.py startapp test_live`.
2. Registrar la app en `INSTALLED_APPS` de `settings.py`.
3. Mapear `path('test/', include('test_live.urls'))` en el core.

### Tarea 2 — Implementación de la Sonda (v1beta)
1. Codificar `test_live/services.py` con SDK `google-genai` v1.68.0+.
2. Asegurar que el primer frame enviado sea el `LiveConnectConfig`.
3. Implementar `asyncio.Event` que bloquee hasta recibir `setup_complete`.

### Tarea 3 — Construcción del Interfaz de Audio
1. Crear la vista que renderice el Walkie-Talkie.
2. Desarrollar JS para capturar audio `audio/webm` o `audio/ogg`
   y convertirlo a `L16;rate=16000`.
