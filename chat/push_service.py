# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/chat/push_service.py
"""
H37 (S138). Push notifications of the platform chat rooms (Web Push
with VAPID keys).

---

H37 (S138). Notificaciones push de las salas de chat (Web Push con
claves VAPID). Pipeline híbrido decidido por Miguel Ángel: el aviso
principal es push; quien no active las push sigue con el aviso por
WhatsApp, y quien está dentro de la sala por WhatsApp (#asistencia)
sigue recibiéndola por WhatsApp.

- Un aviso push por mensaje, agrupado en una sola notificación por
  sala (la última sustituye a la anterior), con el autor y el texto.
- Las claves VAPID viven en el `.env` del servidor
  (`ROOM_PUSH_VAPID_PRIVATE_KEY`, `ROOM_PUSH_VAPID_PUBLIC_KEY`), las
  crea el comando `create_room_push_keys`. Se leen también del propio
  archivo `.env` para no tener que reiniciar procesos tras crearlas.
"""
import json
import logging
import re

from django.conf import settings
from django.utils import timezone

from chat.models import ChatMessage, ChatPushSubscription, ChatRoomMember

logger = logging.getLogger(__name__)

PRIVATE_KEY_NAME = "ROOM_PUSH_VAPID_PRIVATE_KEY"
PUBLIC_KEY_NAME = "ROOM_PUSH_VAPID_PUBLIC_KEY"
VAPID_SUBJECT = "mailto:avisos@grupoalvarez.es"
PUSH_TTL = 24 * 3600
MAX_PUSH_TEXT = 140
GONE_STATUSES = (404, 410)


def _key(name):
    """
    A VAPID key from the environment or from the .env file.

    ---

    Una clave VAPID del entorno o, si el proceso arrancó antes de
    crearla, del propio archivo `.env` del proyecto.
    """
    import os

    value = os.environ.get(name, "")
    if value:
        return value
    from dotenv import dotenv_values

    return dotenv_values(settings.BASE_DIR / ".env").get(name, "") or ""


def public_key():
    """
    Public VAPID key for the browser ("" if not created yet).

    ---

    Clave pública VAPID para el navegador ("" si aún no se ha creado).
    """
    return _key(PUBLIC_KEY_NAME)


def enabled():
    """
    Whether push notifications can be sent (both keys exist).

    ---

    Si se pueden mandar push (existen las dos claves).
    """
    return bool(public_key() and _key(PRIVATE_KEY_NAME))


def subscribe(member, data, user_agent=""):
    """
    Save (or move to this member) a browser push subscription.

    ---

    Guarda la suscripción push del navegador (o la pasa a este miembro
    si ese dispositivo era de otro). Devuelve la suscripción o None si
    los datos no valen.
    """
    try:
        endpoint = str(data["endpoint"])
        keys = data["keys"]
        p256dh = str(keys["p256dh"])
        auth = str(keys["auth"])
    except (KeyError, TypeError):
        return None
    if not endpoint.startswith("https://") or len(endpoint) > 500:
        return None
    subscription, _created = ChatPushSubscription.objects.update_or_create(
        endpoint=endpoint,
        defaults={
            "member": member, "p256dh": p256dh[:200], "auth": auth[:100],
            "user_agent": (user_agent or "")[:200], "last_error": "",
        },
    )
    logger.info(
        "# [CHAT PUSH] Avisos activados para el miembro %s (%s).",
        member.pk, subscription.pk,
    )
    return subscription


def unsubscribe(endpoint):
    """
    Remove a push subscription by its endpoint.

    ---

    Borra una suscripción push por su dirección.
    """
    ChatPushSubscription.objects.filter(endpoint=endpoint).delete()


def payload(message):
    """
    Notification of a room message: title, text, link and group.

    ---

    La notificación de un mensaje: título (sala y autor), texto (o el
    nombre del archivo), enlace a la sala y grupo (una sola
    notificación por sala).
    """
    room = message.room
    # Notifications are plain text: WhatsApp marks out (*x* -> x).
    # Las notificaciones son texto plano: sin marcas de WhatsApp.
    text = re.sub(r"(```|[*_~`])", "", (message.body or "")).strip()
    if message.transcript:
        text = ("%s 🎤 %s" % (text, message.transcript)).strip()
    if not text and message.attachment_name:
        text = "📄 %s" % message.attachment_name
    from chat.room_service import TONE_EMOJI

    if message.tone in TONE_EMOJI:
        text = "%s %s" % (TONE_EMOJI[message.tone], text)
    if len(text) > MAX_PUSH_TEXT:
        text = text[:MAX_PUSH_TEXT - 1] + "…"
    return {
        "title": "#%s · %s" % (room.slug, message.author_name),
        "body": text,
        "url": "/sala/%s/" % room.slug,
        "tag": "sala-%s" % room.slug,
    }


def deliver_push(message_pk, member_pks):
    """
    Send a room message by push to the devices of these members.

    ---

    Manda un mensaje de la sala por push a los dispositivos de estos
    miembros (desde Celery). Un dispositivo que ya no existe se borra;
    si un miembro se queda sin ninguno, recibe el aviso por WhatsApp de
    siempre para no perder el mensaje.
    """
    from pywebpush import WebPushException, webpush
    from py_vapid import Vapid

    message = ChatMessage.objects.select_related("room").filter(
        pk=message_pk,
    ).first()
    if message is None or not enabled():
        return
    vapid = Vapid.from_raw(_key(PRIVATE_KEY_NAME).encode())
    data = json.dumps(payload(message), ensure_ascii=False)
    lost = []
    for member in ChatRoomMember.objects.filter(pk__in=member_pks):
        delivered = False
        for subscription in member.push_subscriptions.all():
            try:
                webpush(
                    subscription_info={
                        "endpoint": subscription.endpoint,
                        "keys": {
                            "p256dh": subscription.p256dh,
                            "auth": subscription.auth,
                        },
                    },
                    data=data,
                    vapid_private_key=vapid,
                    vapid_claims={"sub": VAPID_SUBJECT},
                    ttl=PUSH_TTL,
                )
            except WebPushException as exc:
                status = getattr(exc.response, "status_code", None)
                if status in GONE_STATUSES:
                    logger.info(
                        "# [CHAT PUSH] Dispositivo dado de baja (%s): %s",
                        status, subscription.pk,
                    )
                    subscription.delete()
                else:
                    logger.warning(
                        "# [CHAT PUSH] Push fallido %s: %s",
                        subscription.pk, exc,
                    )
                    ChatPushSubscription.objects.filter(
                        pk=subscription.pk,
                    ).update(last_error=str(exc)[:255])
                continue
            except Exception as exc:  # noqa: BLE001 -- los demás siguen
                logger.exception("# [CHAT PUSH] Error: %s", exc)
                continue
            delivered = True
            ChatPushSubscription.objects.filter(pk=subscription.pk).update(
                last_sent_at=timezone.now(), last_error="",
            )
        if not delivered and not member.push_subscriptions.exists():
            lost.append(member.pk)
    if lost:
        # No device left: the WhatsApp notice, as for everybody else.
        # Sin dispositivo: el aviso por WhatsApp, como a los demás.
        from chat.room_service import _claim_notice
        from chat.tasks import send_room_notice

        now = timezone.now()
        for member_pk in lost:
            if _claim_notice(member_pk, now):
                send_room_notice.delay(member_pk)
