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
from django.db.models import Count, F

from document_explorer.buckets import DOMAIN_MODEL_BY_BUCKET
from document_explorer.models import DocumentIndexEntry, path_digest

BATCH_SIZE = 1000


def _adjust_total_size(bucket, folder_path, delta):
    """
    Propagate a size delta up every ancestor folder (including
    `folder_path` itself) -- `total_size_bytes` is recursive, per
    `DocumentIndexEntry`'s own docstring, so both the old and the new
    location's whole chain need correcting, not just the immediate
    parent. Lives here (not in `move_service.py`, which imports it)
    because `persist_rows()` below needs it too, and `move_service.py`
    already imports `ancestors_of`/`ensure_folder_chain` FROM this
    module -- defining it there and importing it back here would be a
    circular import.

    ---

    Propaga una diferencia de tamaño por todas las carpetas
    antecesoras (incluida la propia `folder_path`) -- `total_size_
    bytes` es recursivo, según el propio docstring de
    `DocumentIndexEntry`, así que hay que corregir toda la cadena
    tanto de la ubicación antigua como de la nueva, no solo el padre
    inmediato. Vive aquí (no en `move_service.py`, que la importa)
    porque `persist_rows()` de más abajo también la necesita, y
    `move_service.py` ya importa `ancestors_of`/`ensure_folder_chain`
    DESDE este módulo -- definirla allí e importarla de vuelta aquí
    sería un import circular.
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


def ensure_folder_chain(bucket_name, folder_path):
    """
    Make sure every ancestor of `folder_path`, and the folder itself,
    exists as a live FOLDER row -- so navigating into a brand new
    destination created by a move (H29, S039) works immediately,
    without waiting for a reseed. Never touches an already-existing
    row (its real `total_size_bytes`/`child_count` are left alone,
    corrected instead by the caller's own size-propagation step);
    only inserts the missing links of the chain, with
    `total_size_bytes=0` as a fresh starting point.

    ---

    Asegura que cada antecesor de `folder_path`, y la propia carpeta,
    existen como fila FOLDER viva -- para que navegar a un destino
    nuevo creado por un movimiento (H29, S039) funcione de inmediato,
    sin esperar a un resembrado. Nunca toca una fila ya existente (su
    `total_size_bytes`/`child_count` reales se dejan como están,
    corregidos en cambio por el propio paso de propagación de tamaño
    de quien llama); solo inserta los eslabones que faltan de la
    cadena, con `total_size_bytes=0` como punto de partida.
    """
    if not folder_path:
        return
    chain = ancestors_of(folder_path)
    hashes = [path_digest(path) for path in chain]
    existing = set(
        DocumentIndexEntry.objects.filter(
            bucket=bucket_name, blob_name_hash__in=hashes,
            deleted_at__isnull=True, purged_at__isnull=True,
        ).values_list("blob_name_hash", flat=True)
    )
    missing = [
        path for path, digest in zip(chain, hashes)
        if digest not in existing
    ]
    if not missing:
        return
    DocumentIndexEntry.objects.bulk_create([
        DocumentIndexEntry(
            bucket=bucket_name,
            blob_name_hash=path_digest(path),
            **folder_row(path),
        )
        for path in missing
    ])


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


def persist_rows(bucket_name, rows, scope_hashes=None, skip_fields=()):
    """
    Create or update the given rows. Returns (created, updated).

    Also propagates the real `size_bytes` of any brand-new FILE row
    up its ancestor folders' `total_size_bytes` (S042, real incident
    -- see `_adjust_total_size()`'s own note) -- never for updated/
    already-existing rows, only genuinely new ones, so this never
    double-counts a file this function has already seen before.

    `scope_hashes` limits the single read query to a known set of blob
    hashes -- used by the per-folder refresh so it does not have to
    load the whole bucket to update one folder.

    `skip_fields` excludes columns from the UPDATE. `bulk_update` only
    writes the fields it is told to, so a field left out here keeps
    whatever value the row already had in the database -- the row
    passed in still carries a default for it (0, ""...), but that
    default is never sent. This exists because `total_size_bytes` is
    only ever known accurately after a full recursive sweep: a
    single-folder refresh sees direct children, not the whole subtree,
    so writing 0 there would silently erase a real total computed
    earlier. Bug found in production (S037): refreshing "DOC. MAQUINAS"
    zeroed out its 1.7 TB total and that of its 64 direct subfolders.

    `parent_path`/`parent_path_hash`/`name` are ALWAYS excluded from
    the UPDATE, regardless of `skip_fields` -- never a caller's
    choice. Real bug found in production (S041): `file_row()` derives
    these from `blob_name`, which never changes (H29 3.1/3.19,
    write-once at indexing); for a brand-new row that is exactly
    right, but for a row that already existed, blindly re-syncing
    them silently undoes ANY virtual relocation or rename done since
    -- `move_entry`, `move_entries`, `apply_quarantine_classification`,
    `apply_classification`, all of it -- because every one of them is
    a pure `parent_path`/`name` write that never touches `blob_name`.
    Confirmed against a real quarantine entry that had been
    `ACTION_RELOCATED` correctly 29 times across 26h and was still
    found sitting back in `_CUARENTENA/` every time
    `refresh_quarantine_index_task` (hourly) ran in between. These
    three fields are the one thing about a file that this function
    must never consider "real bucket truth" for an existing row --
    only at creation time do they mean anything derived from
    `blob_name`.

    ---

    Crea o actualiza las filas dadas. Devuelve (creadas, actualizadas).

    También propaga el `size_bytes` real de cualquier fila FILE
    genuinamente nueva hacia el `total_size_bytes` de sus carpetas
    antecesoras (S042, incidente real -- ver la propia nota de
    `_adjust_total_size()`) -- nunca para filas actualizadas/ya
    existentes, solo las genuinamente nuevas, así que esto nunca
    cuenta dos veces un archivo que esta función ya había visto antes.

    `scope_hashes` acota la única consulta de lectura a un conjunto
    conocido de resúmenes -- lo usa el refresco por carpeta para no
    tener que cargar el cubo entero por actualizar una sola carpeta.

    `skip_fields` excluye columnas de la actualización. `bulk_update`
    solo escribe los campos que se le indican, así que uno omitido
    aquí conserva el valor que ya tuviera la fila en base de datos --
    la fila pasada sigue llevando un valor por defecto para él (0,
    ""...), pero ese valor nunca se envía. Existe porque
    `total_size_bytes` solo se conoce con precisión tras un barrido
    recursivo completo: el refresco de una sola carpeta ve los hijos
    directos, no todo el subárbol, así que escribir 0 ahí borraría en
    silencio un total real calculado antes. Fallo hallado en producción
    (S037): refrescar "DOC. MAQUINAS" puso a cero su total de 1,7 TB y
    el de sus 64 subcarpetas directas.

    `parent_path`/`parent_path_hash`/`name` quedan SIEMPRE excluidos
    de la actualización, sin importar `skip_fields` -- nunca es
    elección de quien llama. Fallo real hallado en producción (S041):
    `file_row()` los deriva de `blob_name`, que nunca cambia (H29
    3.1/3.19, escritura única en la indexación); para una fila nueva
    eso es exactamente correcto, pero para una fila que ya existía,
    resincronizarlos a ciegas deshace en silencio cualquier
    reubicación o renombrado virtual hecho después -- `move_entry`,
    `move_entries`, `apply_quarantine_classification`,
    `apply_classification`, todo -- porque cada una de esas
    operaciones es una escritura pura de `parent_path`/`name` que
    nunca toca `blob_name`. Confirmado contra una entrada real de
    cuarentena que había quedado `ACTION_RELOCATED` correctamente 29
    veces en 26h y que `refresh_quarantine_index_task` (cada hora)
    seguía encontrando de vuelta en `_CUARENTENA/` cada vez que corría
    entre medias. Estos tres campos son lo único de un archivo que
    esta función nunca debe tratar como "verdad del cubo real" para
    una fila que ya existía -- solo al crearla tiene sentido derivarlos
    de `blob_name`.
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

    never_resynced = ("parent_path", "parent_path_hash", "name")
    fields = [
        f for f in sorted(row_defaults().keys())
        if f not in skip_fields and f not in never_resynced
    ]
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

    # Causa raíz real de la deriva negativa de total_size_bytes en
    # _CUARENTENA (S042, confirmada con datos reales antes de escribir
    # esto, nunca supuesta): un archivo NUEVO descubierto por este
    # camino (refresh_quarantine_index_task, la red de seguridad
    # horaria del webhook fallido) entraba aquí con su propio
    # size_bytes correcto, pero SIN sumar nunca ese tamaño a sus
    # carpetas antecesoras -- solo move_entry() sabe propagar tamaño.
    # Cuando ese mismo archivo se reubicaba de verdad más tarde
    # (move_entry SÍ resta al salir de donde estaba), el resultado era
    # una resta sin su suma correspondiente -- el total se iba a
    # negativo. `skip_fields` sigue protegiendo carpetas EXISTENTES de
    # que un barrido parcial les ponga a cero un total ya calculado
    # (S037); esto es un paso aparte, solo para archivos genuinamente
    # nuevos, que sí propaga su tamaño real hacia arriba en el momento
    # en que aparecen.
    new_file_sizes_by_parent = {}
    for entry in to_create:
        if (
            entry.entry_kind == DocumentIndexEntry.KIND_FILE
            and entry.size_bytes
        ):
            new_file_sizes_by_parent[entry.parent_path] = (
                new_file_sizes_by_parent.get(entry.parent_path, 0)
                + entry.size_bytes
            )
    for parent_path, size_delta in new_file_sizes_by_parent.items():
        _adjust_total_size(bucket_name, parent_path, size_delta)

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


def refresh_folder(bucket_name, folder_path, prelisted=None):
    """
    Refresh ONE folder's direct files and direct subfolders against
    the real bucket -- the same logic already validated in the
    `refresh_document_folder` management command, extracted here so
    it can be reused by anything that needs the same routine refresh
    (that command, and `document_explorer.tasks.
    refresh_quarantine_index_task`, H29 S040) without duplicating it.

    `prelisted`: optional `(blobs, subfolders)` already fetched by the
    caller (e.g. because it also needs them to render a report before
    writing) -- avoids listing the same GCS prefix twice. Pass
    `None` (the default) to have this function list it itself.

    Returns `(created, updated, touched, subfolders)` -- `subfolders`
    (the direct subfolder paths found) lets a caller walk deeper
    without re-listing what this call already saw.

    ---

    Refresca los archivos y subcarpetas directos de UNA carpeta
    contra el cubo real -- la misma lógica ya validada del comando de
    gestión `refresh_document_folder`, extraída aquí para que la
    reutilice cualquier cosa que necesite el mismo refresco rutinario
    (ese comando, y `document_explorer.tasks.
    refresh_quarantine_index_task`, H29 S040) sin duplicarla.

    `prelisted`: opcionalmente, `(blobs, subfolders)` ya obtenidos por
    quien llama (p. ej. porque también los necesita para mostrar un
    informe antes de escribir) -- evita listar el mismo prefijo de GCS
    dos veces. Pasar `None` (por defecto) para que esta función lo
    liste ella misma.

    Devuelve `(created, updated, touched, subfolders)` -- `subfolders`
    (las rutas de subcarpeta directas encontradas) permite a quien
    llama bajar más sin volver a listar lo que esta llamada ya vio.
    """
    from django.db import transaction
    from document_explorer.buckets import MARKS_PREFIX
    from document_explorer.gcs_index_service import list_folder_children
    from spare_parts.gcs_service import get_storage_client

    if prelisted is not None:
        blobs, subfolders = prelisted
    else:
        client = get_storage_client()
        blobs, subfolders = list_folder_children(
            client, bucket_name, folder_path,
        )
        blobs = [b for b in blobs if not b.name.startswith(MARKS_PREFIX)]
        subfolders = [
            p for p in subfolders
            if not (p + "/").startswith(MARKS_PREFIX)
        ]

    file_rows = [file_row(b) for b in blobs]
    rows = [folder_row(path) for path in subfolders] + file_rows
    if folder_path:
        rows.append(folder_row(folder_path))

    scope = {path_digest(row["blob_name"]) for row in rows}

    with transaction.atomic():
        created, updated = persist_rows(
            bucket_name, rows, scope_hashes=scope,
            skip_fields=("total_size_bytes",),
        )
        touched = recount_children(
            bucket_name,
            folder_paths=subfolders + (
                [folder_path] if folder_path else []
            ),
        )
    return created, updated, touched, subfolders
