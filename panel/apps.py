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

    def ready(self):
        """
        Under uWSGI, loads the URLs (and every view) at worker start.
        ---
        S153. Django carga las URLs (y con ellas todas las vistas y sus
        librerías: Gemini, WeasyPrint, openpyxl...) en la primera
        petición que recibe cada proceso. Tras cada despliegue, quien
        usaba el panel esperaba 8-14 s (logs/slow_requests.log: "/",
        firmas o fichaje con 0 consultas justo tras cada recarga). Bajo
        uWSGI (la web) se cargan al arrancar el proceso, antes de
        atender a nadie; los comandos de manage.py no lo pagan.
        """
        try:
            import uwsgi  # noqa: F401  (solo existe dentro de uWSGI)
        except ImportError:
            return
        import logging

        from django.urls import get_resolver

        try:
            get_resolver().url_patterns
        except Exception:
            # Si fallara, la primera petición mostrará el error real.
            logging.getLogger(__name__).exception(
                "# [ARRANQUE] No se han podido precargar las URLs.")
