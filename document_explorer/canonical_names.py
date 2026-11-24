# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/canonical_names.py
"""
Keep canonical names in step with the dates and types (S156).

Two cases found by Miguel Ángel ("tenemos el tema de los nombres
canónicos que quizás no se ha aplicado aquí"):

1. A person's or machine's document named "..._SINFECHA" that got its
   date later (read, corrected by hand...) keeps the old name: 137 on
   24/11/2026, e.g. H08_SEGURO_SINFECHA.pdf valid until 12/10/2027.
2. The CAE documentation typed by rules (cae_documents) keeps its
   OneDrive name.

A periodic sweep renames both with the existing canonical functions.
Only the virtual name of the index changes; GCS is never touched.

---

Mantiene los nombres canónicos al día con las fechas y los tipos
(S156): los «..._SINFECHA» que ya tienen fecha (personas y máquinas,
con las funciones de renombrado de siempre) y la documentación CAE
tipada ({EMPRESA}_{TIPO}_{FECHA}, cae_documents.rename_cae_entry).
Solo cambia el nombre virtual del índice, nunca GCS.
"""
import logging

from django.contrib.contenttypes.models import ContentType
from django.db import close_old_connections
from django.db.models import Q

from document_explorer.buckets import CAE_ROOT, PRIMARY_BUCKET
from document_explorer.models import DocumentIndexEntry, PersonIdentity
from fleet.models import MachineAsset

logger = logging.getLogger(__name__)

_BATCH = 300
# Forma de un nombre canónico ({...}_{AAAAMMDD|SINFECHA}[_N].ext): los
# que ya la tienen no se vuelven a mirar.
_CANONICAL_SHAPE = r"^[A-Z0-9_]+_([0-9]{8}|SINFECHA)(_[0-9]+)?[.][a-z0-9]+$"


def _live_files():
    return DocumentIndexEntry.objects.filter(
        bucket=PRIMARY_BUCKET, entry_kind=DocumentIndexEntry.KIND_FILE,
        deleted_at__isnull=True, purged_at__isnull=True,
    )


def rename_dated_sinfecha(limit=_BATCH):
    """Rename "_SINFECHA" person/machine files that now have a date.
    ---
    Renombra los documentos de personas y máquinas que se llaman
    «..._SINFECHA» pero ya tienen fecha de caducidad o de emisión.
    Devuelve cuántos ha renombrado.
    """
    from document_explorer.classification_service import (
        apply_machine_canonical_rename, apply_personal_canonical_rename,
    )

    person_ct = ContentType.objects.get_for_model(PersonIdentity)
    machine_ct = ContentType.objects.get_for_model(MachineAsset)
    entries = list(_live_files().filter(
        name__contains="SINFECHA",
        domain_content_type__in=(person_ct, machine_ct),
        document_type__isnull=False,
    ).filter(
        Q(expiry_date__isnull=False) | Q(issue_date__isnull=False),
    ).select_related("document_type")[:limit])
    renamed = 0
    for entry in entries:
        close_old_connections()
        try:
            if entry.domain_content_type_id == person_ct.pk:
                result = apply_personal_canonical_rename(
                    entry, apply_changes=True)
            else:
                asset = MachineAsset.objects.filter(
                    pk=entry.domain_object_id).first()
                if asset is None:
                    continue
                result = apply_machine_canonical_rename(
                    entry, asset, apply_changes=True)
        except Exception:
            logger.exception("# [canonical] No se pudo renombrar %s",
                             entry.pk)
            continue
        renamed += int(bool(result.get("renamed")))
    return renamed


def rename_cae(limit=_BATCH):
    """Canonical names for the typed CAE files not yet renamed.
    ---
    Nombre canónico para los archivos CAE tipados que aún conservan el
    de OneDrive. Devuelve cuántos ha renombrado.
    """
    from document_explorer.cae_documents import (
        _KEEP_NAME_CODES, rename_cae_entry,
    )

    entries = list(_live_files().filter(
        parent_path__startswith=CAE_ROOT + "/",
        document_type__isnull=False,
    ).exclude(document_type__code__in=_KEEP_NAME_CODES).exclude(
        name__regex=_CANONICAL_SHAPE,
    ).select_related("document_type")[:limit])
    renamed = 0
    for entry in entries:
        close_old_connections()
        try:
            renamed += int(rename_cae_entry(entry))
        except Exception:
            logger.exception("# [canonical] No se pudo renombrar %s",
                             entry.pk)
    return renamed
