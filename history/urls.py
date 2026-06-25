# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/history/urls.py
"""
URL configuration for the history application.
Served under /panel/history/ as defined in enterprise_core/urls.py.
---
Configuracion de URLs para la aplicacion history.
Servida bajo /panel/history/ segun enterprise_core/urls.py.
"""
from django.urls import path

from history.views import (
    MachineHistoryView,
    WorkOrderHistoryListView,
    WorkOrderHistoryDetailView,
)

app_name = "history"

urlpatterns = [
    path(
        "machine/",
        MachineHistoryView.as_view(),
        name="machine_history",
    ),
    path(
        "workorders/",
        WorkOrderHistoryListView.as_view(),
        name="workorder_history_list",
    ),
    path(
        "workorders/<int:pk>/",
        WorkOrderHistoryDetailView.as_view(),
        name="workorder_history_detail",
    ),
]
