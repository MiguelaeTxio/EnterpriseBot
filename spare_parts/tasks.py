# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/spare_parts/tasks.py

"""
Celery tasks for the spare_parts application.

Defines send_delivery_note_photo_email(): sends the original photo/PDF
of a confirmed DeliveryNote as an email attachment via Twilio SendGrid,
then deletes the file from the PythonAnywhere server -- the extracted
data stays in BD permanently, only the source file is removed. This is
a deliberate business rule (S004-H10): the file no longer needs to live
on the server once administración has a copy by email, and it avoids
accumulating photos/PDFs on PythonAnywhere while there is no OneDrive/
SharePoint integration yet (see Hito 15).

---

Tareas Celery para la aplicación spare_parts.

Define send_delivery_note_photo_email(): envía la foto/PDF original de
un DeliveryNote confirmado como adjunto de correo vía Twilio SendGrid,
y a continuación borra el archivo del servidor de PythonAnywhere -- los
datos extraídos se quedan en BD permanentemente, solo se elimina el
archivo origen. Es una regla de negocio deliberada (S004-H10): el
archivo ya no necesita vivir en el servidor una vez que administración
tiene una copia por correo, y evita acumular fotos/PDFs en
PythonAnywhere mientras no exista integración con OneDrive/SharePoint
(ver Hito 15).
"""
import base64
import logging
import os

from celery.contrib.django.task import DjangoTask
from enterprise_core.celery import app

from .models import DeliveryNote

logger = logging.getLogger(__name__)

# Fixed business recipient (S004-H10) -- not a secret, kept as a code
# constant rather than an env var per Miguel Ángel's instruction.
# ---
# Destinatario de negocio fijo (S004-H10) -- no es un secreto, se
# mantiene como constante de código en vez de variable de entorno,
# según indicación de Miguel Ángel.
_RECIPIENT_EMAIL = 'administración@gruasalvarez.com'

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
    email to administración and deletes the file from disk on success.

    Never deletes the file if the email send fails -- Celery retries
    up to max_retries times before giving up, and the file stays on
    the server (safe default) if all retries are exhausted, logged as
    an error for manual follow-up.

    ---

    Envía por correo a administración el archivo origen (foto o PDF)
    del albarán confirmado y borra el archivo del disco solo si el
    envío tuvo éxito.

    Nunca borra el archivo si el envío falla -- Celery reintenta hasta
    max_retries veces antes de desistir, y si se agotan los reintentos
    el archivo se queda en el servidor (comportamiento seguro por
    defecto), registrado como error para seguimiento manual.
    """
    from sendgrid import SendGridAPIClient
    from sendgrid.helpers.mail import (
        Attachment,
        ContentId,
        Disposition,
        FileContent,
        FileName,
        FileType,
        Mail,
    )

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

    api_key = os.getenv('SENDGRID_API_KEY')
    from_email = os.getenv('SPARE_PARTS_EMAIL_FROM')
    if not api_key or not from_email:
        logger.error(
            '# [Tarea] SENDGRID_API_KEY / SPARE_PARTS_EMAIL_FROM no '
            'configuradas en .env -- no se puede enviar el correo del '
            'albarán #%d. El archivo NO se borra.',
            delivery_note_id,
        )
        return

    subject = (
        f'Albarán de proveedor {delivery_note.supplier_name or "s/n"} '
        f'— {delivery_note.delivery_number or delivery_note.pk}'
    )
    body = (
        f'Albarán confirmado en EnterpriseBot.\n\n'
        f'Proveedor: {delivery_note.supplier_name or "-"} '
        f'({delivery_note.supplier_tax_id or "-"})\n'
        f'Destinatario: {delivery_note.recipient_name or "-"} '
        f'({delivery_note.recipient_tax_id or "-"}) '
        f'[{delivery_note.recipient_company_code or "sin resolver"}]\n'
        f'Número de albarán: {delivery_note.delivery_number or "-"}\n'
        f'Fecha: {delivery_note.delivery_date or "-"}\n'
    )

    with open(file_path, 'rb') as f:
        encoded = base64.b64encode(f.read()).decode()

    message = Mail(
        from_email=from_email,
        to_emails=_RECIPIENT_EMAIL,
        subject=subject,
        plain_text_content=body,
    )
    attachment = Attachment()
    attachment.file_content = FileContent(encoded)
    attachment.file_type = FileType(mime_type)
    attachment.file_name = FileName(file_name)
    attachment.disposition = Disposition('attachment')
    attachment.content_id = ContentId(f'delivery-note-{delivery_note.pk}')
    message.attachment = attachment

    try:
        client = SendGridAPIClient(api_key)
        response = client.send(message)
    except Exception as exc:
        logger.exception(
            '# [Tarea] Fallo enviando por correo el albarán #%d '
            '(intento %d/%d). El archivo NO se borra.',
            delivery_note_id, self.request.retries + 1, self.max_retries,
        )
        raise self.retry(exc=exc)

    if response.status_code not in (200, 201, 202):
        logger.error(
            '# [Tarea] SendGrid devolvió %d al enviar el albarán #%d: '
            '%s. El archivo NO se borra.',
            response.status_code, delivery_note_id, response.body,
        )
        raise self.retry(
            exc=RuntimeError(f'SendGrid status {response.status_code}')
        )

    # Success: delete the file from disk and clear the model reference.
    # Éxito: borrar el archivo del disco y limpiar la referencia del modelo.
    if delivery_note.image:
        delivery_note.image.delete(save=False)
    if delivery_note.pdf_file:
        delivery_note.pdf_file.delete(save=False)
    delivery_note.save(update_fields=['image', 'pdf_file'])

    logger.info(
        '# [Tarea] Albarán #%d enviado por correo a %s y archivo '
        'origen eliminado del servidor.',
        delivery_note_id, _RECIPIENT_EMAIL,
    )
