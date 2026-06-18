# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/chat/urls.py
"""
URL configuration for the chat module.
All routes are served under the /panel/chat/ prefix defined in panel/urls.py.
---
Configuración de URLs para el módulo de chat.
Todas las rutas se sirven bajo el prefijo /panel/chat/ definido en panel/urls.py.
"""

from django.urls import path

from chat.views import (
    ChatRoomListView,
    ChatRoomView,
    ChatMessagesPollingView,
    ChatSendView,
    ChatAliasSetView,
    BreakdownRoomManageView,
)
from chat.views_tickets import (
    BreakdownTicketListView,
    BreakdownTicketDetailView,
    BreakdownTicketCreateView,
)

app_name = "chat"

urlpatterns = [
    # Chat room list — Lista de salas de chat IRC (ADMIN y SUPERVISOR).
    # Paso 4 — Hito 13 (2026-05-15)
    path("", ChatRoomListView.as_view(), name="room_list"),

    # Chat room detail — Sala IRC con historial de mensajes y polling HTMX.
    # Paso 4 — Hito 13 (2026-05-15)
    path("<int:room_pk>/", ChatRoomView.as_view(), name="room_detail"),

    # Chat messages polling fragment — Fragmento HTMX de mensajes (polling cada 3s).
    # Paso 4 — Hito 13 (2026-05-15)
    path("<int:room_pk>/messages/", ChatMessagesPollingView.as_view(), name="room_messages"),

    # Chat send — Envío de mensaje desde el panel al broadcast de sección.
    # Paso 6 — Hito 13 (2026-05-15)
    path("<int:room_pk>/send/", ChatSendView.as_view(), name="room_send"),

    # Alias set — Establecimiento de alias del CompanyUser desde el modal de sala.
    # Paso 6 — Hito 13 (2026-05-15)
    path("alias/set/", ChatAliasSetView.as_view(), name="alias_set"),

    # Breakdown ticket list — Lista de tickets de avería (ADMIN y SUPERVISOR).
    # Paso 12 — Hito 13 (2026-05-18)
    path("breakdowns/tickets/", BreakdownTicketListView.as_view(), name="breakdown_ticket_list"),

    # Breakdown ticket detail — Detalle + acciones sobre ticket de avería.
    # Paso 12 — Hito 13 (2026-05-18)
    path("breakdowns/tickets/<int:pk>/", BreakdownTicketDetailView.as_view(), name="breakdown_ticket_detail"),

    # Breakdown ticket create — Creación manual de ticket de avería desde el panel.
    # Paso 3 — Hito 14 (2026-05-21)
    path("breakdowns/tickets/create/", BreakdownTicketCreateView.as_view(), name="breakdown_ticket_create"),

    # Breakdown room manage — Gestión de membresía M2M de la sala BREAKDOWNS.
    # Paso 12 — Hito 13 (2026-05-18)
    path("breakdowns/manage/", BreakdownRoomManageView.as_view(), name="breakdown_room_manage"),
]
