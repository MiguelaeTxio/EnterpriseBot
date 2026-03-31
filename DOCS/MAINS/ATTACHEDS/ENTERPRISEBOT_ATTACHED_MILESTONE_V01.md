# ANEXO HITO 1: INFRAESTRUCTURA DE VOZ (SIDECAR BRIDGE)
# ESTADO: REACTIVADO (EN PROGRESO)
# FECHA: 2026-03-31
# LEY SUPREMA PARA LA PRÓXIMA SESIÓN

---

## 1. DIRECTRIZ TÉCNICA VINCULANTE (MARZO 2026) - INMUTABLE
Queda terminantemente prohibido el uso de datos de entrenamiento del modelo para la interacción con el SDK de Google GenAI. La implementación debe regirse exclusivamente por el estándar de Marzo 2026 validado en la sesión actual:

*   **MODELO ESTÁNDAR:** `models/gemini-3.1-flash-live-preview` (Naturaleza Multimodal Live).
*   **ENDPOINT:** `v1beta` (Mandatorio para AI Studio / API KEY).
*   **MÉTODO DE ENVÍO:** `send_realtime_input`. Queda prohibido `send_client_content` para mensajería activa.
*   **ESQUEMA DE MENSAJE:** No se debe incluir el atributo `role` en los envíos de contenido.
*   **PARÁMETROS DE CONTROL:** Uso de `turn_complete=True`.
*   **AUDIO OUTPUT:** 24000Hz PCM (Requiere remuestreo a 8000Hz para Twilio).

## 2. ARQUITECTURA DE SIDECAR (AlwaysOn Task)
Debido a la incompatibilidad del proxy uWSGI con WebSockets persistentes, la orquestación de la IA se delega en la **AlwaysOn Task** ya existente.

### Tarea 1: Adaptación del Voice Orchestrator Daemon
1.  Modificar el script de la AlwaysOn Task para aplicar el **Patrón Maestro v7**.
2.  Implementar la escucha de eventos desde la aplicación Django para disparar llamadas salientes o responder a flujos de Media Streams entrantes.
3.  Configurar el loop asíncrono para manejar la concurrencia de múltiples llamadas.

### Tarea 2: Puente de Comunicación Django <-> Sidecar
1.  Establecer un canal de señalización (vía archivos en `SWAP` o Redis si está disponible) para que los webhooks de Twilio en `vox_bridge` informen al Sidecar del `stream_sid` activo.
2.  Asegurar que el Sidecar sea capaz de leer el flujo binario de audio de Twilio y retransmitirlo mediante `send_realtime_input(audio=...)`.

## 3. HOJA DE RUTA DETALLADA
1.  **Validación de Salida:** Verificar la AlwaysOn Task con el script `test_connectivity_v7.py`.
2.  **Transcodificación:** Implementar en el Sidecar la conversión G.711 mu-law (8kHz) <-> PCM (24kHz).
3.  **Bidi Test:** Realizar la primera llamada real de Twilio conectada al Sidecar.

---
