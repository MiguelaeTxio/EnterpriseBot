# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/DOCS/MAINS/ATTACHEDS/DOCS_ATTACHED_2_ANNEX_V01/V01DOC_VOICE_SIDECAR_ARCHITECTURE.md

# ESPECIFICACIÓN TÉCNICA: ARQUITECTURA DE VOZ SIDECAR (MARZO 2026)

## 1. CONCEPTO / CONCEPT
Debido a las limitaciones de PythonAnywhere con WebSockets en el servidor web principal (WSGI), se implementa un modelo de "Sidecar". Un proceso independiente gestiona el flujo de audio binario mientras Django gestiona la persistencia y lógica de negocio.

## 2. ESPECIFICACIONES DEL PUENTE / BRIDGE SPECS
- Protocolo: WSS (Secure WebSockets).
- Formato de Audio: G.711 mu-law (8-bit, 8000Hz, Mono).
- Motor de IA: Gemini 3.1 Pro (Streaming Multimodal).
- Latencia Objetivo: < 400ms.

## 3. FLUJO DE LLAMADA
1. Twilio -> Webhook Inbound (Django).
2. Django -> TwiML <Connect><Stream>.
3. Twilio -> WebSocket Stream -> voice_sidecar_bridge.py.
4. Bridge -> Gemini API (Bidirectional Stream).
