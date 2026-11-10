# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/whatsapp/window_service.py
"""
H30 (S127). Meta 24-hour customer service window: record every inbound
message and, while the window is open, send notifications as plain
text instead of a template.

---

H30 (S127). Ventana de atención de 24 horas de Meta: se anota cada
mensaje entrante y, mientras la ventana está abierta, las
notificaciones salen como texto libre en vez de plantilla. Orden de
Miguel Ángel (S127): "no enviar la plantilla cuando estemos dentro de
la ventana de 24 horas [...] avisos y cualquier notificación". Desde el
01/10/2026 Meta cobra también las plantillas de utilidad dentro de la
ventana; el texto libre sigue siendo gratuito.

Reglas:
- La ventana se cuenta desde el último mensaje ENTRANTE del teléfono
  (`WhatsAppCustomerWindow`), nunca desde `WhatsAppSession.last_message_at`
  (auto_now: lo mueve cualquier guardado, también los salientes).
- Margen de 15 minutos antes de las 24 h: un texto libre fuera de
  ventana lo rechaza Meta después de aceptarlo Twilio (error 63016),
  sin excepción en `messages.create`, y el aviso se perdería.
- Solo se sustituye por texto una plantilla de texto puro
  (`twilio/text`). Una plantilla con botones (respuesta rápida, enlace)
  sigue saliendo como plantilla: los botones mueven flujos reales del
  webhook ("Leer aquí", reactivar sesión...) y en texto libre se
  perderían.
"""
import json
import logging
import re
from datetime import timedelta

from django.utils import timezone

logger = logging.getLogger(__name__)

WINDOW = timedelta(hours=24)
SAFETY_MARGIN = timedelta(minutes=15)
PLAIN_TEXT_TYPE = "twilio/text"

# Cuerpo de cada plantilla de texto puro, por content_sid (None = no es
# de texto puro). Vive lo que el proceso; una plantilla aprobada no
# cambia de texto sin cambiar de SID.
_template_bodies = {}


def to_e164(raw):
    """
    E.164 form of a phone (+34XXXXXXXXX for a 9-digit Spanish number).

    ---

    Teléfono en E.164: los 9 dígitos españoles con +34; un número que ya
    trae prefijo internacional se deja con sus dígitos. "" si no hay
    dígitos.
    """
    text = (raw or "").replace("whatsapp:", "").strip()
    digits = re.sub(r"\D", "", text)
    if not digits:
        return ""
    if text.startswith("+"):
        return "+" + digits
    if digits.startswith("00"):
        return "+" + digits[2:]
    if len(digits) == 9:
        return "+34" + digits
    return "+" + digits


def record_inbound(company, phone):
    """
    Note an inbound message from this phone (opens/extends the window).

    ---

    Anota un mensaje entrante de este teléfono: abre o alarga su
    ventana de 24 h. Nunca rompe el webhook.
    """
    from whatsapp.models import WhatsAppCustomerWindow

    number = to_e164(phone)
    if not number:
        return
    try:
        WhatsAppCustomerWindow.objects.update_or_create(
            company=company,
            phone_number=number,
            defaults={"last_inbound_at": timezone.now()},
        )
    except Exception:
        logger.exception(
            "# [WHATSAPP WINDOW] No se pudo anotar el entrante de %s.",
            number,
        )


def window_open(company, phone):
    """
    True if this phone wrote to the company less than 24 h ago.

    ---

    True si este teléfono escribió a la empresa hace menos de 24 h
    (menos el margen de seguridad). `company=None`: a cualquier empresa.
    """
    from whatsapp.models import WhatsAppCustomerWindow

    number = to_e164(phone)
    if not number:
        return False
    limit = timezone.now() - WINDOW + SAFETY_MARGIN
    windows = WhatsAppCustomerWindow.objects.filter(
        phone_number=number, last_inbound_at__gte=limit,
    )
    # Sin empresa (envíos genéricos sin ella a mano): cualquier ventana
    # abierta de ese teléfono -- hay un único remitente de WhatsApp.
    if company is not None:
        windows = windows.filter(company=company)
    return windows.exists()


def _plain_body(client, content_sid):
    """
    Body of a plain-text template, or None.

    ---

    Cuerpo de una plantilla de texto puro (Content API de Twilio), o
    None si tiene botones u otro tipo, o si no se puede leer.
    """
    if content_sid in _template_bodies:
        return _template_bodies[content_sid]
    body = None
    try:
        content = client.content.v1.contents(content_sid).fetch()
        types = content.types or {}
        if set(types) == {PLAIN_TEXT_TYPE}:
            body = (types[PLAIN_TEXT_TYPE] or {}).get("body") or None
    except Exception as exc:
        logger.warning(
            "# [WHATSAPP WINDOW] No se pudo leer la plantilla %s: %s -- "
            "sale como plantilla.", content_sid, exc,
        )
        return None
    _template_bodies[content_sid] = body
    return body


def render_template_text(client, content_sid, variables):
    """
    Plain-text rendering of a template, or None.

    ---

    El texto de la plantilla con sus variables sustituidas ({{1}},
    {{2}}...), o None si la plantilla no es de texto puro.
    """
    body = _plain_body(client, content_sid)
    if body is None:
        return None
    values = variables or {}
    if isinstance(values, str):
        values = json.loads(values)
    return re.sub(
        r"\{\{\s*(\w+)\s*\}\}",
        lambda match: str(values.get(match.group(1), match.group(0))),
        body,
    )


def send_notification(
    client, sender, company, phone, content_sid, variables=None,
    text=None, status_callback=None, media_url=None,
):
    """
    Send a notification: plain text inside the window, else template.

    ---

    Envía una notificación por WhatsApp. Dentro de la ventana de 24 h,
    texto libre: `text` si se da, si no el propio texto de la plantilla
    con sus variables. Fuera de la ventana, o si la plantilla tiene
    botones, la plantilla. Devuelve el mensaje de Twilio; su atributo
    `sent_as_text` dice cómo salió. Las excepciones de Twilio se
    propagan, como antes, para que cada llamador las trate igual.
    `status_callback` (H37, S132), si se da, es la URL a la que Twilio
    manda el estado de entrega del mensaje. `media_url` (S149, nóminas),
    si se da, es el archivo que acompaña al texto libre dentro de la
    ventana; fuera, el archivo lo lleva la propia plantilla.
    """
    to_number = to_e164(phone)
    from_number = sender if sender.startswith("whatsapp:") else (
        "whatsapp:%s" % sender
    )
    body = None
    if window_open(company, to_number):
        body = text or render_template_text(client, content_sid, variables)
    extra = {"status_callback": status_callback} if status_callback else {}
    if body and media_url:
        extra["media_url"] = [media_url]
    if body:
        message = client.messages.create(
            from_=from_number, to="whatsapp:%s" % to_number, body=body,
            **extra,
        )
        message.sent_as_text = True
        logger.info(
            "# [WHATSAPP WINDOW] %s dentro de la ventana: texto libre "
            "(plantilla %s no usada).", to_number, content_sid,
        )
        return message
    kwargs = {
        "from_": from_number,
        "to": "whatsapp:%s" % to_number,
        "content_sid": content_sid,
        **extra,
    }
    if variables:
        kwargs["content_variables"] = (
            variables if isinstance(variables, str)
            else json.dumps(variables)
        )
    message = client.messages.create(**kwargs)
    message.sent_as_text = False
    return message
