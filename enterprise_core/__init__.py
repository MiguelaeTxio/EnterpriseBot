# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/enterprise_core/__init__.py

# This file is intentionally left without Celery imports.
# The Celery app is loaded directly by the worker via -A enterprise_core,
# which triggers celery.py explicitly without conflicting with Django's
# app registry initialisation order.
# ---
# Este archivo se deja intencionadamente sin imports de Celery.
# La app Celery es cargada directamente por el worker via -A enterprise_core,
# lo que dispara celery.py explícitamente sin conflicto con el orden de
# inicialización del registry de apps de Django.
