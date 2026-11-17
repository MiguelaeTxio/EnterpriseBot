# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/hr_calendar/worker_requests.py
"""
Worker requests (H24, S147): what the worker asks for from "Mis
solicitudes" and what a supervisor does with it.

Miguel Ángel (S147): a service page where workers request their
vacation, personal-matters days and the days they want to see the
doctor, manage the proof of having gone to the doctor (until now it
went through the partes), and request the documents the company is
bound to give them; supervisors see and handle those requests and
claims. Approving is the only way a request becomes a real
VacationPeriod or AbsencePeriod (the same creation functions the
Vacaciones tab uses); files live in the worker's own folder as any
other document of theirs (subject_upload_service).

---

Solicitudes de los trabajadores (H24, S147): lo que el trabajador pide
desde "Mis solicitudes" y lo que hace con ello un supervisor.

Miguel Ángel (S147): una página de servicio en la que los trabajadores
solicitan sus vacaciones, sus días de asuntos propios y los días que
quieren ir al médico, gestionan los justificantes de haber ido al
médico (hasta ahora iba por los partes) y piden los documentos que la
empresa está obligada a facilitarles; los supervisores ven esas
peticiones y reclamaciones y las gestionan. Aprobar es la única forma
de que una petición se convierta en un VacationPeriod o AbsencePeriod
de verdad (con las mismas funciones de alta que la pestaña Vacaciones);
los archivos viven en la carpeta del propio trabajador como cualquier
otro documento suyo (subject_upload_service).
"""
import datetime
import logging

from django.db import transaction
from django.utils import timezone

from hr_calendar.models import WorkerRequest, WorkerRequestFile

logger = logging.getLogger(__name__)

# Documentos que la empresa debe dar al trabajador y que puede pedir
# (S147). (clave, nombre, referencia legal, tipo de documento de la
# ficha con el que se archiva la entrega por defecto; "" = lo elige el
# supervisor al entregar).
DOCUMENTS = (
    ("NOMINA", "Nómina (recibo de salarios)", "art. 29 ET", "NOMINA"),
    ("RETENCIONES", "Certificado de retenciones (IRPF)",
     "art. 108 RIRPF", ""),
    ("CERT_EMPRESA", "Certificado de empresa (para el paro)",
     "art. 298 LGSS", ""),
    ("REGISTRO_JORNADA", "Registro de jornada", "art. 34.9 ET",
     "REGISTRO_JORNADA"),
    ("CONTRATO", "Copia del contrato, prórrogas y modificaciones",
     "art. 8 ET", "CONTRATO"),
    ("CERT_SERVICIOS", "Certificado de servicios prestados", "",
     "CERTIF_TRABAJO_COLEGIO"),
    ("RECONOCIMIENTO", "Resultado del reconocimiento médico",
     "art. 22 LPRL", "RECONOCIMIENTO_MEDICO"),
    ("FINIQUITO", "Finiquito (liquidación)", "art. 49.2 ET", ""),
    ("OTRO", "Otro documento", "", ""),
)
DOCUMENT_LABELS = {code: label for code, label, _l, _t in DOCUMENTS}
DOCUMENT_TYPES = {code: type_code for code, _n, _l, type_code in DOCUMENTS}

# Catálogo de ausencias con el que se aprueba cada tipo (seed de
# work_order_processor: seed_absence_categories).
ABSENCE_CODES = {
    WorkerRequest.Kind.PERSONAL: "PERSONAL_MATTERS",
    WorkerRequest.Kind.MEDICAL: "MEDICAL_APPOINTMENT",
}
# Tipo de documento del justificante: el nuevo si ya existe en el
# catálogo (pendiente de confirmar por Miguel Ángel, S147); si no, el
# informe médico.
PROOF_TYPE_CODES = ("JUSTIFICANTE_ASISTENCIA_MEDICA", "INFORME_MEDICO")
DATED_KINDS = (
    WorkerRequest.Kind.VACATION, WorkerRequest.Kind.PERSONAL,
    WorkerRequest.Kind.MEDICAL,
)
MAX_FILE_BYTES = 15 * 1024 * 1024
# S153: desde "Mis solicitudes" solo se piden documentos. Miguel Ángel:
# vacaciones, días libres y médico "que sigan el cauce normal"; lo
# concedido lo apunta la empresa en Vacaciones y el trabajador lo ve.
WORKER_KINDS = (WorkerRequest.Kind.DOCUMENT,)


class RequestError(ValueError):
    """
    A request that cannot be done; the message is for the user.
    ---
    Una acción que no se puede hacer; el mensaje es para el usuario.
    """


def person_label(person):
    """
    "Apellidos, Nombre".
    ---
    "Apellidos, Nombre" del trabajador.
    """
    surnames = " ".join(
        p for p in (person.first_surname, person.second_surname) if p
    )
    return ("%s, %s" % (surnames, person.given_name)).strip(", ")


def _parse_date(raw):
    try:
        return datetime.date.fromisoformat((raw or "").strip())
    except ValueError:
        return None


def _parse_time(raw):
    try:
        return datetime.time.fromisoformat((raw or "").strip()[:5])
    except ValueError:
        return None


def day_count(request):
    """
    Calendar days the request covers, or None.
    ---
    Días naturales que abarca la petición, o None si no lleva fechas.
    """
    if request.date_start and request.date_end:
        return (request.date_end - request.date_start).days + 1
    return None


def create_request(person, company, created_by, data):
    """
    Stores a new request from the worker's form (a dict of strings).
    ---
    Guarda una petición nueva desde el formulario del trabajador (un
    diccionario de textos). RequestError con el motivo si falta algo.
    Vacaciones y asuntos propios no admiten días ya pasados; el médico
    sí (se puede pedir después, con el justificante).
    """
    kind = (data.get("kind") or "").strip()
    if kind not in WORKER_KINDS:
        raise RequestError(
            "Desde aquí solo se piden documentos. Las vacaciones, los "
            "días libres y las citas médicas se piden por el cauce "
            "habitual.")
    note = (data.get("note") or "").strip()
    fields = {
        "company": company, "person": person, "kind": kind, "note": note,
        "created_by": created_by,
    }
    if kind in DATED_KINDS:
        start = _parse_date(data.get("date_start"))
        end = _parse_date(data.get("date_end")) or start
        if start is None:
            raise RequestError("Indica el día (o desde qué día).")
        if end < start:
            raise RequestError(
                "La fecha de fin no puede ser anterior a la de inicio.")
        today = timezone.localdate()
        if kind != WorkerRequest.Kind.MEDICAL and start < today:
            raise RequestError(
                "No se pueden pedir días que ya han pasado.")
        fields.update(date_start=start, date_end=end)
        if kind == WorkerRequest.Kind.MEDICAL:
            time_from = _parse_time(data.get("time_from"))
            time_to = _parse_time(data.get("time_to"))
            if time_from and time_to and time_to <= time_from:
                raise RequestError(
                    "La hora de vuelta tiene que ser posterior a la de "
                    "salida.")
            fields.update(time_from=time_from, time_to=time_to)
    elif kind == WorkerRequest.Kind.DOCUMENT:
        code = (data.get("document_code") or "").strip()
        if code not in DOCUMENT_LABELS:
            raise RequestError("Elige el documento que necesitas.")
        if code == "OTRO" and not note:
            raise RequestError("Escribe qué documento necesitas.")
        fields.update(
            document_code=code,
            period=(data.get("period") or "").strip()[:120],
        )
    elif not note:
        raise RequestError("Escribe tu reclamación o consulta.")
    request = WorkerRequest.objects.create(**fields)
    logger.info(
        "[solicitudes] nueva #%s %s de la persona %s", request.pk, kind,
        person.pk,
    )
    return request


def cancel_by_worker(request):
    """
    The worker withdraws a pending request.
    ---
    El trabajador anula una petición que aún no se ha resuelto.
    """
    if request.status != WorkerRequest.Status.PENDING:
        raise RequestError("Solo se puede anular una petición pendiente.")
    request.status = WorkerRequest.Status.CANCELLED
    request.resolved_at = timezone.now()
    request.save(update_fields=["status", "resolved_at"])


def _resolve(request, status, by, response=None):
    request.status = status
    request.resolved_by = by
    request.resolved_at = timezone.now()
    fields = ["status", "resolved_by", "resolved_at"]
    if response is not None:
        request.response = response.strip()
        fields.append("response")
    return fields


def _absence_note(request):
    parts = ["Solicitud del trabajador nº %s." % request.pk]
    if request.time_from or request.time_to:
        parts.append("Horas: %s a %s." % (
            request.time_from.strftime("%H:%M") if request.time_from
            else "—",
            request.time_to.strftime("%H:%M") if request.time_to else "—",
        ))
    if request.note:
        parts.append(request.note)
    return " ".join(parts)


def approve(request, by, response=""):
    """
    Approves a dated request and creates its real period.
    ---
    Aprueba una petición con fechas y crea su periodo real: vacaciones
    -> VacationPeriod (create_vacation_period, con su tarea fantasma);
    asuntos propios y médico -> AbsencePeriod con su categoría. Todo o
    nada (una transacción).
    """
    from hr_calendar.services import (
        absence_categories, create_absence_period, create_vacation_period,
    )

    if request.status != WorkerRequest.Status.PENDING:
        raise RequestError("La petición ya está resuelta.")
    if request.kind not in DATED_KINDS:
        raise RequestError(
            "Las peticiones de documentos se entregan; las reclamaciones "
            "se responden.")
    with transaction.atomic():
        if request.kind == WorkerRequest.Kind.VACATION:
            try:
                request.vacation_period = create_vacation_period(
                    request.person, request.company, by,
                    request.date_start, request.date_end,
                )
            except ValueError as exc:
                raise RequestError(str(exc)) from exc
            except Exception as exc:  # tarea fantasma sin datos base
                logger.exception("[solicitudes] vacaciones #%s", request.pk)
                raise RequestError(
                    "No se han podido registrar las vacaciones: falta el "
                    "centro de gasto PERSONAL o la categoría Vacaciones."
                ) from exc
            extra = ["vacation_period"]
        else:
            code = ABSENCE_CODES[request.kind]
            category = absence_categories(request.company).filter(
                code=code).first()
            if category is None:
                raise RequestError(
                    "No existe la categoría de ausencia %s activa." % code)
            try:
                request.absence_period = create_absence_period(
                    request.person, request.company, by, category.pk,
                    request.date_start, request.date_end,
                    _absence_note(request),
                )
            except ValueError as exc:
                raise RequestError(str(exc)) from exc
            extra = ["absence_period"]
        fields = _resolve(request, WorkerRequest.Status.APPROVED, by,
                          response)
        request.save(update_fields=fields + extra)
    logger.info("[solicitudes] #%s aprobada por %s", request.pk, by.pk)
    return request


def deny(request, by, response):
    """
    Denies a pending request; the reason is mandatory.
    ---
    Deniega una petición pendiente; el motivo es obligatorio.
    """
    if request.status != WorkerRequest.Status.PENDING:
        raise RequestError("La petición ya está resuelta.")
    if not (response or "").strip():
        raise RequestError("Escribe el motivo de la denegación.")
    fields = _resolve(request, WorkerRequest.Status.DENIED, by, response)
    request.save(update_fields=fields)
    logger.info("[solicitudes] #%s denegada por %s", request.pk, by.pk)
    return request


def answer(request, by, response):
    """
    Answers a claim or query.
    ---
    Responde una reclamación o consulta (también se puede volver a
    responder: la respuesta se sustituye).
    """
    if request.kind != WorkerRequest.Kind.CLAIM:
        raise RequestError("Solo las reclamaciones se responden.")
    if request.status == WorkerRequest.Status.CANCELLED:
        raise RequestError("El trabajador la anuló.")
    if not (response or "").strip():
        raise RequestError("Escribe la respuesta.")
    fields = _resolve(request, WorkerRequest.Status.ANSWERED, by, response)
    request.save(update_fields=fields)
    return request


def undo(request, by):
    """
    Back to pending, deleting the period the approval created.
    ---
    Deshace una resolución (aprobada, denegada, entregada o respondida):
    vuelve a pendiente y, si la aprobación creó un periodo, lo borra
    (delete_vacation_period, que quita también su tarea fantasma). Los
    archivos entregados se quedan en la ficha del trabajador.
    """
    from hr_calendar.services import delete_vacation_period

    if request.status in (WorkerRequest.Status.PENDING,
                          WorkerRequest.Status.CANCELLED):
        raise RequestError("La petición no está resuelta.")
    with transaction.atomic():
        if request.vacation_period_id:
            delete_vacation_period(request.vacation_period)
        if request.absence_period_id:
            request.absence_period.delete()
        request.vacation_period = None
        request.absence_period = None
        request.status = WorkerRequest.Status.PENDING
        request.resolved_by = None
        request.resolved_at = None
        request.save(update_fields=[
            "vacation_period", "absence_period", "status", "resolved_by",
            "resolved_at",
        ])
    logger.info("[solicitudes] #%s deshecha por %s", request.pk, by.pk)
    return request


def _document_type(code):
    from document_explorer.models import DocumentTypeCatalog

    return DocumentTypeCatalog.objects.filter(
        code=code, is_active=True,
    ).first()


def proof_document_type():
    """
    The catalogue type the medical proofs are filed with.
    ---
    Tipo del catálogo con el que se archivan los justificantes médicos.
    """
    for code in PROOF_TYPE_CODES:
        found = _document_type(code)
        if found is not None:
            return found
    return None


def _store_file(request, role, data, filename, document_type, by,
                issue_date=None):
    """
    Files the bytes in the worker's folder and links them.
    ---
    Archiva los bytes en la carpeta del trabajador (como una subida
    desde su ficha) y los enlaza a la petición.
    """
    from django.contrib.contenttypes.models import ContentType

    from document_explorer.models import PersonIdentity
    from document_explorer.subject_upload_service import (
        SubjectUploadError, upload_subject_document,
    )

    if not data:
        raise RequestError("El archivo está vacío.")
    if len(data) > MAX_FILE_BYTES:
        raise RequestError("El archivo pasa de 15 MB.")
    if document_type is None:
        raise RequestError("Falta el tipo de documento en el catálogo.")
    try:
        result = upload_subject_document(
            subject=request.person,
            domain_content_type=ContentType.objects.get_for_model(
                PersonIdentity),
            document_type=document_type, data=data,
            original_filename=filename or "archivo.pdf",
            typed_date=None, typed_issue_date=issue_date,
            subject_label=person_label(request.person), uploaded_by=by,
        )
    except SubjectUploadError as exc:
        raise RequestError(str(exc)) from exc
    return WorkerRequestFile.objects.create(
        request=request, role=role, entry=result["entry"],
        name=(filename or result["entry"].name)[:255], uploaded_by=by,
    )


def add_proof(request, data, filename, by):
    """
    The worker (or a supervisor) uploads the medical proof.
    ---
    El trabajador (o un supervisor en su nombre) sube el justificante de
    una petición de médico. Queda "Recibido" hasta que lo revise un
    supervisor.
    """
    if request.kind != WorkerRequest.Kind.MEDICAL:
        raise RequestError("El justificante va en una petición de médico.")
    if request.status in (WorkerRequest.Status.DENIED,
                          WorkerRequest.Status.CANCELLED):
        raise RequestError("La petición está %s." % (
            request.get_status_display().lower()))
    stored = _store_file(
        request, WorkerRequestFile.Role.PROOF, data, filename,
        proof_document_type(), by, issue_date=request.date_start,
    )
    request.proof_status = WorkerRequest.ProofStatus.RECEIVED
    request.proof_reviewed_by = None
    request.proof_reviewed_at = None
    request.save(update_fields=[
        "proof_status", "proof_reviewed_by", "proof_reviewed_at",
    ])
    logger.info("[solicitudes] #%s justificante %s", request.pk, stored.pk)
    return stored


def review_proof(request, by, valid):
    """
    A supervisor accepts or rejects the uploaded proof.
    ---
    Un supervisor da por bueno o no el justificante subido.
    """
    if request.proof_status == WorkerRequest.ProofStatus.NONE:
        raise RequestError("No hay justificante que revisar.")
    request.proof_status = (WorkerRequest.ProofStatus.VALID if valid
                            else WorkerRequest.ProofStatus.REJECTED)
    request.proof_reviewed_by = by
    request.proof_reviewed_at = timezone.now()
    request.save(update_fields=[
        "proof_status", "proof_reviewed_by", "proof_reviewed_at",
    ])
    return request


def person_documents(person):
    """
    The live documents of the worker's file, newest first.
    ---
    Los documentos vivos de la ficha del trabajador, más recientes
    primero, para entregar uno que ya existe.
    """
    from django.contrib.contenttypes.models import ContentType

    from document_explorer.models import DocumentIndexEntry, PersonIdentity

    return DocumentIndexEntry.objects.filter(
        domain_content_type=ContentType.objects.get_for_model(
            PersonIdentity),
        domain_object_id=person.pk,
        entry_kind=DocumentIndexEntry.KIND_FILE,
        deleted_at__isnull=True, purged_at__isnull=True,
    ).select_related("document_type").order_by("-issue_date", "-pk")


def deliver(request, by, response="", data=None, filename="",
            type_code="", entry_id=None):
    """
    Delivers a requested document: a new file or one already filed.
    ---
    Entrega un documento pedido: un archivo nuevo (se archiva en la
    ficha con el tipo elegido) o uno que ya está en su ficha. Se puede
    entregar más de uno; la petición pasa a "Entregada".
    """
    if request.kind != WorkerRequest.Kind.DOCUMENT:
        raise RequestError("Solo se entregan documentos pedidos.")
    if request.status in (WorkerRequest.Status.DENIED,
                          WorkerRequest.Status.CANCELLED):
        raise RequestError("La petición está %s." % (
            request.get_status_display().lower()))
    with transaction.atomic():
        if entry_id:
            entry = person_documents(request.person).filter(
                pk=entry_id).first()
            if entry is None:
                raise RequestError(
                    "Ese documento no es de la ficha del trabajador.")
            WorkerRequestFile.objects.create(
                request=request, role=WorkerRequestFile.Role.DELIVERY,
                entry=entry, name=entry.name[:255], uploaded_by=by,
            )
        elif data:
            _store_file(
                request, WorkerRequestFile.Role.DELIVERY, data, filename,
                _document_type(type_code), by,
            )
        else:
            raise RequestError(
                "Sube el archivo o elige uno de su ficha.")
        fields = _resolve(request, WorkerRequest.Status.DELIVERED, by,
                          response if response.strip() else None)
        request.save(update_fields=fields)
    logger.info("[solicitudes] #%s entregada por %s", request.pk, by.pk)
    return request


def detail_text(request):
    """
    One line with what is asked: dates and hours, or the document.
    ---
    Una línea con lo que se pide: fechas y horas, o el documento.
    """
    if request.kind == WorkerRequest.Kind.DOCUMENT:
        text = DOCUMENT_LABELS.get(request.document_code,
                                   request.document_code)
        return "%s — %s" % (text, request.period) if request.period else text
    if request.date_start is None:
        return ""
    if request.date_end and request.date_end != request.date_start:
        text = "%s a %s" % (request.date_start.strftime("%d/%m/%Y"),
                            request.date_end.strftime("%d/%m/%Y"))
    else:
        text = request.date_start.strftime("%d/%m/%Y")
    if request.time_from or request.time_to:
        text += " (%s–%s)" % (
            request.time_from.strftime("%H:%M") if request.time_from
            else "?",
            request.time_to.strftime("%H:%M") if request.time_to else "?",
        )
    return text
