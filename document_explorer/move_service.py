# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/move_service.py
"""
File move for the explorer (H29, S039): change a file's folder while
keeping it in the same bucket.

Decided explicitly by Miguel Angel: scope is FILES ONLY -- moving a
folder recursively is a different, much bigger operation (could mean
thousands of objects for something like `DOC. MAQUINAS`), deferred on
purpose. The destination folder can be an existing one or a brand new
path typed by hand; if it does not exist yet as an indexed folder,
moving into it creates the whole missing ancestor chain
(`index_writer.ensure_folder_chain`), the same way a fresh upload
would. Never crosses buckets -- only changes `blob_name`/`parent_path`
within the bucket the file already lives in.

This is the first operation in the explorer that writes to Google
Cloud Storage rather than only reading it or flipping the trash flag
(H29's original design keeps GCS contact to exactly two moments:
opening a document, and an administrator emptying a trash -- a move is
a deliberate, explicit third one, added here on purpose, not a
loosening of that rule for anything else).

---

Movimiento de archivos para el explorador (H29, S039): cambia la
carpeta de un archivo mantiéndolo en el mismo cubo.

Decidido explícitamente por Miguel Ángel: el alcance es SOLO ARCHIVOS
-- mover una carpeta de forma recursiva es una operación distinta y
mucho mayor (podrían ser miles de objetos en algo como
`DOC. MAQUINAS`), aplazada a propósito. La carpeta destino puede ser
una ya existente o una ruta nueva escrita a mano; si todavía no existe
como carpeta indexada, mover hacia ella crea toda la cadena de
antecesores que falte (`index_writer.ensure_folder_chain`), igual que
haría una subida nueva. Nunca cruza de cubo -- solo cambia
`blob_name`/`parent_path` dentro del cubo en el que ya vive el
archivo.

Es la primera operación del explorador que escribe de verdad en Google
Cloud Storage en vez de solo leerlo o cambiar la bandera de papelera
(el diseño original de H29 acota el contacto con GCS a exactamente dos
momentos: abrir un documento, y que un administrador vacíe una
papelera -- un movimiento es un tercero deliberado y explícito,
añadido aquí a propósito, no un relajamiento de esa regla para
cualquier otra cosa).
"""
from django.db import transaction
from django.db.models import F

from document_explorer.index_writer import ancestors_of, ensure_folder_chain
from document_explorer.models import DocumentIndexEntry, path_digest
from spare_parts.gcs_service import move_file as gcs_move_file


class MoveConflict(Exception):
    """
    A live file with the same name already exists at the destination.

    ---

    Ya existe un archivo vivo con el mismo nombre en el destino.
    """


def move_entry(entry, destination_folder):
    """
    Move `entry` (a live FILE `DocumentIndexEntry`) into
    `destination_folder` (a folder path string, `""` for the bucket
    root). No-op if the destination is where the file already lives.
    Raises `MoveConflict` without touching GCS if a live file with the
    same name already sits at the destination.

    ---

    Mueve `entry` (un `DocumentIndexEntry` de tipo FILE vivo) a
    `destination_folder` (una ruta de carpeta, `""` para la raíz del
    cubo). No hace nada si el destino es donde ya vive el archivo.
    Lanza `MoveConflict` sin tocar GCS si ya hay un archivo vivo con el
    mismo nombre en el destino.
    """
    destination_folder = destination_folder.strip("/")
    if destination_folder == entry.parent_path:
        return

    new_blob_name = (
        "%s/%s" % (destination_folder, entry.name)
        if destination_folder else entry.name
    )
    new_blob_hash = path_digest(new_blob_name)

    conflict = DocumentIndexEntry.objects.filter(
        bucket=entry.bucket, blob_name_hash=new_blob_hash,
        deleted_at__isnull=True, purged_at__isnull=True,
    ).exclude(pk=entry.pk).exists()
    if conflict:
        raise MoveConflict(
            "Ya existe un archivo con ese nombre en el destino."
        )

    ensure_folder_chain(entry.bucket, destination_folder)

    old_blob_name = entry.blob_name
    old_parent_path = entry.parent_path
    size = entry.size_bytes or 0

    # Único punto de contacto con GCS de todo el movimiento -- si esto
    # falla, nada de lo de abajo se ejecuta y el índice queda como
    # estaba, sin inconsistencia.
    gcs_move_file(entry.bucket, old_blob_name, new_blob_name)

    with transaction.atomic():
        entry.blob_name = new_blob_name
        entry.blob_name_hash = new_blob_hash
        entry.parent_path = destination_folder
        entry.parent_path_hash = path_digest(destination_folder)
        entry.save(update_fields=[
            "blob_name", "blob_name_hash",
            "parent_path", "parent_path_hash",
        ])
        _adjust_total_size(entry.bucket, old_parent_path, -size)
        _adjust_total_size(entry.bucket, destination_folder, size)
        _adjust_child_count(entry.bucket, old_parent_path, -1)
        _adjust_child_count(entry.bucket, destination_folder, 1)


def _adjust_total_size(bucket, folder_path, delta):
    """
    Propagate a size delta up every ancestor folder (including
    `folder_path` itself) -- `total_size_bytes` is recursive, per
    `DocumentIndexEntry`'s own docstring, so both the old and the new
    location's whole chain need correcting, not just the immediate
    parent.

    ---

    Propaga una diferencia de tamaño por todas las carpetas
    antecesoras (incluida la propia `folder_path`) -- `total_size_
    bytes` es recursivo, según el propio docstring de
    `DocumentIndexEntry`, así que hay que corregir toda la cadena
    tanto de la ubicación antigua como de la nueva, no solo el padre
    inmediato.
    """
    if not delta:
        return
    hashes = [path_digest(path) for path in ancestors_of(folder_path)]
    if not hashes:
        return
    DocumentIndexEntry.objects.filter(
        bucket=bucket, blob_name_hash__in=hashes,
        deleted_at__isnull=True, purged_at__isnull=True,
    ).update(total_size_bytes=F("total_size_bytes") + delta)


def _adjust_child_count(bucket, folder_path, delta):
    """
    `child_count` only counts DIRECT children, so only the immediate
    parent folder (old or new) needs correcting -- never the whole
    ancestor chain, unlike `total_size_bytes`.

    ---

    `child_count` solo cuenta hijos DIRECTOS, así que solo hay que
    corregir la carpeta padre inmediata (antigua o nueva) -- nunca
    toda la cadena de antecesores, a diferencia de `total_size_bytes`.
    """
    if not folder_path:
        return
    DocumentIndexEntry.objects.filter(
        bucket=bucket, blob_name_hash=path_digest(folder_path),
        deleted_at__isnull=True, purged_at__isnull=True,
    ).update(child_count=F("child_count") + delta)
