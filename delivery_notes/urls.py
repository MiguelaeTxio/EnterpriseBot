# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/delivery_notes/urls.py
"""
URL routing for the delivery_notes admin CRUD module.
---
Enrutamiento de URLs del módulo de administración de albaranes.
"""
from django.urls import path

from . import views

app_name = 'delivery_notes'

urlpatterns = [
    path('', views.DeliveryNoteAdminListView.as_view(), name='list'),
    path(
        '<int:pk>/',
        views.DeliveryNoteAdminDetailView.as_view(),
        name='detail',
    ),
    path(
        '<int:pk>/eliminar/',
        views.DeliveryNoteAdminDeleteView.as_view(),
        name='delete',
    ),
]
