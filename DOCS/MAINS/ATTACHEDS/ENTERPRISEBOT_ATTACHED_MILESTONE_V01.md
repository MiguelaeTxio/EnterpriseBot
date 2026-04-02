# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/DOCS/MAINS/ATTACHEDS/ENTERPRISEBOT_ATTACHED_MILESTONE_V01.md
# ANEXO HITO 1: INFRAESTRUCTURA DE VOZ (ESTABILIZACIÓN FINAL)
# ESTADO: LISTO PARA PRUEBAS DE CAMPO (READY FOR FIELD TESTING)
# FECHA: 2026-04-02

---

## 1. CONTEXTO TÉCNICO CONSOLIDADO
* **Arquitectura:** Sidecar Bridge asíncrono con Gemini 2.0 Flash Live (v1).
* **Región Twilio:** Configurada en **US1** (EE. UU.) para sincronía con el Bridge.
* **Transcodificación:** Validada mu-law (8kHz) <-> PCM Linear (16kHz).
* **Seguridad:** Aplicación `test_live` eliminada; superficie de ataque reducida.

## 2. HOJA DE RUTA PARA LA SIGUIENTE SESIÓN (LEY SUPREMA)
La próxima sesión debe ejecutar estrictamente las siguientes tareas en este orden:

1. **Activación de Infraestructura:**
   - Ejecutar el orquestador: `python3 voice_orchestrator.py`.
   - Verificar la creación del túnel ngrok y la escritura de la URL en `DOCS/SESSION/NGROK_URL.txt`.

2. **Monitoreo de Logs en Tiempo Real:**
   - Establecer visualización activa de los logs de `VoiceSidecar` y `VoxServices` para auditar el handshake de Google Gemini.

3. **Disparo de Llamada Saliente (Outbound Test):**
   - Ejecutar `python3 trigger_outbound_call.py`.
   - El sistema debe marcar al número +34688360595 desde el número USA de Twilio.

4. **Validación de Interacción Bidireccional:**
   - Confirmar recepción de saludo inicial de Gemini ("Hola, soy EnterpriseBot...").
   - Verificar capacidad de interrupción (Barge-in) y latencia percibida.

5. **Auditoría de Persistencia:**
   - Verificar la creación del registro en la tabla `vox_bridge_callinteraction` con el `call_sid` correspondiente.

---
*Referencia Técnica Obligatoria:* `V01DOC_VOICE_SIDECAR_ARCHITECTURE.md`.
