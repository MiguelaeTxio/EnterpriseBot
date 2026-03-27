# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/DOCS/MAINS/ATTACHEDS/ENTERPRISEBOT_ATTACHED_MILESTONE_V01.md

# ANEXO HITO 1: Validación e Implementación de Infraestructura de Voz
# ESTADO: EN PROGRESO (Fase F: Implementación del Bridge de Voz asíncrono)
# SESIÓN ANTERIOR: AAAE (Configuración de Infraestructura Twilio y Blindaje de Entorno)
# PRÓXIMA SESIÓN: AAAF (Construcción del Consumer de WebSockets y Enrutamiento ASGI)

---

## 1. FUENTE DE LA VERDAD PARA LA SESIÓN AAAF
Este documento es la LEY SUPREMA para la próxima sesión. El desarrollo debe ceñirse estrictamente a esta hoja de ruta y a la guía técnica satélite V01DOC_TWILIO_INFRASTRUCTURE_GUIDE.md. Queda terminantemente prohibido inventar o suponer lógica no descrita en estos documentos.

## 2. ESTADO TÉCNICO AL CIERRE DE LA SESIÓN ACTUAL
- **Infraestructura Externa:** Account SID, API Key SID y Secret verificados y operativos en Twilio.
- **Identidad Telefónica:** Número +1 478 223 8292 vinculado a la TwiML App "EnterpriseBot_Voice_Bridge_App".
- **Entorno del Servidor:** Archivo .env actualizado con credenciales de Twilio; variables de MundoSMS depreciadas mediante comentarios.
- **Configuración Webhook:** Endpoint definido en https://MiguelAeTxio.pythonanywhere.com/vox/inbound/

## 3. HOJA DE RUTA TÉCNICA EXHAUSTIVA (Sesión AAAF)

### Tarea 1: Implementación del Consumer de Voz (vox_bridge/consumers.py)
Desarrollar la lógica asíncrona para la gestión del flujo binario de Twilio.
- **Clase:** VoiceConsumer(AsyncWebsocketConsumer).
- **Evento "connect":** Aceptar la conexión y preparar buffers de audio.
- **Evento "receive":** 
    - Tipo "start": Capturar el "streamSid" para permitir el envío de audio de vuelta (Outbound).
    - Tipo "media": Decodificar el payload Base64 (G.711 mu-law) y enviarlo al stream de Gemini 3.1 Pro.
- **Evento "disconnect":** Cerrar la sesión de Gemini y registrar la duración en CallInteraction.

### Tarea 2: Configuración del Enrutamiento ASGI (enterprise_core/asgi.py)
Establecer el protocolo de comunicación para WebSockets.
- **ProtocolTypeRouter:** Mapear el protocolo "websocket" mediante URLRouter.
- **Ruta:** path('media-stream', consumers.VoiceConsumer.as_view()).

### Tarea 3: Vista de Inicialización TwiML (vox_bridge/views.py)
Programar el receptor del Webhook POST de Twilio.
- **Función:** inbound_voice(request).
- **Respuesta:** TwiML XML que contenga <Response><Connect><Stream url="wss://{{host}}/media-stream" /></Connect></Response>.
- **Seguridad:** Uso obligatorio de @csrf_exempt.

## 4. ESPECIFICACIONES TÉCNICAS (NO NEGOCIABLES)
- Formato de Audio: G.711 mu-law (8000 Hz, 8-bit, Mono).
- Latencia Objetivo: < 500ms para respuesta de IA.
