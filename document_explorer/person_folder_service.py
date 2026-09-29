# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/person_folder_service.py
"""
H30 (S125). Moves (virtually) all of a person's documentation to the
folder their current state asks for, ACTIVOS/{EMPRESA}/... or
INACTIVOS/... (S99 rule, `naming_service.build_person_category_root`).

---

H30 (S125). Mueve (virtualmente, solo índice) toda la documentación de
una persona a la carpeta que le corresponde según su estado actual:
ACTIVOS/{EMPRESA}/... o INACTIVOS/... (regla de S99,
`naming_service.build_person_category_root`). Sale de la reactivación
de S117 para compartirla con el punto 4 de S125: un trabajador que se
activa por contrato/alta o cambia de empresa pasa a
ACTIVOS/{EMPRESA}/ sin que nadie mueva nada a mano.
"""
import logging

from django.contrib.contenttypes.models import ContentType
from django.db import transaction

from document_explorer import naming_service
from document_explorer.models import DocumentIndexEntry, PersonIdentity
from document_explorer.move_service import move_entries

logger = logging.getLogger(__name__)

BUCKET = "cgs_grupo_alvarez"


def expected_base_folder(person, is_active=None):
    """
    Folder the person should live in (without collision suffix).

    ---

    Carpeta donde debería vivir la persona (sin sufijo de colisión).
    `is_active` permite calcularla para un estado que todavía no se ha
    guardado (baja, reactivación).
    """
    active = person.is_active_employee if is_active is None else is_active
    return "%s/%s" % (
        naming_service.build_person_category_root(
            person.first_surname, person.second_surname,
            person.employer_company, active,
        ),
        naming_service.build_person_folder_name(
            person.first_surname, person.second_surname, person.given_name,
        ),
    )


def is_in_expected_folder(person):
    """
    Whether folder_path already is the expected one (or its _N twin).

    ---

    Si `folder_path` ya es la carpeta esperada (o su gemela _N por
    colisión con otra persona del mismo nombre).
    """
    base = expected_base_folder(person)
    current = person.folder_path or ""
    if current == base:
        return True
    prefix = base + "_"
    return current.startswith(prefix) and current[len(prefix):].isdigit()


def free_folder_for(person, base_folder):
    """
    The base folder, or base_N if another person's files are there.

    ---

    La carpeta base o, si ya hay archivos de otra persona en ella,
    base_2, base_3... (misma regla que la reactivación de S117).
    """
    person_ct = ContentType.objects.get_for_model(PersonIdentity)
    folder, ordinal = base_folder, 2
    while DocumentIndexEntry.objects.filter(
        bucket=BUCKET, parent_path=folder,
        entry_kind=DocumentIndexEntry.KIND_FILE,
        deleted_at__isnull=True, purged_at__isnull=True,
    ).exclude(
        domain_content_type=person_ct, domain_object_id=person.pk,
    ).exists():
        folder = "%s_%d" % (base_folder, ordinal)
        ordinal += 1
    return folder


def move_person_documents(person, new_folder_path):
    """
    Move every linked file of the person and save folder_path.

    Returns the number of files moved. The caller saves any other
    field it changed in the same transaction.

    ---

    Mueve todos los archivos vinculados a la persona y guarda
    `folder_path`. Devuelve cuántos archivos se han movido.
    """
    person_ct = ContentType.objects.get_for_model(PersonIdentity)
    entries = list(DocumentIndexEntry.objects.filter(
        bucket=BUCKET, domain_content_type=person_ct,
        domain_object_id=person.pk,
        entry_kind=DocumentIndexEntry.KIND_FILE,
        deleted_at__isnull=True, purged_at__isnull=True,
    ))
    moved = len(move_entries(entries, new_folder_path)) if entries else 0
    person.folder_path = new_folder_path
    person.save(update_fields=["folder_path", "updated_at"])
    return moved


def relocate_if_needed(person):
    """
    Move the person to the expected folder when they are not there.

    ---

    Si la persona no está en su carpeta esperada (se ha activado, ha
    cambiado de empresa), mueve su documentación allí. Devuelve
    (movida: bool, carpeta, archivos movidos).
    """
    if is_in_expected_folder(person):
        return False, person.folder_path, 0
    folder = free_folder_for(person, expected_base_folder(person))
    with transaction.atomic():
        moved = move_person_documents(person, folder)
    logger.info(
        "# [PERSON-FOLDER] PersonIdentity pk=%s -> %s (%d archivo(s)).",
        person.pk, folder, moved,
    )
    return True, folder, moved
