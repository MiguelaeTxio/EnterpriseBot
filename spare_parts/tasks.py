# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/spare_parts/tasks.py

"""
Celery tasks for the spare_parts application.

Verificación S014 (2026-07-13): este comentario existe para disparar
de verdad, en producción, el reinicio condicional del worker Celery
(id 242133) del nuevo paso de deploy.yml -- confirmar en el resumen
del Action y en la pestaña Tasks del dashboard de PythonAnywhere que
el estado pasa por Starting/Restarting y vuelve a Running.

Defines extract_delivery_note_data() (Gemini Vision extraction, runs
in the background after upload) and
upload_delivery_note_photo_to_drive() (S014-H10: uploads the confirmed
delivery note's source photo/PDF to Google Drive and deletes it from
the server -- replaces the email-based persistence that existed up to
S014, see spare_parts/gdrive_service.py for the full design rationale
of the Drive integration).

---

Tareas Celery para la aplicación spare_parts.

Define extract_delivery_note_data() (extracción Gemini Vision, corre
en segundo plano tras la subida) y upload_delivery_note_photo_to_drive()
(S014-H10: sube la foto/PDF origen del albarán confirmado a Google
Drive y la borra del servidor -- sustituye la persistencia por correo
que existía hasta S014, ver spare_parts/gdrive_service.py para el
razonamiento completo del diseño de la integración con Drive).
"""
import logging
from datetime import date

from celery.contrib.django.task import DjangoTask
from enterprise_core.celery import app

from .gdrive_service import GDriveNotConfigured, upload_delivery_note_file
from .models import DeliveryNote, DeliveryNoteLine
from .services import (
    GeminiVisionExtractionService,
    parse_decimal,
    resolve_document_assignment,
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

    # S015-H10, primer punto de la hoja de ruta: asignación SIEMPRE
    # completa por albarán -- se resuelve el código único del
    # documento (general_machine_code_raw, leído exclusivamente de
    # Observaciones/Notas por el prompt) UNA sola vez, y se aplica el
    # mismo assignment_type/machine a TODAS las líneas. Ya no hay
    # resolución por línea ni respaldo -- ver
    # services.validate_document_assignment(), invocada en la
    # pantalla de revisión (DeliveryNoteDetailView) y en la
    # confirmación (DeliveryNoteConfirmView) para decidir si el
    # albarán se puede confirmar o debe rechazarse.
    # ---
    # S015-H10, first roadmap point: assignment is ALWAYS whole-
    # document -- the document's single code (general_machine_code_raw,
    # read exclusively from Observaciones/Notas by the prompt) is
    # resolved ONCE, and the same assignment_type/machine is applied
    # to EVERY line. No more per-line resolution or fallback -- see
    # services.validate_document_assignment(), used on the review
    # screen (DeliveryNoteDetailView) and on confirmation
    # (DeliveryNoteConfirmView) to decide whether the note can be
    # confirmed or must be rejected.
    # S020 (2026-07-15): además del código (Observaciones o
    # delimitado en línea), si no hay código pero el texto del
    # albarán contiene "repuesto"/"stock"/"almacén",
    # general_warehouse_keyword_found llega en true desde la propia
    # extracción -- resolve_document_assignment aplica el fallback a
    # WAREHOUSE sin diferenciar (ver docstring, confirmado por Miguel
    # Ángel).
    assignment_type, machine = resolve_document_assignment(
        delivery_note.general_machine_code_raw or None,
        extraction.general_warehouse_keyword_found,
        company,
    )

    for line_data in extraction.lines:
        DeliveryNoteLine.objects.create(
            delivery_note=delivery_note,
            line_number=line_data.line_number,
            reference=line_data.reference or '',
            description=line_data.description,
            quantity=parse_decimal(line_data.quantity) or 0,
            unit_price=parse_decimal(line_data.unit_price),
            total_price=parse_decimal(line_data.total_price),
            assignment_type=assignment_type,
            machine=machine,
        )

    logger.info(
        '# [Tarea] Albarán #%d extraído correctamente en segundo '
        'plano: %d línea(s).',
        delivery_note_id, len(extraction.lines),
    )


@app.task(base=DjangoTask, bind=True, max_retries=3, default_retry_delay=60)
def upload_delivery_note_photo_to_drive(self, delivery_note_id: int) -> None:
    """
    Uploads the confirmed delivery note's source file (photo or PDF)
    to Google Drive (spare_parts.gdrive_service, S014-H10) and deletes
    the file from disk only after a successful upload + share.
    Replaces send_delivery_note_photo_email(), removed in S014.

    Never deletes the file if the upload fails -- Celery retries up to
    max_retries times before giving up, and the file stays on the
    server (safe default) if all retries are exhausted, logged as an
    error for manual follow-up. GDriveNotConfigured (missing env vars,
    i.e. the one-time authorization at /panel/gdrive/authorize/ hasn't
    been done yet) is NOT retried -- retrying won't fix a missing
    credential, it would just spam the log every 60s until someone
    notices; logged once as an actionable error instead.

    ---

    Sube la foto/PDF origen del albarán confirmado a Google Drive
    (spare_parts.gdrive_service, S014-H10) y borra el archivo del
    disco solo tras una subida + compartición con éxito. Sustituye a
    send_delivery_note_photo_email(), eliminada en S014.

    Nunca borra el archivo si la subida falla -- Celery reintenta hasta
    max_retries veces antes de desistir, y si se agotan los reintentos
    el archivo se queda en el servidor (comportamiento seguro por
    defecto), registrado como error para seguimiento manual.
    GDriveNotConfigured (faltan variables de entorno, es decir, la
    autorización de un solo uso en /panel/gdrive/authorize/ todavía no
    se ha hecho) NO se reintenta -- reintentar no arregla una
    credencial que falta, solo llenaría el log cada 60s hasta que
    alguien lo note; se registra una sola vez como error accionable.
    """
    try:
        delivery_note = DeliveryNote.objects.get(pk=delivery_note_id)
    except DeliveryNote.DoesNotExist:
        logger.error(
            '# [Tarea] upload_delivery_note_photo_to_drive: DeliveryNote '
            '#%d no existe.',
            delivery_note_id,
        )
        return

    if not delivery_note.image and not delivery_note.pdf_file:
        logger.info(
            '# [Tarea] Albarán #%d sin archivo asociado -- nada que '
            'subir (probablemente ya procesado en una ejecución '
            'anterior).',
            delivery_note_id,
        )
        return

    try:
        result = upload_delivery_note_file(delivery_note)
    except GDriveNotConfigured as exc:
        logger.error(
            '# [Tarea] Google Drive no configurado todavía -- albarán '
            '#%d NO subido, archivo NO borrado. %s',
            delivery_note_id, exc,
        )
        return
    except Exception as exc:
        logger.exception(
            '# [Tarea] Fallo subiendo a Drive el albarán #%d (intento '
            '%d/%d). El archivo NO se borra.',
            delivery_note_id, self.request.retries + 1, self.max_retries,
        )
        raise self.retry(exc=exc)

    # Success: persist the Drive reference, then delete the local file
    # and clear the model reference -- same order/safety principle the
    # email flow had (never delete before confirming the destination
    # succeeded).
    # Éxito: persistir la referencia de Drive, después borrar el
    # archivo local y limpiar la referencia del modelo -- mismo
    # orden/principio de seguridad que tenía el flujo de correo (nunca
    # borrar antes de confirmar que el destino tuvo éxito).
    delivery_note.drive_file_id = result['file_id']
    delivery_note.drive_web_link = result['web_link']
    if delivery_note.image:
        delivery_note.image.delete(save=False)
    if delivery_note.pdf_file:
        delivery_note.pdf_file.delete(save=False)
    delivery_note.save(update_fields=[
        'drive_file_id', 'drive_web_link', 'image', 'pdf_file',
    ])

    logger.info(
        '# [Tarea] Albarán #%d subido a Google Drive (file_id=%s) y '
        'archivo origen eliminado del servidor.',
        delivery_note_id, result['file_id'],
    )
