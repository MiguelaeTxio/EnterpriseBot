# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/chat/services.py
"""
Service layer for the chat module.

H17 — Paso 1: dispatch_inbound_message() y todo el despachador IRC de
mensajes entrantes (_handle_alias_collection, _handle_breakdown_routing,
_resolve_pending_routing, process_breakdown_turn, _persist_and_broadcast,
_persist_inbound_only, _send_breakdown_card, _resolve_alias,
_is_employee_help_request, _send_employee_help_menu, DispatchResult)
eliminados junto con ChatRoom y ChatMessage.

Reparación (2026-07-07, a petición de Miguel Ángel): este archivo llevaba
desde H17 con un import roto a nivel de módulo (`from chat.models import
ChatRoom, ChatMessage`, modelos que ya no existen) sin que nadie lo
notara, porque nada en todo el proyecto volvió a importar chat.services
hasta que H10 Paso 4-bis lo hizo por primera vez (ver
chat/ticket_resolution.py) y disparó el ImportError. Verificado
exhaustivamente (grep de cada función/clase del despachador en todo el
proyecto) que ninguna se llama desde ningún sitio -- el enrutamiento de
WhatsApp actual pasa por whatsapp/views.py -> whatsapp/services.py,
que persiste directamente en BreakdownTicket.conversation_log (H17
Paso 2), sin pasar por este despachador. Se retira por completo en vez
de dejarlo como código muerto que aparenta funcionar.

Este archivo se conserva como placeholder vacío para futuros servicios
del módulo chat que no dependan de ChatRoom/ChatMessage.

---

Service layer for the chat module.

H17 — Step 1: dispatch_inbound_message() and the entire inbound-message
IRC dispatcher (_handle_alias_collection, _handle_breakdown_routing,
_resolve_pending_routing, process_breakdown_turn, _persist_and_broadcast,
_persist_inbound_only, _send_breakdown_card, _resolve_alias,
_is_employee_help_request, _send_employee_help_menu, DispatchResult)
removed along with ChatRoom and ChatMessage.

Fix (2026-07-07, at Miguel Ángel's request): this file had a broken
module-level import (`from chat.models import ChatRoom, ChatMessage`,
models that no longer exist) since H17, unnoticed because nothing in
the whole project re-imported chat.services until H10 Paso 4-bis did
so for the first time (see chat/ticket_resolution.py) and triggered the
ImportError. Exhaustively verified (grepped every dispatcher
function/class across the whole project) that none of them are called
from anywhere -- WhatsApp routing now goes through whatsapp/views.py ->
whatsapp/services.py, which persists directly into
BreakdownTicket.conversation_log (H17 Step 2), bypassing this
dispatcher entirely. Retired outright instead of being left as dead
code that only looks like it works.

This file is kept as an empty placeholder for future chat-module
services that don't depend on ChatRoom/ChatMessage.
"""
