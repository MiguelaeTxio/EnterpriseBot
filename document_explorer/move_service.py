# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/move_service.py
"""
File move for the explorer (H29, S039): change a file's VIRTUAL
location while its real object in Google Cloud Storage never moves.

Rewritten from the ground up after Miguel Angel caught a real design
mistake in the first version, verbatim: "deberíamos de haberlo hecho
casi a nivel de base de datos y no mover archivos realmente... en la
nube lo único que tenemos que tener son los archivos [contenido], y
lo que tenemos que tener claro es toda la estructura en base de
datos... si movemos, movemos punteros." The first version called
`spare_parts.gcs_service.move_file()` (copy + delete on the real GCS
object) on every move -- correct in principle, but moving a single
400 MB manual took long enough, with no progress indicator, that
Miguel Ángel had no way to know whether it was still running or
whether it was safe to cancel. His own analogy: a floppy disk's
directory track versus the data track -- the map of where everything
is lives in one place, cheap to rewrite, and the bytes underneath
never have to move for the map to change.

`DocumentIndexEntry` already had the two columns this needs, from
day one of H29:

- `blob_name` / `blob_name_hash`: the REAL, PERMANENT path of the
  object inside the bucket. Set once at indexing time
  (`index_writer.file_row`) and never written again by this module.
  It is what `OpenDocumentView` hands to `generate_signed_url()` --
  opening a document always finds the real bytes, regardless of how
  many times it has been "moved" since.
- `parent_path` / `parent_path_hash` / `name`: the VIRTUAL location --
  what the explorer actually displays and navigates by
  (`FolderListingView._page`'s `scope=here` already filtered on
  `parent_path_hash`, never on `blob_name`, from the very first
  version of H29 -- normal browsing was accidentally already
  pointer-based). Moving a file now means writing only these three
  columns. No network call, no GCS contact, no waiting -- a database
  write, done in the time it takes to save one row.

Two real consequences worth writing down, not hidden in a diff:

1. `blob_name` and the VIRTUAL location can now differ permanently
   for a moved file -- by design, not a bug. A file's real object may
   still sit at `PLATAFORMAS (Z)/Z-09/...` in the bucket while the
   explorer shows it inside `MANUALES DE USO`. Any code that reasons
   about "where a file lives" must use `parent_path`, never infer it
   from `blob_name`.
2. Recursive search (`scope=here_recursive`/`global` in
   `document_explorer.views`) used to scan `blob_name__startswith` --
   that only ever reflected the ORIGINAL location. It has been
   rewritten to scan `parent_path` for files (the virtual location, the
   only one this design changes) and `blob_name` for folders (folders
   are never moved -- out of scope, same as the first version -- so
   their `blob_name` still reliably equals their virtual path).

A folder emptied by moving everything out of it is left behind as an
orphan row (`child_count` reaches 0 but the row itself is not
deleted) -- cosmetic, non-blocking, a candidate for a future "empty
folders" tool, not solved here.

---

Movimiento de archivos para el explorador (H29, S039): cambia la
ubicación VIRTUAL de un archivo mientras su objeto real en Google
Cloud Storage no se mueve nunca.

Reescrito de raíz después de que Miguel Ángel señalara un fallo de
diseño real en la primera versión, verbatim: "deberíamos de haberlo
hecho casi a nivel de base de datos y no mover archivos realmente...
en la nube lo único que tenemos que tener son los archivos
[contenido], y lo que tenemos que tener claro es toda la estructura en
base de datos... si movemos, movemos punteros." La primera versión
llamaba a `spare_parts.gcs_service.move_file()` (copia + borrado del
objeto real de GCS) en cada movimiento -- correcto en principio, pero
mover un solo manual de 400 MB tardaba lo bastante, sin ningún
indicador de progreso, que Miguel Ángel no tenía forma de saber si
seguía en marcha ni si era seguro cancelar. Su propia analogía: la
pista de directorio de un disquete frente a la pista de datos -- el
mapa de dónde está cada cosa vive en un solo sitio, barato de
reescribir, y los bytes de debajo no tienen que moverse nunca para que
el mapa cambie.

`DocumentIndexEntry` ya tenía las dos columnas que esto necesita,
desde el primer día de H29:

- `blob_name` / `blob_name_hash`: la ruta REAL y PERMANENTE del objeto
  dentro del cubo. Se fija una sola vez al indexar
  (`index_writer.file_row`) y este módulo nunca la vuelve a escribir.
  Es lo que `OpenDocumentView` le pasa a `generate_signed_url()` --
  abrir un documento siempre encuentra los bytes reales, se haya
  "movido" las veces que se haya movido.
- `parent_path` / `parent_path_hash` / `name`: la ubicación VIRTUAL --
  lo que el explorador muestra y por lo que navega de verdad
  (`FolderListingView._page` con `scope=here` ya filtraba por
  `parent_path_hash`, nunca por `blob_name`, desde la primera versión
  de H29 -- la navegación normal ya funcionaba por punteros sin
  querer). Mover un archivo ahora significa escribir solo esas tres
  columnas. Sin llamada de red, sin contacto con GCS, sin espera --
  una escritura de base de datos, lo que tarda guardar una fila.

Dos consecuencias reales que conviene dejar escritas, no escondidas en
un diff:

1. `blob_name` y la ubicación VIRTUAL pueden ahora diferir de forma
   permanente para un archivo movido -- por diseño, no por fallo. El
   objeto real de un archivo puede seguir estando en
   `PLATAFORMAS (Z)/Z-09/...` dentro del cubo mientras el explorador
   lo muestra dentro de `MANUALES DE USO`. Cualquier código que
   razone sobre "dónde vive un archivo" debe usar `parent_path`, nunca
   inferirlo de `blob_name`.
2. La búsqueda recursiva (`scope=here_recursive`/`global` en
   `document_explorer.views`) escaneaba `blob_name__startswith` --
   eso solo reflejaba siempre la ubicación ORIGINAL. Se ha reescrito
   para escanear `parent_path` en archivos (la ubicación virtual, la
   única que este diseño cambia) y `blob_name` en carpetas (las
   carpetas nunca se mueven -- fuera de alcance, igual que en la
   primera versión -- así que su `blob_name` sigue siendo su ruta
   virtual de fiar).

Una carpeta que se queda vacía al sacar todo su contenido queda como
fila huérfana (`child_count` llega a 0 pero la fila no se borra) --
cosmético, no bloqueante, candidato a una futura herramienta de
"carpetas vacías", no resuelto aquí.
"""
from django.db import transaction
from django.db.models import F

from document_explorer.index_writer import ancestors_of, ensure_folder_chain
from document_explorer.models import DocumentIndexEntry, path_digest


def _split_name(name):
    if "." in name:
        stem, ext = name.rsplit(".", 1)
        return stem, "." + ext
    return name, ""


def _virtual_location_taken(bucket, folder_path, name, exclude_pk=None):
    """
    Whether a live entry already sits at this VIRTUAL location
    (`parent_path` + `name`) -- the collision that matters now that
    moving never touches `blob_name`. Two different real objects can
    perfectly well end up wanting the same displayed name in the same
    displayed folder; that is what this checks for.

    ---

    Si ya hay una entrada viva en esta ubicación VIRTUAL (`parent_path`
    + `name`) -- la colisión que importa ahora que mover nunca toca
    `blob_name`. Dos objetos reales distintos pueden perfectamente
    querer el mismo nombre mostrado en la misma carpeta mostrada; esto
    es lo que se comprueba.
    """
    query = DocumentIndexEntry.objects.filter(
        bucket=bucket, parent_path_hash=path_digest(folder_path),
        name=name, deleted_at__isnull=True, purged_at__isnull=True,
    )
    if exclude_pk is not None:
        query = query.exclude(pk=exclude_pk)
    return query.exists()


def _resolve_free_name(bucket, destination_folder, name, exclude_pk=None):
    """
    Return the display name to use in `destination_folder` for `name`,
    appending a correlative numeric suffix -- " (1)", " (2)"... --
    before the extension when the plain name is already taken there
    (as a VIRTUAL location -- see `_virtual_location_taken`).

    Decision of Miguel Ángel (S039), for "mover todos los manuales":
    when several selected files share a generic name (`MANUAL DEL
    OPERADOR.pdf`, five different machines) landing in the same flat
    folder, moving must never block the batch or stop to ask which
    name goes where, one by one -- a correlative number is enough for
    now, because the Gemini classification engine will open and rename
    each file properly later, one at a time.

    ---

    Devuelve el nombre a mostrar en `destination_folder` para `name`,
    añadiendo un sufijo numérico correlativo -- " (1)", " (2)"... --
    antes de la extensión cuando el nombre tal cual ya está ocupado
    allí (como ubicación VIRTUAL -- ver `_virtual_location_taken`).

    Decisión de Miguel Ángel (S039), para "mover todos los manuales":
    cuando varios archivos seleccionados comparten un nombre genérico
    (`MANUAL DEL OPERADOR.pdf`, cinco máquinas distintas) y aterrizan
    en la misma carpeta plana, mover nunca debe bloquear el lote ni
    parar a preguntar qué nombre va con cuál, uno a uno -- un número
    correlativo basta por ahora, porque el motor de clasificación con
    Gemini abrirá y renombrará cada archivo correctamente más adelante,
    uno por uno.
    """
    if not _virtual_location_taken(
        bucket, destination_folder, name, exclude_pk=exclude_pk,
    ):
        return name

    stem, ext = _split_name(name)
    suffix = 1
    while True:
        candidate_name = "%s (%d)%s" % (stem, suffix, ext)
        if not _virtual_location_taken(
            bucket, destination_folder, candidate_name,
            exclude_pk=exclude_pk,
        ):
            return candidate_name
        suffix += 1


def move_entry(entry, destination_folder):
    """
    Move `entry` (a live FILE `DocumentIndexEntry`) into
    `destination_folder` (a folder path string, `""` for the bucket
    root) -- a pure index write, `entry.blob_name` is never touched
    and Google Cloud Storage is never contacted. No-op if the
    destination is where the file already virtually lives. A name
    collision at the destination never blocks the move -- see
    `_resolve_free_name`; `entry.name` may come back different from
    what it was before the call, when that happened.

    ---

    Mueve `entry` (un `DocumentIndexEntry` de tipo FILE vivo) a
    `destination_folder` (una ruta de carpeta, `""` para la raíz del
    cubo) -- una escritura de índice pura, `entry.blob_name` no se
    toca nunca y Google Cloud Storage no se contacta nunca. No hace
    nada si el destino es donde ya vive virtualmente el archivo. Una
    colisión de nombre en el destino nunca bloquea el movimiento -- ver
    `_resolve_free_name`; `entry.name` puede volver distinto de como
    estaba antes de la llamada, cuando eso ha ocurrido.
    """
    destination_folder = destination_folder.strip("/")
    if destination_folder == entry.parent_path:
        return

    ensure_folder_chain(entry.bucket, destination_folder)
    new_name = _resolve_free_name(
        entry.bucket, destination_folder, entry.name, exclude_pk=entry.pk,
    )

    old_parent_path = entry.parent_path
    size = entry.size_bytes or 0

    with transaction.atomic():
        entry.parent_path = destination_folder
        entry.parent_path_hash = path_digest(destination_folder)
        entry.name = new_name
        entry.save(update_fields=[
            "parent_path", "parent_path_hash", "name",
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
