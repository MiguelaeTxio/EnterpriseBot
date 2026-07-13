# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/spare_parts/urls.py
"""
URL routing for the spare parts and supplier delivery note module.
---
Enrutamiento de URLs del módulo de albaranes de proveedores y
repuestos.
"""
from django.urls import path

from . import views

app_name = 'spare_parts'

urlpatterns = [
    path(
        'delivery-notes/upload/',
        views.DeliveryNoteUploadView.as_view(),
        name='delivery_note_upload',
    ),
    path(
        'delivery-notes/<int:pk>/',
        views.DeliveryNoteDetailView.as_view(),
        name='delivery_note_detail',
    ),
    path(
        'delivery-notes/<int:pk>/confirm/',
        views.DeliveryNoteConfirmView.as_view(),
        name='delivery_note_confirm',
    ),
    path('suppliers/', views.SupplierListView.as_view(), name='supplier_list'),
    path('suppliers/create/', views.SupplierCreateView.as_view(), name='supplier_create'),
    path('suppliers/<int:pk>/edit/', views.SupplierUpdateView.as_view(), name='supplier_edit'),
    path('suppliers/<int:pk>/deactivate/', views.SupplierDeactivateView.as_view(), name='supplier_deactivate'),
    path('suppliers/<int:pk>/reactivate/', views.SupplierReactivateView.as_view(), name='supplier_reactivate'),
    path('suppliers/<int:pk>/delete/', views.SupplierDeleteView.as_view(), name='supplier_delete'),
]
