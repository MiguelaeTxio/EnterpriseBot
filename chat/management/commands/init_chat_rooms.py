# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/chat/management/commands/init_chat_rooms.py
"""
Management command: init_chat_rooms

H17 — Paso 1: comando retirado. Creaba instancias ChatRoom(SECTION) y
ChatRoom(BREAKDOWNS) por empresa, modelo eliminado junto con ChatMessage
y BreakdownConversationTurn.

Reparación (2026-07-07, a petición de Miguel Ángel): este comando
llevaba desde H17 con un import roto a nivel de módulo (`from
chat.models import ChatRoom`, modelo que ya no existe) -- nunca se
había vuelto a invocar desde entonces (verificado: ningún `call_command`
ni referencia en todo el proyecto), pero habría fallado con
ImportError igual que chat/services.py si alguien lo hubiera ejecutado.
Se retira por completo en vez de dejarlo como comando roto disponible.

Este archivo se conserva como placeholder vacío -- Django requiere que
exista para no romper el descubrimiento de comandos del paquete
management/commands si algún otro comando se añade a esta misma app
en el futuro.

---

Management command: init_chat_rooms

H17 — Step 1: command retired. Created ChatRoom(SECTION) and
ChatRoom(BREAKDOWNS) instances per company, model removed along with
ChatMessage and BreakdownConversationTurn.

Fix (2026-07-07, at Miguel Ángel's request): this command had a broken
module-level import (`from chat.models import ChatRoom`, model that no
longer exists) since H17 -- never invoked again since then (verified:
no `call_command` nor reference anywhere in the project), but it would
have failed with an ImportError just like chat/services.py if anyone
had run it. Retired outright instead of being left as a broken command
sitting there.

This file is kept as an empty placeholder -- Django needs it present
so command discovery for this app's management/commands package isn't
broken if another command is added here in the future.
"""
