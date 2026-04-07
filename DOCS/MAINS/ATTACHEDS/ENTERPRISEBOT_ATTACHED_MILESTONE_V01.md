# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/DOCS/MAINS/ATTACHEDS/ENTERPRISEBOT_ATTACHED_MILESTONE_V01.md

# ENTERPRISEBOT — ANEXO HITO V01 — VALIDACIÓN DE INFRAESTRUCTURA DE VOZ
**Estado:** EN PROGRESO
**Última actualización:** 2026-04-07

---

## SECCIÓN 1 — LOGROS DE LA SESIÓN ACTUAL
1.  **Saneamiento de Entorno:** Eliminación de scripts de prueba obsoletos (`test_ia_locally.py`, `debug_webhook_locally.py`, etc.) y archivos residuales.
2.  **Persistencia Documental:** Generación de la Constelación Documental Satélite del Hito 1 en `DOCS_ATTACHED_2_ANNEX_V01/`:
    - `ARCH_VOICE_INFRASTRUCTURE.md`: Flujo multi-salto Twilio-Ngrok-Bridge-Gemini.
    - `API_HANDSHAKE_PROTOCOL.md`: Técnica de doble handshake HTTP/WSS.
    - `TRANSCODING_ENGINE_SPECS.md`: Detalles de audioop y gestión de `streamSid`.
3.  **Validación Técnica E2E:** Confirmación mediante logs `DEBUG` del funcionamiento del bridge:
    - Handshake con Gemini 3.1 Live exitoso.
    - Transcodificación bidireccional (mu-law 8kHz ↔ PCM 24kHz) operativa.
    - Orquestación de eventos de Twilio (`start`, `media`, `stop`) estabilizada.

---

## SECCIÓN 2 — HOJA DE RUTA PARA LA SIGUIENTE SESIÓN (LEY SUPREMA)

1.  **Calibración de VAD (RMS):**
    - Auditar los valores de RMS reportados en los logs de la sesión actual (rango observado: 8.0 a 485.0).
    - Ajustar los umbrales de `activity_start` y `activity_end` en `vox_bridge/services.py` para evitar falsos positivos por ruido de línea.
    - Implementar un mecanismo de "histeresis" o conteo de frames para estabilizar la transición `Hablando: True/False`.
2.  **Validación de Latencia:** Realizar pruebas de estrés para medir el TTFT (Time to First Token) tras el ajuste del VAD.
3.  **Cierre de Hito 1:** Una vez calibrado el RMS, proceder al marcado del hito como COMPLETADO en el Master Document.

---

## SECCIÓN 3 — PAH — REGISTRO DE SESIÓN
**Título:** Depuración de Infraestructura de Voz y Documentación Satélite del Hito 1
**Descripción:** Sesión centrada en la validación técnica del Hito 1. Se ha purgado el entorno de scripts obsoletos y se ha generado la Constelación Documental Satélite (Arquitectura, Handshake y Transcodificación). Las pruebas en DEBUG confirman que el bridge gestiona el flujo A2A con Gemini 3.1 Live satisfactoriamente, habiéndose identificado la necesidad de calibrar los umbrales de RMS para optimizar la detección de voz (VAD) en la próxima sesión.
