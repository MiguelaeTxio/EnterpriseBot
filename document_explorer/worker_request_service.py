# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/worker_request_service.py
"""
H30 (S125), roadmap item 3. Documents asked to the worker over
WhatsApp and checked against what was asked when they arrive.

---

H30 (S125), punto 3 de la hoja de ruta. Documentos pedidos al propio
trabajador por WhatsApp, y comprobación de lo que entrega contra lo
pedido. Diseño de Miguel Ángel (S125), tal cual:

- El supervisor da luz verde desde Avisos > Pendientes; solo tipos
  marcados "lo aporta el trabajador", solo con móvil válido y solo a
  trabajadores dados de alta con acceso al panel (S125).
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
- Segunda entrega (la otra cara, más páginas) de un documento aceptado
  por WhatsApp en las últimas 24 h: se añade a él (un solo PDF),
  siempre que sea lo esperado (mismo tipo, misma persona).
- Adjunto SIN solicitud pendiente: actualización o primera subida por
  iniciativa del trabajador -- se clasifica contra el catálogo de
  Personal, se valida igual y se archiva con su nombre canónico. Ningún
  adjunto de trabajador va a la cuarentena; ninguno se pierde (lo que
  no encaja va a NO CONFORMES/ con aviso al trabajador).
"""
import hashlib
import json
import logging
import os
import re
import unicodedata
from datetime import date, timedelta

import fitz
import requests
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.utils import timezone
from google.genai.types import GenerateContentConfig, HttpOptions, Part

from ai_services.gemini_client import DEFAULT_MODEL, get_gemini_client
from document_explorer.classification_service import (
    _generate_content_with_retry,
)
from document_explorer import index_writer, naming_service
from document_explorer.buckets import NO_CONFORMES_PREFIX
from document_explorer.models import (
    DocumentIndexEntry, DocumentTypeCatalog, PersonIdentity,
    WorkerDocumentRequest, WorkerDocumentSubmission,
)
from document_management.models import DocumentSubstitutionLog
from document_explorer.person_phone_service import (
    has_panel_access, mobile_of,
)
from document_explorer.subject_upload_service import (
    BUCKET, SubjectUploadError, upload_subject_document,
)
from spare_parts.gcs_service import (
    download_bytes, get_storage_client, upload_bytes,
)

logger = logging.getLogger(__name__)

TEMPLATE_MISSING = "document_request_missing"
TEMPLATE_EXPIRY = "document_request_expiry"
CLOSING = "Responda a este mensaje con una foto o un PDF del documento."
SECOND_DELIVERY_HOURS = 24
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
        if not has_panel_access(person):
            summary["skipped"].append(
                "%s: sin acceso al panel (no está dado de alta)" % label
            )
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


def _candidate_types(queue, recent):
    """
    Types Gemini may choose from, requested ones first.

    ---

    Tipos entre los que Gemini puede elegir, primero los pedidos. Con
    solicitudes abiertas: lo pedido y lo recién aceptado (segunda
    entrega). Sin solicitudes: además, todo el catálogo activo de
    Personal (actualización o primera subida por iniciativa del
    trabajador), sin las plantillas de circulares.
    """
    types, seen = [], set()

    def add(doc_type):
        if doc_type.pk not in seen:
            types.append(doc_type)
            seen.add(doc_type.pk)

    for request_obj in queue:
        add(request_obj.document_type)
    for prior in recent:
        add(prior.entry.document_type)
    if not queue:
        for doc_type in DocumentTypeCatalog.objects.filter(
            is_active=True,
            is_notification_template=False,
            domain__in=(
                DocumentTypeCatalog.DOMAIN_PERSONAL,
                DocumentTypeCatalog.DOMAIN_BOTH,
            ),
        ).exclude(
            # Imagen/vídeo/audio genéricos no son un documento: con
            # ellos Gemini "clasificaba" cualquier foto (S125).
            family=DocumentTypeCatalog.FAMILY_MEDIA,
        ).order_by("label"):
            add(doc_type)
    return types


def _recent_accepted(person):
    """
    Documents accepted over WhatsApp for this person in the last 24 h
    (still current), newest first -- candidates for a second delivery.

    ---

    Documentos aceptados por WhatsApp de esta persona en las últimas
    24 h (ventana de sesión de WhatsApp) y aún vigentes, el más reciente
    primero: candidatos a recibir una segunda entrega (la otra cara).
    """
    since = timezone.now() - timedelta(hours=SECOND_DELIVERY_HOURS)
    recent, seen_types = [], set()
    for prior in WorkerDocumentSubmission.objects.filter(
        person=person,
        status=WorkerDocumentSubmission.STATUS_ACCEPTED,
        processed_at__gte=since,
        entry__isnull=False,
        entry__is_obsolete=False,
        entry__deleted_at__isnull=True,
        entry__purged_at__isnull=True,
        entry__document_type__isnull=False,
    ).select_related(
        "entry", "entry__document_type", "request",
    ).order_by("-processed_at", "-pk"):
        if prior.entry.document_type_id not in seen_types:
            recent.append(prior)
            seen_types.add(prior.entry.document_type_id)
    return recent


class TransientGeminiError(Exception):
    """
    Gemini saturated/unavailable after its own retries: try later.

    ---

    Gemini saturado o caído tras sus propios reintentos: se vuelve a
    intentar más tarde desde la tarea (S125, 429 real en la prueba de
    cuatro fotos a la vez).
    """


def _is_transient(exc):
    """
    Whether a Gemini failure is transient (quota, timeout, unavailable).

    ---

    Si el fallo de Gemini es pasajero (cuota, tiempo agotado, caído).
    """
    text = str(exc)
    return any(mark in text for mark in (
        "429", "RESOURCE_EXHAUSTED", "503", "UNAVAILABLE", "504",
        "DEADLINE_EXCEEDED",
    ))


def _looks_like_other_side(verdict, doc_type):
    """
    The side of a card without holder nor expiry (typically the back).

    ---

    La cara de un documento sin titular ni caducidad legibles (lo
    normal en un reverso), de un tipo que sí tiene caducidad.
    """
    return bool(
        doc_type.tracks_expiry
        and _parse_iso(verdict.get("expiry_date")) is None
        and not _holder_read(verdict)
    )


def _only_other_side(doc_type):
    """
    Rejection reason for a side that never got its front.

    ---

    Motivo para una cara que nunca recibió su anverso: no es "de otra
    persona", es que falta la cara con los datos.
    """
    return (
        "solo una cara de su %s, sin la cara donde figuran sus datos y "
        "la caducidad. Envíe también esa cara" % doc_type.label
    )


def _wait_for_other_side(context, verdict):
    """
    Park a side that arrived before its front; the task retries it.

    ---

    Aparca una cara que ha llegado antes que su anverso; la tarea la
    reintenta en unos segundos. No bloquea a las demás fotos de la
    persona (solo espera PROCESSING, no WAITING).
    """
    submission = context.submission
    submission.status = WorkerDocumentSubmission.STATUS_WAITING
    submission.verdict = verdict
    submission.reason = "Esperando la otra cara del documento."
    submission.save(update_fields=["status", "verdict", "reason"])
    return WorkerDocumentSubmission.STATUS_WAITING


def process_submission(submission_id, final=False):
    """
    Check one attachment and act.

    ---

    Comprueba un adjunto y actúa (decisiones de Miguel Ángel, S125):

    1. Es uno de los documentos pedidos -> se valida contra lo pedido;
       conforme a la ficha, no conforme a NO CONFORMES/ con aviso.
    0. Es el mismo archivo que uno ya aceptado (huella SHA-256), o
       -- en el paso 2 -- una cara que ya está en el documento aceptado
       (Gemini compara): repetido, no se añade nada y se le dice al
       trabajador (S125: el anverso enviado dos veces).
    2. Es otra parte de un documento aceptado por WhatsApp en las
       últimas 24 h (misma persona, mismo tipo) -> se añade a él.
    3. Hay solicitudes abiertas y no es nada de lo anterior -> no
       conforme ("Hemos solicitado X y usted ha entregado Y").
    4. Sin solicitudes -> actualización o primera subida por iniciativa
       del trabajador: se clasifica contra el catálogo, se valida y se
       archiva con su nombre canónico; si no encaja, NO CONFORMES/ y
       aviso. Ningún adjunto de trabajador va a la cuarentena.
    """
    submission = WorkerDocumentSubmission.objects.select_related(
        "person",
    ).get(pk=submission_id)
    if submission.status not in (
        WorkerDocumentSubmission.STATUS_PROCESSING,
        WorkerDocumentSubmission.STATUS_WAITING,
    ):
        return submission.status
    waited = submission.status == WorkerDocumentSubmission.STATUS_WAITING
    person = submission.person
    content_type = (submission.media_content_type or "").split(";")[0]
    content_type = content_type.lower()
    extension = MEDIA_EXTENSIONS.get(content_type, "bin")
    try:
        data = _download_media(submission.media_url)
    except Exception as exc:
        # El adjunto sigue en Twilio y su URL queda en el registro.
        _reply(submission.from_phone, (
            "No hemos podido recibir su archivo. Por favor, vuelva a "
            "enviarlo."
        ))
        return _finish(
            submission, WorkerDocumentSubmission.STATUS_ERROR,
            "No se pudo descargar de Twilio: %s" % exc,
        )

    submission.content_sha256 = hashlib.sha256(data).hexdigest()
    submission.save(update_fields=["content_sha256"])
    context = _Delivery(submission, person, data, content_type, extension)
    # Solo es repetido si el documento que contiene esa foto sigue vivo
    # en la ficha (S125: Miguel Ángel borró su permiso y al reenviarlo
    # se le contestó "ya la teníamos").
    same_file = WorkerDocumentSubmission.objects.filter(
        person=person,
        content_sha256=submission.content_sha256,
        status=WorkerDocumentSubmission.STATUS_ACCEPTED,
        entry__document_type__isnull=False,
        entry__is_obsolete=False,
        entry__deleted_at__isnull=True,
        entry__purged_at__isnull=True,
    ).exclude(pk=submission.pk).select_related(
        "entry__document_type",
    ).order_by("-processed_at").first()
    if same_file is not None:
        return _duplicate(
            context, same_file.entry.document_type.label,
            "mismo archivo que el adjunto %s" % same_file.pk,
        )

    queue = open_requests(person)
    recent = _recent_accepted(person)
    if content_type not in GEMINI_MIME_TYPES:
        return _refuse(
            context, queue, "un archivo que no es una foto ni un PDF", {},
        )
    candidates = _candidate_types(queue, recent)
    if waited and submission.verdict:
        # Ya leída: solo se esperaba a su anverso.
        verdict = submission.verdict
    else:
        try:
            verdict = _read_with_gemini(data, content_type, candidates)
        except Exception as exc:
            if _is_transient(exc) and not final:
                raise TransientGeminiError(str(exc)) from exc
            logger.exception(
                "# [DOC REQUEST] Gemini falló (%s)", submission.pk,
            )
            return _fail(
                context, "Gemini no pudo leer el archivo: %s" % exc,
            )

    code = (verdict.get("detected_type_code") or "").strip().upper()
    described = (verdict.get("detected_description") or "").strip()
    requested = next(
        (req for req in queue if req.document_type.code == code), None,
    )
    if requested is not None:
        problem = _check_document(verdict, person, requested.document_type)
        if problem and _looks_like_other_side(
            verdict, requested.document_type,
        ):
            if not final:
                return _wait_for_other_side(context, verdict)
            problem = _only_other_side(requested.document_type)
        if problem:
            return _refuse(context, queue, problem, verdict)
        return _accept(context, requested.document_type, verdict, requested)

    prior = next(
        (p for p in recent if p.entry.document_type.code == code), None,
    )
    if prior is not None:
        if _holder_read(verdict) and not _holder_matches(verdict, person):
            return _refuse(context, queue, "%s de otra persona" % (
                prior.entry.document_type.label,
            ), verdict)
        return _append(context, prior, verdict)

    chosen = next((t for t in candidates if t.code == code), None)
    if queue or chosen is None:
        return _refuse(
            context, queue, described or "un documento que no se reconoce",
            verdict,
        )
    problem = _check_document(verdict, person, chosen)
    if problem and _looks_like_other_side(verdict, chosen):
        if not final:
            return _wait_for_other_side(context, verdict)
        problem = _only_other_side(chosen)
    if problem:
        return _refuse(context, queue, problem, verdict)
    return _accept(context, chosen, verdict, None)


class _Delivery:
    """
    One attachment being processed (keeps the call signatures short).

    ---

    Un adjunto en proceso (mantiene cortas las firmas de las funciones).
    """

    def __init__(self, submission, person, data, content_type, extension):
        self.submission = submission
        self.person = person
        self.data = data
        self.content_type = content_type
        self.extension = extension


def _read_with_gemini(data, content_type, candidates):
    """
    Ask Gemini which of the candidate types the document is, and read
    holder and dates.

    ---

    Pregunta a Gemini cuál de los tipos candidatos es el documento y
    lee titular y fechas. Solo puede elegir entre esos tipos u OTRO.
    """
    types_text = "\n".join(
        "- %s: %s" % (doc_type.code, doc_type.label)
        for doc_type in candidates
    )
    prompt = (
        "Eres un asistente que revisa documentación laboral española. "
        "Un trabajador ha enviado este archivo por WhatsApp. Estos son "
        "los únicos tipos de documento posibles:\n"
        "%s\n\n"
        "Responde:\n"
        "- detected_type_code: el código de la lista que corresponde a "
        "lo que es REALMENTE el archivo (también si es solo una cara o "
        "una parte del documento); si no es ninguno de ellos, '%s'.\n"
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
    response = _generate_content_with_retry(
        client,
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


def _holder_read(verdict):
    """
    Whether Gemini read any holder data at all.

    ---

    Si Gemini ha leído algún dato del titular.
    """
    return bool(
        _normalize_text(verdict.get("holder_id_number")).strip()
        or _normalize_text(verdict.get("holder_full_name")).strip()
    )


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


def _check_document(verdict, person, doc_type):
    """
    Return "" if the document is valid for the person, else what is
    wrong with it (worded for the worker).

    ---

    Devuelve "" si el documento vale para la persona o, si no, qué le
    pasa (redactado para el trabajador): es de esa persona, trae
    caducidad si el tipo la tiene, no está caducado y es más reciente
    que el vigente que ya tenemos.
    """
    label = doc_type.label
    if not _holder_matches(verdict, person):
        return "%s de otra persona" % label
    if not doc_type.tracks_expiry:
        return ""
    expiry = _parse_iso(verdict.get("expiry_date"))
    if expiry is None:
        return "%s en el que no se lee la fecha de caducidad" % label
    if expiry < timezone.localdate():
        return "%s caducado el %s" % (label, expiry.strftime("%d/%m/%Y"))
    current = _current_entry(person, doc_type)
    if current and current.expiry_date and expiry <= current.expiry_date:
        return (
            "%s que no es más reciente que el que ya tenemos "
            "(caduca el %s)" % (
                label, current.expiry_date.strftime("%d/%m/%Y"),
            )
        )
    return ""


def _file_in_record(context, doc_type, data, extension, expiry, issue,
                    uploaded_by):
    """
    File a document in the person's record (direct classification).

    ---

    Archiva un documento en la ficha de la persona (clasificación
    directa: tipo, vínculo, nombre canónico, fechas y sustitución del
    vigente), igual que una subida del supervisor.
    """
    return upload_subject_document(
        subject=context.person,
        domain_content_type=ContentType.objects.get_for_model(PersonIdentity),
        document_type=doc_type,
        data=data,
        original_filename="whatsapp_%s.%s" % (
            context.submission.media_sid, extension,
        ),
        typed_date=expiry,
        typed_issue_date=issue,
        subject_label=_person_label(context.person),
        uploaded_by=uploaded_by,
    )["entry"]


def _accept(context, doc_type, verdict, request_obj):
    """
    File the document; close the request (if any) and move the queue.

    ---

    Archiva el documento en la ficha. Si respondía a una solicitud, la
    marca recibida, lo confirma y pide el siguiente de la cola; si era
    iniciativa del trabajador, confirma que queda archivado.
    """
    submission = context.submission
    try:
        entry = _file_in_record(
            context, doc_type, context.data, context.extension,
            _parse_iso(verdict.get("expiry_date")),
            _parse_iso(verdict.get("issue_date")),
            request_obj.approved_by if request_obj else None,
        )
    except SubjectUploadError as exc:
        return _fail(
            context, "No se pudo archivar en la ficha: %s" % exc, verdict,
        )
    if request_obj is not None:
        request_obj.status = WorkerDocumentRequest.STATUS_RECEIVED
        request_obj.received_at = timezone.now()
        request_obj.received_entry = entry
        request_obj.save(update_fields=[
            "status", "received_at", "received_entry",
        ])
        submission.request = request_obj
        _reply(submission.from_phone, (
            "Documento recibido y aceptado: %s. Si el documento tiene "
            "otra cara, envíela ahora. Gracias." % doc_type.label
        ))
        advance_queue(context.person, free_text=True)
        reason = "Aceptado como %s (solicitud)." % doc_type.code
    else:
        _reply(submission.from_phone, (
            "Documento recibido y archivado: %s. Si el documento tiene "
            "otra cara, envíela ahora. Gracias." % doc_type.label
        ))
        reason = "Archivado como %s (sin solicitud)." % doc_type.code
    return _finish(
        submission, WorkerDocumentSubmission.STATUS_ACCEPTED, reason,
        verdict=verdict, entry=entry,
    )


def _merge_into_pdf(parts):
    """
    Join photos and/or PDFs into one PDF, in order.

    ---

    Une fotos y/o PDF en un solo PDF, en orden (PyMuPDF).
    """
    merged = fitz.open()
    for data, content_type in parts:
        # El formato se decide por los propios bytes: el content_type
        # guardado puede no reflejar lo que hay (p. ej. un PDF ya unido).
        real_type = _content_type_of_bytes(data, content_type)
        if real_type == "application/pdf":
            source = fitz.open(stream=data, filetype="pdf")
        else:
            image = fitz.open(
                stream=data,
                filetype=MEDIA_EXTENSIONS.get(real_type, "jpg"),
            )
            source = fitz.open("pdf", image.convert_to_pdf())
        merged.insert_pdf(source)
    return merged.tobytes()


def _append(context, prior, verdict):
    """
    Add a second delivery (other side, more pages) to a document
    accepted over WhatsApp in the last 24 h.

    ---

    Añade una segunda entrega (la otra cara, más páginas) a un
    documento aceptado por WhatsApp en las últimas 24 h: une ambos en
    un PDF, lo archiva como documento nuevo con las mismas fechas y
    deja el anterior obsoleto con su registro de sustitución (nunca se
    sobrescribe un blob, S102).
    """
    submission = context.submission
    old_entry = prior.entry
    doc_type = old_entry.document_type
    try:
        old_data = download_bytes(BUCKET, old_entry.blob_name)
        if _already_included(old_data, old_entry, context):
            return _duplicate(
                context, doc_type.label,
                "esa cara o página ya está en %s" % old_entry.name,
            )
        merged = _merge_into_pdf([
            (old_data, (old_entry.content_type or "").lower()),
            (context.data, context.content_type),
        ])
        new_entry = _file_in_record(
            context, doc_type, merged, "pdf",
            old_entry.expiry_date, old_entry.issue_date,
            prior.request.approved_by if prior.request else None,
        )
    except Exception as exc:
        logger.exception("# [DOC REQUEST] No se pudo unir (%s)", submission.pk)
        return _fail(
            context, "No se pudo añadir al documento aceptado: %s" % exc,
            verdict,
        )
    old_entry.refresh_from_db(fields=["is_obsolete"])
    if not old_entry.is_obsolete:
        old_entry.is_obsolete = True
        old_entry.save(update_fields=["is_obsolete"])
        entry_ct = ContentType.objects.get_for_model(DocumentIndexEntry)
        DocumentSubstitutionLog.objects.create(
            company=context.person.company,
            superseding_content_type=entry_ct,
            superseding_object_id=new_entry.pk,
            superseding_label=new_entry.name,
            superseded_content_type=entry_ct,
            superseded_object_id=old_entry.pk,
            superseded_label=old_entry.name,
            subject_label=_person_label(context.person),
            document_type=doc_type.code,
            reasoning=(
                "Segunda entrega por WhatsApp (S125): unida al documento "
                "aceptado en un solo PDF."
            ),
        )
    # Las entregas cuyo contenido está ahora en el PDF unido apuntan a
    # él: si ese PDF se borra, sus caras dejan de contar como repetidas.
    WorkerDocumentSubmission.objects.filter(
        entry=old_entry, status=WorkerDocumentSubmission.STATUS_ACCEPTED,
    ).update(entry=new_entry)
    if prior.request and prior.request.received_entry_id == old_entry.pk:
        prior.request.received_entry = new_entry
        prior.request.save(update_fields=["received_entry"])
    submission.request = prior.request
    _reply(submission.from_phone, (
        "Recibida también esta parte de su %s; la hemos unido al "
        "documento. Gracias." % doc_type.label
    ))
    return _finish(
        submission, WorkerDocumentSubmission.STATUS_ACCEPTED,
        "Añadido a %s (segunda entrega)." % old_entry.name,
        verdict=verdict, entry=new_entry,
    )


_SAME_PAGE_SCHEMA = {
    "type": "object",
    "properties": {"already_included": {"type": "boolean"}},
    "required": ["already_included"],
}


def _content_type_of_bytes(data, fallback="image/jpeg"):
    """
    Real MIME type from the bytes (PDF, PNG, JPEG, WebP).

    ---

    Tipo real sacado de los propios bytes (PDF, PNG, JPEG, WebP). El
    guardado en el índice puede ser application/octet-stream, que
    Gemini rechaza (400 en la prueba real de S125).
    """
    if data[:5] == b"%PDF-":
        return "application/pdf"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return fallback


def _already_included(old_data, old_entry, context):
    """
    Whether the new photo shows a side/page already in the document.

    ---

    Si la foto nueva muestra una cara o página que ya está en el
    documento aceptado (aunque sea otra foto de la misma cara). Gemini
    compara los dos archivos; el trabajador que repite el anverso no
    debe acabar con un PDF de dos anversos y sin reverso (S125).
    """
    prompt = (
        "El PRIMER archivo es un documento ya archivado (una o varias "
        "caras o páginas). El SEGUNDO es una foto nueva del mismo tipo "
        "de documento. ¿La foto nueva muestra una cara o página que YA "
        "está en el primer archivo (aunque la foto sea distinta: otro "
        "encuadre, otra luz)? Responde already_included=true si es una "
        "cara o página repetida, false si es una cara o página nueva."
    )
    client = get_gemini_client()
    response = _generate_content_with_retry(
        client,
        model=DEFAULT_MODEL,
        contents=[
            Part.from_bytes(
                data=old_data,
                mime_type=_content_type_of_bytes(old_data),
            ),
            Part.from_bytes(
                data=context.data, mime_type=context.content_type,
            ),
            prompt,
        ],
        config=GenerateContentConfig(
            http_options=HttpOptions(timeout=90_000),
            response_mime_type="application/json",
            response_schema=_SAME_PAGE_SCHEMA,
            temperature=0.0,
        ),
    )
    return bool(json.loads(response.text.strip()).get("already_included"))


def _duplicate(context, label, reason):
    """
    The worker sent again something we already have.

    ---

    El trabajador ha vuelto a enviar algo que ya teníamos: no se añade
    nada a la ficha y se le dice, por si le falta la otra cara.
    """
    _reply(context.submission.from_phone, (
        "Esta cara de su %s ya la teníamos. Si le falta enviar la otra "
        "cara, envíela ahora." % label
    ))
    return _finish(
        context.submission, WorkerDocumentSubmission.STATUS_DUPLICATE,
        "Repetido: %s." % reason,
    )


def _fail(context, reason, verdict=None):
    """
    Something broke after download: keep the file and tell the worker.

    ---

    Algo ha fallado después de descargar (Gemini, archivado, unión):
    el archivo se guarda en NO CONFORMES/ para revisión humana y el
    trabajador lo sabe -- ni se pierde ni se queda en silencio.
    """
    submission = context.submission
    try:
        entry = _store_loose_object(
            NO_CONFORMES_PREFIX.rstrip("/"), context.person, submission,
            context.data, context.content_type, context.extension,
        )
    except Exception:
        logger.exception(
            "# [DOC REQUEST] Tampoco se pudo guardar (%s)", submission.pk,
        )
        entry = None
    _reply(submission.from_phone, (
        "Hemos recibido su archivo, pero no hemos podido revisarlo "
        "automáticamente. Lo revisará una persona."
    ))
    return _finish(
        submission, WorkerDocumentSubmission.STATUS_ERROR, reason,
        verdict=verdict, entry=entry,
    )


def _refuse(context, queue, delivered, verdict):
    """
    Keep the file in NO CONFORMES and tell the worker why.

    ---

    Guarda el archivo en NO CONFORMES/ (ningún adjunto se pierde) y le
    dice al trabajador por qué. Con una solicitud abierta, con la frase
    de Miguel Ángel; la solicitud sigue abierta para que lo reenvíe.
    """
    submission = context.submission
    entry = _store_loose_object(
        NO_CONFORMES_PREFIX.rstrip("/"), context.person, submission,
        context.data, context.content_type, context.extension,
    )
    if queue:
        active = queue[0]
        text = (
            "El archivo entregado no es el solicitado. Hemos solicitado "
            "%s y usted ha entregado %s. %s" % (
                active.document_type.label, delivered, CLOSING,
            )
        )
        submission.request = active
    else:
        text = (
            "El archivo entregado no se ha podido archivar: usted ha "
            "entregado %s." % delivered
        )
    _reply(submission.from_phone, text)
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
