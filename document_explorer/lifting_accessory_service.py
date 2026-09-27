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

from datetime import date

from django.db import transaction
from django.db.models import Q

from document_explorer.models import (
    DocumentIndexEntry,
    LiftingAccessory,
    LiftingAccessoryAssignment,
    LiftingAccessoryReview,
)

BUCKET = "cgs_grupo_alvarez"

# Tipos documentales que se ofrecen al vincular un certificado o una
# revisión: los certificados del fabricante (y las declaraciones CE de
# cables y eslingas) y las revisiones de eslingas ya catalogadas.
CERTIFICATE_TYPE_CODES = ("CERT_ACCESORIO_ELEVACION", "CE")
REVIEW_TYPE_CODES = ("REVISION_ESLINGAS", "CERT_ACCESORIO_ELEVACION")


@transaction.atomic
def assign_accessory(accessory, responsible_person, start_date,
                     machine=None, notes=""):
    """
    Deliver an accessory: close the open delivery (if any) the day the
    new one starts and create the new one -- never overwrite history.
    ---
    Entrega un accesorio: cierra la entrega abierta (si la hay) el día
    en que empieza la nueva y crea la nueva -- el historial nunca se
    sobrescribe (decisión 3 de Miguel Ángel, S121).
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
                    source_entry=None):
    """
    Record one periodic review of one accessory.
    ---
    Registra una revisión periódica de un accesorio. La vigencia la
    calcula el propio modelo (revisión + 12 meses, salvo caducidad
    indicada, que prevalece -- decisión 5).
    """
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


def certificate_candidates(current_entry_id=None):
    """
    Documents offered as manufacturer certificate: certificate types
    not yet linked to another accessory, plus the current one.
    ---
    Documentos que se ofrecen como certificado del fabricante: de los
    tipos de certificado, los que no están vinculados ya a otro
    accesorio, más el vinculado ahora (para poder conservarlo al
    editar).
    """
    qs = _live_documents().filter(
        document_type__code__in=CERTIFICATE_TYPE_CODES,
    ).filter(
        Q(lifting_accessories__isnull=True) | Q(pk=current_entry_id),
    )
    return qs.select_related("document_type").distinct().order_by(
        "parent_path", "name",
    )


def review_candidates():
    """
    Documents offered as the document of a review.
    ---
    Documentos que se ofrecen como documento de una revisión.
    """
    return _live_documents().filter(
        document_type__code__in=REVIEW_TYPE_CODES,
    ).select_related("document_type").order_by("parent_path", "name")


def resolve_document(entry_id, allowed_codes):
    """
    Return the live document with that id and one of the allowed type
    codes, or None -- a forged id never links an arbitrary document.
    ---
    Devuelve el documento vivo con ese id y uno de los tipos
    permitidos, o None -- un id manipulado nunca vincula un documento
    cualquiera.
    """
    if not entry_id:
        return None
    try:
        entry_id = int(entry_id)
    except (TypeError, ValueError):
        return None
    return _live_documents().filter(
        pk=entry_id, document_type__code__in=allowed_codes,
    ).first()


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
