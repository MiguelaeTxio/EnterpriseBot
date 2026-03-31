# GUÍA TÉCNICA: INFRAESTRUCTURA DE VOZ TWILIO MEDIA STREAMS
# Versión: 1.2 (Optimización Regional IE1 y Códec Adaptativo)
# Fecha de Actualización: 2026-03-31

---

## 1. RESUMEN EJECUTIVO / EXECUTIVE SUMMARY
Este documento constituye la especificación técnica oficial para el bridge de voz de EnterpriseBot. Tras la desestimación de la infraestructura síncrona de MundoSMS, el proyecto adopta Twilio Media Streams como estándar de comunicación bidireccional en tiempo real. Este cambio permite una latencia inferior a los 500ms, facilitando una conversación natural entre el usuario y Gemini 3.1 Pro.

## 2. RECURSOS DE INFRAESTRUCTURA / INFRASTRUCTURE RESOURCES
A continuación se detallan los activos configurados en la consola de Twilio que deben ser utilizados por la lógica del servidor:

- **Account SID:** AC67757db0d7ba0951546bf152b8cf9b1f
- **API Key SID (SK):** SKd696318e9614df9052bd074e07b335ea
- **Número de Teléfono Oficial:** +1 260 346 6780 (Actualizado - US Paid)
- **TwiML App:** EnterpriseBot_Voice_Bridge_App
- **Endpoint Webhook (POST):** https://MiguelAeTxio.pythonanywhere.com/vox/inbound/

## 3. PROTOCOLO DE AUDIO (G.711 ADAPTATIVO: MU-LAW/A-LAW) / AUDIO PROTOCOL
Twilio transmite el audio utilizando compresión logarítmica para telefonía digital. El bridge se adapta dinámicamente al códec negociado por la región de borde:

- **Codificación:** audio/x-mulaw (PCMU) para US / audio/x-alaw (PCMA) para EU.
- **Frecuencia de Muestreo:** 8000 Hz.
- **Canales:** Mono (1 canal).
- **Muestreo:** 8 bits por muestra.
- **Encapsulamiento:** Los datos binarios llegan en paquetes JSON bajo la clave "payload", codificados en Base64.

## 4. GESTIÓN DEL FLUJO WEBSOCKET / WEBSOCKET LIFECYCLE
El bridge en Django debe procesar los eventos en el siguiente orden estricto:

1. **Evento "connected":** Se recibe al establecerse la conexión TCP. Sirve para inicializar buffers.
2. **Evento "start":** Twilio envía metadatos de la llamada. Es obligatorio extraer el "streamSid" y el "encoding" para configurar el DSP.
3. **Evento "media":** Este evento se repite cada 20ms aproximadamente. Contiene el audio del usuario.
4. **Evento "stop":** Indica que el usuario ha colgado. El bridge debe cerrar la sesión de Gemini y liberar recursos.

## 5. ARQUITECTURA DE SEGURIDAD / SECURITY ARCHITECTURE
- La validación SSL debe permanecer activada en Twilio para proteger el túnel de datos.
- Las credenciales (SID y Secret) deben residir exclusivamente en el archivo .env del servidor, nunca en el código fuente.
- Se utilizará el API Key SID para la firma de peticiones, evitando el uso del Auth Token maestro de la cuenta.

## 6. OPTIMIZACIÓN REGIONAL (IE1 - IRELAND)
- **Región Activa y Mandatoria:** Ireland (IE1).
- **Justificación:** Optimización de latencia para terminales móviles en la Unión Europea.
- **Estado:** Activo (Configurado en Dashboard Twilio).
- **Latencia Objetivo:** < 300ms.
