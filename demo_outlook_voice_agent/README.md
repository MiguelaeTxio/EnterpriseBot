# Agente demo de voz para Outlook (S142, sesión invasora fuera de hitos)

Demostración aparte, sin hito. Agente residente en el PC Windows de
Miguel Ángel: vigila la pantalla y, cuando Outlook se maximiza, ofrece
un modal para grabar un mensaje oral (botón de inicio y de detención),
lo transcribe con Gemini y envía un correo a `nummenor@gmail.com` con
asunto `prueba` y la transcripción como cuerpo, manejando Outlook con
Gemini Vision y clics en pantalla.

## Estado

1. **Prueba de viabilidad** (`viability_probe.py`): comprueba por
   separado detección de Outlook maximizado, micrófono, transcripción
   y localización del botón de correo nuevo (mueve el cursor, no hace
   clic, no envía nada).
2. Agente completo: pendiente del resultado de la prueba.

## Entorno

- Carpeta: `C:\EnterpriseBot\demo_outlook_voice_agent`.
- Entorno virtual propio: `demo_agent_venv` (ignorado por git,
  patrón `*_venv/`), invocado siempre por su intérprete, nunca con
  `Activate.ps1`.
- Dependencias: `requirements.in` / `requirements.txt` propios
  (`com-environment-management`); el candado se compila en el PC.
- Credenciales: la misma clave de servicio local del agente H28
  (`%LOCALAPPDATA%\EnterpriseBot\H28MigrationAgent\service_account_key.json`,
  o `H28_AGENT_KEY_PATH`), proyecto y cuenta leídos de la propia clave.
- Modelo: `gemini-3.5-flash` en Vertex AI, región `global`
  (directriz 4.1 del documento maestro).
