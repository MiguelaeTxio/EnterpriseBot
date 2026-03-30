# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/DOCS/MAINS/ATTACHEDS/ENTERPRISEBOT_ATTACHED_MILESTONE_V01.md
# ANEXO HITO 1: VALIDACIÓN E IMPLEMENTACIÓN DE VOZ CONVERSACIONAL
# ESTADO: EN PROGRESO (Fase: Estabilización de Infraestructura y Audio)

## 1. FUENTE DE LA VERDAD (ESTADO ACTUAL MARZO 2026)
Este documento refleja el estado técnico real al cierre de la sesión para que el modelo entrante inicie su investigación.
- **Arquitectura:** Sidecar Bridge (WSS) mediando entre Twilio Media Streams y Gemini 3.1 Live.
- **Persistencia de Red:** El nodo web de Django lee la URL dinámica desde `NGROK_URL.txt` para generar el TwiML.
- **Entorno:** Puerto 8081 configurado en Bridge y ngrok.

## 2. BITÁCORA DE INCIDENCIAS (SÍNTOMAS OBSERVADOS)
El modelo entrante DEBE investigar las causas de los siguientes hechos:
- **Hecho A (Silencio Técnico):** Al realizar la llamada, Twilio conecta correctamente con el Bridge. Se escucha un sonido inicial (chasquido/pop), pero después el sistema entra en silencio total. No hay audibilidad de la IA a pesar de que la sesión Gemini Live figura como establecida.
- **Hecho B (Bloqueo de Recursos):** Se han detectado colisiones recurrentes en el puerto 8081 (`OSError: [Errno 98]`) y en el endpoint de ngrok (`ERR_NGROK_334`). Estos procesos parecen persistir en segundo plano tras el cierre de la consola, impidiendo nuevas pruebas de ignición.

## 3. HOJA DE RUTA PARA LA SIGUIENTE SESIÓN
El modelo entrante debe actuar con rigor técnico sobre los siguientes puntos:
### Tarea 1: Auditoría de Integridad del Código
Investigar a fondo la lógica actual en `vox_bridge/services.py` y `voice_sidecar_bridge.py` para identificar por qué el flujo de audio se interrumpe o no se transmite tras la conexión inicial. El modelo debe decidir el diagnóstico basándose en la documentación del SDK de marzo de 2026.

### Tarea 2: Estabilización de la Capa de Transporte
Asegurar un método de limpieza y arranque que garantice que el puerto 8081 y el túnel de ngrok estén plenamente disponibles antes de iniciar el flujo de voz.

### Tarea 3: Prueba de Validación
Una vez resueltos los puntos anteriores, validar la audibilidad bidireccional y la fluidez de la conversación.

## 4. ESPECIFICACIONES TÉCNICAS
- Modelo: models/gemini-3.1-flash-live-preview.
- Puerto: 8081.
- SDK: google-genai (v1.68.0).
