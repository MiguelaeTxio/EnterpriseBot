# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/whatsapp/urls.py
"""
URL configuration for the whatsapp channel app.
Registers the two webhook endpoints exposed to Twilio:
  - /api/whatsapp/incoming/  — inbound user messages (chatbot pipeline).
  - /api/whatsapp/presence/  — presence reminder responses (1h / 2h / disponible).
This module is included in enterprise_core/urls.py under the prefix api/whatsapp/.
---
Configuración de URLs para la app del canal WhatsApp.
Registra los dos endpoints webhook expuestos a Twilio:
  - /api/whatsapp/incoming/  — mensajes entrantes del usuario (pipeline del chatbot).
  - /api/whatsapp/presence/  — respuestas a recordatorios de presencia (1h / 2h / disponible).
Este módulo se incluye en enterprise_core/urls.py bajo el prefijo api/whatsapp/.
"""

from django.urls import path

from .views import IncomingWhatsAppView, PresenceWhatsAppView

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
]
