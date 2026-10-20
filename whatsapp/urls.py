# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/whatsapp/urls.py
"""
URL configuration for the whatsapp channel app.

Webhook endpoints exposed to Twilio:
  - /api/whatsapp/incoming/  -- inbound user messages (chatbot).
  - /api/whatsapp/presence/  -- presence reminder responses.
  - /api/whatsapp/albaran-status/<token>/  -- delivery status of the
    albarán notice (H37, S132).

Included in enterprise_core/urls.py under the prefix api/whatsapp/.

---

Configuración de URLs de la app del canal WhatsApp.

Endpoints webhook expuestos a Twilio:
  - /api/whatsapp/incoming/  -- mensajes entrantes del usuario
    (chatbot).
  - /api/whatsapp/presence/  -- respuestas a recordatorios de presencia
    (1h / 2h / disponible).
  - /api/whatsapp/albaran-status/<token>/  -- informe de entrega del
    aviso del albarán (H37, S132).

Se incluye en enterprise_core/urls.py bajo el prefijo api/whatsapp/.
"""

from django.urls import path

from .views import (
    AlbaranNoticeStatusView,
    IncomingWhatsAppView,
    PresenceWhatsAppView,
)

app_name = "whatsapp"

urlpatterns = [
    path(
        "incoming/",
        IncomingWhatsAppView.as_view(),
        name="incoming",
    ),
    path(
        "presence/",
        PresenceWhatsAppView.as_view(),
        name="presence",
    ),
    # H37 (S132): Twilio delivery status of the albarán notice.
    # Informe de entrega de Twilio del aviso del albarán.
    path(
        "albaran-status/<str:token>/",
        AlbaranNoticeStatusView.as_view(),
        name="albaran_notice_status",
    ),
]
