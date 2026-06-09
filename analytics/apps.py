# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/analytics/apps.py
"""
Django application configuration for the analytics module.
---
Configuracion de aplicacion Django para el modulo de analitica.
"""
from django.apps import AppConfig


class AnalyticsConfig(AppConfig):
    """
    AppConfig for the analytics application.
    ---
    AppConfig para la aplicacion analytics.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "analytics"
    verbose_name = "Laboratorio de Analisis"
