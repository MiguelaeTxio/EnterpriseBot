# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/insurance/apps.py
"""
Insurance renewal reports (Documentation hub, "Seguros" tab).
---
Informes de renovación de seguros (pestaña "Seguros" de Documentación).
"""
from django.apps import AppConfig


class InsuranceConfig(AppConfig):
    """
    App config for the insurance renewal reports.
    ---
    Configuración de la app de informes de seguros.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "insurance"
    verbose_name = "Seguros"
