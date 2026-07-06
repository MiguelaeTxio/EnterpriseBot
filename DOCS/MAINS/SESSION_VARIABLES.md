# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/DOCS/MAINS/SESSION_VARIABLES.md
# VARIABLES DE SESIÓN DE PROYECTO: EnterpriseBot
# Este archivo centraliza la configuración para la sesión actual.

---

## ENTERPRISEBOT

- **PROJECT_ID**: EnterpriseBot
- **GEN_SERVER_ROOT**: /home/MiguelAeTxio/
- **APP_SERVER_ROOT**: PROJECTS/EnterpriseBot/
- **SERVER_ROOT**: {GEN_SERVER_ROOT}{APP_SERVER_ROOT}
- **LOCAL_SWAP**: SWAP/
- **LOCAL_VENV**: "N/A - Remote Server Development"
- **SERVER_VENV**: EnterpriseBot_venv
- **SFTP_CONNECTION**: MiguelAeTxio@ssh.pythonanywhere.com:PROJECTS/EnterpriseBot
- **DB_NAME**: MiguelAeTxio$enterprisebot
- **PROJECT_MASTER_DOC_PATH**: /home/MiguelAeTxio/PROJECTS/EnterpriseBot/DOCS/MAINS/ENTERPRISEBOT_MASTER_DOCUMENT.md
- **PROJECT_DIRECTORY_PATH**: /home/MiguelAeTxio/PROJECTS/EnterpriseBot/DOCS/SESSION/ENTERPRISEBOT_PROJECT_DIRECTORY.txt
- **PROJECT_ATTACHMENTS_PATH**: /home/MiguelAeTxio/PROJECTS/EnterpriseBot/DOCS/MAINS/ATTACHEDS/
- **PROJECT_SESSION_DATA_PATH**: {SERVER_ROOT}DOCS/SESSION/
- **PROJECT_GEMINI_HISTORY**: {PROJECT_SESSION_DATA_PATH}GEMINI_SESSIONS_HISTORY.md
- **PROJECT_TEMP_HISTORY**: {PROJECT_SESSION_DATA_PATH}TEMP_SESSIONS_HISTORY.md
- **PROJECT_COMPLETED_SESSIONS_DIR**: {PROJECT_SESSION_DATA_PATH}COMPLETED/

---

## LOGS — ARCHIVOS NO VERSIONADOS DEL SERVIDOR

**No viven en GitHub.** Son artefactos de ejecución en el servidor
(procesos always-on y logs web estándar de PythonAnywhere). Para
solicitarlos usar `com-file-request` citando la línea exacta de esta
tabla — nunca `doc-project-directory-enterprisebot` (manifiesto de
árbol de código fuente, no cubre `/var/log/` ni rutas fuera del
proyecto).

**Nota de reparación (2026-07-06):** esta tabla estaba anotada como
"actualizada" en el registro de S057 (anexo H17) pero no existía en
este archivo — reparado en esta sesión tras detectar la
discrepancia empíricamente.

- **LOG_VOICE_ORCHESTRATOR**: /var/log/alwayson-log-234987.log
- **LOG_CELERY_WORKER**: /var/log/alwayson-log-242133.log
- **LOG_BRIDGE**: {SERVER_ROOT}logs/bridge.log
- **LOG_WEB_ACCESS**: /var/log/enterprisebot-miguelaetxio.pythonanywhere.com.access.log
- **LOG_WEB_ERROR**: /var/log/enterprisebot-miguelaetxio.pythonanywhere.com.error.log
- **LOG_WEB_SERVER**: /var/log/enterprisebot-miguelaetxio.pythonanywhere.com.server.log
