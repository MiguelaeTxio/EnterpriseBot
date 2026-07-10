# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/mimoo_updates/urls.py
"""
URL configuration for the mimoo_updates application.
Served under /mimoo-updates/ as defined in enterprise_core/urls.py --
not linked from any menu or template, only reachable by knowing the
full URL including the token.
---
Configuracion de URLs para la aplicacion mimoo_updates.
Servida bajo /mimoo-updates/ segun enterprise_core/urls.py -- no
enlazada desde ningun menu ni plantilla, solo alcanzable conociendo
la URL completa, token incluido.
"""
from django.urls import path

from mimoo_updates import views

app_name = "mimoo_updates"

urlpatterns = [
    path("<str:token>/manifest.json", views.manifest_view, name="manifest"),
    path("<str:token>/apk", views.apk_view, name="apk"),
]
