#!/bin/bash
# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/start_celery_worker.sh
#
# EnterpriseBot — Arranque del worker Celery para procesamiento de PDFs.
# Worker Celery startup script for PDF work order processing.
#
# Always-on task registrada en PythonAnywhere.
# Registered as always-on task in PythonAnywhere.

set -e

# Activar entorno virtual / Activate virtual environment
source /home/MiguelAeTxio/.virtualenvs/EnterpriseBot_venv/bin/activate

# Cargar variables de entorno / Load environment variables
cd /home/MiguelAeTxio/PROJECTS/EnterpriseBot

# Arrancar worker Celery con concurrencia 1 (suficiente para el volumen
# de Grupo Álvarez; conserva recursos en PythonAnywhere).
# Start Celery worker with concurrency 1 (sufficient for Grupo Álvarez
# volume; conserves resources on PythonAnywhere).
#
# -B (2026-07-23): embebe Celery Beat en este mismo proceso -- no hay
# ningún always-on task separado para Beat (cuenta de PythonAnywhere
# al máximo de always-on tasks, confirmado en el dashboard: los otros
# dos slots son de Campu Studi Online, un proyecto distinto), así que
# CELERY_BEAT_SCHEDULE (enterprise_core/settings.py) nunca se había
# estado disparando -- ni la tarea de autocuración de personal nueva
# de hoy, ni ninguna de las cuatro que ya existían antes
# (expire-whatsapp-sessions, check-in-meeting-reminders,
# expire-presence-statuses, send-document-expiry-alerts). Seguro con
# un único worker (Celery solo advierte contra -B con VARIOS workers
# simultáneos, por duplicar el disparo del scheduler -- no es el caso
# aquí).
exec python -m dotenv run celery -A enterprise_core worker \
    --beat \
    --loglevel=info \
    --concurrency=1 \
    --queues=work_orders \
    --hostname=enterprisebot_worker@%h
