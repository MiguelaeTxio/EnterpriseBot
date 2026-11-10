# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/empty_folder_service.py
"""
Empty folders of the explorer (H24, S149 invasora).

Miguel Ángel asked for a button in the explorer to clean empty folders
from the panel, instead of running `find_empty_folders` from the
console. Same logic as that command (S72), now shared by both: a folder
is empty when nothing alive hangs from it (`deleted_at`/`purged_at`
null), walking from the deepest folders up, so a chain of folders that
only held other empty folders goes away in one pass. Index-only write,
the object in GCS is never touched (directive 4.12).

---

Carpetas vacías del explorador (H24, S149 invasora).

Miguel Ángel pidió un botón en el explorador para limpiar las carpetas
vacías desde el panel, en vez de lanzar `find_empty_folders` por
consola. Misma lógica que ese comando (S72), ahora compartida por los
dos: una carpeta está vacía cuando no cuelga de ella nada vivo
(`deleted_at`/`purged_at` nulos), recorriendo de las más profundas a
las de arriba, de modo que una cadena de carpetas que solo contenía
otras carpetas vacías desaparece en una sola pasada. Escritura de
índice pura: el objeto en GCS nunca se toca (directriz 4.12).
"""
from django.db import transaction
from django.db.models import Count
from django.utils import timezone

from document_explorer import index_writer
from document_explorer.models import (
    DataOperationLog, DataOperationLogEntry, DocumentIndexEntry,
)


def _subtree(bucket, under_path):
    """Live rows of the bucket strictly inside `under_path` (all at the root)."""
    rows = DocumentIndexEntry.objects.filter(
        bucket=bucket, deleted_at__isnull=True, purged_at__isnull=True,
    )
    if under_path:
        rows = rows.filter(blob_name__startswith=under_path + "/")
    return rows


def find_empty_folders(bucket, under_path=""):
    """
    The empty folders inside `under_path`, deepest first.

    The folder `under_path` itself is never included: it is the one
    being looked at. Two queries for the whole subtree, never a COUNT
    per folder.

    ---

    Las carpetas vacías dentro de `under_path`, las más profundas
    primero. La propia `under_path` nunca se incluye: es la que se está
    mirando. Dos consultas para todo el subárbol, nunca un COUNT por
    carpeta.
    """
    under_path = (under_path or "").strip("/")
    rows = _subtree(bucket, under_path)
    folders = list(
        rows.filter(entry_kind=DocumentIndexEntry.KIND_FOLDER)
        .only("id", "bucket", "blob_name", "name", "parent_path")
    )
    folders.sort(key=lambda f: f.blob_name.count("/"), reverse=True)
    live_children = dict(
        rows.values("parent_path").annotate(n=Count("pk"))
        .values_list("parent_path", "n")
    )
    empty = []
    for folder in folders:
        if live_children.get(folder.blob_name, 0) > 0:
            continue
        empty.append(folder)
        # Ya no cuenta como hijo vivo de su propio padre.
        live_children[folder.parent_path] = max(
            0, live_children.get(folder.parent_path, 0) - 1,
        )
    return empty


def trash_empty_folders(bucket, under_path, company_user):
    """
    Send the empty folders inside `under_path` to `company_user`'s trash.

    Same as deleting them by hand: they go to the acting user's own
    trash (restorable from there) and the operation is logged like any
    bulk trash. Returns the `DataOperationLog`, or None when there was
    nothing to clean.

    ---

    Manda a la papelera de `company_user` las carpetas vacías de
    `under_path`. Igual que borrarlas a mano: van a la papelera del
    propio usuario (restaurables desde allí) y la operación queda
    registrada como cualquier borrado en bloque. Devuelve el
    `DataOperationLog`, o None si no había nada que limpiar.
    """
    under_path = (under_path or "").strip("/")
    empty = find_empty_folders(bucket, under_path)
    if not empty:
        return None
    now = timezone.now()
    with transaction.atomic():
        log = DataOperationLog.objects.create(
            operation_type=DataOperationLog.OPERATION_TRASH,
            performed_by=company_user,
            bucket=bucket,
            path_prefix=under_path,
            status=DataOperationLog.STATUS_RUNNING,
        )
        DocumentIndexEntry.objects.filter(
            pk__in=[f.pk for f in empty],
        ).update(deleted_at=now, deleted_by=company_user)
        DataOperationLogEntry.objects.bulk_create([
            DataOperationLogEntry(
                log=log,
                group_number=number,
                action=DataOperationLogEntry.ACTION_TRASHED,
                index_entry=folder,
                bucket=folder.bucket,
                blob_name=folder.blob_name,
                name=folder.name,
                parent_path=folder.parent_path,
                detail="Carpeta vacía movida a la papelera de %s."
                % company_user,
            )
            for number, folder in enumerate(empty, start=1)
        ])
        log.groups_count = len(empty)
        log.kept_count = len(empty)
        log.status = DataOperationLog.STATUS_COMPLETED
        log.save(update_fields=["groups_count", "kept_count", "status"])
    # Las carpetas que quedan pierden esos hijos de su contador.
    parents = {f.parent_path for f in empty}
    index_writer.recount_children(bucket, folder_paths=list(parents))
    return log
