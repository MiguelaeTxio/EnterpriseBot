# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/DOCS/MAINS/ATTACHEDS/ENTERPRISEBOT_ATTACHED_MILESTONE_V01.md

# ANEXO HITO 1: Test de prueba inicial y configuración de hitos
# ESTADO: EN PROGRESO

---

## 1. FUENTE DE LA VERDAD PARA LA SESIÓN AAAB
Este documento rige la lógica de la próxima sesión. El modelo no podrá suponer comportamientos no descritos aquí.

## 2. REFERENCIAS TÉCNICAS
- **Documentación Base:** API MundoSMS VozPush v0.30.
- **Arquitectura:** Inbound AI IVR (Recepcionista Inteligente).
- **IA:** Google Gemini (models/gemini-1.5-flash para latencia mínima).

## 3. HOJA DE RUTA TÉCNICA (Sesión AAAB)

### Fase A: Inicialización del Proyecto Django
1. Activar entorno virtual: `workon EnterpriseBot_venv`.
2. Crear archivo `requirements.in` con: `django`, `python-dotenv`, `google-generativeai`, `requests`.
3. Ejecutar `pip install -r requirements.txt` (tras compilar).
4. Crear proyecto `enterprise_core` y aplicación `vox_bridge`.

### Fase B: Configuración de Variables de Entorno (.env)
Se deben configurar las siguientes claves obligatorias:
- `MUNDOSMS_USER`: Usuario de la plataforma MundoSMS.
- `MUNDOSMS_PASS`: Contraseña de la API.
- `GEMINI_API_KEY`: Clave para la inferencia de IA.

### Fase C: Implementación del Webhook "Discriminador"
1. **URL de Entrada:** `/api/vox/inbound/`
2. **Lógica de la Vista (`InboundCallView`):**
   - Debe aceptar peticiones HTTP de MundoSMS.
   - Debe generar un XML de respuesta inmediato para "saludar" y "grabar".
3. **Flujo de Respuesta XML Inicial:**
   ```xml
   <?xml version="1.0" encoding="UTF-8"?>
   <dialplan>
       <read voice="es-es-f1">Bienvenido a Enterprise Bot. Por favor, diga su nombre y el departamento con el que desea hablar tras la señal.</read>
       <record duration="5" b_beep="1" timeout_silence="2"/>
   </dialplan>
   ```

### Fase D: Simulación y Verificación
1. Uso de `curl` para simular la petición de MundoSMS al Webhook local/remoto.
2. Verificación de que el XML devuelto cumple estrictamente el esquema de la API v0.30.

## 4. VARIABLES Y CONSTANTES OBLIGATORIAS
- APP_NAME: `vox_bridge`
- DEFAULT_VOICE: `es-es-f1` (Sara)
- RECORD_DURATION: `5` segundos.

---
## FIN DE LA LEY SUPREMA PARA AAAB
