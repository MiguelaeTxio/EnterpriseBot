# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/apps.py
"""
Application configuration for the panel app.
---
Configuración de la aplicación panel.
"""

from django.apps import AppConfig


class PanelConfig(AppConfig):
    """
    AppConfig for the panel application.
    Registers the app under the 'panel' label within the Django project.
    ---
    AppConfig para la aplicación panel.
    Registra la app bajo la etiqueta 'panel' dentro del proyecto Django.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "panel"
    verbose_name = "Panel de Administración"
