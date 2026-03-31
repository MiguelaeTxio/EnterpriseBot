# ANEXO HITO 2: VALIDACIÓN Y AISLAMIENTO DE DIAGNÓSTICO (test_live)
# ESTADO: EN PROGRESO (Fase: Creación de Sonda Multimodal)
# FECHA: 2026-03-31
# LEY SUPREMA PARA LA PRÓXIMA SESIÓN

---

## 1. OBJETIVO TÉCNICO / TECHNICAL OBJECTIVE
Debido a la opacidad en el apretón de manos (handshake) observado en el Bridge de Twilio, se requiere la creación de una aplicación Django aislada denominada `test_live`. El propósito es validar la audibilidad de Gemini Live (v1beta) mediante una interfaz web "Walkie-Talkie", eliminando las variables de red de Twilio y ngrok.

## 2. ESPECIFICACIÓN DE LA APLICACIÓN `test_live`
La aplicación debe implementarse con rigor industrial bajo el modelo de "Sonda de Diagnóstico".

### A. Estructura de Backend (Django)
- **Modelos:** No se requiere persistencia compleja, pero se debe incluir una clase `LiveTestLog` para auditar latencias de handshake.
- **Servicios (`services.py`):** Implementación de `GeminiLiveProbe`.
    - **Requisito:** Espera síncrona del mensaje `setup_complete` de Google.
    - **Endpoint API:** `v1beta`.
    - **Audio Format:** PCM Linear 16-bit a 16000Hz.
- **Vistas (`views.py`):** Endpoint `ProcessAudioView` que reciba blobs de audio vía POST y devuelva la respuesta binaria de la IA.

### B. Interfaz "Walkie-Talkie" (Frontend)
- **Template:** `walkie_talkie.html`.
- **Lógica JS:** Uso de `MediaRecorder` API para captura de audio.
- **Botonería:** 
    1. `INICIAR SESIÓN`: Dispara el handshake con Google.
    2. `HABLAR` (Hold to Talk): Captura y envía el audio al soltar.
    3. `DETENER`: Cierra el socket de Google limpiamente.

## 3. HOJA DE RUTA DETALLADA (LEY TÉCNICA)
El modelo entrante DEBE seguir estos pasos sin desviaciones:

### Tarea 1: Registro e Inicialización
1. Ejecutar `python manage.py startapp test_live`.
2. Registrar la app en `INSTALLED_APPS` de `settings.py`.
3. Mapear `path('test/', include('test_live.urls'))` en el core.

### Tarea 2: Implementación de la Sonda (v1beta)
1. Codificar `test_live/services.py` con el SDK `google-genai` v1.68.0+.
2. Asegurar que el primer frame enviado sea el `LiveConnectConfig`.
3. Implementar un `asyncio.Event` que bloquee el flujo hasta recibir `setup_complete`.

### Tarea 3: Construcción del Interfaz de Audio
1. Crear la vista que renderice el Walkie-Talkie.
2. Desarrollar el script de JavaScript para capturar audio `audio/webm` o `audio/ogg` y convertirlo (si es necesario en el backend) a `L16;rate=16000`.

## 4. DEFINICIÓN DE VARIABLES Y LÓGICA
- **URL de Prueba:** `/test/walkie-talkie/`
- **Variable de Estado:** `self.is_api_ready` (Booleano para control de UI).
- **Mime-Type Recomendado:** `audio/L16;rate=16000`.

---
