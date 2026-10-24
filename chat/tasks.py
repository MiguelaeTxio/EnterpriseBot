# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/chat/tasks.py
"""
Celery tasks for the chat module.

H17 -- Paso 1: broadcast_inbound_message and purge_old_chat_messages
removed along with the old ChatRoom and ChatMessage.
H37 (S138): WhatsApp notice of the platform chat rooms, one by one.

---

Tareas Celery para el módulo de chat.

H17 -- Paso 1: broadcast_inbound_message y purge_old_chat_messages
eliminados junto con los antiguos ChatRoom y ChatMessage.
H37 (S138): aviso por WhatsApp de las salas de chat de la plataforma,
uno por miembro.
"""
from celery import shared_task


@shared_task(name="chat.tasks.send_room_notice")
def send_room_notice(member_pk):
    """
    Send the WhatsApp notice of one room member.

    ---

    Manda el aviso por WhatsApp de un miembro de la sala
    (`chat.room_service.deliver_notice`).
    """
    from chat.room_service import deliver_notice

    deliver_notice(member_pk)
