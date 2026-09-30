# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/inbox_service.py
"""
H30 (S126). Panel "Bandeja de entrada": files the supervisor drags in
(signed documents downloaded from Docuten, or any other document) are
identified by content, classified and filed in the worker's record.

---

H30 (S126). Pestaña "Bandeja de entrada" del panel. Diseño de Miguel
Ángel (S126): la propia supervisora sube, arrastrando o con el diálogo,
los documentos firmados que descarga de Docuten (o cualquier otro
documento de un trabajador) -- sin agente vigilando su PC. Aquí:

- Cada archivo se identifica por su huella SHA-256 (`InboxItem`): el
  mismo archivo nunca se procesa dos veces, llegue suelto o dentro de
  un ZIP. Un archivo ya existente en la plataforma (mismo MD5 que un
  documento vivo) sale como "ya estaba", sin tocar nada.
- Un ZIP se abre aquí mismo y cada archivo de dentro es un
  `InboxItem` propio (Docuten no documenta si una descarga de varios
  llega en ZIP o en PDF sueltos: se aceptan las dos cosas).
- Gemini lee el documento contra el catálogo de Personal (circulares
  incluidas): tipo, titular (DNI/NIE y nombre), fechas y, si es una
  circular, si está firmada y si es de Docuten.
- Se identifica al trabajador por DNI/NIE y, si no, por apellido y
  nombre -- solo con certeza (una única persona).
- Conforme -> se archiva en su ficha (`upload_subject_document`: tipo,
  nombre canónico, fechas y sustitución del vigente). Una circular
  firmada queda además registrada como firmada
  (`DocumentAcknowledgment`, canal DOCUTEN o PAPER, con el PDF firmado
  como documento de origen).
- No conforme -> "NO CONFORMES BANDEJA DE ENTRADA/" con su motivo,
  separado del NO CONFORMES del H28.
"""
import base64
import hashlib
import io
import json
import logging
import zipfile
from datetime import date

from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.utils import timezone
from google.genai.types import GenerateContentConfig, HttpOptions, Part

from ai_services.gemini_client import DEFAULT_MODEL, get_gemini_client
from document_explorer import index_writer, naming_service
from document_explorer.buckets import (
    INBOX_NO_CONFORMES_PREFIX, INBOX_STAGING_PREFIX,
)
from document_explorer.classification_service import (
    _generate_content_with_retry,
)
from document_explorer.models import (
    DocumentAcknowledgment, DocumentIndexEntry, DocumentTypeCatalog,
    InboxItem, PersonIdentity,
)
from document_explorer.subject_upload_service import (
    BUCKET, SubjectUploadError, content_type_of, upload_subject_document,
)
from document_explorer.worker_request_service import (
    _holder_matches, _normalize_text, _person_label,
)
from spare_parts.gcs_service import (
    delete_file, download_bytes, get_storage_client, upload_bytes,
)

logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = {"pdf", "jpg", "jpeg", "png", "webp", "heic"}
ZIP_EXTENSION = "zip"
MAX_ZIP_MEMBERS = 500
GEMINI_MIME_TYPES = {
    "application/pdf", "image/jpeg", "image/png", "image/webp",
    "image/heic",
}
OTHER_CODE = "OTRO"

_INBOX_SCHEMA = {
    "type": "object",
    "properties": {
        "detected_type_code": {"type": "string"},
        "detected_description": {"type": "string"},
        "holder_full_name": {"type": "string"},
        "holder_id_number": {"type": "string"},
        "several_people": {"type": "boolean"},
        "issue_date": {"type": "string"},
        "expiry_date": {"type": "string"},
        "is_signed": {"type": "boolean"},
        "signed_with_docuten": {"type": "boolean"},
        "signature_date": {"type": "string"},
    },
    "required": [
        "detected_type_code", "detected_description", "holder_full_name",
        "holder_id_number", "several_people", "issue_date",
        "expiry_date", "is_signed", "signed_with_docuten",
        "signature_date",
    ],
}


class InboxUploadError(Exception):
    """
    A file the inbox does not accept (message shown to the supervisor).

    ---

    Archivo que la bandeja no admite (mensaje para el supervisor).
    """


class TransientInboxError(Exception):
    """
    Gemini saturated/unavailable: try again later.

    ---

    Gemini saturado o caído: se reintenta más tarde desde la tarea.
    """


# ---------------------------------------------------------------------
# Registro de archivos subidos
# ---------------------------------------------------------------------

def _extension_of(name):
    """
    Lowercase extension of a file name ("" if none).

    ---

    Extensión en minúsculas del nombre ("" si no tiene).
    """
    return name.rsplit(".", 1)[-1].lower() if "." in name else ""


def _gcs_md5(data):
    """
    MD5 in the base64 form GCS stores (`DocumentIndexEntry.md5_hash`).

    ---

    MD5 en la forma base64 que guarda GCS (`md5_hash` del índice).
    """
    return base64.b64encode(hashlib.md5(data).digest()).decode("ascii")


def register_upload(name, data, uploaded_by):
    """
    Register one uploaded file (a ZIP is opened into its files).

    Returns a list of (InboxItem, created, note) -- `note` explains an
    item that was not queued again (already archived, already in
    progress). Raises InboxUploadError for a file type not accepted.

    ---

    Registra un archivo subido (un ZIP se abre en sus archivos).
    Devuelve una lista de (InboxItem, creado, nota): la nota explica
    por qué un archivo no vuelve a la cola (ya archivado, ya en
    proceso). Lanza InboxUploadError si el tipo no se admite.
    """
    extension = _extension_of(name)
    if extension == ZIP_EXTENSION:
        return _register_zip(name, data, uploaded_by)
    if extension not in ALLOWED_EXTENSIONS:
        raise InboxUploadError(
            "%s: solo se admiten PDF, imágenes (JPG, PNG, WEBP, HEIC) y "
            "ZIP." % name
        )
    return [_register_file(name, data, uploaded_by, "")]


def _register_zip(name, data, uploaded_by):
    """
    Open a ZIP and register every accepted file inside.

    ---

    Abre un ZIP y registra cada archivo admitido de dentro. Se ignoran
    carpetas, archivos ocultos y los de macOS (__MACOSX); un archivo de
    tipo no admitido se devuelve como aviso, nunca en silencio.
    """
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise InboxUploadError("%s: el ZIP está dañado." % name)
    members = [
        info for info in archive.infolist()
        if not info.is_dir()
        and not info.filename.startswith("__MACOSX/")
        and not info.filename.rsplit("/", 1)[-1].startswith(".")
    ]
    if not members:
        raise InboxUploadError("%s: el ZIP está vacío." % name)
    if len(members) > MAX_ZIP_MEMBERS:
        raise InboxUploadError(
            "%s: el ZIP tiene %d archivos; como máximo %d por ZIP." % (
                name, len(members), MAX_ZIP_MEMBERS,
            )
        )
    results = []
    for info in members:
        member_name = info.filename.rsplit("/", 1)[-1]
        if _extension_of(member_name) not in ALLOWED_EXTENSIONS:
            results.append((
                None, False,
                "%s (dentro de %s): tipo de archivo no admitido." % (
                    member_name, name,
                ),
            ))
            continue
        results.append(_register_file(
            member_name, archive.read(info), uploaded_by, name,
        ))
    return results


def _register_file(name, data, uploaded_by, container_name):
    """
    Create (or reuse) the InboxItem of one file and queue it.

    ---

    Crea (o reutiliza) el InboxItem de un archivo y lo encola. Mismo
    archivo ya archivado o en proceso -> no se vuelve a encolar. Si
    antes salió no conforme o con error, se procesa de nuevo (p. ej.
    tras corregir la ficha del trabajador).
    """
    from document_explorer.tasks import process_inbox_item_task

    sha256 = hashlib.sha256(data).hexdigest()
    extension = _extension_of(name)
    content_type = content_type_of(data, name)
    if content_type == "application/octet-stream" and extension == "heic":
        content_type = "image/heic"
    with transaction.atomic():
        item = InboxItem.objects.select_for_update().filter(
            sha256=sha256,
        ).first()
        if item is not None and item.status not in (
            InboxItem.RETRYABLE_STATUSES
        ):
            note = (
                "Ya se había subido (%s)." % item.get_status_display()
                if item.status not in InboxItem.OPEN_STATUSES
                else "Ya está en la cola."
            )
            return item, False, note
        created = item is None
        if created:
            item = InboxItem(sha256=sha256)
        staging_blob = "%s%s.%s" % (INBOX_STAGING_PREFIX, sha256, extension)
        upload_bytes(BUCKET, staging_blob, data, content_type=content_type)
        item.original_name = name[:255]
        item.container_name = (container_name or "")[:255]
        item.content_type = content_type
        item.size_bytes = len(data)
        item.staging_blob = staging_blob
        item.status = InboxItem.STATUS_PENDING
        item.reason = ""
        item.verdict = {}
        item.person = None
        item.document_type = None
        item.entry = None
        item.acknowledgment = None
        item.uploaded_by = uploaded_by
        item.processed_at = None
        item.save()
        item_pk = item.pk
        transaction.on_commit(
            lambda: process_inbox_item_task.delay(item_pk),
        )
    return item, created, ""


# ---------------------------------------------------------------------
# Clasificación y archivo
# ---------------------------------------------------------------------

def _candidate_types():
    """
    Personal catalog types Gemini may choose from (circulars included).

    ---

    Tipos del catálogo de Personal entre los que puede elegir Gemini,
    circulares incluidas (son el caso principal: firmadas de Docuten),
    sin la familia Media (imagen/vídeo genéricos no son un documento).
    """
    return list(DocumentTypeCatalog.objects.filter(
        is_active=True,
        domain__in=(
            DocumentTypeCatalog.DOMAIN_PERSONAL,
            DocumentTypeCatalog.DOMAIN_BOTH,
        ),
    ).exclude(
        family=DocumentTypeCatalog.FAMILY_MEDIA,
    ).order_by("label"))


def _read_with_gemini(data, content_type, candidates):
    """
    Ask Gemini what the document is, whose, its dates and signature.

    ---

    Pregunta a Gemini qué documento es, de quién, sus fechas y, si es
    una circular, si está firmada y si la firma es de Docuten.
    """
    types_text = "\n".join(
        "- %s: %s%s" % (
            doc_type.code, doc_type.label,
            " (circular/notificación de la empresa al trabajador)"
            if doc_type.is_notification_template else "",
        )
        for doc_type in candidates
    )
    prompt = (
        "Eres un asistente que revisa documentación laboral española de "
        "un grupo de empresas de grúas. La supervisora de documentación "
        "ha subido este archivo. Estos son los únicos tipos de "
        "documento posibles:\n"
        "%s\n\n"
        "Responde:\n"
        "- detected_type_code: el código de la lista que corresponde a "
        "lo que es REALMENTE el documento; si no es ninguno, '%s'.\n"
        "- detected_description: qué es el documento, en pocas "
        "palabras y en castellano.\n"
        "- holder_full_name: nombre y apellidos del trabajador al que "
        "se refiere el documento (en una circular, el trabajador "
        "destinatario que la firma, nunca la empresa ni quien la "
        "emite), o cadena vacía.\n"
        "- holder_id_number: DNI/NIE de ese trabajador tal como "
        "aparece, o cadena vacía.\n"
        "- several_people: true si el documento es de varios "
        "trabajadores distintos (p. ej. firmado por varios).\n"
        "- issue_date y expiry_date: fecha del documento y fecha de "
        "caducidad o validez, en formato AAAA-MM-DD, o cadena vacía. "
        "No inventes ninguna fecha.\n"
        "- is_signed: true si el trabajador lo ha firmado (firma "
        "manuscrita, biométrica o electrónica visible).\n"
        "- signed_with_docuten: true si la firma es de la plataforma "
        "Docuten (sello, código de verificación o referencias a "
        "Docuten en el documento).\n"
        "- signature_date: fecha de la firma del trabajador en formato "
        "AAAA-MM-DD, o cadena vacía."
    ) % (types_text, OTHER_CODE)
    client = get_gemini_client()
    response = _generate_content_with_retry(
        client,
        model=DEFAULT_MODEL,
        contents=[Part.from_bytes(data=data, mime_type=content_type), prompt],
        config=GenerateContentConfig(
            http_options=HttpOptions(timeout=120_000),
            response_mime_type="application/json",
            response_schema=_INBOX_SCHEMA,
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


def _prefer_active(people):
    """
    Keep only active employees if that leaves anyone.

    ---

    Si hay varios, se queda con los trabajadores activos (si queda
    alguno).
    """
    active = [person for person in people if person.is_active_employee]
    return active or people


def identify_person(verdict):
    """
    The worker the document belongs to, or (None, why not).

    ---

    Trabajador al que pertenece el documento, o (None, motivo). Manda
    el DNI/NIE leído; si no hay, apellido y nombre. Solo con certeza:
    una única persona (si hay varias, se prefieren los activos).
    """
    read_id = _normalize_text(
        verdict.get("holder_id_number"),
    ).replace(" ", "")
    people = list(PersonIdentity.objects.all())
    if read_id:
        by_id = [
            person for person in people
            if _normalize_text(person.dni).replace(" ", "") == read_id
        ]
        by_id = _prefer_active(by_id)
        if len(by_id) == 1:
            return by_id[0], ""
        if len(by_id) > 1:
            return None, "el DNI/NIE %s está en varias fichas" % read_id
    holder = (verdict.get("holder_full_name") or "").strip()
    if not holder:
        return None, "no se lee el trabajador del documento"
    by_name = _prefer_active([
        person for person in people
        if _holder_matches({"holder_full_name": holder}, person)
    ])
    if len(by_name) == 1:
        return by_name[0], ""
    if not by_name:
        return None, "ningún trabajador se llama «%s»" % holder
    return None, "«%s» coincide con %d trabajadores" % (holder, len(by_name))


def _finish(item, status, reason, **fields):
    """
    Close an item and remove its temporary GCS copy.

    ---

    Cierra el archivo con su estado y motivo y borra la copia temporal
    de _BANDEJA_ENTRADA/ -- salvo en un error, que la conserva para
    poder volver a clasificarlo sin volver a subirlo.
    """
    if status == InboxItem.STATUS_ERROR:
        item.status = status
        item.reason = reason[:2000]
        item.processed_at = timezone.now()
        for name, value in fields.items():
            setattr(item, name, value)
        item.save()
        return status
    if item.staging_blob:
        try:
            delete_file(BUCKET, item.staging_blob)
        except Exception:
            logger.exception(
                "# [INBOX] No se pudo borrar la copia temporal %s",
                item.staging_blob,
            )
    item.status = status
    item.reason = reason[:2000]
    item.staging_blob = ""
    item.processed_at = timezone.now()
    for name, value in fields.items():
        setattr(item, name, value)
    item.save()
    return status


def _store_no_conforme(item, data, person):
    """
    Keep a non-conforming file in its own folder, indexed.

    ---

    Guarda un archivo no conforme en "NO CONFORMES BANDEJA DE
    ENTRADA/" y lo indexa (ningún archivo se pierde). El nombre lleva
    el principio de la huella: nunca pisa un objeto existente.
    """
    folder = INBOX_NO_CONFORMES_PREFIX.rstrip("/")
    who = (
        naming_service._sanitize_token(_person_label(person))
        if person is not None else "DESCONOCIDO"
    )
    blob_name = "%s/BANDEJA_%s_%s_%s.%s" % (
        folder, who, timezone.localdate().strftime("%Y%m%d"),
        item.sha256[:12], _extension_of(item.original_name) or "bin",
    )
    upload_bytes(
        BUCKET, blob_name, data,
        content_type=item.content_type or "application/octet-stream",
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


def _reject(item, data, reason, verdict, person=None, doc_type=None):
    """
    Non-conforming: stored apart, with its reason.

    ---

    No conforme: se guarda aparte y queda el motivo visible.
    """
    entry = _store_no_conforme(item, data, person)
    return _finish(
        item, InboxItem.STATUS_REJECTED, reason, verdict=verdict,
        person=person, document_type=doc_type, entry=entry,
    )


def process_item(item_id, final=False):
    """
    Classify and file one inbox item.

    ---

    Clasifica y archiva un archivo de la bandeja. Con `final`, un fallo
    transitorio de Gemini ya no se reintenta: queda como error visible.
    """
    item = InboxItem.objects.select_related("uploaded_by").get(pk=item_id)
    if item.status not in InboxItem.OPEN_STATUSES:
        return item.status
    item.status = InboxItem.STATUS_PROCESSING
    item.save(update_fields=["status"])
    try:
        data = download_bytes(BUCKET, item.staging_blob)
    except Exception as exc:
        return _finish(
            item, InboxItem.STATUS_ERROR,
            "No se pudo leer la copia temporal: %s" % exc,
        )

    existing = DocumentIndexEntry.objects.filter(
        md5_hash=_gcs_md5(data),
        entry_kind=DocumentIndexEntry.KIND_FILE,
        document_type__isnull=False,
        deleted_at__isnull=True,
        purged_at__isnull=True,
    ).first()
    if existing is not None:
        return _finish(
            item, InboxItem.STATUS_DUPLICATE,
            "Este mismo archivo ya está en la plataforma: %s." % (
                existing.name,
            ),
            entry=existing, document_type=existing.document_type,
        )

    content_type = (item.content_type or "").split(";")[0].lower()
    if content_type not in GEMINI_MIME_TYPES:
        return _reject(item, data, "No es un PDF ni una imagen legible.", {})
    candidates = _candidate_types()
    try:
        verdict = _read_with_gemini(data, content_type, candidates)
    except Exception as exc:
        if not final:
            item.status = InboxItem.STATUS_PENDING
            item.save(update_fields=["status"])
            raise TransientInboxError(str(exc)) from exc
        logger.exception("# [INBOX] Gemini falló (%s)", item.pk)
        return _finish(
            item, InboxItem.STATUS_ERROR,
            "Gemini no pudo leer el archivo: %s" % exc,
        )

    code = (verdict.get("detected_type_code") or "").strip().upper()
    described = (verdict.get("detected_description") or "").strip()
    doc_type = next((t for t in candidates if t.code == code), None)
    if doc_type is None:
        return _reject(
            item, data,
            "Tipo de documento no reconocido: %s." % (
                described or "desconocido",
            ),
            verdict,
        )
    if verdict.get("several_people"):
        return _reject(
            item, data,
            "%s de varios trabajadores: súbelo separado por trabajador."
            % doc_type.label,
            verdict, doc_type=doc_type,
        )
    person, why_not = identify_person(verdict)
    if person is None:
        return _reject(
            item, data, "%s: %s." % (doc_type.label, why_not), verdict,
            doc_type=doc_type,
        )
    if doc_type.is_notification_template and not verdict.get("is_signed"):
        return _reject(
            item, data, "%s sin firmar." % doc_type.label, verdict,
            person=person, doc_type=doc_type,
        )
    return _archive(item, data, verdict, person, doc_type)


def _archive(item, data, verdict, person, doc_type):
    """
    File the document in the worker's record (and register a signature).

    ---

    Archiva el documento en la ficha del trabajador. Los archivos de
    una misma persona se archivan de uno en uno (bloqueo de su fila):
    dos subidas a la vez del mismo tipo nunca deciden el vigente sin
    verse. Una circular firmada queda además registrada como firmada.
    """
    expiry = _parse_iso(verdict.get("expiry_date"))
    signature_date = _parse_iso(verdict.get("signature_date"))
    issue = _parse_iso(verdict.get("issue_date")) or signature_date
    acknowledgment = None
    try:
        with transaction.atomic():
            PersonIdentity.objects.select_for_update().get(pk=person.pk)
            entry = upload_subject_document(
                subject=person,
                domain_content_type=ContentType.objects.get_for_model(
                    PersonIdentity,
                ),
                document_type=doc_type,
                data=data,
                original_filename=item.original_name,
                typed_date=expiry if doc_type.tracks_expiry else None,
                typed_issue_date=issue,
                subject_label=_person_label(person),
                uploaded_by=item.uploaded_by,
            )["entry"]
            if doc_type.is_notification_template:
                acknowledgment = DocumentAcknowledgment.objects.create(
                    person=person,
                    document_type=doc_type,
                    delivery_date=(
                        signature_date or issue or timezone.localdate()
                    ),
                    source_entry=entry,
                    extraction_method=DocumentAcknowledgment.METHOD_GEMINI,
                    channel=(
                        DocumentAcknowledgment.CHANNEL_DOCUTEN
                        if verdict.get("signed_with_docuten")
                        else DocumentAcknowledgment.CHANNEL_PAPER
                    ),
                )
    except SubjectUploadError as exc:
        return _finish(
            item, InboxItem.STATUS_ERROR,
            "No se pudo archivar en la ficha: %s" % exc,
            verdict=verdict, person=person, document_type=doc_type,
        )
    if acknowledgment is not None:
        reason = "%s firmada%s, archivada en la ficha de %s." % (
            doc_type.label,
            " por Docuten" if acknowledgment.channel == (
                DocumentAcknowledgment.CHANNEL_DOCUTEN
            ) else "",
            _person_label(person),
        )
    else:
        reason = "%s archivado en la ficha de %s." % (
            doc_type.label, _person_label(person),
        )
    return _finish(
        item, InboxItem.STATUS_ARCHIVED, reason, verdict=verdict,
        person=person, document_type=doc_type, entry=entry,
        acknowledgment=acknowledgment,
    )


def requeue_items(items, uploaded_by):
    """
    Classify again non-conforming or failed items.

    Returns (requeued, skipped) counts.

    ---

    Vuelve a clasificar los archivos no conformes o con error (p. ej.
    tras corregir la ficha del trabajador), sin volver a subirlos: un
    error conserva su copia temporal; un no conforme se relee de su
    copia en NO CONFORMES BANDEJA DE ENTRADA/. El resto se salta.
    Devuelve (encolados, saltados).
    """
    from document_explorer.tasks import process_inbox_item_task

    requeued = skipped = 0
    for item in items:
        if item.status not in InboxItem.RETRYABLE_STATUSES:
            skipped += 1
            continue
        if not item.staging_blob:
            if item.entry is None:
                skipped += 1
                continue
            data = download_bytes(item.entry.bucket, item.entry.blob_name)
            item.staging_blob = "%s%s.%s" % (
                INBOX_STAGING_PREFIX, item.sha256,
                _extension_of(item.original_name) or "bin",
            )
            upload_bytes(
                BUCKET, item.staging_blob, data,
                content_type=item.content_type or "application/octet-stream",
            )
        item.status = InboxItem.STATUS_PENDING
        item.reason = ""
        item.processed_at = None
        item.uploaded_by = uploaded_by
        item.save(update_fields=[
            "staging_blob", "status", "reason", "processed_at",
            "uploaded_by",
        ])
        item_pk = item.pk
        transaction.on_commit(
            lambda pk=item_pk: process_inbox_item_task.delay(pk),
        )
        requeued += 1
    return requeued, skipped
