# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/DOCS/MAINS/ATTACHEDS/ENTERPRISEBOT_ATTACHED_MILESTONE_V01.md

# ANEXO HITO 1: Test de prueba inicial y configuración de hitos
# ESTADO: EN PROGRESO (Fase D: Conexión de Audio e Integración Final)

---

## 1. FUENTE DE LA VERDAD PARA LA SESIÓN AAAC
Este documento es la LEY SUPREMA para la próxima sesión. Ningún modelo podrá suponer comportamientos no descritos aquí.

## 2. ESTADO TÉCNICO AL CIERRE DE AAAB
- **Infraestructura:** Django 5.2.12 operativo en `enterprisebot-miguelaetxio.pythonanywhere.com`.
- **Base de Datos:** MySQL `MiguelAeTxio$enterprisebot` migrada y conectada con persistencia activa.
- **Cerebro IA:** `GeminiAudioService` implementado en `vox_bridge/services.py` usando exclusivamente el modelo `models/gemini-2.0-pro-exp-02-05`.
- **Webhook:** Endpoint `/api/vox/inbound/` funcional, devolviendo el XML inicial de saludo y grabación de 5s.

## 3. HOJA DE RUTA TÉCNICA (Sesión AAAC - EXHAUSTIVA)

### Fase D: El Cierre del Bucle Conversacional
El objetivo es procesar el audio que MundoSMS envía tras la ejecución del comando `<record>`.

1. **Implementación de AudioHandlingService (`vox_bridge/services.py`):**
   - Crear función `download_remote_audio(url)` utilizando la librería `requests`.
   - El audio debe guardarse temporalmente en `/home/MiguelAeTxio/SWAP/` con un nombre basado en el `call_id`.
   - Debe manejar errores de red y validar que el archivo es un audio válido.

2. **Refactorización de la Vista Discriminadora (`vox_bridge/views.py`):**
   - **Lógica de Bifurcación:** La vista debe detectar si la petición trae el parámetro `[LAST_RECORD]` (enviado por MundoSMS tras grabar).
   - **Flujo de Audio:** 
     a. Si no hay audio -> Enviar XML de saludo (ya implementado).
     b. Si hay audio -> 
        1. Descargar audio al SWAP.
        2. Invocar `GeminiAudioService.classify_call_intent(path)`.
        3. Eliminar archivo temporal del SWAP.
        4. Generar respuesta XML dinámica.

3. **Definición de Extensiones de Redirección:**
   - Según la respuesta de Gemini, el XML devuelto debe ser:
     - VENTAS: `<dialplan><call destination="EXTENSION_VENTAS"/></dialplan>`
     - SOPORTE: `<dialplan><call destination="EXTENSION_SOPORTE"/></dialplan>`
     - ADMINISTRACION: `<dialplan><call destination="EXTENSION_ADMIN"/></dialplan>`
     - ERROR_AMBIGUO: Reproducir un mensaje de disculpa y colgar o derivar a recepción general.

4. **Registro de la Interacción:**
   - Cada ciclo debe guardar en el modelo `CallInteraction` los datos de la llamada: ID, teléfono, URL del audio, transcripción y decisión final.

### 4. VARIABLES Y CONSTANTES OBLIGATORIAS PARA AAAC
- MODEL: `models/gemini-2.0-pro-exp-02-05`
- TEMP_STORAGE: `/home/MiguelAeTxio/SWAP/`
- DEPARTAMENTOS: VENTAS, SOPORTE, ADMINISTRACION.

---
## FIN DE LA LEY SUPREMA PARA AAAC
