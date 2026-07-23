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
    # --- H10 Paso 5/6 (corregido 2026-07-07): Almacen para Mecanicos, ---
    # --- entidad distinta del catalogo de Administracion ---
    path(
        'almacen/',
        views.SparePartWarehouseListView.as_view(),
        name='warehouse_list',
    ),
    path(
        'almacen/<int:pk>/devolver/',
        views.SparePartReturnToWarehouseView.as_view(),
        name='return_to_warehouse',
    ),
    path(
        'almacen/<int:pk>/ajustar/',
        views.SparePartStockAdjustView.as_view(),
        name='stock_adjust',
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
    # --- Caso B: consumo pre-asignado (limbo) ---
    path(
        'lineas/<int:entry_line_pk>/pre-asignados/',
        views.SparePartPreAssignedListView.as_view(),
        name='pre_assigned_list',
    ),
    path(
        'lineas/<int:entry_line_pk>/consumir-pre-asignado/<int:entry_pk>/',
        views.SparePartConsumePreAssignedView.as_view(),
        name='consume_pre_assigned',
    ),
    # --- Caso C: alta ad-hoc + consumo (digitalizacion organica) ---
    path(
        'lineas/<int:entry_line_pk>/alta-nuevo/',
        views.SparePartRegisterNewAndConsumeView.as_view(),
        name='register_new',
    ),
    # --- H10 Paso 4-bis: resolucion de ticket por tarea (antes de guardar) ---
    path(
        'resolucion-ticket/',
        views.TaskTicketResolutionView.as_view(),
        name='task_ticket_resolution',
    ),
    # --- Modal global "Anadir repuesto" (2026-07-23): busqueda cruzada ---
    # --- WAREHOUSE + PRE_ASSIGNED de toda la empresa, antes de guardar ---
    path(
        'buscar-global/',
        views.SparePartGlobalSearchView.as_view(),
        name='search_global',
    ),
    # --- H10 Paso 7: alta de repuestos por canibalizacion ---
    path(
        'canibalizacion/crear/',
        views.SparePartSalvageCreateView.as_view(),
        name='salvage_create',
    ),
    path(
        'canibalizacion/lineas-origen/',
        views.SparePartSalvageOriginLinesView.as_view(),
        name='salvage_origin_lines',
    ),
    # --- Alta rapida en almacen sin proveedor conocido (2026-07-07) ---
    path(
        'almacen/alta-rapida/',
        views.SparePartQuickIntakeCreateView.as_view(),
        name='quick_intake_create',
    ),
    # --- Selector de material en el parte de trabajo (2026-07-07) ---
    path(
        'materiales/buscar/',
        views.SparePartMaterialSearchView.as_view(),
        name='material_search',
    ),
    path(
        'materiales/alta-rapida/',
        views.SparePartMaterialQuickCreateView.as_view(),
        name='material_quick_create',
    ),
]
