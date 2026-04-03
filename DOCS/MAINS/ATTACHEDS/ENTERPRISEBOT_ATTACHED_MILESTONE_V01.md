# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/DOCS/MAINS/ATTACHEDS/ENTERPRISEBOT_ATTACHED_MILESTONE_V01.md
# ANEXO HITO 1: INFRAESTRUCTURA DE VOZ (ESTABILIZACIÓN FINAL)
# ESTADO: EN PROGRESO (PENDIENTE DE HANDSHAKE v1beta)
# FECHA ACTUALIZACIÓN: 2026-04-03

---

## 1. ESTADO TÉCNICO AL CIERRE DE SESIÓN
* **Infraestructura de Red:** Túnel Ngrok v3 y Sidecar Bridge (aiohttp) validados externamente. Resolución de URL dinámica operativa.
* **Dependencias:** `requirements.in` blindado. `google-genai` fijado en 1.69.0. `aiohttp` fijado en 3.13.5 (CVE-2026-34517 Mitigado).
* **Bloqueo Detectado:** Error HTTP 404 en el handshake de Gemini. Causa identificada: Uso de `api_version='v1'` en lugar de `v1beta` para el motor Live de Gemini 2.5 Flash en el SDK 1.69.0.

## 2. HOJA DE RUTA PARA LA SIGUIENTE SESIÓN (LEY SUPREMA)
La próxima sesión DEBE seguir estrictamente estos pasos sin desviaciones ni suposiciones:

1. **Corrección Quirúrgica de Handshake (Prioridad Máxima):**
   - Modificar `vox_bridge/services.py`.
   - Localizar el constructor `genai.Client`.
   - Cambiar EXCLUSIVAMENTE `http_options={'api_version': 'v1'}` por `http_options={'api_version': 'v1beta'}`.
   - Prohibido alterar cualquier otra línea, comentario o docstring del archivo.

2. **Validación de Arquitectura de Extremo a Extremo (Zero-Cost):**
   - Iniciar orquestador: `python3 voice_orchestrator.py`.
   - En consola secundaria, ejecutar: `python -m dotenv run python test_bridge_connectivity.py`.
   - Auditar en logs la recepción del evento `setup_complete` de Google.

3. **Prueba de Campo Outbound (Llamada Real):**
   - Una vez validado el handshake, ejecutar: `python manage.py launch_voice_system`.
   - Confirmar recepción de llamada en +34688360595.
   - Verificar la inyección del saludo inicial: "Hola, soy EnterpriseBot. ¿En qué puedo ayudarte?".

4. **Auditoría de Persistencia:**
   - Verificar en la base de datos `MiguelAeTxio$enterprisebot` la creación del registro en `vox_bridge_callinteraction`.
   - Comprobar que el campo `full_transcript` recoge el saludo inicial del bot.

---
*Referencia Técnica Obligatoria:* `V01DOC_VOICE_SIDECAR_ARCHITECTURE.md`.
