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


@shared_task(name="chat.tasks.post_room_voice")
def post_room_voice(room_pk, attachment, author_person_pk, author_name,
                    company_user_pk, member_pk):
    """
    Transcribe and post a voice message recorded in the room.

    ---

    Transcribe y publica un mensaje de voz grabado en la sala (S138,
    `chat.room_service.post_voice`).
    """
    from chat.room_service import post_voice

    post_voice(
        room_pk, attachment, author_person_pk=author_person_pk,
        author_name=author_name, company_user_pk=company_user_pk,
        member_pk=member_pk,
    )


@shared_task(name="chat.tasks.whatsapp_voice_note")
def whatsapp_voice_note(post_data):
    """
    Transcribe a WhatsApp voice note and feed it back as text.

    ---

    Transcribe una nota de voz de WhatsApp y la vuelve a pasar por el
    webhook como si fuera un texto (S138, todos los caminos llevan a
    Roma): Alia, la sala o el asistente la tratan igual que lo escrito.
    El audio va con la petición (`EBVoiceBlob`/`EBVoiceType`) para que
    la sala lo publique con su texto.
    """
    import logging

    from django.test import RequestFactory

    from chat.room_service import _say, media_bytes, store_upload
    from chat.voice_service import base_type, transcribe
    from whatsapp.views import IncomingWhatsAppView

    logger = logging.getLogger(__name__)
    media_url = post_data.get("MediaUrl0", "")
    content_type = base_type(post_data.get("MediaContentType0", ""))
    from_number = post_data.get("From", "").replace("whatsapp:", "")
    try:
        data = media_bytes(media_url)
    except Exception:  # noqa: BLE001 -- se avisa a quien la mandó
        logger.exception("# [CHAT VOZ] Nota de voz no descargada.")
        _say(from_number, "No he podido descargar la nota de voz.")
        return
    text = transcribe(data, content_type)
    if not text:
        _say(from_number, (
            "No he entendido la nota de voz. ¿Puedes repetirla o "
            "escribirlo?"
        ))
        return
    attachment = store_upload(data, content_type, "nota_de_voz")
    fed = dict(post_data)
    for key in list(fed):
        if key.startswith("Media"):
            fed.pop(key)
    fed.update({"Body": text, "NumMedia": "0", "EBVoice": "1"})
    if attachment is not None:
        fed.update({
            "EBVoiceBlob": attachment["blob"],
            "EBVoiceType": attachment["type"],
        })
    request = RequestFactory().post(
        "/api/whatsapp/incoming/", fed,
        HTTP_HOST="enterprisebot-miguelaetxio.pythonanywhere.com",
    )
    IncomingWhatsAppView.as_view()(request)
