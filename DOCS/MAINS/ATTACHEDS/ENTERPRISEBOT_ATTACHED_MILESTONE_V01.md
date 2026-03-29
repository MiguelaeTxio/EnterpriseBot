# ANEXO HITO 1: VALIDACIÓN E IMPLEMENTACIÓN DE VOZ CONVERSACIONAL
# ESTADO: EN PROGRESO (Fase: Estabilización de Señalización y Audio)
# PROYECTO: EnterpriseBot
# FECHA DE CIERRE: 2026-03-29

---

## 1. FUENTE DE LA VERDAD PARA LA PRÓXIMA SESIÓN
Este documento es la LEY SUPREMA. El modelo entrante debe ignorar cualquier suposición y ceñirse estrictamente a los hechos técnicos aquí descritos. El objetivo prioritario es resolver la discrepancia de cuentas detectada y validar el flujo de audio bidireccional.

## 2. ESTADO TÉCNICO AL CIERRE DE LA SESIÓN (HECHOS CONSUMADOS)
*   **Infraestructura Always-on Task:** Activa y estable bajo el comando `/home/MiguelAeTxio/.virtualenvs/EnterpriseBot_venv/bin/python -u /home/MiguelAeTxio/PROJECTS/EnterpriseBot/voice_orchestrator.py`.
*   **Conectividad:** Túnel ngrok v3.37.3 operativo. El orquestador inyecta el `authtoken` por CLI. Última URL verificada: `https://deistical-rosalia-detonative.ngrok-free.dev`.
*   **Motor de Voz:** `voice_sidecar_bridge.py` escuchando en el puerto 8080. Refactorizado para protocolo Twilio (JSON + Base64 PCMU).
*   **Django Webhook:** `InboundCallView` en `vox_bridge/views.py` refactorizado para auto-descubrir la URL de ngrok vía API local (127.0.0.1:4040).
*   **Dependencias:** Entorno virtual sincronizado con `twilio` y `requests`. `requirements.in` actualizado y comentado.
*   **Log System:** Transparencia total activada (flush=True). Salida directa al Dashboard de PythonAnywhere.

## 3. HALLAZGO CRÍTICO (BLOQUEO ACTUAL)
Se ha detectado una discrepancia de Identidad (Account SID):
*   **En el servidor (.env):** AC67757db0d7ba0951546bf152b8cf9b1f
*   **En la consola web de Twilio:** ACd8fd956e126840342eaa2d201baed1fd
Esto provoca que las llamadas no sean visibles en la consola web y que la API devuelva errores de acceso al intentar disparar llamadas salientes desde el script de validación.

## 4. HOJA DE RUTA TÉCNICA EXHAUSTIVA (PRÓXIMA SESIÓN)

### Tarea 1: Sincronización de Identidad de Cuenta
1.  **Auditar el .env:** Corregir `TWILIO_ACCOUNT_SID`, `TWILIO_API_KEY_SID` y `TWILIO_API_KEY_SECRET` para que coincidan con la cuenta activa donde reside el número +1 260 346 6780.
2.  **Verificación de Geo-Permissions:** Confirmar que la cuenta correcta tiene activado "Spain (+34)" en los permisos de voz.

### Tarea 2: Validación del Disparador Saliente
1.  Ejecutar el script `trigger_outbound_call.py` (usando el SDK oficial de Twilio).
2.  Confirmar la recepción de llamada en el terminal +34 688 36 05 95.

### Tarea 3: Prueba de Estrés de Audio
1.  Establecer conversación con Gemini 3.1 Pro.
2.  Monitorear el log horizontal para detectar eventos `[EVENT] media`.
3.  Ajustar latencia si el RTT supera los 500ms.

## 5. ESPECIFICACIONES DE IMPLEMENTACIÓN
*   **Protocolo de Logs:** Queda terminantemente prohibido volver a redireccionar logs a archivos físicos durante la fase de depuración.
*   **Consultas a ngrok:** Django debe seguir consultando la API local de ngrok para mantener la resiliencia ante reinicios del túnel.
