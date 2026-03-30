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
    - **Prohibición:** Queda terminantemente prohibido el uso de modelos de la familia "Pro" no-Live para el flujo de voz, debido a limitaciones de latencia y falta de soporte para bidireccionalidad en tiempo real.
*   **Middleware de Audio (Sidecar):** Capa de transcodificación obligatoria entre Twilio (G.711 mu-law) y Gemini Live (PCM Linear 16-bit).

## 3. Hoja de Ruta Estratégica
### Hito 1: Validación de Infraestructura de Voz en Tiempo Real (EN PROGRESO)
(Ver anexo `ENTERPRISEBOT_ATTACHED_MILESTONE_V01.md`)
- Implementación de puente con Twilio Media Streams (Audio binario sobre WSS).
- Estabilización del flujo de transcodificación mu-law -> PCM.
- Orquestación de audio nativo con Gemini 3.1 Live.

---
## 4. Sistema de Ruegos y Preguntas (Stand-by)
