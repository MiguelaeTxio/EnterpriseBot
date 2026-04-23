# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/fleet/apps.py

"""
Django application configuration for the fleet app.
Manages the MachineAsset model and the machine catalog import command.

---

Configuración de la aplicación Django para la app fleet.
Gestiona el modelo MachineAsset y el comando de importación del catálogo de maquinaria.
"""

from django.apps import AppConfig


class FleetConfig(AppConfig):
    """
    AppConfig for the fleet application.
    Sets the default auto field and the human-readable application name.

    ---

    AppConfig para la aplicación fleet.
    Establece el campo automático por defecto y el nombre legible de la aplicación.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name                = "fleet"
    verbose_name        = "Flota y Centros de Gasto"
