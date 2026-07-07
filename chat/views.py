# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/chat/views.py
"""
View definitions for the chat module.

H17 — Paso 1: ChatRoomView, ChatMessagesPollingView, ChatRoomListView,
ChatSendView, ChatAliasSetView y BreakdownRoomManageView eliminadas
junto con ChatRoom y ChatMessage. Las vistas de tickets de avería
viven en chat/views_tickets.py, ya actualizado para H17 (sin
dependencia de ChatRoom).

Reparación (2026-07-07, a petición de Miguel Ángel): este archivo
llevaba desde H17 con un import roto a nivel de módulo (`from
chat.models import ChatRoom, ChatMessage`, modelos que ya no existen).
Verificado exhaustivamente que ninguna de sus clases se importa ni se
enruta desde ningún sitio -- chat/urls.py solo importa desde
chat.views_tickets, nunca desde este archivo. Se retira por completo
en vez de dejarlo como código muerto e inalcanzable.

Este archivo se conserva como placeholder vacío para futuras vistas
del módulo chat que no dependan de ChatRoom/ChatMessage.

---

View definitions for the chat module.

H17 — Step 1: ChatRoomView, ChatMessagesPollingView, ChatRoomListView,
ChatSendView, ChatAliasSetView and BreakdownRoomManageView removed
along with ChatRoom and ChatMessage. Breakdown ticket views live in
chat/views_tickets.py, already updated for H17 (no ChatRoom
dependency).

Fix (2026-07-07, at Miguel Ángel's request): this file had a broken
module-level import (`from chat.models import ChatRoom, ChatMessage`,
models that no longer exist) since H17. Exhaustively verified that
none of its classes are imported or routed to from anywhere --
chat/urls.py only imports from chat.views_tickets, never from this
file. Retired outright instead of being left as dead, unreachable
code.

This file is kept as an empty placeholder for future chat-module
views that don't depend on ChatRoom/ChatMessage.
"""
