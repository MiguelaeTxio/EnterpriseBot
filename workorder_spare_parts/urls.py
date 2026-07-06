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
]
