# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/vox_bridge/urls.py
from django.urls import path
from .views import InboundCallView, ForwardToMobileView

urlpatterns = [
    # Endpoint principal para la recepción de llamadas IVR
    path('inbound/', InboundCallView.as_view(), name='vox_inbound'),
    # Endpoint de reenvío a móvil para verificación Meta/WhatsApp (sin validación de firma)
    path('forward-to-mobile/', ForwardToMobileView.as_view(), name='vox_forward_to_mobile'),
]
