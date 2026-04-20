# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/DOCS/MAINS/ENTERPRISEBOT_MASTER_DOCUMENT.md
# Documento Maestro: Proyecto EnterpriseBot
---
## 1. Visión General del Proyecto
EnterpriseBot es una solución omnicanal de nivel empresarial orientada a la orquestación de inteligencia artificial conversacional en tiempo real. El objetivo es proporcionar una experiencia de usuario fluida, humana y de baja latencia a través de canales de voz y mensajería.

## 2. Arquitectura Técnica (Pivotaje Estratégico a Multimodal Live API)
*   **Entorno Virtual:** EnterpriseBot_venv (Python 3.10)
*   **Framework Base:** Django (Configurado para gestión de WebSockets y tareas asíncronas)
*   **Motor de IA (ESTÁNDAR OBLIGATORIO):** Gemini 3.1 Live (models/gemini-3.1-flash-live-preview).
    - **Naturaleza:** Arquitectura Stateful (Estado persistente) para streaming A2A (Audio-to-Audio) nativo.
    - **Prohibición:** Queda terminantemente prohibido el uso de modelos de la familia "Pro" no-Live para el flujo de voz.
*   **Middleware de Audio (Sidecar):** Capa de transcodificación obligatoria entre Twilio (G.711 mu-law/A-law) y Gemini Live (PCM Linear 16-bit).

## 3. Hoja de Ruta Estratégica
### Hito 1: Validación de Infraestructura de Voz en Tiempo Real (COMPLETADO)
(Ver anexo `ENTERPRISEBOT_ATTACHED_MILESTONE_V01.md`)
- Implementación de puente con Twilio Media Streams.
- Estabilización del flujo de transcodificación mu-law/A-law -> PCM.
- Orquestación de audio nativo con Gemini Live 2.5 Flash Native Audio (Vertex AI).
- Validación E2E con llamada real confirmada.

### Hito 2: Validación y Aislamiento de Diagnóstico vía Aplicación test_live (COMPLETADO)
(Ver anexo `ENTERPRISEBOT_ATTACHED_MILESTONE_V02.md`)
- Creación de aplicación Django `test_live` para aislamiento de API.
- Implementación de interfaz "Walkie-Talkie" para pruebas directas.
- Auditoría de Handshake de Google GenAI (v1beta) sin dependencias externas.

### Hito 3: IVR Conversacional Configurable desde Producción (COMPLETADO)
(Ver anexo `ENTERPRISEBOT_ATTACHED_MILESTONE_V03.md`)
- Diseño del modelo de datos multiempresa (Company, CompanyUser, Contact, Section,
  PhoneNumber, CallFlow, PresenceStatus, CorporateVoiceProfile, DataCaptureSet).
- Sistema de presencia con gestión de ausencias temporales y persistentes.
- Panel de administración personalizado para empresas cliente (sin acceso al admin Django).
- Motor de inyección dinámica de configuración IVR en LiveConnectConfig.

---
## 4. Directrices Técnicas Vinculantes

Estas directrices son de **OBLIGADO CUMPLIMIENTO** en todas las sesiones
de desarrollo del proyecto. El modelo las carga al inicio de sesión desde
este documento y las aplica sin excepción.

### 4.1. Inteligencia Artificial
- **SDK:** `google-genai 1.69.0`
- **Modelo IVR Conversacional:** `gemini-live-2.5-flash-native-audio`
- **Plataforma:** Vertex AI — autenticación via Service Account JSON
- **Variables de entorno:** `GCP_CREDENTIALS_PATH`, `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION`
- **Protocolo de sesión:** Setup-First via `async with client.aio.live.connect(...)`
- **Voice:** `Aoede` — obligatorio en `speech_config` para modelo de audio nativo
- **VAD servidor:** `disabled=True` (obligatorio para puentes de telefonía)
- **Greeting:** `await session.send_client_content(turns=..., turn_complete=True)`
- **Firma audio SDK 1.69.0:** `await session.send_realtime_input(audio=types.Blob(data=..., mime_type='audio/pcm;rate=16000'))`

### 4.2. Telefonía
- **Twilio SDK Python:** `twilio 9.10.4`
- **Autenticación Twilio:** API Key (TWILIO_API_KEY_SID + TWILIO_API_KEY_SECRET)
- **Transcodificación:** mu-law 8kHz ↔ PCM 16kHz ↔ PCM 24kHz via `audioop`
- **streamSid:** OBLIGATORIO en nivel raíz de cada mensaje `media` saliente

### 4.3. Infraestructura y Framework
- **Framework:** Django `5.2.12`
- **Servidor async:** aiohttp `3.13.5` — puerto `8081`
- **Túnel:** ngrok v3 — API local en puerto `4041`
- **Entorno:** PythonAnywhere WSGI — Python `3.10.5`
- **Entorno virtual:** `EnterpriseBot_venv`
- **Base de datos:** MySQL — `MiguelAeTxio$enterprisebot`
- **Gestión de dependencias:** `pip-tools` (requirements.in → requirements.txt)

### 4.4. Requisito SINE QUA NON
Antes de entregar o implementar cualquier código que involucre servicios
externos o APIs, el modelo **DEBE** actualizarse en línea obligatoriamente
para usar datos actuales de implementación en lugar de datos obsoletos.

### Hito 4: Canal WhatsApp — Chatbot Conversacional y Sistema de Presencia (COMPLETADO)
(Ver anexo `ENTERPRISEBOT_ATTACHED_MILESTONE_V04.md`)
- Integración de WhatsApp como canal bidireccional sobre infraestructura Twilio existente.
- Chatbot conversacional impulsado por Gemini 2.5 Flash (texto) con contexto multiempresa.
- Cierre del bucle de presencia del Hito 3: webhook /api/whatsapp/presence/ y tareas Celery.
- Nueva app Django `whatsapp` con modelos WhatsAppSession, WhatsAppMessage, WhatsAppTemplate.
- Templates Meta gestionados via Content Template Builder (SID prefijo HX).
- Sender +34607961650 registrado y operativo en producción. Validación E2E superada.
- Panel de gestión de templates WhatsApp integrado en /panel/ (Paso 24). COMPLETADO 2026-04-20.

### Hito 5: Arquitectura Omnicanal IVR ↔ WhatsApp (PAUSADO)
(Ver anexo `ENTERPRISEBOT_ATTACHED_MILESTONE_V05.md`)
- Hito híbrido que cierra el ciclo omnicanal completo de EnterpriseBot.
- Línea A — Panel: entrada WhatsApp en sidebar con historial de sesiones activas.
- Línea B — Persistencia IVR: nuevo modelo CallDataCapture vinculado a Section,
  Contact y CallFlow. Los datos capturados por DataCaptureSet persisten en BD.
- Línea C — Puente IVR ↔ WhatsApp: datos capturados por el IVR (nombre, teléfono,
  motivo) se envían vía WhatsApp al contacto referente de la sección antes del
  transfer de llamada. Flujo: IVR captura → persiste en BD → WhatsApp notifica
  al agente interno → transfer ejecutado. Cierre del ciclo omnicanal completo.

## 5. Sistema de Ruegos y Preguntas (Stand-by)
