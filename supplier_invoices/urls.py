# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/supplier_invoices/urls.py
"""
URLs of Warehouse > Supplier invoices.

---

URLs de Almacén > Facturas de proveedor (H28, S151).
"""
from django.urls import path

from . import views

app_name = "supplier_invoices"

urlpatterns = [
    path("", views.InvoicesPageView.as_view(), name="list"),
    path(
        "resultados/", views.InvoicesResultsView.as_view(), name="results",
    ),
    path(
        "reprocesar/", views.InvoiceRetryView.as_view(), name="retry",
    ),
    path("<int:pk>/", views.InvoiceDetailView.as_view(), name="detail"),
]
