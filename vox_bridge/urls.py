# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/vox_bridge/urls.py
from django.urls import path
from .views import InboundCallView

urlpatterns = [
    # Endpoint principal para la recepción de llamadas
    path('inbound/', InboundCallView.as_view(), name='vox_inbound'),
]
