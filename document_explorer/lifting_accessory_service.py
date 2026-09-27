# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/lifting_accessory_service.py
"""
H30 (S121). Business rules for lifting accessories (slings, load
lines, shackles...): deliveries with history, per-accessory reviews
and the documents that can be linked to them.

---

H30 (S121). Reglas de negocio de los accesorios de elevación
(eslingas, líneas de carga, grilletes...): entregas con historial,
revisiones por accesorio y los documentos que se les pueden vincular.
Las vistas del panel nunca escriben estos modelos directamente -- pasan
por aquí, para que la pestaña y cualquier uso futuro apliquen la misma
regla.
"""

import re
from datetime import date

from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.utils import timezone

from document_explorer.index_writer import ensure_folder_chain
from document_explorer.models import (
    DocumentIndexEntry,
    DocumentTypeCatalog,
    LiftingAccessory,
    LiftingAccessoryAssignment,
    LiftingAccessoryReview,
    path_digest,
)

BUCKET = "cgs_grupo_alvarez"

# S121 -- decisión de Miguel Ángel: "igual que tenemos fichas técnicas
# para los EPIs, debemos tener certificados para los accesorios de
# elevación, y estos deben estar perfectamente tipados". Lo que ya está
# en el bucket lo tipa y enlaza el sistema; el supervisor solo sube el
# documento al dar de alta algo nuevo (nunca elige archivos de una
# lista ni ve rutas).
CERTIFICATE_TYPE_CODE = "CERT_ACCESORIO_ELEVACION"
REVIEW_TYPE_CODE = "REVISION_ESLINGAS"

# Carpetas de lo subido desde el panel, una subcarpeta por tipo de
# accesorio -- mismo patrón que _FICHAS_TECNICAS_EPI/<código>.
CERTIFICATES_ROOT = "_CERTIFICADOS_ACCESORIOS_ELEVACION"
REVIEWS_ROOT = "_REVISIONES_ACCESORIOS_ELEVACION"
_CONTENT_TYPES = {
    "pdf": "application/pdf",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
}


@transaction.atomic
def assign_accessory(accessory, responsible_person, machine, start_date,
                     notes=""):
    """
    Deliver an accessory to a cost centre and a responsible person:
    close the open delivery (if any) the day the new one starts and
    create the new one -- never overwrite history.
    ---
    Entrega un accesorio a un centro de gasto y a una persona
    responsable (ambos obligatorios, S121): cierra la entrega abierta
    (si la hay) el día en que empieza la nueva y crea la nueva -- el
    historial nunca se sobrescribe.
    """
    LiftingAccessoryAssignment.objects.filter(
        accessory=accessory, end_date__isnull=True,
    ).update(end_date=start_date)
    return LiftingAccessoryAssignment.objects.create(
        accessory=accessory,
        responsible_person=responsible_person,
        machine=machine,
        start_date=start_date,
        notes=notes,
    )


def return_accessory(accessory, end_date):
    """
    Close the open delivery of an accessory (returned to the store).
    Returns how many deliveries were closed (0 or 1).
    ---
    Cierra la entrega abierta de un accesorio (devuelto al almacén).
    Devuelve cuántas entregas se cerraron (0 o 1).
    """
    return LiftingAccessoryAssignment.objects.filter(
        accessory=accessory, end_date__isnull=True,
    ).update(end_date=end_date)


def register_review(accessory, review_date, explicit_expiry_date=None,
                    review_file=None):
    """
    Record one periodic review of one accessory, with its document
    uploaded if given.
    ---
    Registra una revisión periódica de un accesorio y, si se da, sube
    su documento ya tipado REVISION_ESLINGAS y enlazado al accesorio.
    La vigencia la calcula el propio modelo (revisión + 12 meses, salvo
    caducidad indicada, que prevalece -- decisión 5).
    """
    source_entry = None
    if review_file is not None:
        source_entry = _upload_document(
            accessory, review_file, REVIEW_TYPE_CODE, REVIEWS_ROOT,
            "REVISION", stamp_date=review_date,
        )
    return LiftingAccessoryReview.objects.create(
        accessory=accessory,
        review_date=review_date,
        explicit_expiry_date=explicit_expiry_date,
        source_entry=source_entry,
    )


def set_active(accessories, is_active):
    """
    Retire or reactivate accessories; retiring also closes their open
    delivery on today's date. Returns how many were changed.
    ---
    Retira del servicio o reactiva accesorios; retirar cierra además su
    entrega abierta con fecha de hoy (un accesorio retirado no sigue a
    cargo de nadie). Devuelve cuántos cambiaron.
    """
    changed = 0
    with transaction.atomic():
        for accessory in accessories:
            if accessory.is_active == is_active:
                continue
            accessory.is_active = is_active
            accessory.save(update_fields=["is_active", "updated_at"])
            if not is_active:
                return_accessory(accessory, date.today())
            changed += 1
    return changed


def _live_documents():
    """
    Live files of the documentation bucket.
    ---
    Archivos vivos del cubo de documentación.
    """
    return DocumentIndexEntry.objects.filter(
        bucket=BUCKET,
        entry_kind=DocumentIndexEntry.KIND_FILE,
        deleted_at__isnull=True,
        purged_at__isnull=True,
    )


def _accessory_ct():
    """
    ContentType of LiftingAccessory.
    ---
    ContentType de LiftingAccessory.
    """
    return ContentType.objects.get_for_model(LiftingAccessory)


def certificates_of(accessories):
    """
    {accessory pk: [certificate entries]} for the given accessories, in
    one query.
    ---
    {pk del accesorio: [certificados]} de los accesorios dados, en una
    sola consulta.
    """
    ids = [accessory.pk for accessory in accessories]
    result = {pk: [] for pk in ids}
    if not ids:
        return result
    for entry in _live_documents().filter(
        document_type__code=CERTIFICATE_TYPE_CODE,
        domain_content_type=_accessory_ct(),
        domain_object_id__in=ids,
    ).order_by("-id"):
        result[entry.domain_object_id].append(entry)
    return result


def link_certificate(accessory, entry):
    """
    Link an existing certificate to the accessory (generic domain link).
    ---
    Vincula un certificado existente al accesorio (vínculo genérico de
    dominio, como la ficha técnica de un EPI). Solo cambia el vínculo
    -- el archivo real no se toca (4.12).
    """
    entry.domain_content_type = _accessory_ct()
    entry.domain_object_id = accessory.pk
    entry.save(update_fields=[
        "domain_content_type", "domain_object_id", "updated_at",
    ])
    return entry


def _safe_segment(value):
    """
    File-name-safe version of a free text (the accessory identifier).
    ---
    Versión segura para nombre de archivo de un texto libre (el nº del
    accesorio: "15/678" -> "15-678").
    """
    value = re.sub(r"[^0-9A-Za-z]+", "-", value or "").strip("-")
    return value.upper() or "SIN-NUMERO"


def _upload_document(accessory, uploaded_file, type_code, root, label,
                     stamp_date=None):
    """
    Upload a file typed `type_code` into `root/<accessory type>/` and link
    it to the accessory.
    ---
    Sube un archivo tipado `type_code` a `root/<tipo de accesorio>/` y
    lo enlaza al accesorio (vínculo genérico de dominio) -- mismo flujo
    que la ficha técnica de un EPI (EpiTechnicalSheetUploadView). Cada
    subida AÑADE un documento, nunca sustituye a otro (4.12). Lanza
    ValueError si el archivo no es PDF o imagen.
    """
    from spare_parts.gcs_service import upload_bytes

    extension = (
        uploaded_file.name.rsplit(".", 1)[-1].lower()
        if "." in uploaded_file.name else ""
    )
    if extension not in _CONTENT_TYPES:
        raise ValueError("Debe ser un PDF o una imagen.")
    document_type = DocumentTypeCatalog.objects.get(code=type_code)
    data = uploaded_file.read()
    stamp = timezone.now().strftime("%Y%m%d%H%M%S")
    if stamp_date is not None:
        stamp = "%s_%s" % (stamp_date.strftime("%Y%m%d"), stamp)
    filename = "%s_%s_%s_%s.%s" % (
        accessory.accessory_type.code, _safe_segment(accessory.identifier),
        label, stamp, extension,
    )
    target_folder = "%s/%s" % (root, accessory.accessory_type.code)
    ensure_folder_chain(BUCKET, target_folder)
    blob_name = "%s/%s" % (target_folder, filename)
    upload_bytes(
        BUCKET, blob_name, data, content_type=_CONTENT_TYPES[extension],
    )
    return DocumentIndexEntry.objects.create(
        bucket=BUCKET,
        entry_kind=DocumentIndexEntry.KIND_FILE,
        blob_name=blob_name,
        blob_name_hash=path_digest(blob_name),
        parent_path=target_folder,
        parent_path_hash=path_digest(target_folder),
        name=filename,
        size_bytes=len(data),
        content_type=_CONTENT_TYPES[extension],
        document_type=document_type,
        domain_content_type=_accessory_ct(),
        domain_object_id=accessory.pk,
    )


def upload_certificate(accessory, uploaded_file):
    """
    Upload a certificate, typed CERT_ACCESORIO_ELEVACION and linked.
    ---
    Sube un certificado, ya tipado CERT_ACCESORIO_ELEVACION y enlazado
    al accesorio.
    """
    return _upload_document(
        accessory, uploaded_file, CERTIFICATE_TYPE_CODE, CERTIFICATES_ROOT,
        "CERT_ACCESORIO_ELEVACION",
    )


def accessories_for_machine(machine):
    """
    Accessories currently delivered to a machine (open deliveries).
    ---
    Accesorios entregados ahora mismo a una máquina (entregas
    abiertas), para la sección de la ficha de máquina.
    """
    return LiftingAccessory.objects.filter(
        assignments__machine=machine,
        assignments__end_date__isnull=True,
    ).select_related("accessory_type").distinct().order_by(
        "accessory_type__display_order", "identifier",
    )


def accessories_for_person(person, company):
    """
    Accessories of the company currently delivered to a person.
    ---
    Accesorios de la empresa entregados ahora mismo a una persona (es su
    responsable, entrega abierta), para la sección de la ficha de
    personal.
    """
    return LiftingAccessory.objects.filter(
        company=company,
        assignments__responsible_person=person,
        assignments__end_date__isnull=True,
    ).select_related("accessory_type").distinct().order_by(
        "accessory_type__display_order", "identifier",
    )
