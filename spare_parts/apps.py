# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/spare_parts/apps.py
"""
App configuration for the spare parts and delivery note module.
---
Configuración de la app del módulo de albaranes y repuestos.
"""
from django.apps import AppConfig


class SparePartsConfig(AppConfig):
    """
    App configuration for spare_parts.
    ---
    Configuración de la app spare_parts.
    """

    default_auto_field = 'django.db.models.BigAutoField'
    name = 'spare_parts'
    verbose_name = 'Albaranes y Repuestos'
