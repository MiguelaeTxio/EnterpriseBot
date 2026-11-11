# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/supplier_invoices/urls.py
"""
URLs of the FACTURACIÓN folder of the inbox.

---

URLs de la carpeta FACTURACIÓN de la bandeja de entrada (H28, S151).
"""
from django.urls import path

from . import views

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
]
