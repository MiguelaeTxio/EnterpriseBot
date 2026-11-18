# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/warehouse_inventory/urls.py
"""
URLs of Warehouse > Photo inventory.

---

H10 (S151, sesión invasora). Rutas de Almacén > Inventario por fotos.
"""
from django.urls import path

from . import views

app_name = "warehouse_inventory"

urlpatterns = [
    path("", views.InventoryHomeView.as_view(), name="home"),
    path("empezar/", views.InventoryStartView.as_view(), name="start"),
    path("foto/", views.InventoryUploadView.as_view(), name="upload"),
    path(
        "<int:pk>/fotos/", views.InventoryPhotosView.as_view(),
        name="photos",
    ),
    path(
        "<int:pk>/cerrar/", views.InventoryCloseView.as_view(),
        name="close",
    ),
    path(
        "<int:pk>/reabrir/", views.InventoryReopenView.as_view(),
        name="reopen",
    ),
    path(
        "<int:pk>/diferencias/", views.DifferencesPageView.as_view(),
        name="differences",
    ),
    path(
        "<int:pk>/diferencias/resultados/",
        views.DifferencesResultsView.as_view(),
        name="differences_results",
    ),
    path(
        "<int:pk>/diferencias/revisar/",
        views.DifferencesResolveView.as_view(),
        name="differences_resolve",
    ),
]
