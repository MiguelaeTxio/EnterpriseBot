# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/history/urls.py
"""
URL configuration for the history application.
Served under /panel/history/ as defined in enterprise_core/urls.py.
---
Configuracion de URLs para la aplicacion history.
Servida bajo /panel/history/ segun enterprise_core/urls.py.
"""
from django.urls import path

from history.views import MachineHistoryView

app_name = "history"

urlpatterns = [
    path(
        "machine/",
        MachineHistoryView.as_view(),
        name="machine_history",
    ),
]
