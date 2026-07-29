# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/index_writer.py
"""
Writing rows into the document index (H29).

Extracted so the full seeding command and the per-folder refresh share
one implementation instead of two that drift apart. Everything here
writes in batches: one query to read the current state of a bucket,
partition in memory, then bulk_create/bulk_update. Row-at-a-time
writing over tens of thousands of objects is not an option.

The one invariant every function preserves: a row already sitting in
someone's trash is never touched. The bucket does not get to overrule
a deletion made from the panel.

---

Escritura de filas en el índice documental (H29).

Extraído para que el comando de sembrado completo y el de refresco por
carpeta compartan una implementación en vez de dos que acaben
divergiendo. Todo lo de aquí escribe por lotes: una consulta para leer
el estado actual de un cubo, reparto en memoria, y luego
bulk_create/bulk_update. Escribir fila a fila sobre decenas de miles de
objetos no es una opción.

El invariante que preservan todas las funciones: una fila que ya está
en la papelera de alguien no se toca nunca. El cubo no puede revocar un
borrado hecho desde el panel.
"""
from django.apps import apps
from django.contrib.contenttypes.models import ContentType
from django.db.models import Count

from document_explorer.buckets import DOMAIN_MODEL_BY_BUCKET
from document_explorer.models import DocumentIndexEntry, path_digest

BATCH_SIZE = 1000


def split_path(blob_name):
    """
    Split a blob name into (parent_path, name).

    ---

    Parte un nombre de blob en (carpeta_contenedora, nombre).
    """
    if "/" not in blob_name:
        return "", blob_name
    parent, _, name = blob_name.rpartition("/")
    return parent, name


def ancestors_of(parent_path):
    """
    Return every ancestor folder path, root first.

    ---

    Devuelve todas las carpetas antecesoras, de la raíz hacia dentro.
    """
    if not parent_path:
        return []
    parts = parent_path.split("/")
    return ["/".join(parts[:i + 1]) for i in range(len(parts))]


def row_defaults():
    """
    Uniform field set, required by bulk_update.

    ---

    Conjunto uniforme de campos, que bulk_update exige.
    """
    return {
        "entry_kind": DocumentIndexEntry.KIND_FILE,
        "blob_name": "",
        "parent_path": "",
        "parent_path_hash": "",
        "name": "",
        "size_bytes": None,
        "content_type": "",
        "crc32c": "",
        "md5_hash": "",
        "generation": None,
        "gcs_updated_at": None,
        "total_size_bytes": 0,
    }


def folder_row(path, total_size_bytes=0):
    """
    Build the row of a folder.

    ---

    Construye la fila de una carpeta.
    """
    parent_path, name = split_path(path)
    row = row_defaults()
    row.update({
        "entry_kind": DocumentIndexEntry.KIND_FOLDER,
        "blob_name": path,
        "parent_path": parent_path,
        "parent_path_hash": path_digest(parent_path),
        "name": name,
        "total_size_bytes": total_size_bytes,
    })
    return row


def file_row(blob):
    """
    Build the row of an object, from the metadata the listing returns.

    Verified in production (S037): size, crc32c, md5 and generation
    come back populated for every object in all five buckets, so no
    per-object read is needed to fill this in.

    ---

    Construye la fila de un objeto con los metadatos que devuelve el
    listado.

    Verificado en producción (S037): tamaño, crc32c, md5 y generación
    llegan rellenos en todos los objetos de los cinco cubos, así que no
    hace falta leer objeto por objeto para completar esto.
    """
    parent_path, name = split_path(blob.name)
    row = row_defaults()
    row.update({
        "entry_kind": DocumentIndexEntry.KIND_FILE,
        "blob_name": blob.name,
        "parent_path": parent_path,
        "parent_path_hash": path_digest(parent_path),
        "name": name,
        "size_bytes": blob.size,
        "content_type": blob.content_type or "",
        "crc32c": blob.crc32c or "",
        "md5_hash": blob.md5_hash or "",
        "generation": blob.generation,
        "gcs_updated_at": blob.updated,
    })
    return row


def accumulate_folder_sizes(file_rows, folder_paths):
    """
    Add each file's size into every ancestor folder, in one pass.

    Asking the database for a recursive sum per folder would be exactly
    the kind of nested query the index exists to avoid.

    ---

    Acumula el tamaño de cada archivo en todas sus carpetas
    antecesoras, en una sola pasada.

    Pedir a la base de datos una suma recursiva por carpeta sería justo
    el tipo de consulta anidada que el índice existe para evitar.
    """
    sizes = {path: 0 for path in folder_paths}
    for row in file_rows:
        size = row["size_bytes"] or 0
        for ancestor in ancestors_of(row["parent_path"]):
            if ancestor in sizes:
                sizes[ancestor] += size
    return sizes


def persist_rows(bucket_name, rows, scope_hashes=None):
    """
    Create or update the given rows. Returns (created, updated).

    `scope_hashes` limits the single read query to a known set of blob
    hashes -- used by the per-folder refresh so it does not have to
    load the whole bucket to update one folder.

    ---

    Crea o actualiza las filas dadas. Devuelve (creadas, actualizadas).

    `scope_hashes` acota la única consulta de lectura a un conjunto
    conocido de resúmenes -- lo usa el refresco por carpeta para no
    tener que cargar el cubo entero por actualizar una sola carpeta.
    """
    query = DocumentIndexEntry.objects.filter(
        bucket=bucket_name, purged_at__isnull=True,
    )
    if scope_hashes is not None:
        query = query.filter(blob_name_hash__in=list(scope_hashes))

    existing = {
        digest: (pk, deleted_at)
        for digest, pk, deleted_at in query.values_list(
            "blob_name_hash", "id", "deleted_at",
        )
    }

    fields = sorted(row_defaults().keys())
    to_create = []
    to_update = []

    for row in rows:
        digest = path_digest(row["blob_name"])
        found = existing.get(digest)
        if found is None:
            to_create.append(DocumentIndexEntry(
                bucket=bucket_name, blob_name_hash=digest, **row
            ))
        elif found[1] is None:
            to_update.append(DocumentIndexEntry(
                id=found[0],
                bucket=bucket_name,
                blob_name_hash=digest,
                **row
            ))

    DocumentIndexEntry.objects.bulk_create(
        to_create, batch_size=BATCH_SIZE,
    )
    if to_update:
        DocumentIndexEntry.objects.bulk_update(
            to_update, fields, batch_size=BATCH_SIZE,
        )
    return len(to_create), len(to_update)


def recount_children(bucket_name, folder_paths=None):
    """
    Refresh the precomputed child counter with two queries.

    Never one COUNT per folder: that is the N+1 this field exists to
    prevent.

    ---

    Refresca el contador precalculado de hijos con dos consultas.

    Nunca un COUNT por carpeta: ese es el N+1 que este campo existe
    para evitar.
    """
    counts = dict(
        DocumentIndexEntry.objects
        .filter(
            bucket=bucket_name,
            deleted_at__isnull=True,
            purged_at__isnull=True,
        )
        .values_list("parent_path_hash")
        .annotate(total=Count("id"))
    )

    folders = DocumentIndexEntry.objects.filter(
        bucket=bucket_name,
        entry_kind=DocumentIndexEntry.KIND_FOLDER,
        deleted_at__isnull=True,
        purged_at__isnull=True,
    )
    if folder_paths is not None:
        folders = folders.filter(
            blob_name_hash__in=[path_digest(p) for p in folder_paths],
        )

    folders = list(folders)
    for folder in folders:
        folder.child_count = counts.get(
            path_digest(folder.blob_name), 0,
        )
    if folders:
        DocumentIndexEntry.objects.bulk_update(
            folders, ["child_count"], batch_size=BATCH_SIZE,
        )
    return len(folders)


def link_domain_objects(bucket_name):
    """
    Point each entry at its business row, when the bucket has one.

    Returns (linked_count, model_name), or (0, None) for buckets with
    no domain model -- the historical bucket, whose objects have none.
    That absence is the very reason the index exists.

    ---

    Apunta cada entrada a su fila de negocio, si el cubo tiene modelo.

    Devuelve (vinculadas, nombre_modelo), o (0, None) en los cubos sin
    modelo de dominio -- el histórico, cuyos objetos no tienen ninguno.
    Esa ausencia es justamente el motivo de que el índice exista.
    """
    mapping = DOMAIN_MODEL_BY_BUCKET.get(bucket_name)
    if mapping is None:
        return 0, None

    app_label, model_name, field = mapping
    model = apps.get_model(app_label, model_name)
    content_type = ContentType.objects.get_for_model(model)

    by_blob_name = dict(
        model.objects.exclude(**{field: ""}).values_list(field, "id")
    )
    if not by_blob_name:
        return 0, model.__name__

    pending = []
    entries = DocumentIndexEntry.objects.filter(
        bucket=bucket_name,
        entry_kind=DocumentIndexEntry.KIND_FILE,
        domain_object_id__isnull=True,
    )
    for entry in entries:
        object_id = by_blob_name.get(entry.blob_name)
        if object_id is None:
            continue
        entry.domain_content_type = content_type
        entry.domain_object_id = object_id
        pending.append(entry)

    if pending:
        DocumentIndexEntry.objects.bulk_update(
            pending,
            ["domain_content_type", "domain_object_id"],
            batch_size=BATCH_SIZE,
        )
    return len(pending), model.__name__
