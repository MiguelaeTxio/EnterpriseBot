# ANEXO HITO 1: VALIDACIÓN E IMPLEMENTACIÓN DE VOZ CONVERSACIONAL
# ESTADO: EN PROGRESO (Fase: Estabilización de Protocolo Live 2026)

## 1. FUENTE DE LA VERDAD (LEY SUPREMA)
Este documento es la única fuente de verdad. El modelo entrante tiene PROHIBIDO escribir una sola línea de código sin realizar antes una inmersión integral en las clases de unión (Union types) del SDK google-genai (v1alpha) de marzo de 2026. Se prohíbe el método de ensayo y error.

## 2. BITÁCORA FORENSE DE ERRORES (MARZO 2026)
Para evitar la repetición de fallos, el modelo debe conocer las colisiones técnicas ocurridas:
- **Error 400:** `response_mime_type` solo acepta texto en la API de Chat. Prohibido usar audio/wav allí.
- **Error 1007 (Invalid Frame):** Se dispara si se declara `response_mime_type` en LiveConnectConfig para audio, o si la jerarquía de `media_chunks` es incorrecta.
- **Error 1011 (Internal Error):** Ocurre por Setup Frames incompletos. Requiere obligatoriamente `response_modalities=["AUDIO"]`.
- **TypeError:** `AsyncSession.send()` NO acepta el argumento `end_of_batch` en sesiones Live.
- **Deprecation:** `generation_config` debe estar aplanado directamente en la raíz de `LiveConnectConfig`.

## 3. HOJA DE RUTA PARA LA SIGUIENTE SESIÓN (ROADMAP)
El modelo debe seguir este orden exacto:

### Tarea 0: Auditoría Estructural del SDK
1. Investigar la firma exacta de `LiveClientRealtimeInput`. Confirmar si `media_chunks` es una lista de `Blob` o de `Part`.
2. Verificar el esquema de `LiveServerMessage` para la captura de audio en `stream_from_google`.

### Tarea 1: Estabilización de Servicios (`vox_bridge/services.py`)
1. Implementar `connect()` con `response_modalities=["AUDIO"]` y `system_instruction` como objeto `Content`.
2. Asegurar que `send_audio_frame` envíe la jerarquía binaria exacta que no provoque el error 1007.

### Tarea 2: Validación de Audio (Prueba de Ignición)
1. Lanzar el Bridge en el puerto 8081.
2. Levantar túnel ngrok con inyección de entorno (`python -m dotenv`).
3. Realizar llamada al terminal +34688360595 y confirmar audibilidad en castellano.

## 4. ESPECIFICACIONES TÉCNICAS MANDATORIAS
- Puerto local: 8081 (El 8080 presenta bloqueos de kernel).
- Versión API: v1alpha.
- Idioma: Castellano de España.
