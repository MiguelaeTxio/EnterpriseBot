# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/machine_documents/urls.py
"""
URL configuration for the machine_documents application.
Served under /panel/documentacion-centros-gasto/ as defined in
enterprise_core/urls.py.
---
Configuración de URLs para la aplicación machine_documents.
Servida bajo /panel/documentacion-centros-gasto/ según
enterprise_core/urls.py.
"""
from django.urls import path

from machine_documents.views import (
    MachineDocumentBatchUploadView,
    MachineDocumentListView,
)

app_name = "machine_documents"

urlpatterns = [
    path(
        "",
        MachineDocumentListView.as_view(),
        name="list",
    ),
    path(
        "subir/",
        MachineDocumentBatchUploadView.as_view(),
        name="upload",
    ),
]
