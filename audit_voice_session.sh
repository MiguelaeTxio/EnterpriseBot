#!/bin/bash
# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/audit_voice_session.sh
# Auditor de Sesión v1.2 - Corrección de Rutas de Entorno (.env)

PROJECT_ROOT="/home/MiguelAeTxio/PROJECTS/EnterpriseBot"
ENV_FILE="$PROJECT_ROOT/.env"
LOG_FILE="$PROJECT_ROOT/DOCS/SESSION/bridge_runtime.log"
TRIGGER_SCRIPT="$PROJECT_ROOT/trigger_outbound_call.py"

# Asegurar integridad del log / Ensure log integrity
[ ! -f "$LOG_FILE" ] && touch "$LOG_FILE"

# Disparo de llamada forzando la ruta del archivo .env
# Trigger call forcing the .env file path
# # [AUDIT] Iniciando llamada saliente al terminal +34688360595...
python -m dotenv -f "$ENV_FILE" run python3 "$TRIGGER_SCRIPT"

# Monitorización de eventos en tiempo real
# Real-time event monitoring
# # [AUDIT] Monitorizando bridge_runtime.log... (Ctrl+C para salir)
tail -f "$LOG_FILE" | grep --line-buffered -E "\[EVENT\]|\[STREAM\]|\[ERROR\]|\[SUCCESS\]|\[INFO\]|\[CRITICAL\]"
