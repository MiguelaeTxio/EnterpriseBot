# Agente demo de voz para Outlook (S142, sesión invasora fuera de hitos)

Demostración aparte, sin hito. Agente residente en el PC Windows de
Miguel Ángel: vigila la pantalla y, cuando Outlook se maximiza, ofrece
un modal para grabar un mensaje oral (botón de inicio y de detención),
lo transcribe con Gemini y envía un correo a `nummenor@gmail.com` con
asunto `prueba` y la transcripción como cuerpo, manejando Outlook con
Gemini Vision y clics en pantalla.

## Estado

1. **Prueba de viabilidad** (`viability_probe.py`): sigue el flujo
   real. Vigila la pantalla y solo cuando Outlook pasa a maximizado
   muestra el modal (Iniciar grabacion / Detener); al detener,
   transcribe con Gemini y localiza con su vision el boton de correo
   nuevo, llevando el cursor encima sin clic. No envia nada. Al
   cerrar el modal vuelve a vigilar.
   Superada en S142 tras dar a la cuenta de servicio
   `roles/aiplatform.user`.
2. **Agente completo** (`main.py`, con `common.py`, `desktop.py` y
   `gemini_ops.py`): mismo disparo y modal. Al detener, transcribe y
   envia el correo manejando Outlook con vision de Gemini y clics:
   (1) correo nuevo, (2) Para, (3) Asunto, (4) cuerpo, (5) comprobacion
   visual del borrador (si no cuadra, se queda abierto SIN enviar),
   (6) Enviar. Capturas de cada paso en `demo_data/`, log en
   `demo_agent.log`. El texto se escribe al principio del cuerpo
   (Ctrl+Inicio), por encima de la firma de correo. Prueba real
   superada en S142 (2026-10-30): correo recibido en
   `nummenor@gmail.com` con asunto `prueba` y la transcripcion.

## Uso

```powershell
cd C:\EnterpriseBot\demo_outlook_voice_agent
.\demo_agent_venv\Scripts\python.exe main.py
```

Con la consola vigilando, maximizar Outlook (si ya estaba maximizado
al arrancar no cuenta), grabar, pulsar Detener y no tocar raton ni
teclado hasta que vuelva el modal.

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
