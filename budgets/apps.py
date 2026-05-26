# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/budgets/apps.py
"""
Django application configuration for the budgets module.
Handles insurance company tariffs and automated budget calculation
for the ASISTENCIA section.
---
Configuración de la aplicación Django para el módulo de presupuestos.
Gestiona las tarifas de compañías aseguradoras y el cálculo automático
de presupuestos para la sección ASISTENCIA.
"""

from django.apps import AppConfig


class BudgetsConfig(AppConfig):
    """
    AppConfig for the budgets application.
    Registers the app under the 'budgets' label with BigAutoField as default PK.
    ---
    AppConfig para la aplicación budgets.
    Registra la app bajo la etiqueta 'budgets' con BigAutoField como PK por defecto.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "budgets"
    verbose_name = "Presupuestos ASISTENCIA"
