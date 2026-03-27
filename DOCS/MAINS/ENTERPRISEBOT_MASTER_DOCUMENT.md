# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/DOCS/MAINS/ENTERPRISEBOT_MASTER_DOCUMENT.md
# Documento Maestro: Proyecto EnterpriseBot
---
## 1. Visión General del Proyecto
EnterpriseBot es una solución omnicanal de nivel empresarial orientada a la orquestación de inteligencia artificial conversacional en tiempo real. El objetivo es proporcionar una experiencia de usuario fluida, humana y de baja latencia a través de canales de voz y mensajería, utilizando modelos de lenguaje de última generación (Gemini 3.1 Pro) para la toma de decisiones y respuesta dinámica.
---
## 2. Arquitectura Técnica (Pivotaje Estratégico a Twilio)
*   **Entorno Virtual:** EnterpriseBot_venv (Python 3.10)
*   **Framework Base:** Django (Configurado para gestión de WebSockets y tareas asíncronas)
*   **Canales de Comunicación:**
    - **Voz:** Twilio Programmable Voice / Media Streams (WebSockets)
    - **Mensajería:** WhatsApp Business API (Meta)
*   **Motor de IA:** Google Gemini (models/gemini-3.1-pro-preview)
---
## 3. Hoja de Ruta Estratégica
### Hito 0: Inicialización de Estructura e Infraestructura (COMPLETADO)

### Hito 1: Validación de Infraestructura de Voz en Tiempo Real (EN PROGRESO)
(Ver anexo `ENTERPRISEBOT_ATTACHED_MILESTONE_V01.md`)
- Desestimación de MundoSMS por limitaciones síncronas e inestabilidad de API.
- Implementación de puente con Twilio Media Streams (Audio binario sobre WSS).
- Pruebas de latencia y orquestación de audio con Gemini.

### Hito 2: Prototipo de Chatbot WhatsApp (PENDIENTE)

### Hito 3: Integración de Voice Bot Conversacional (PENDIENTE)
- Gestión de interrupciones (Barge-in) y cancelación de eco.
- Persistencia de interacciones de voz en tiempo real.

---
## 4. Sistema de Ruegos y Preguntas (Stand-by)
