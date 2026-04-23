# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/ivr_config/apps.py
"""
Application configuration for the ivr_config Django app.
This app provides the multicompany IVR configuration engine,
including data models, presence management, and dynamic call flow injection.
---
Configuración de la aplicación Django ivr_config.
Esta app proporciona el motor de configuración IVR multiempresa,
incluyendo modelos de datos, gestión de presencia e inyección dinámica de flujos de llamada.
"""

from django.apps import AppConfig


class IvrConfigConfig(AppConfig):
    """
    AppConfig for the ivr_config application.
    Registers the app under the verbose name 'Configuración IVR'
    and sets BigAutoField as the default primary key type.
    ---
    AppConfig para la aplicación ivr_config.
    Registra la app bajo el nombre legible 'Configuración IVR'
    y establece BigAutoField como tipo de clave primaria por defecto.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name               = "ivr_config"
    verbose_name       = "Configuración IVR"

    def ready(self) -> None:
        """
        Imports ivr_config.signals to register all signal handlers when the
        application is fully loaded. This is the canonical Django pattern for
        signal registration — importing signals in apps.py ready() guarantees
        they are connected exactly once regardless of import order.

        ---

        Importa ivr_config.signals para registrar todos los manejadores de señal
        cuando la aplicación está completamente cargada. Este es el patrón Django
        canónico para el registro de señales — importar señales en apps.py ready()
        garantiza que se conectan exactamente una vez independientemente del orden
        de importación.
        """
        import ivr_config.signals  # noqa: F401
