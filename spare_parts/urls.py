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
]
