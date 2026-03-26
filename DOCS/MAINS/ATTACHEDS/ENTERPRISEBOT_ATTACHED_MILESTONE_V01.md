# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/DOCS/MAINS/ATTACHEDS/ENTERPRISEBOT_ATTACHED_MILESTONE_V01.md

# ANEXO HITO 1: Test de prueba inicial y configuración de hitos
# ESTADO: EN PROGRESO (Fase D: Rectificación del Puente y Validación Real)

---

## 1. FUENTE DE LA VERDAD PARA LA SESIÓN AAAD
Este documento es la LEY SUPREMA para la próxima sesión. El sistema ha sido configurado con éxito en su capa de Back-end (Django), pero el puente de telecomunicaciones con MundoSMS ha sido rechazado por un error de validación XML (Error API 3).

## 2. ESTADO TÉCNICO AL CIERRE DE AAAC
- **Back-end Django**: `vox_bridge/views.py` refactorizado con máquina de estados síncrona.
- **Servicios**: `vox_bridge/services.py` implementado con AudioHandlingService y GeminiAudioService (SDK 2026).
- **Entorno**: Archivo `.env` actualizado con la variable `MUNDOSMS_PILOT_NUMBER=34858150405`.
- **Bloqueo Actual**: El script `activate_bridge.py` devuelve `ERROR API: 3 - New XML not accepted`. El motor XML de MundoSMS rechaza la declaración de cabecera y requiere el uso de CDATA para la URL.

## 3. HOJA DE RUTA TÉCNICA (Sesión AAAD - EXHAUSTIVA)

### Tarea 1: Refactorización Quirúrgica de `activate_bridge.py`
Se debe modificar la variable `dialplan_xml` en el script para eliminar la cabecera XML y encapsular la URL en un bloque CDATA para evitar conflictos de caracteres.
- **Estructura Requerida**: 
  `<dialplan><http-request method="post" mode="sync"><![CDATA[https://enterprisebot-miguelaetxio.pythonanywhere.com/api/vox/inbound/]]></http-request></dialplan>`

### Tarea 2: Activación y Verificación del Puente
1. Ejecutar `python -m dotenv run python activate_bridge.py`.
2. Verificar que la respuesta de la API de MundoSMS devuelva `status_code: 0`.

### Tarea 3: Prueba de Fuego Real
1. Realizar llamada al `+34 858 150 405`.
2. Verificar flujo completo: Saludo -> Grabación -> Proceso Gemini -> Transferencia.
3. Auditar registros en el modelo `CallInteraction` (MySQL).

## 4. VARIABLES Y CONSTANTES OBLIGATORIAS PARA AAAD
- DID: `34858150405`
- WEBHOOK_URL: `https://enterprisebot-miguelaetxio.pythonanywhere.com/api/vox/inbound/`
- MODELO IA: `models/gemini-3.1-pro-preview`

---
## FIN DE LA LEY SUPREMA PARA AAAD
