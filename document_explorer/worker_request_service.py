# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/worker_request_service.py
"""
H30 (S125), roadmap item 3. Documents asked to the worker over
WhatsApp and checked against what was asked when they arrive.

---

H30 (S125), punto 3 de la hoja de ruta. Documentos pedidos al propio
trabajador por WhatsApp, y comprobación de lo que entrega contra lo
pedido. Diseño de Miguel Ángel (S125), tal cual:

- El supervisor da luz verde desde Avisos > Pendientes; solo tipos
  marcados "lo aporta el trabajador" y solo con móvil válido.
- Cola por trabajador: una sola solicitud activa (SENT) a la vez;
  cuando su documento se acepta, se pide la siguiente, hasta vaciarla.
- Lo que entrega el trabajador NO va a la cuarentena: Gemini lo lee y
  se comprueba que es uno de los documentos pedidos, que es realmente
  eso, que es suyo y que no es obsoleto frente a lo que se pide
  (caducado, o no más reciente que el vigente que ya tenemos).
  Conforme -> se clasifica directamente en su ficha
  (`upload_subject_document`: tipo, vínculo, nombre canónico, fechas y
  sustitución del vigente). No conforme -> se guarda en NO CONFORMES/
  y se avisa al trabajador: "El archivo entregado no es el
  solicitado. Hemos solicitado X y usted ha entregado Y."
- Un adjunto de un trabajador SIN solicitud pendiente sigue el camino
  de la hoja de ruta de S124: a la cuarentena. Ningún adjunto se
  pierde.
"""
import json
import logging
import os
import re
import unicodedata
from datetime import date

import requests
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.utils import timezone
from google.genai.types import GenerateContentConfig, HttpOptions, Part

from ai_services.gemini_client import DEFAULT_MODEL, get_gemini_client
from ai_services.gemini_rate_limiter import acquire_gemini_slot
from document_explorer import index_writer, naming_service
from document_explorer.buckets import NO_CONFORMES_PREFIX, QUARANTINE_PREFIX
from document_explorer.models import (
    DocumentIndexEntry, DocumentTypeCatalog, PersonIdentity,
    WorkerDocumentRequest, WorkerDocumentSubmission,
)
from document_explorer.person_phone_service import mobile_of
from document_explorer.subject_upload_service import (
    BUCKET, SubjectUploadError, upload_subject_document,
)
from spare_parts.gcs_service import get_storage_client, upload_bytes

logger = logging.getLogger(__name__)

TEMPLATE_MISSING = "document_request_missing"
TEMPLATE_EXPIRY = "document_request_expiry"
CLOSING = "Responda a este mensaje con una foto o un PDF del documento."
WHATSAPP_QUARANTINE_FOLDER = QUARANTINE_PREFIX + "WHATSAPP"
MEDIA_EXTENSIONS = {
    "application/pdf": "pdf",
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/heic": "heic",
}
GEMINI_MIME_TYPES = {
    "application/pdf", "image/jpeg", "image/png", "image/webp",
    "image/heic",
}
OTHER_CODE = "OTRO"

_VALIDATION_SCHEMA = {
    "type": "object",
    "properties": {
        "detected_type_code": {"type": "string"},
        "detected_description": {"type": "string"},
        "holder_full_name": {"type": "string"},
        "holder_id_number": {"type": "string"},
        "issue_date": {"type": "string"},
        "expiry_date": {"type": "string"},
    },
    "required": [
        "detected_type_code", "detected_description", "holder_full_name",
        "holder_id_number", "issue_date", "expiry_date",
    ],
}


class RequestError(Exception):
    """
    A request that cannot be created or sent (shown to the supervisor).

    ---

    Solicitud que no se puede crear o enviar (se muestra al supervisor).
    """


# ---------------------------------------------------------------------
# Solicitudes y cola por trabajador
# ---------------------------------------------------------------------

def open_requests(person):
    """
    Open requests of a person, oldest first (the queue).

    ---

    Solicitudes abiertas de la persona, la más antigua primero (la
    cola). La activa (SENT) va siempre la primera.
    """
    queue = list(WorkerDocumentRequest.objects.filter(
        person=person, status__in=WorkerDocumentRequest.OPEN_STATUSES,
    ).select_related("document_type").order_by("created_at", "pk"))
    queue.sort(key=lambda req: req.status != WorkerDocumentRequest.STATUS_SENT)
    return queue


def _current_entry(person, document_type):
    """
    Current (non-obsolete) document of that type for the person.

    ---

    Documento vigente (no obsoleto, no borrado) de ese tipo de la
    persona; el de caducidad más lejana si hubiera varios.
    """
    return DocumentIndexEntry.objects.filter(
        bucket=BUCKET,
        entry_kind=DocumentIndexEntry.KIND_FILE,
        domain_content_type=ContentType.objects.get_for_model(
            PersonIdentity,
        ),
        domain_object_id=person.pk,
        document_type=document_type,
        is_obsolete=False,
        deleted_at__isnull=True,
        purged_at__isnull=True,
    ).order_by("-expiry_date", "-pk").first()


def create_requests(pairs, approved_by):
    """
    Queue one request per (person_id, document_type_id) pair.

    Skips types not marked `worker_provides`, people without a valid
    mobile and pairs that already have an open request. Then sends
    the head of each touched queue. Returns a summary dict for the
    supervisor.

    ---

    Encola una solicitud por cada pareja (persona, tipo). Descarta los
    tipos sin la marca "lo aporta el trabajador", las personas sin
    móvil válido y las parejas que ya tienen una solicitud abierta.
    Después envía la primera de cada cola tocada. Devuelve un resumen
    para el supervisor.
    """
    summary = {"queued": 0, "skipped": [], "sent": 0, "send_errors": []}
    touched = {}
    for person_id, type_id in pairs:
        person = PersonIdentity.objects.filter(pk=person_id).first()
        doc_type = DocumentTypeCatalog.objects.filter(pk=type_id).first()
        if person is None or doc_type is None:
            continue
        label = "%s -- %s" % (_person_label(person), doc_type.label)
        if not doc_type.worker_provides:
            summary["skipped"].append(
                "%s: el tipo no está marcado «lo aporta el trabajador»"
                % label
            )
            continue
        if not mobile_of(person):
            summary["skipped"].append("%s: sin móvil válido" % label)
            continue
        if WorkerDocumentRequest.objects.filter(
            person=person, document_type=doc_type,
            status__in=WorkerDocumentRequest.OPEN_STATUSES,
        ).exists():
            summary["skipped"].append("%s: ya está pedido" % label)
            continue
        current = _current_entry(person, doc_type)
        WorkerDocumentRequest.objects.create(
            person=person,
            document_type=doc_type,
            reason=(
                WorkerDocumentRequest.REASON_EXPIRY if current
                else WorkerDocumentRequest.REASON_MISSING
            ),
            approved_by=approved_by,
        )
        summary["queued"] += 1
        touched[person.pk] = person

    for person in touched.values():
        sent, error = advance_queue(person, free_text=False)
        if sent:
            summary["sent"] += 1
        if error:
            summary["send_errors"].append(
                "%s: %s" % (_person_label(person), error)
            )
    return summary


def advance_queue(person, free_text):
    """
    Send the next queued request if the person has none active.

    `free_text=True` when the worker has just written (24h window
    open): plain message. Otherwise the approved template.
    Returns (sent: bool, error: str).

    ---

    Envía la siguiente solicitud de la cola si la persona no tiene
    ninguna activa. `free_text=True` cuando el trabajador acaba de
    escribir (ventana de 24 h abierta): mensaje normal. Si no, la
    plantilla aprobada. Devuelve (enviada, error).
    """
    queue = open_requests(person)
    if not queue or queue[0].status == WorkerDocumentRequest.STATUS_SENT:
        return False, ""
    request_obj = queue[0]
    try:
        sid = _send_request_message(request_obj, free_text)
    except RequestError as exc:
        request_obj.send_error = str(exc)
        request_obj.save(update_fields=["send_error"])
        logger.error(
            "# [DOC REQUEST] No enviada la solicitud %s: %s",
            request_obj.pk, exc,
        )
        return False, str(exc)
    request_obj.status = WorkerDocumentRequest.STATUS_SENT
    request_obj.sent_at = timezone.now()
    request_obj.message_sid = sid
    request_obj.send_error = ""
    request_obj.save(update_fields=[
        "status", "sent_at", "message_sid", "send_error",
    ])
    logger.info(
        "# [DOC REQUEST] Solicitud %s enviada (%s) -- SID %s",
        request_obj.pk, request_obj.document_type.code, sid,
    )
    return True, ""


def _request_text(request_obj):
    """
    Free-text version of the request message (same wording as the
    templates).

    ---

    Versión en texto libre del mensaje de solicitud (mismas frases que
    las plantillas).
    """
    label = request_obj.document_type.label
    if request_obj.reason == WorkerDocumentRequest.REASON_EXPIRY:
        current = _current_entry(request_obj.person, request_obj.document_type)
        if current and current.expiry_date:
            return "Su documento %s tiene fecha de caducidad %s y debe " \
                "renovarse. %s" % (
                    label, current.expiry_date.strftime("%d/%m/%Y"), CLOSING,
                )
    return "Falta en su ficha el documento %s. %s" % (label, CLOSING)


def _send_request_message(request_obj, free_text):
    """
    Send one request over WhatsApp; returns the Twilio SID.

    ---

    Envía una solicitud por WhatsApp; devuelve el SID de Twilio.
    """
    from whatsapp.models import WhatsAppTemplate
    from whatsapp.tasks import _build_twilio_client, _get_whatsapp_sender

    person = request_obj.person
    phone = mobile_of(person)
    sender = _get_whatsapp_sender()
    if not phone:
        raise RequestError("sin móvil válido en la ficha")
    if not sender:
        raise RequestError("TWILIO_WHATSAPP_SENDER no configurado")
    client = _build_twilio_client()
    if free_text:
        message = client.messages.create(
            from_="whatsapp:%s" % sender,
            to="whatsapp:%s" % phone,
            body=_request_text(request_obj),
        )
        return message.sid

    current = _current_entry(person, request_obj.document_type)
    is_expiry = (
        request_obj.reason == WorkerDocumentRequest.REASON_EXPIRY
        and current is not None and current.expiry_date is not None
    )
    template = WhatsAppTemplate.objects.filter(
        company=person.company,
        name=TEMPLATE_EXPIRY if is_expiry else TEMPLATE_MISSING,
        is_active=True,
    ).first()
    if template is None:
        raise RequestError("plantilla WhatsApp no registrada")
    variables = {
        "1": person.given_name or _person_label(person),
        "2": request_obj.document_type.label,
    }
    if is_expiry:
        variables["3"] = current.expiry_date.strftime("%d/%m/%Y")
    try:
        message = client.messages.create(
            from_="whatsapp:%s" % sender,
            to="whatsapp:%s" % phone,
            content_sid=template.content_sid,
            content_variables=json.dumps(variables),
        )
    except Exception as exc:  # Twilio: el motivo real va al panel.
        raise RequestError("Twilio: %s" % exc) from exc
    return message.sid


def cancel_request(request_obj):
    """
    Cancel an open request and send the next one of the queue.

    ---

    Cancela una solicitud abierta y pide la siguiente de la cola.
    """
    was_active = request_obj.status == WorkerDocumentRequest.STATUS_SENT
    request_obj.status = WorkerDocumentRequest.STATUS_CANCELLED
    request_obj.save(update_fields=["status"])
    if was_active:
        advance_queue(request_obj.person, free_text=False)


# ---------------------------------------------------------------------
# Adjuntos entrantes
# ---------------------------------------------------------------------

def register_incoming_media(person, from_phone, post):
    """
    Record an incoming attachment and queue its processing.

    Called from the WhatsApp webhook before any other conversation
    logic, so no attachment is lost whatever the conversation state.

    ---

    Registra un adjunto entrante y encola su proceso. Se llama desde el
    webhook de WhatsApp antes de cualquier otra lógica de conversación,
    así ningún adjunto se pierde sea cual sea el estado de la
    conversación (respuesta tardía, mensajes intermedios, ticket de
    avería abierto). WhatsApp manda un solo adjunto por mensaje
    (MediaUrl0).
    """
    from document_explorer.tasks import process_worker_submission_task

    media_url = post.get("MediaUrl0", "")
    submission = WorkerDocumentSubmission.objects.create(
        person=person,
        from_phone=from_phone,
        media_url=media_url,
        media_sid=media_url.rstrip("/").rsplit("/", 1)[-1],
        media_content_type=post.get("MediaContentType0", ""),
    )
    transaction.on_commit(
        lambda: process_worker_submission_task.delay(submission.pk),
    )
    return submission


def _download_media(url):
    """
    Download a Twilio media file (HTTP Basic with the API key).

    ---

    Descarga un adjunto de Twilio (HTTP Basic con la API key, como
    exige Twilio; la URL redirige a una dirección firmada).
    """
    response = requests.get(
        url,
        auth=(
            os.environ["TWILIO_API_KEY_SID"],
            os.environ["TWILIO_API_KEY_SECRET"],
        ),
        timeout=60,
    )
    response.raise_for_status()
    return response.content


def process_submission(submission_id):
    """
    Check one attachment against the person's open requests and act.

    ---

    Comprueba un adjunto contra las solicitudes abiertas de la persona
    y actúa: conforme a la ficha, no conforme a NO CONFORMES/ con aviso
    al trabajador, sin solicitud a la cuarentena.
    """
    submission = WorkerDocumentSubmission.objects.select_related(
        "person",
    ).get(pk=submission_id)
    if submission.status != WorkerDocumentSubmission.STATUS_PROCESSING:
        return submission.status
    person = submission.person
    content_type = (submission.media_content_type or "").split(";")[0]
    extension = MEDIA_EXTENSIONS.get(content_type.lower(), "bin")
    try:
        data = _download_media(submission.media_url)
    except Exception as exc:
        return _finish(
            submission, WorkerDocumentSubmission.STATUS_ERROR,
            "No se pudo descargar de Twilio: %s" % exc,
        )

    queue = open_requests(person) if person is not None else []
    if not queue:
        entry = _store_loose_object(
            WHATSAPP_QUARANTINE_FOLDER, person, submission, data,
            content_type, extension,
        )
        _reply(submission.from_phone, (
            "Hemos recibido su archivo. Gracias."
        ))
        return _finish(
            submission, WorkerDocumentSubmission.STATUS_QUARANTINED,
            "Sin solicitud pendiente: a la cuarentena.", entry=entry,
        )

    active = queue[0]
    if content_type.lower() not in GEMINI_MIME_TYPES:
        return _reject(
            submission, person, active, data, content_type, extension,
            "un archivo que no es una foto ni un PDF", {},
        )
    try:
        verdict = _read_with_gemini(data, content_type, person, queue)
    except Exception as exc:
        logger.exception("# [DOC REQUEST] Gemini falló (%s)", submission.pk)
        return _finish(
            submission, WorkerDocumentSubmission.STATUS_ERROR,
            "Gemini no pudo leer el archivo: %s" % exc,
        )

    matched, delivered = _decide(verdict, person, queue)
    if matched is None:
        return _reject(
            submission, person, active, data, content_type, extension,
            delivered, verdict,
        )
    return _accept(
        submission, person, matched, data, content_type, extension, verdict,
    )


def _read_with_gemini(data, content_type, person, queue):
    """
    Ask Gemini what the document is and read holder and dates.

    ---

    Pregunta a Gemini qué documento es y lee titular y fechas. Solo
    puede elegir entre los tipos pedidos o OTRO: nunca clasifica
    contra el catálogo entero.
    """
    types_text = "\n".join(
        "- %s: %s" % (req.document_type.code, req.document_type.label)
        for req in queue
    )
    prompt = (
        "Eres un asistente que revisa documentación laboral española. "
        "A un trabajador se le ha pedido UNO de estos documentos:\n"
        "%s\n\n"
        "Mira el archivo adjunto y responde:\n"
        "- detected_type_code: el código de la lista que corresponde a "
        "lo que es REALMENTE el archivo; si no es ninguno de ellos, "
        "'%s'.\n"
        "- detected_description: qué es el documento, en pocas "
        "palabras y en castellano (p. ej. 'Tarjeta sanitaria', 'DNI', "
        "'Recibo de la luz', 'Foto sin documento').\n"
        "- holder_full_name: nombre y apellidos del titular tal como "
        "aparecen, o cadena vacía.\n"
        "- holder_id_number: DNI/NIE del titular tal como aparece, o "
        "cadena vacía.\n"
        "- issue_date y expiry_date: fecha de expedición y fecha de "
        "caducidad o validez, en formato AAAA-MM-DD, o cadena vacía si "
        "no se leen. No inventes ninguna fecha."
    ) % (types_text, OTHER_CODE)
    client = get_gemini_client()
    acquire_gemini_slot()
    response = client.models.generate_content(
        model=DEFAULT_MODEL,
        contents=[Part.from_bytes(data=data, mime_type=content_type), prompt],
        config=GenerateContentConfig(
            http_options=HttpOptions(timeout=90_000),
            response_mime_type="application/json",
            response_schema=_VALIDATION_SCHEMA,
            temperature=0.0,
        ),
    )
    return json.loads(response.text.strip())


def _parse_iso(value):
    """
    Parse an AAAA-MM-DD string, or None.

    ---

    Convierte AAAA-MM-DD en fecha, o None.
    """
    try:
        year, month, day = (int(part) for part in (value or "").split("-"))
        return date(year, month, day)
    except (ValueError, TypeError):
        return None


def _normalize_text(value):
    """
    Uppercase ASCII letters and digits only.

    ---

    Solo letras ASCII en mayúscula y dígitos (sin acentos ni signos).
    """
    value = unicodedata.normalize("NFD", value or "")
    value = "".join(ch for ch in value if unicodedata.category(ch) != "Mn")
    return re.sub(r"[^A-Z0-9 ]", "", value.upper())


def _holder_matches(verdict, person):
    """
    Whether the document belongs to the person.

    DNI/NIE decides when both are known; otherwise the first surname
    and the given name must appear in the holder name.

    ---

    Si el documento es de la persona. Manda el DNI/NIE cuando se
    conocen los dos; si no, el primer apellido y el nombre tienen que
    aparecer en el titular leído.
    """
    read_id = _normalize_text(verdict.get("holder_id_number")).replace(" ", "")
    own_id = _normalize_text(person.dni).replace(" ", "")
    if read_id and own_id:
        return read_id == own_id
    holder = " %s " % _normalize_text(verdict.get("holder_full_name"))
    surname = _normalize_text(person.first_surname).strip()
    given = _normalize_text(person.given_name).split()
    return bool(surname) and (" %s " % surname) in holder and any(
        (" %s " % word) in holder for word in given
    )


def _decide(verdict, person, queue):
    """
    Return (matched request, "") or (None, what was delivered).

    ---

    Devuelve (solicitud casada, "") o (None, descripción de lo
    entregado) para el aviso de no conforme. Reglas, por orden:
    es uno de los tipos pedidos, es de esa persona, trae caducidad si
    el tipo la tiene, no está caducado y es más reciente que el
    vigente que ya tenemos.
    """
    code = (verdict.get("detected_type_code") or "").strip().upper()
    described = (verdict.get("detected_description") or "").strip()
    matched = next(
        (req for req in queue if req.document_type.code == code), None,
    )
    if matched is None:
        return None, described or "un documento que no se reconoce"
    label = matched.document_type.label
    if not _holder_matches(verdict, person):
        return None, "%s de otra persona" % label
    expiry = _parse_iso(verdict.get("expiry_date"))
    if matched.document_type.tracks_expiry:
        if expiry is None:
            return None, (
                "%s en el que no se lee la fecha de caducidad" % label
            )
        if expiry < timezone.localdate():
            return None, "%s caducado el %s" % (
                label, expiry.strftime("%d/%m/%Y"),
            )
        current = _current_entry(person, matched.document_type)
        if current and current.expiry_date and expiry <= current.expiry_date:
            return None, (
                "%s que no es más reciente que el que ya tenemos "
                "(caduca el %s)" % (
                    label, current.expiry_date.strftime("%d/%m/%Y"),
                )
            )
    return matched, ""


def _accept(submission, person, request_obj, data, content_type,
            extension, verdict):
    """
    File the document in the person's record and move the queue on.

    ---

    Archiva el documento en la ficha de la persona (clasificación
    directa, nunca cuarentena), marca la solicitud como recibida,
    confirma al trabajador y pide el siguiente de la cola.
    """
    doc_type = request_obj.document_type
    try:
        result = upload_subject_document(
            subject=person,
            domain_content_type=ContentType.objects.get_for_model(
                PersonIdentity,
            ),
            document_type=doc_type,
            data=data,
            original_filename="whatsapp_%s.%s" % (
                submission.media_sid, extension,
            ),
            typed_date=_parse_iso(verdict.get("expiry_date")),
            typed_issue_date=_parse_iso(verdict.get("issue_date")),
            subject_label=_person_label(person),
            uploaded_by=request_obj.approved_by,
        )
    except SubjectUploadError as exc:
        return _finish(
            submission, WorkerDocumentSubmission.STATUS_ERROR,
            "No se pudo archivar en la ficha: %s" % exc, verdict=verdict,
        )
    entry = result["entry"]
    request_obj.status = WorkerDocumentRequest.STATUS_RECEIVED
    request_obj.received_at = timezone.now()
    request_obj.received_entry = entry
    request_obj.save(update_fields=[
        "status", "received_at", "received_entry",
    ])
    submission.request = request_obj
    _reply(submission.from_phone, (
        "Documento recibido y aceptado: %s. Gracias." % doc_type.label
    ))
    advance_queue(person, free_text=True)
    return _finish(
        submission, WorkerDocumentSubmission.STATUS_ACCEPTED,
        "Aceptado como %s." % doc_type.code, verdict=verdict, entry=entry,
    )


def _reject(submission, person, active, data, content_type, extension,
            delivered, verdict):
    """
    Keep the file in NO CONFORMES and tell the worker.

    ---

    Guarda el archivo en NO CONFORMES/ (ningún adjunto se pierde) y
    avisa al trabajador con la frase de Miguel Ángel; la solicitud
    sigue abierta para que lo reenvíe.
    """
    entry = _store_loose_object(
        NO_CONFORMES_PREFIX.rstrip("/"), person, submission, data,
        content_type, extension,
    )
    _reply(submission.from_phone, (
        "El archivo entregado no es el solicitado. Hemos solicitado %s y "
        "usted ha entregado %s. %s" % (
            active.document_type.label, delivered, CLOSING,
        )
    ))
    submission.request = active
    return _finish(
        submission, WorkerDocumentSubmission.STATUS_REJECTED,
        "No conforme: %s." % delivered, verdict=verdict, entry=entry,
    )


def _store_loose_object(folder, person, submission, data, content_type,
                        extension):
    """
    Upload the file to a folder (quarantine or NO CONFORMES) and index
    it, never overwriting an existing blob.

    ---

    Sube el archivo a una carpeta (cuarentena o NO CONFORMES) y lo
    indexa, igual que el agente H28 (`RegisterUploadedObjectView`);
    el nombre lleva el SID del adjunto, único en Twilio, así que nunca
    pisa un objeto existente.
    """
    who = (
        naming_service._sanitize_token(_person_label(person))
        if person is not None else "DESCONOCIDO"
    )
    blob_name = "%s/WHATSAPP_%s_%s_%s.%s" % (
        folder, who, timezone.localdate().strftime("%Y%m%d"),
        submission.media_sid or submission.pk, extension,
    )
    upload_bytes(
        BUCKET, blob_name, data,
        content_type=content_type or "application/octet-stream",
    )
    blob = get_storage_client().bucket(BUCKET).get_blob(blob_name)
    parent_path, _ = index_writer.split_path(blob_name)
    with transaction.atomic():
        index_writer.ensure_folder_chain(BUCKET, parent_path)
        index_writer.persist_rows(BUCKET, [index_writer.file_row(blob)])
        index_writer.recount_children(
            BUCKET, folder_paths=index_writer.ancestors_of(parent_path),
        )
    return DocumentIndexEntry.objects.filter(
        bucket=BUCKET, blob_name=blob_name,
    ).first()


def _reply(phone, text):
    """
    Plain WhatsApp message to the worker (24h window is open: they
    have just written). Never raises.

    ---

    Mensaje normal de WhatsApp al trabajador (la ventana de 24 h está
    abierta: acaba de escribir). Nunca lanza excepción.
    """
    from whatsapp.tasks import _build_twilio_client, _get_whatsapp_sender

    try:
        _build_twilio_client().messages.create(
            from_="whatsapp:%s" % _get_whatsapp_sender(),
            to="whatsapp:%s" % phone,
            body=text,
        )
    except Exception:
        logger.exception("# [DOC REQUEST] No se pudo responder a %s", phone)


def _finish(submission, status, reason, verdict=None, entry=None):
    """
    Close a submission with its final status.

    ---

    Cierra un adjunto con su estado final.
    """
    submission.status = status
    submission.reason = reason
    if verdict is not None:
        submission.verdict = verdict
    if entry is not None:
        submission.entry = entry
    submission.processed_at = timezone.now()
    submission.save(update_fields=[
        "status", "reason", "verdict", "entry", "request", "processed_at",
    ])
    logger.info(
        "# [DOC REQUEST] Adjunto %s: %s -- %s",
        submission.pk, status, reason,
    )
    return status


def _person_label(person):
    """
    "SURNAMES, Name" label of a person.

    ---

    Etiqueta "APELLIDOS, Nombre" de la persona.
    """
    surnames = " ".join(
        part for part in (person.first_surname, person.second_surname)
        if part
    )
    return "%s, %s" % (surnames, person.given_name)
