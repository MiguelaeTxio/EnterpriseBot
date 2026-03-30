# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/DOCS/MAINS/ATTACHEDS/DOCS_ATTACHED_2_ANNEX_V01/V01DOC_VOICE_SIDECAR_ARCHITECTURE.md
# ESPECIFICACIÓN TÉCNICA: ARQUITECTURA DE VOZ SIDECAR (MARZO 2026)

## 1. CONCEPTO / CONCEPT
Debido a las limitaciones de PythonAnywhere con WebSockets, se implementa un modelo de "Sidecar". Este actúa ahora como un Procesador de Señal Digital (DSP) en tiempo real.

## 2. ESPECIFICACIONES DEL PUENTE / BRIDGE SPECS
- **Protocolo:** WSS (Secure WebSockets).
- **Entrada desde Twilio:** G.711 mu-law (8-bit, 8000Hz, Mono).
- **Salida hacia Gemini Live:** PCM Linear (16-bit, 16000Hz, Mono).
- **Motor de IA:** Gemini 3.1 Flash Live (A2A Nativo).

## 3. FLUJO DE LLAMADA Y TRANSCODIFICACIÓN
1. **Twilio -> Sidecar:** Recibe JSON con payload mu-law (Base64).
2. **Sidecar (Middleware):**
    - Decodifica Base64.
    - Transcodifica mu-law -> PCM 16-bit.
    - Resampling 8kHz -> 16kHz.
3. **Sidecar -> Gemini Live:** Envía Blob binario PCM.
4. **Gemini Live -> Sidecar:** Devuelve audio PCM en tiempo real.
5. **Sidecar (Middleware):**
    - Resampling 16kHz -> 8kHz.
    - Transcodifica PCM -> mu-law.
6. **Sidecar -> Twilio:** Envía evento "media" con payload mu-law.
