# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/supplier_invoices/urls.py
"""
URLs of the FACTURACIÓN folder of the inbox.

---

URLs de la carpeta FACTURACIÓN de la bandeja de entrada (H28, S151).
"""
from django.urls import path

from . import views, views_agent

app_name = "supplier_invoices"

urlpatterns = [
    path("", views.InvoicesPaneView.as_view(), name="pane"),
    path(
        "resultados/", views.InvoicesResultsView.as_view(), name="results",
    ),
    path("subir/", views.InvoiceUploadView.as_view(), name="upload"),
    path(
        "reprocesar/", views.InvoiceRetryView.as_view(), name="retry",
    ),
    path("<int:pk>/", views.InvoiceDetailView.as_view(), name="detail"),
    # Agente H28: carpeta local FACTURACIÓN de OneDrive (S151).
    path(
        "agente/sincronizar/",
        views_agent.AgentInvoiceSyncView.as_view(),
        name="agent_sync",
    ),
    path(
        "agente/subir/",
        views_agent.AgentInvoiceUploadView.as_view(),
        name="agent_upload",
    ),
    path(
        "agente/<int:pk>/archivo/",
        views_agent.AgentInvoiceFileView.as_view(),
        name="agent_file",
    ),
    path(
        "agente/<int:pk>/local/",
        views_agent.AgentInvoiceLocalView.as_view(),
        name="agent_local",
    ),
]
