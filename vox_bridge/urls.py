# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/vox_bridge/urls.py
from django.urls import path
from .views import (
    InboundCallView,
    ForwardToMobileView,
    HoldMusicView,
    TransferStatusView,
    TransferAcceptView,
    ContactStatusView,
)

urlpatterns = [
    # Endpoint principal para la recepción de llamadas IVR
    path('inbound/', InboundCallView.as_view(), name='vox_inbound'),
    # Endpoint de reenvío a móvil para verificación Meta/WhatsApp (sin validación de firma)
    path('forward-to-mobile/', ForwardToMobileView.as_view(), name='vox_forward_to_mobile'),
    # -----------------------------------------------------------------------
    # PASO 39 — Transferencia real vía Dial Conference
    # STEP 39 — Real call transfer via Dial Conference
    # -----------------------------------------------------------------------
    # Música de espera servida como waitUrl durante la Conference de transferencia.
    # Hold music served as waitUrl during the transfer Conference.
    path('hold_music/', HoldMusicView.as_view(), name='vox_hold_music'),
    # Webhook de Twilio cuando el <Dial> de la Conference termina (action URL).
    # Twilio webhook when the Conference <Dial> ends (action URL).
    # DialCallStatus: completed → fin normal; no-answer/busy/failed → reconectar María.
    path(
        'transfer_status/<str:call_sid>/',
        TransferStatusView.as_view(),
        name='vox_transfer_status',
    ),
    # Invocado cuando el contacto de sección acepta la transferencia.
    # Invoked when the section contact accepts the transfer (reserved for future DTMF flow).
    path(
        'transfer_accept/<str:conference_name>/',
        TransferAcceptView.as_view(),
        name='vox_transfer_accept',
    ),
    # DT-1 FIX — StatusCallback de la llamada saliente al contacto.
    # Twilio reporta el resultado real (contestada/no contestada) aquí.
    # El action URL del <Dial><Conference> siempre devuelve 'answered'.
    path(
        'contact_status/<str:caller_call_sid>/',
        ContactStatusView.as_view(),
        name='vox_contact_status',
    ),
]
