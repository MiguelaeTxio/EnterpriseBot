# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/chat/urls.py
"""
URL configuration for the chat module.
H17 — Paso 1: Chat IRC routes (room list, room detail, messages polling,
send, alias set, breakdown room manage) removed along with ChatRoom.
Only breakdown ticket routes are kept.
All routes are served under the /panel/chat/ prefix defined in panel/urls.py.
---
Configuración de URLs para el módulo de chat.
H17 — Paso 1: Rutas del chat IRC (lista de salas, detalle de sala, polling
de mensajes, envío, establecimiento de alias, gestión de sala BREAKDOWNS)
eliminadas junto con ChatRoom.
Solo se conservan las rutas de tickets de avería.
Todas las rutas se sirven bajo el prefijo /panel/chat/ definido en panel/urls.py.
"""

from django.urls import path

from chat.views_tickets import (
    BreakdownTicketListView,
    BreakdownTicketDetailView,
    BreakdownTicketCreateView,
)

app_name = "chat"

urlpatterns = [
    # Breakdown ticket list — Lista de tickets de avería (ADMIN, SUPERVISOR, WORKSHOPBOSS).
    # Paso 12 — Hito 13 (2026-05-18)
    path("breakdowns/tickets/", BreakdownTicketListView.as_view(), name="breakdown_ticket_list"),

    # Breakdown ticket detail — Detalle + acciones sobre ticket de avería.
    # Paso 12 — Hito 13 (2026-05-18)
    path("breakdowns/tickets/<int:pk>/", BreakdownTicketDetailView.as_view(), name="breakdown_ticket_detail"),

    # Breakdown ticket create — Creación manual de ticket de avería desde el panel.
    # Paso 3 — Hito 14 (2026-05-21)
    path("breakdowns/tickets/create/", BreakdownTicketCreateView.as_view(), name="breakdown_ticket_create"),
]
