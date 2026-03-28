# ANEXO HITO 1: VALIDACIÓN E IMPLEMENTACIÓN DE VOZ CONVERSACIONAL
# ESTADO: EN PROGRESO (Fase: Pivotaje a Señalización Internacional)
# PROYECTO: EnterpriseBot

---

## 1. FUENTE DE LA VERDAD PARA LA PRÓXIMA SESIÓN
Este documento es la LEY SUPREMA. El modelo de IA en la siguiente sesión debe ignorar cualquier configuración de Twilio-US o Voximplant anterior y centrarse exclusivamente en la reactivación de Twilio mediante numeración internacional compatible con cuentas Trial.

## 2. ESTADO TÉCNICO AL CIERRE DE LA SESIÓN ACTUAL
- **Infraestructura de Servidor:** Always-on Task activa y estable en PythonAnywhere.
- **Motor de Voz:** `voice_sidecar_bridge.py` operando en "Modo Universal" (soporta JSON y Frames Binarios RAW).
- **Socket:** Escucha activa en el puerto 8080.
- **Integración IA:** Gemini 3.1 Pro estabilizado tras inyectar `GEMINI_API_KEY` en `settings.py`.
- **Dependencias:** Entorno virtual sincronizado (V1.2) incluyendo `mysqlclient`, `websockets`, `google-genai` y `python-dotenv`.
- **Logs:** Redirección configurada hacia `bridge_runtime.log`.

## 3. HOJA DE RUTA TÉCNICA EXHAUSTIVA (PRÓXIMA SESIÓN)

### Tarea 1: Despliegue de Conectividad (Túnel)
- Ejecutar el script de instalación de **ngrok** en el servidor para obtener una URL `wss://` pública.
- El puerto de origen del túnel debe ser el **8080**.

### Tarea 2: Adquisición de Numeración Internacional (Twilio)
- Investigar la disponibilidad de números en regiones con menos restricciones trial (ej: **Alemania +49**).
- Realizar la compra del número y verificar el cumplimiento de los "Geo-Permissions" para permitir el tráfico hacia España (+34).

### Tarea 3: Reconfiguración de Webhooks en Django
- Actualizar `vox_bridge/views.py` para que la respuesta TwiML utilice la URL dinámica del túnel.
- Ajustar el enrutador de señalización para que Telnyx/Voximplant (pausados) cedan el paso a la nueva señalización de Twilio.

## 4. ESPECIFICACIONES DE IMPLEMENTACIÓN
- **Protocolo de Audio:** G.711 mu-law (PCMU), 8000 Hz, Mono.
- **Modo de Ejecución:** El bridge debe lanzarse siempre con el flag `-u` (unbuffered) para auditoría en tiempo real.
