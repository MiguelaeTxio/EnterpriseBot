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


@shared_task(name="chat.tasks.relay_room_message")
def relay_room_message(message_pk, member_pks):
    """
    Send a room message to the members inside by WhatsApp.

    ---

    Manda un mensaje de la sala a los miembros que están dentro por
    WhatsApp (S138, `chat.room_service.deliver_relay`).
    """
    from chat.room_service import deliver_relay

    deliver_relay(message_pk, member_pks)


@shared_task(name="chat.tasks.post_whatsapp_to_room")
def post_whatsapp_to_room(member_pk, body, media_url, content_type):
    """
    Post in the room a WhatsApp message with a file.

    ---

    Publica en la sala un mensaje de WhatsApp con foto o PDF (S138,
    `chat.room_service.post_whatsapp_message`).
    """
    from chat.room_service import post_whatsapp_message

    post_whatsapp_message(member_pk, body, media_url, content_type)


@shared_task(name="chat.tasks.send_room_push")
def send_room_push(message_pk, member_pks):
    """
    Send a room message by push to these members.

    ---

    Manda un mensaje de la sala por push a estos miembros (S138,
    `chat.push_service.deliver_push`).
    """
    from chat.push_service import deliver_push

    deliver_push(message_pk, member_pks)
