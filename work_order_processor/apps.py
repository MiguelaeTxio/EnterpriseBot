# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/work_order_processor/apps.py

"""
AppConfig for the work_order_processor application.
Registers the app under its canonical label and sets the default
auto-generated primary key type for all models in this app.

---

AppConfig de la aplicación work_order_processor.
Registra la app bajo su etiqueta canónica y establece el tipo de clave
primaria autogenerada por defecto para todos los modelos de esta app.
"""

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class WorkOrderProcessorConfig(AppConfig):
    """
    Django application configuration for work_order_processor.
    ---
    Configuración de la aplicación Django work_order_processor.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name               = "work_order_processor"
    verbose_name       = _("Procesador de Partes de Trabajo")
