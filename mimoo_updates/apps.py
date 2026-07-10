# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/mimoo_updates/apps.py
"""
Django application configuration for the mimoo_updates module.
Serves a compiled APK and its version manifest from disk behind a
random-token URL, so the app can check for updates without exposing
a discoverable public download page.
---
Configuracion de aplicacion Django para el modulo mimoo_updates.
Sirve un APK compilado y su manifiesto de version desde disco tras
una URL con token aleatorio, para que la app pueda comprobar
actualizaciones sin exponer una pagina de descarga publica y
descubrible.
"""
from django.apps import AppConfig


class MimooUpdatesConfig(AppConfig):
    """
    AppConfig for the mimoo_updates application.
    ---
    AppConfig para la aplicacion mimoo_updates.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "mimoo_updates"
    verbose_name = "Actualizaciones de MiMoo"
