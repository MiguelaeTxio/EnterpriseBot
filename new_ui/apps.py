# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/new_ui/apps.py
"""
Django app of the new interface (S163).

---

App de la nueva interfaz (S163, sesión invasora de UX). Todo lo suyo
vive aquí (vistas, plantillas, JS, rutas, tablas); de `panel` solo usa
el armazón común de la aplicación (plantilla base y barra lateral).
"""

from django.apps import AppConfig


class NewUiConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "new_ui"
    verbose_name = "Nueva interfaz"
