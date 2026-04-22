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
exec python -m dotenv run celery -A enterprise_core worker \
    --loglevel=info \
    --concurrency=1 \
    --queues=work_orders \
    --hostname=enterprisebot_worker@%h
