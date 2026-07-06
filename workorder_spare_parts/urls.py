# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/workorder_spare_parts/urls.py
"""
URL routing for workorder_spare_parts.
---
Enrutamiento de URLs de workorder_spare_parts.
"""
from django.urls import path

from . import views

app_name = 'workorder_spare_parts'

urlpatterns = [
    path(
        'catalogo/',
        views.SparePartEntryListView.as_view(),
        name='catalog_list',
    ),
    path(
        'catalogo/crear/',
        views.SparePartEntryCreateView.as_view(),
        name='catalog_create',
    ),
    path(
        'catalogo/<int:pk>/editar/',
        views.SparePartEntryUpdateView.as_view(),
        name='catalog_edit',
    ),
    path(
        'catalogo/<int:pk>/eliminar/',
        views.SparePartEntryDeleteView.as_view(),
        name='catalog_delete',
    ),
    # --- Caso A: consumo desde almacen (H10 Paso 4, bloque 2/4) ---
    path(
        'lineas/<int:entry_line_pk>/buscar-almacen/',
        views.SparePartWarehouseSearchView.as_view(),
        name='search_warehouse',
    ),
    path(
        'lineas/<int:entry_line_pk>/consumir-almacen/<int:entry_pk>/',
        views.SparePartConsumeFromWarehouseView.as_view(),
        name='consume_warehouse',
    ),
]
