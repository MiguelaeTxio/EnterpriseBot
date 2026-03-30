# ANEXO HITO 1: VALIDACIÓN E IMPLEMENTACIÓN DE VOZ CONVERSACIONAL
# ESTADO: EN PROGRESO (Fase: Validación de Audibilidad y Pivotaje Lingüístico)

## 1. FUENTE DE LA VERDAD PARA LA PRÓXIMA SESIÓN
Este documento es la LEY SUPREMA. El modelo entrante debe ignorar cualquier suposición y ceñirse a los hechos técnicos aquí descritos. La infraestructura de red (ngrok v3 + Always-on Task) está verificada y operativa. El error de sintaxis del SDK de Google GenAI (`unexpected keyword argument 'contents'`) ha sido corregido usando `message=`.

## 2. ESTADO TÉCNICO AL CIERRE (HECHOS CONSUMADOS)
*   **Identidad de Red:** Túnel ngrok activo en `https://deistical-rosalia-detonative.ngrok-free.dev`.
*   **Señalización HTTP:** Django despacha TwiML dinámico que apunta al WebSocket `wss://` correcto.
*   **Modo de Estabilidad:** El sistema está configurado en **INGLÉS** y con salida **WAV DIRECTA** (sin transcodificación audioop activa) para garantizar el éxito del primer contacto sonoro.
*   **Terminal de Prueba:** El disparador de llamadas está fijado en el número **+34688360595**.

## 3. HOJA DE RUTA TÉCNICA EXHAUSTIVA (PRÓXIMA SESIÓN)
El modelo entrante debe seguir este orden de operaciones sin desviaciones:

### Tarea 1: Prueba de Fuego (Ignición Inicial)
1.  **Ejecución:** Lanzar el script de auditoría: `/home/MiguelAeTxio/PROJECTS/EnterpriseBot/audit_voice_session.sh`.
2.  **Verificación:** Descolgar el teléfono y confirmar la recepción del saludo inicial en INGLÉS: "Hello, I am EnterpriseBot, how can I help you?".
3.  **Auditoría de Logs:** Verificar en `bridge_runtime.log` que los eventos `[EVENT]` y `[STREAM]` fluyen sin excepciones `TypeError`.

### Tarea 2: Pivotaje Lingüístico al Castellano
1.  **Refactorización:** Tras el éxito de la Tarea 1, modificar `vox_bridge/services.py`.
2.  **Instrucción de Sistema:** Cambiar el prompt a: "Eres EnterpriseBot, asistente oficial. Responde SIEMPRE en CASTELLANO de España. Sé conciso y profesional."
3.  **Prueba Inbound:** Realizar llamada entrante al número oficial para verificar la persistencia de la personalidad en castellano.

### Tarea 3: Re-activación de Transcodificación (Opcional)
1.  Si Twilio presenta latencia por el tamaño del WAV, implementar nuevamente `audioop` pero usando la firma corregida del SDK: `self.session.send_message(message=[types.Part.from_bytes(...)])`.

## 4. ESPECIFICACIONES DE IMPLEMENTACIÓN
*   **Carga de Entorno:** Mandatorio usar `python -m dotenv -f /home/MiguelAeTxio/PROJECTS/EnterpriseBot/.env run` para cualquier ejecución de script.
*   **Logs:** Mantener `flush=True` en todos los procesos para visibilidad en el Dashboard.
