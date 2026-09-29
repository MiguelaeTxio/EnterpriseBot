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
# Migrado a Python 3.12 en S93/H32 (imagen de sistema "innit") -- ver
# com-environment-management sección 4.2 para el detalle completo.
source /home/MiguelAeTxio/.virtualenvs/EnterpriseBot_venv_py312/bin/activate

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
#
# H30 (S123), decisión de Miguel Ángel: concurrencia 2. Con 1, la
# alerta de caída del agente H28 (check_system_agents_task, cada 5
# minutos) quedó en cola detrás de refresh_quarantine_index_task, que a
# las 10:00 seguía corriendo más de 5 minutos: una tarea larga no debe
# retrasar las rápidas. Con CELERY_WORKER_PREFETCH_MULTIPLIER = 1 y
# acks_late (settings.py), el proceso ocupado no se reserva tareas: las
# toma el otro.
exec python -m dotenv run celery -A enterprise_core worker \
    --beat \
    --loglevel=info \
    --concurrency=2 \
    --queues=work_orders \
    --hostname=enterprisebot_worker@%h
