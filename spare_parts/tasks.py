# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/spare_parts/tasks.py

"""
Celery tasks for the spare_parts application.

Defines send_delivery_note_photo_email(): sends the original photo/PDF
of a confirmed DeliveryNote as an email attachment via the Twilio
Email API (native Twilio Console product, base URL
https://comms.twilio.com/v1/Emails -- NOT the classic Twilio SendGrid
product, and NOT the sendgrid-python package). Authenticates with the
same TWILIO_API_KEY_SID/TWILIO_API_KEY_SECRET already used by the rest
of the project for Voice/WhatsApp -- Twilio Email shares the account's
API keys, no separate credential is required. After a successful send
the file is deleted from the PythonAnywhere server -- the extracted
data stays in BD permanently, only the source file is removed. This is
a deliberate business rule (S004-H10): the file no longer needs to
live on the server once administración has a copy by email, and it
avoids accumulating photos/PDFs on PythonAnywhere while there is no
OneDrive/SharePoint integration yet (see Hito 15).

---

Tareas Celery para la aplicación spare_parts.

Define send_delivery_note_photo_email(): envía la foto/PDF original de
un DeliveryNote confirmado como adjunto de correo vía la API Twilio
Email (producto nativo de la consola de Twilio, base URL
https://comms.twilio.com/v1/Emails -- NO el producto Twilio SendGrid
clásico, ni el paquete sendgrid-python). Se autentica con las mismas
TWILIO_API_KEY_SID/TWILIO_API_KEY_SECRET que ya usa el resto del
proyecto para Voz/WhatsApp -- Twilio Email comparte las claves API de
la cuenta, no requiere credencial separada. Tras un envío con éxito el
archivo se borra del servidor de PythonAnywhere -- los datos
extraídos se quedan en BD permanentemente, solo se elimina el archivo
origen. Es una regla de negocio deliberada (S004-H10): el archivo ya
no necesita vivir en el servidor una vez que administración tiene una
copia por correo, y evita acumular fotos/PDFs en PythonAnywhere
mientras no exista integración con OneDrive/SharePoint (ver Hito 15).
"""
import base64
import logging
import os

import requests
from celery.contrib.django.task import DjangoTask
from enterprise_core.celery import app

from .models import DeliveryNote

logger = logging.getLogger(__name__)

# Twilio Email API -- verified in S004-H10 against current Twilio docs
# (docs.twilio.com/email/api/overview, /getting-started, 2026). Async
# endpoint: a 202 response means Twilio accepted the send request, not
# final delivery confirmation. Full delivery tracking (SENT/DELIVERED/
# FAILED) would require polling the returned operationLocation or a
# status webhook -- out of scope for S004, noted here for a future step.
# ---
# API Twilio Email -- verificada en S004-H10 contra la documentación
# actual de Twilio (docs.twilio.com/email/api/overview,
# /getting-started, 2026). Endpoint asíncrono: una respuesta 202
# significa que Twilio aceptó la solicitud de envío, no que la entrega
# final esté confirmada. El seguimiento completo de entrega
# (SENT/DELIVERED/FAILED) requeriría sondear el operationLocation
# devuelto o un webhook de estado -- fuera de alcance de S004, se deja
# anotado aquí como posible paso futuro.
_TWILIO_EMAIL_API_URL = 'https://comms.twilio.com/v1/Emails'

# Mismo buzón real para remitente y destinatario, confirmado por
# Miguel Ángel en S004 (no existe no-reply@ en el dominio del grupo).
# Same real mailbox for sender and recipient, confirmed by Miguel
# Ángel in S004 (no no-reply@ address exists on the group's domain).
_ADMIN_EMAIL = 'administracion@gruasalvarez.com'
_ADMIN_NAME = 'Administración Grupo Álvarez'

_MIME_TYPES = {
    '.pdf': 'application/pdf',
    '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.png': 'image/png',
    '.webp': 'image/webp',
}


@app.task(base=DjangoTask, bind=True, max_retries=3, default_retry_delay=60)
def send_delivery_note_photo_email(self, delivery_note_id: int) -> None:
    """
    Sends the confirmed delivery note's source file (photo or PDF) by
    email to administración via the Twilio Email API and deletes the
    file from disk only if Twilio accepts the send (202 Accepted).

    Never deletes the file if the send fails -- Celery retries up to
    max_retries times before giving up, and the file stays on the
    server (safe default) if all retries are exhausted, logged as an
    error for manual follow-up.

    ---

    Envía por correo a administración, vía la API Twilio Email, el
    archivo origen (foto o PDF) del albarán confirmado, y borra el
    archivo del disco solo si Twilio acepta el envío (202 Accepted).

    Nunca borra el archivo si el envío falla -- Celery reintenta hasta
    max_retries veces antes de desistir, y si se agotan los reintentos
    el archivo se queda en el servidor (comportamiento seguro por
    defecto), registrado como error para seguimiento manual.
    """
    try:
        delivery_note = DeliveryNote.objects.get(pk=delivery_note_id)
    except DeliveryNote.DoesNotExist:
        logger.error(
            '# [Tarea] send_delivery_note_photo_email: DeliveryNote '
            '#%d no existe.',
            delivery_note_id,
        )
        return

    file_field = delivery_note.image or delivery_note.pdf_file
    if not file_field:
        logger.info(
            '# [Tarea] Albarán #%d sin archivo asociado -- nada que '
            'enviar (probablemente ya procesado en una ejecución '
            'anterior).',
            delivery_note_id,
        )
        return

    file_path = file_field.path
    file_name = os.path.basename(file_path)
    extension = os.path.splitext(file_name)[1].lower()
    mime_type = _MIME_TYPES.get(extension, 'application/octet-stream')

    api_key_sid = os.getenv('TWILIO_API_KEY_SID')
    api_key_secret = os.getenv('TWILIO_API_KEY_SECRET')
    if not api_key_sid or not api_key_secret:
        logger.error(
            '# [Tarea] TWILIO_API_KEY_SID / TWILIO_API_KEY_SECRET no '
            'configuradas en .env -- no se puede enviar el correo del '
            'albarán #%d. El archivo NO se borra.',
            delivery_note_id,
        )
        return

    subject = (
        f'Albarán de proveedor {delivery_note.supplier_name or "s/n"} '
        f'— {delivery_note.delivery_number or delivery_note.pk}'
    )
    html_body = (
        f'<p>Albarán confirmado en EnterpriseBot.</p>'
        f'<p>'
        f'Proveedor: {delivery_note.supplier_name or "-"} '
        f'({delivery_note.supplier_tax_id or "-"})<br>'
        f'Destinatario: {delivery_note.recipient_name or "-"} '
        f'({delivery_note.recipient_tax_id or "-"}) '
        f'[{delivery_note.recipient_company_code or "sin resolver"}]<br>'
        f'Número de albarán: {delivery_note.delivery_number or "-"}<br>'
        f'Fecha: {delivery_note.delivery_date or "-"}'
        f'</p>'
    )

    with open(file_path, 'rb') as f:
        encoded = base64.b64encode(f.read()).decode()

    payload = {
        'from': {'address': _ADMIN_EMAIL, 'name': _ADMIN_NAME},
        'to': [{'address': _ADMIN_EMAIL, 'name': _ADMIN_NAME}],
        'content': {'subject': subject, 'html': html_body},
        'attachments': [{
            'filename': file_name,
            'contentType': mime_type,
            'content': encoded,
        }],
    }

    try:
        response = requests.post(
            _TWILIO_EMAIL_API_URL,
            json=payload,
            auth=(api_key_sid, api_key_secret),
            timeout=30,
        )
    except requests.RequestException as exc:
        logger.exception(
            '# [Tarea] Fallo de red enviando por correo el albarán '
            '#%d (intento %d/%d). El archivo NO se borra.',
            delivery_note_id, self.request.retries + 1, self.max_retries,
        )
        raise self.retry(exc=exc)

    if response.status_code != 202:
        logger.error(
            '# [Tarea] Twilio Email devolvió %d al enviar el albarán '
            '#%d: %s. El archivo NO se borra.',
            response.status_code, delivery_note_id, response.text,
        )
        raise self.retry(
            exc=RuntimeError(f'Twilio Email status {response.status_code}')
        )

    operation_id = response.json().get('operationId', '')

    # Success (202 Accepted): delete the file from disk and clear the
    # model reference. Note this confirms Twilio accepted the request,
    # not final delivery -- see module docstring.
    # Éxito (202 Accepted): borrar el archivo del disco y limpiar la
    # referencia del modelo. Esto confirma que Twilio aceptó la
    # solicitud, no la entrega final -- ver docstring del módulo.
    if delivery_note.image:
        delivery_note.image.delete(save=False)
    if delivery_note.pdf_file:
        delivery_note.pdf_file.delete(save=False)
    delivery_note.save(update_fields=['image', 'pdf_file'])

    logger.info(
        '# [Tarea] Albarán #%d enviado por correo a %s '
        '(operationId=%s) y archivo origen eliminado del servidor.',
        delivery_note_id, _ADMIN_EMAIL, operation_id,
    )
