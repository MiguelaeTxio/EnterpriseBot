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

Sender domain (S005-H10 update): campustudionline.com, authenticated
in the Twilio console -- domain owned by Miguel Ángel, used to avoid
depending on a third party authenticating gruasalvarez.com, which
remained blocked. The real administración recipient is unchanged and
confirmed by Miguel Ángel: administracion@gruasalvarez.com, receiving
via its own normal MX, unrelated to Twilio's sender-domain
authentication.

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

Dominio remitente (actualización S005-H10): campustudionline.com,
autenticado en la consola de Twilio -- dominio propiedad de Miguel
Ángel, usado para no depender de que un tercero autentique
gruasalvarez.com, que seguía bloqueado. El destinatario real de
administración no cambia y está confirmado por Miguel Ángel:
administracion@gruasalvarez.com, que recibe por su propio MX normal,
sin relación con la autenticación de dominio remitente de Twilio.
"""
import base64
import logging
import os
from datetime import date

import requests
from celery.contrib.django.task import DjangoTask
from enterprise_core.celery import app

from .models import DeliveryNote, DeliveryNoteLine
from .services import (
    GeminiVisionExtractionService,
    parse_decimal,
    resolve_line_assignment,
    resolve_recipient_company_code,
)

logger = logging.getLogger(__name__)


# S014-H10, Bloque B punto 2 (conversión síncrono -> asíncrono,
# pendiente desde S013): la extracción Gemini Vision de un albarán se
# ejecuta aquí, en segundo plano, en vez de bloquear la petición HTTP
# del operario dentro de DeliveryNoteUploadView.post() como hasta
# ahora. El operario hace la foto, la sube, y DeliveryNoteUploadView
# solo guarda el archivo (status=PENDING, valor por defecto del
# campo) y encola esta tarea -- el albarán pasa a PROCESSED cuando
# Gemini termina, o a ERROR si falla (sin borrar el archivo, a
# diferencia del comportamiento síncrono anterior que sí lo hacía --
# en segundo plano no hay ninguna petición HTTP a la que devolver un
# mensaje de error, así que el archivo se conserva para que el
# operario pueda ver el fallo y reintentar desde
# DeliveryNoteDetailView, ver DeliveryNoteRetryExtractionView en
# views.py).
# ---
# S014-H10, Bloque B point 2 (sync -> async conversion, pending since
# S013): the Gemini Vision extraction of a delivery note now runs
# here, in the background, instead of blocking the operator's HTTP
# request inside DeliveryNoteUploadView.post() as before. The operator
# takes the photo, uploads it, and DeliveryNoteUploadView only saves
# the file (status=PENDING, the field's default) and enqueues this
# task -- the note becomes PROCESSED once Gemini finishes, or ERROR if
# it fails (without deleting the file, unlike the previous synchronous
# behaviour -- there is no HTTP request left to return an error
# message to in the background, so the file is kept so the operator
# can see the failure and retry from DeliveryNoteDetailView, see
# DeliveryNoteRetryExtractionView in views.py).
@app.task(base=DjangoTask, bind=True, max_retries=0)
def extract_delivery_note_data(self, delivery_note_id: int) -> None:
    """
    Runs GeminiVisionExtractionService on a just-uploaded DeliveryNote
    and creates its DeliveryNoteLine rows. Sets status=PROCESSED on
    success, status=ERROR on failure (file kept for a manual retry).

    max_retries=0: unlike send_delivery_note_photo_email (transient
    network/API errors worth retrying automatically), an extraction
    failure here is surfaced to the operator as status=ERROR for an
    explicit, visible retry instead of silent background retries --
    consistent with the previous synchronous behaviour, which also
    never retried automatically and instead reported the failure
    immediately.

    ---

    Ejecuta GeminiVisionExtractionService sobre un DeliveryNote recién
    subido y crea sus filas DeliveryNoteLine. Marca status=PROCESSED
    si tiene éxito, status=ERROR si falla (el archivo se conserva
    para un reintento manual).

    max_retries=0: a diferencia de send_delivery_note_photo_email
    (errores transitorios de red/API que merece la pena reintentar
    automáticamente), un fallo de extracción aquí se muestra al
    operario como status=ERROR para un reintento explícito y visible
    en vez de reintentos silenciosos en segundo plano -- coherente
    con el comportamiento síncrono anterior, que tampoco reintentaba
    automáticamente y reportaba el fallo de inmediato.
    """
    try:
        delivery_note = DeliveryNote.objects.get(pk=delivery_note_id)
    except DeliveryNote.DoesNotExist:
        logger.error(
            '# [Tarea] extract_delivery_note_data: DeliveryNote #%d '
            'no existe.',
            delivery_note_id,
        )
        return

    company = delivery_note.company
    file_path = (
        delivery_note.pdf_file.path
        if delivery_note.source_type == 'PDF'
        else delivery_note.image.path
    )

    try:
        extraction = GeminiVisionExtractionService().extract(file_path)
    except Exception:
        logger.exception(
            '# [Tarea] Fallo en la extracción Gemini Vision del '
            'albarán #%d. El archivo NO se borra -- status=ERROR '
            'para reintento manual.',
            delivery_note_id,
        )
        delivery_note.status = 'ERROR'
        delivery_note.save(update_fields=['status'])
        return

    delivery_note.supplier_name = extraction.supplier_name or ''
    delivery_note.supplier_tax_id = extraction.supplier_tax_id or ''
    delivery_note.recipient_name = extraction.recipient_name or ''
    delivery_note.recipient_tax_id = extraction.recipient_tax_id or ''
    delivery_note.recipient_company_code = resolve_recipient_company_code(
        extraction.recipient_tax_id
    )
    delivery_note.delivery_number = extraction.delivery_number or ''
    if extraction.delivery_date:
        try:
            delivery_note.delivery_date = date.fromisoformat(
                extraction.delivery_date
            )
        except ValueError:
            delivery_note.delivery_date = None
    delivery_note.general_machine_code_raw = (
        extraction.general_machine_code_raw or ''
    )
    delivery_note.extraction_raw = extraction.model_dump()
    delivery_note.status = 'PROCESSED'
    delivery_note.save()

    # Reintento (DeliveryNoteRetryExtractionView): si esta tarea ya
    # había creado líneas en un intento anterior fallido a medias, se
    # eliminan antes de recrearlas para no duplicar.
    delivery_note.lines.all().delete()

    for line_data in extraction.lines:
        effective_raw_code = (
            line_data.machine_code_raw
            or delivery_note.general_machine_code_raw
            or None
        )
        assignment_type, machine = resolve_line_assignment(
            effective_raw_code, company,
        )
        DeliveryNoteLine.objects.create(
            delivery_note=delivery_note,
            line_number=line_data.line_number,
            reference=line_data.reference or '',
            description=line_data.description,
            quantity=parse_decimal(line_data.quantity) or 0,
            unit_price=parse_decimal(line_data.unit_price),
            total_price=parse_decimal(line_data.total_price),
            machine_code_raw=line_data.machine_code_raw or '',
            assignment_type=assignment_type,
            machine=machine,
        )

    logger.info(
        '# [Tarea] Albarán #%d extraído correctamente en segundo '
        'plano: %d línea(s).',
        delivery_note_id, len(extraction.lines),
    )

# Twilio Email API -- re-verified 2026-07-06 against
# docs.twilio.com/email/api/reference/mail-send-resource: attachments
# is a CHILD property of `content`, not a top-level sibling. The
# original S004 implementation had it at the top level, which Twilio
# rejected with "Invalid value 'attachments' provided for field
# 'attachments'" (400) -- confirmed empirically in S005 against a real
# send attempt (albarán #6). Async endpoint: a 202 response means
# Twilio accepted the send request, not final delivery confirmation.
# Full delivery tracking (SENT/DELIVERED/FAILED) would require polling
# the returned operationLocation or a status webhook -- out of scope,
# noted here for a future step.
# ---
# API Twilio Email -- re-verificada 2026-07-06 contra
# docs.twilio.com/email/api/reference/mail-send-resource: attachments
# es una propiedad HIJA de `content`, no un hermano de nivel raíz. La
# implementación original de S004 lo tenía en la raíz, lo que Twilio
# rechazaba con "Invalid value 'attachments' provided for field
# 'attachments'" (400) -- confirmado empíricamente en S005 contra un
# envío real (albarán #6). Endpoint asíncrono: una respuesta 202
# significa que Twilio aceptó la solicitud de envío, no que la entrega
# final esté confirmada. El seguimiento completo de entrega
# (SENT/DELIVERED/FAILED) requeriría sondear el operationLocation
# devuelto o un webhook de estado -- fuera de alcance, se deja
# anotado aquí como posible paso futuro.
_TWILIO_EMAIL_API_URL = 'https://comms.twilio.com/v1/Emails'

# Remitente: dominio autenticado en Twilio (S005-H10, verificado en
# consola Twilio: campustudionline.com, propiedad de Miguel Ángel --
# evita depender de que un tercero autentique gruasalvarez.com).
# no-reply@ no necesita existir como buzón real -- Twilio Email es solo
# de envío, no gestiona ni requiere acceso a ninguna bandeja de entrada.
# Destinatario: buzón real de administración, sin relación con la
# autenticación de dominio de Twilio -- recibe por su propio MX normal.
#
# TEMPORAL (S005, 2026-07-06): destinatario cambiado a una dirección de
# prueba fuera de Microsoft 365 -- gruasalvarez.com (Exchange Online)
# está poniendo en cuarentena silenciosa los envíos desde el dominio
# recién autenticado campustudionline.com (Twilio marca DELIVERED a
# nivel SMTP -- confirmado, respuesta 250 de PROD.OUTLOOK.COM -- pero
# el mensaje nunca llega a ninguna carpeta visible del buzón, ni
# siquiera Correo no deseado -- confirmado por captura real de Outlook,
# probablemente cuarentena de Microsoft 365 Defender, capa distinta a
# la carpeta de spam del cliente). Este cambio permite validar el resto
# del flujo (adjunto, plantilla, borrado de archivo) sin depender de
# que se resuelva la cuarentena. Miguel Ángel tiene reunión esta misma
# tarde con el responsable de Microsoft 365 de Grupo Álvarez para dar
# de alta el remitente -- revertir a
# _RECIPIENT_EMAIL = 'administracion@gruasalvarez.com' en cuanto se
# confirme la resolución.
# ---
# Sender: domain authenticated in Twilio (S005-H10, verified in Twilio
# console: campustudionline.com, owned by Miguel Ángel -- avoids
# depending on a third party authenticating gruasalvarez.com). no-reply@
# does not need to exist as a real mailbox -- Twilio Email is send-only,
# it does not manage or require access to any inbox.
# Recipient: real administración mailbox, unrelated to Twilio's domain
# authentication -- receives via its own normal MX.
#
# TEMPORARY (S005, 2026-07-06): recipient switched to a test address
# outside Microsoft 365 -- gruasalvarez.com (Exchange Online) is
# silently quarantining sends from the newly authenticated domain
# campustudionline.com (Twilio marks it DELIVERED at SMTP level --
# confirmed, 250 response from PROD.OUTLOOK.COM -- but the message
# never reaches any visible mailbox folder, not even Junk -- confirmed
# via real Outlook screenshot, most likely Microsoft 365 Defender
# quarantine, a layer distinct from the client's spam folder). This
# switch lets the rest of the flow (attachment, template, file
# deletion) be validated without depending on the quarantine being
# resolved. Miguel Ángel has a meeting this afternoon with Grupo
# Álvarez's Microsoft 365 admin to allow-list the sender -- revert to
# _RECIPIENT_EMAIL = 'administracion@gruasalvarez.com' once resolved.
_SENDER_EMAIL = 'no-reply@campustudionline.com'
_SENDER_NAME = 'EnterpriseBot'
_RECIPIENT_EMAIL = 'nummenor@gmail.com'  # TEMPORAL -- ver nota arriba, revertir a administracion@gruasalvarez.com
_RECIPIENT_NAME = 'Prueba temporal S005'

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
        # S014-H10, Bloque B punto 1 (salvaguarda pendiente desde
        # S013): formato de fecha siempre en español (DD/MM/AAAA) en
        # este correo, sin excepción -- str(date) por defecto en
        # Python es ISO (AAAA-MM-DD) independientemente de cómo lo
        # haya leído Gemini del documento original.
        f'Fecha: '
        f'{delivery_note.delivery_date.strftime("%d/%m/%Y") if delivery_note.delivery_date else "-"}'
        f'</p>'
    )

    with open(file_path, 'rb') as f:
        encoded = base64.b64encode(f.read()).decode()

    payload = {
        'from': {'address': _SENDER_EMAIL, 'name': _SENDER_NAME},
        'to': [{'address': _RECIPIENT_EMAIL, 'name': _RECIPIENT_NAME}],
        'content': {
            'subject': subject,
            'html': html_body,
            'attachments': [{
                'filename': file_name,
                'contentType': mime_type,
                'content': encoded,
            }],
        },
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
        delivery_note_id, _RECIPIENT_EMAIL, operation_id,
    )
