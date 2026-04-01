# ANEXO HITO 1: INFRAESTRUCTURA DE VOZ (ESTABILIZACIÓN FINAL)
# ESTADO: EN PROGRESO (REQUIERE REFACTORIZACIÓN URGENTE)
# FECHA: 2026-04-01

---

## 1. NOTA DE CIERRE DE SESIÓN ANTERIOR (MANDATORIA)
El modelo anterior ha fallado por agotamiento de tokens y sesgo de entrenamiento (2025). La lógica actual en `vox_bridge/services.py` es **OBSOLETA** e **INCORRECTA**. No permite la interacción (cierra el turno) y persiste en el idioma inglés.

## 2. HOJA DE RUTA PARA LA SIGUIENTE SESIÓN (LEY SUPREMA)

**DIAGNÓSTICO Y ACCIÓN INMEDIATA:**
1.  **IGNORAR** cualquier dato de entrenamiento previo sobre el SDK de Google GenAI.
2.  **PRIORIDAD ABSOLUTA:** Consultar la documentación oficial online de la Multimodal Live API (v1beta) a fecha de Abril 2026.

**REFACTORIZACIÓN DE `vox_bridge/services.py`:**
- **OBJETO CONFIGURACIÓN:** El `language_code="es-ES"` DEBE anidarse dentro de `generation_config` -> `speech_config`. Cualquier otra ubicación es ignorada por el servidor de Google.
- **VOZ CERTIFICADA:** Usar exclusivamente la voz **"Aoede"** o la indicada en la documentación live como HD Multilingual para castellano. "Puck" y "Kore" han dado errores de regresión al inglés.
- **GESTIÓN DE TURNOS (TRIPLE CHECK):** El mensaje inicial de saludo generado por texto en `send_initial_greeting` **NO DEBE** llevar el parámetro `turn_complete=True`. Si se envía como `True`, la sesión se cierra tras el saludo. Debe quedar en `False` o nulo para mantener el micrófono abierto.
- **DSP (AUDIOOP):**
    - **Uplink:** 8kHz (Twilio) -> 16kHz (Google). Factor 2.
    - **Downlink:** 24kHz (Google) -> 8kHz (Twilio). Factor 1/3 (Mandatorio para evitar aceleración de voz).

**OBJETIVO DE LA SESIÓN:** Conseguir que el bot salude en castellano y se quede escuchando la respuesta del usuario sin colgar.

---
