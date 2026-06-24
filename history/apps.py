# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/history/apps.py
"""
Django application configuration for the history module.
---
Configuracion de aplicacion Django para el modulo de historial de maquinas.
"""
from django.apps import AppConfig


class HistoryConfig(AppConfig):
    """
    AppConfig for the history application.
    ---
    AppConfig para la aplicacion history.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "history"
    verbose_name = "Historial de Maquinas"
