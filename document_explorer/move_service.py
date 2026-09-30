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
from django.db.models import Case, F, Q, Value, When

from document_explorer.index_writer import (
    _adjust_total_size, ancestors_of, ensure_folder_chain, recount_children,
)
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


def move_entry(entry, destination_folder, ensure_folder=True):
    """
    Move `entry` (a live FILE `DocumentIndexEntry`) into
    `destination_folder` (a folder path string, `""` for the bucket
    root) -- a pure index write, `entry.blob_name` is never touched
    and Google Cloud Storage is never contacted. No-op if the
    destination is where the file already virtually lives. A name
    collision at the destination never blocks the move -- see
    `_resolve_free_name`; `entry.name` may come back different from
    what it was before the call, when that happened.

    `ensure_folder=False` skips `ensure_folder_chain` -- for a batch
    of several entries going to the same destination in one request
    (`MoveView`), the chain only needs creating once, not once
    per file: measured in production (S039), each move was paying
    ~350-420 ms of pure server time, largely from repeating this same
    existence check on every single call for a destination that, past
    the first file, always already exists.

    ---

    Mueve `entry` (un `DocumentIndexEntry` de tipo FILE vivo) a
    `destination_folder` (una ruta de carpeta, `""` para la raíz del
    cubo) -- una escritura de índice pura, `entry.blob_name` no se
    toca nunca y Google Cloud Storage no se contacta nunca. No hace
    nada si el destino es donde ya vive virtualmente el archivo. Una
    colisión de nombre en el destino nunca bloquea el movimiento -- ver
    `_resolve_free_name`; `entry.name` puede volver distinto de como
    estaba antes de la llamada, cuando eso ha ocurrido.

    `ensure_folder=False` se salta `ensure_folder_chain` -- para un
    lote de varias entradas con el mismo destino en una sola petición
    (`MoveView`), la cadena solo hace falta crearla una vez, no
    una por archivo: medido en producción (S039), cada movimiento
    pagaba ~350-420 ms de tiempo puro de servidor, en buena parte por
    repetir esta misma comprobación de existencia en cada llamada para
    un destino que, a partir del primer archivo, ya existe siempre.
    """
    destination_folder = destination_folder.strip("/")
    if destination_folder == entry.parent_path:
        return

    if ensure_folder:
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


def _bulk_adjust(bucket, field_name, deltas):
    """
    Apply many different per-folder deltas to `field_name` in a SINGLE
    UPDATE, via one `CASE WHEN blob_name_hash = ... THEN field + delta
    ...` per folder -- the real fix for `move_entries`' query count.

    `move_entry`'s own `_adjust_total_size`/`_adjust_child_count` issue
    one UPDATE per folder per call, which was fine for a single file
    but does not scale: measured in production (S039), moving ~190
    files that way took ~75 seconds even after every other
    optimisation (batching HTTP requests, skipping repeated
    `ensure_folder_chain` calls) -- each of those still-separate
    UPDATEs pays real MySQL round-trip latency on this host, and
    hundreds of them add up on their own, independently of how many
    HTTP requests it took to get there. This collapses however many
    distinct folders a whole batch touches into one query, full stop.

    ---

    Aplica muchas diferencias distintas por carpeta a `field_name` en
    una ÚNICA UPDATE, vía un `CASE WHEN blob_name_hash = ... THEN
    field + delta ...` por carpeta -- la corrección real al número de
    consultas de `move_entries`.

    Las propias `_adjust_total_size`/`_adjust_child_count` de
    `move_entry` emiten una UPDATE por carpeta y por llamada, que
    estaba bien para un solo archivo pero no escala: medido en
    producción (S039), mover ~190 archivos así seguía tardando ~75
    segundos incluso después de cualquier otra optimización (agrupar
    peticiones HTTP, saltarse `ensure_folder_chain` repetido) -- cada
    una de esas UPDATE seguía pagando latencia real de ida y vuelta a
    MySQL en este servidor, y cientos de ellas suman por su cuenta, con
    independencia de en cuántas peticiones HTTP se hubiera repartido.
    Esto reduce a una sola consulta las carpetas distintas que toque
    un lote entero, sean las que sean.
    """
    deltas = {
        folder_path: delta for folder_path, delta in deltas.items()
        if delta and folder_path
    }
    if not deltas:
        return
    hash_to_delta = {
        path_digest(folder_path): delta
        for folder_path, delta in deltas.items()
    }
    # Value(delta) sin más se infiere como IntegerField pase lo que
    # pase el campo real -- combinado con F("total_size_bytes")
    # (BigIntegerField) en el mismo Case(), Django no sabe qué tipo de
    # salida darle y lanza FieldError ("mixed types: IntegerField,
    # BigIntegerField. You must set output_field."), visto en
    # producción (S039). Usar el propio campo del modelo como
    # output_field, tanto en cada Value() como en el Case(), lo deja
    # sin ambigüedad.
    field = DocumentIndexEntry._meta.get_field(field_name)
    whens = [
        When(
            blob_name_hash=digest,
            then=F(field_name) + Value(delta, output_field=field),
        )
        for digest, delta in hash_to_delta.items()
    ]
    DocumentIndexEntry.objects.filter(
        bucket=bucket, blob_name_hash__in=list(hash_to_delta.keys()),
        deleted_at__isnull=True, purged_at__isnull=True,
    ).update(**{
        field_name: Case(*whens, default=F(field_name), output_field=field),
    })


def move_entries(entries, destination_folder):
    """
    Move many files into `destination_folder` at once, in a FIXED,
    small number of database round trips regardless of batch size --
    what `MoveView` actually calls now. Not `move_entry()` looped:
    that was still ~6 queries per file (collision check, save, four
    size/count adjustments), each paying real round-trip latency on
    this host, and a loop of those was measured taking ~75 seconds for
    ~190 files even in a single HTTP request (S039) -- the request
    count was never the real bottleneck past a certain point, the
    per-file query count was.

    What this does instead:

    1. One query to read every name already taken at the destination
       (`_virtual_location_taken` would have repeated this per file).
    2. Collision resolution for the whole batch happens in Python
       against that one set, extended in memory as each file claims
       its name -- so two files in the SAME batch that would collide
       with each other are also numbered correctly, not just against
       what already existed before the move started.
    3. One `bulk_update()` for every moved entry's `parent_path`/
       `parent_path_hash`/`name`.
    4. One `_bulk_adjust()` call for `total_size_bytes` and one for
       `child_count`, covering every distinct folder the whole batch
       touches (old locations and the new one) in a single UPDATE
       each, via `Case`/`When` -- see `_bulk_adjust`.

    Files already sitting in `destination_folder` are skipped (same
    no-op rule as `move_entry`). Returns a list of
    `(original_name, final_name)` for every file actually moved, in
    the same order as `entries` -- `final_name` differs from
    `original_name` exactly when a collision was renamed.

    ---

    Mueve muchos archivos a `destination_folder` de una vez, en un
    número FIJO y pequeño de viajes de ida y vuelta a la base de
    datos, sea cual sea el tamaño del lote -- lo que llama `MoveView`
    ahora de verdad. No es `move_entry()` en un bucle: eso seguían
    siendo ~6 consultas por archivo (comprobación de colisión, guardado,
    cuatro ajustes de tamaño/contenido), cada una pagando latencia real
    de ida y vuelta en este servidor, y un bucle de esas se midió
    tardando ~75 segundos para ~190 archivos incluso en una sola
    petición HTTP (S039) -- el número de peticiones dejó de ser el
    cuello de botella real a partir de cierto punto; el número de
    consultas por archivo sí lo era.

    Lo que hace esto en su lugar:

    1. Una consulta para leer todos los nombres ya ocupados en el
       destino (`_virtual_location_taken` la habría repetido por
       archivo).
    2. La resolución de colisiones de todo el lote ocurre en Python
       contra ese único conjunto, ampliado en memoria según cada
       archivo reclama su nombre -- así que dos archivos del MISMO
       lote que chocarían entre sí también se numeran bien, no solo
       contra lo que ya existía antes de empezar a mover.
    3. Un único `bulk_update()` para el `parent_path`/`parent_path_hash`/
       `name` de cada entrada movida.
    4. Una llamada a `_bulk_adjust()` para `total_size_bytes` y otra
       para `child_count`, cubriendo todas las carpetas distintas que
       toca el lote entero (ubicaciones antiguas y la nueva) en una
       única UPDATE cada una, vía `Case`/`When` -- ver `_bulk_adjust`.

    Los archivos que ya estén en `destination_folder` se omiten (misma
    regla de no-op que `move_entry`). Devuelve una lista de
    `(nombre_original, nombre_final)` por cada archivo movido de
    verdad, en el mismo orden que `entries` -- `nombre_final` difiere
    de `nombre_original` justo cuando hubo una colisión renombrada.
    """
    if not entries:
        return []

    bucket = entries[0].bucket
    destination_folder = destination_folder.strip("/")
    ensure_folder_chain(bucket, destination_folder)

    movable = [
        entry for entry in entries
        if entry.parent_path != destination_folder
    ]
    if not movable:
        return []

    used_names = set(
        DocumentIndexEntry.objects.filter(
            bucket=bucket,
            parent_path_hash=path_digest(destination_folder),
            deleted_at__isnull=True, purged_at__isnull=True,
        )
        .exclude(pk__in=[entry.pk for entry in movable])
        .values_list("name", flat=True)
    )

    size_deltas = {}
    count_deltas = {}
    results = []

    for entry in movable:
        original_name = entry.name
        final_name = original_name
        if final_name in used_names:
            stem, ext = _split_name(original_name)
            suffix = 1
            while final_name in used_names:
                final_name = "%s (%d)%s" % (stem, suffix, ext)
                suffix += 1
        used_names.add(final_name)

        old_parent_path = entry.parent_path
        size = entry.size_bytes or 0

        entry.parent_path = destination_folder
        entry.parent_path_hash = path_digest(destination_folder)
        entry.name = final_name

        for ancestor in ancestors_of(old_parent_path):
            size_deltas[ancestor] = size_deltas.get(ancestor, 0) - size
        for ancestor in ancestors_of(destination_folder):
            size_deltas[ancestor] = size_deltas.get(ancestor, 0) + size

        count_deltas[old_parent_path] = (
            count_deltas.get(old_parent_path, 0) - 1
        )
        count_deltas[destination_folder] = (
            count_deltas.get(destination_folder, 0) + 1
        )

        results.append((original_name, final_name))

    with transaction.atomic():
        DocumentIndexEntry.objects.bulk_update(
            movable,
            ["parent_path", "parent_path_hash", "name"],
            batch_size=500,
        )
        _bulk_adjust(bucket, "total_size_bytes", size_deltas)
        # S125: el contador de hijos se recuenta de verdad en vez de
        # sumar/restar -- en carpetas con el contador desfasado la resta
        # daba negativo y MySQL (sin signo) tumbaba el traslado entero
        # ("BIGINT UNSIGNED value is out of range ... child_count + -12").
        recount_children(bucket, folder_paths=[
            folder_path for folder_path, delta in count_deltas.items()
            if delta and folder_path
        ])

    return results


def merge_folders(bucket, source_folder, destination_folder):
    """
    Merge two duplicate folder trees of the same bucket into one
    (H29, S043) -- real incident that motivated this: the same
    subfolder name (`H-11 TANQUETA ELECTRICA AUTO PROPULSADA`) existed
    twice under two different parent folders (`MINIGRUA` and `MINIGRUA
    Y MAQUINA ESPECIAL`), each with its own copy of the same real
    documents, splitting one machine's paperwork across two places the
    quarantine consumer treated as unrelated. Miguel Ángel, verbatim
    (S043), confirming the real cause and the fix belongs in the
    system itself, not a one-off manual cleanup: "eso es un error
    nuestro... nuestro sistema debe estar preparado para arreglar esa
    selva."

    A folder merge is never a new primitive: it is `move_entries()`
    applied to every live FILE under `source_folder`, each landing at
    the path it would occupy under `destination_folder` if the whole
    subtree had been renamed in place -- same relative depth
    preserved, so a file two levels deep inside the source lands two
    levels deep inside the destination, not flattened. FOLDERS never
    move (this module's own founding rule, see module docstring) --
    `destination_folder`'s own subtree gets recreated on demand by
    `move_entries()`'s `ensure_folder_chain()` call for each distinct
    target used, and every FOLDER row still sitting under
    `source_folder` once its files are gone is deleted outright at the
    end of this call (never a soft delete: an empty virtual-folder row
    is not content, it has nothing a user could ever want to restore
    from a papelera). This closes roadmap item 8 (`carpetas vacías`)
    as a side effect for the folders a merge empties, rather than
    building a second, separate cleanup pass for the exact same
    orphan-row problem.

    Name collisions inside a group landing at the same destination
    path are resolved by `move_entries()`'s own ordinal renaming --
    Miguel Ángel, verbatim (S043), confirming this explicitly instead
    of human review per case: "Confirmo el diseño con renombrado
    ordenado automático."

    Returns `(results, removed_folder_count)`: `results` is a list of
    dicts (`blob_name`, `original_name`, `final_name`,
    `destination_parent_path`), one per file actually moved, carrying
    the real `blob_name` forward from before the move for accurate
    audit logging -- `move_entries()`'s own tuple return loses it.
    `removed_folder_count` is how many orphaned FOLDER rows were
    deleted from the index. Never touches Google Cloud Storage (4.12)
    -- `blob_name` of every moved file stays exactly what it was at
    indexing time; only `parent_path`/`name` change, and FOLDER rows
    removed here were only ever database rows, never real GCS objects
    this call deletes.

    ---

    Fusiona dos árboles de carpeta duplicados del mismo cubo en uno
    solo (H29, S043) -- incidente real que lo motivó: el mismo nombre
    de subcarpeta (`H-11 TANQUETA ELECTRICA AUTO PROPULSADA`) existía
    dos veces bajo dos carpetas padre distintas (`MINIGRUA` y `MINIGRUA
    Y MAQUINA ESPECIAL`), cada una con su propia copia de los mismos
    documentos reales, partiendo la documentación de una sola máquina
    en dos sitios que el consumidor de cuarentena trataba como si no
    tuvieran relación. Miguel Ángel, verbatim (S043), confirmando la
    causa real y que el arreglo pertenece al propio sistema, no a una
    limpieza manual puntual: "eso es un error nuestro... nuestro
    sistema debe estar preparado para arreglar esa selva."

    Fusionar carpetas nunca es una primitiva nueva: es `move_entries()`
    aplicado a cada ARCHIVO vivo bajo `source_folder`, aterrizando cada
    uno en la ruta que ocuparía bajo `destination_folder` si todo el
    subárbol se hubiera renombrado en el sitio -- misma profundidad
    relativa conservada, así que un archivo dos niveles dentro del
    origen aterriza dos niveles dentro del destino, nunca aplanado. Las
    CARPETAS nunca se mueven (regla fundacional propia de este módulo,
    ver docstring del módulo) -- el propio subárbol de
    `destination_folder` se recrea bajo demanda por la llamada a
    `ensure_folder_chain()` de `move_entries()` para cada destino
    distinto usado, y toda fila FOLDER que siga bajo `source_folder`
    una vez vaciada de archivos se borra sin más al final de esta
    llamada (nunca un borrado blando: una fila de carpeta virtual
    vacía no es contenido, no tiene nada que un usuario pudiera querer
    restaurar de una papelera). Esto cierra el punto 8 de la hoja de
    ruta (`carpetas vacías`) como efecto colateral para las carpetas
    que una fusión deja vacías, en vez de construir una segunda pasada
    de limpieza separada para el mismo problema de filas huérfanas.

    Las colisiones de nombre dentro de un grupo que aterriza en la
    misma ruta destino se resuelven con el propio renombrado ordinal de
    `move_entries()` -- Miguel Ángel, verbatim (S043), confirmando esto
    explícitamente en vez de revisión humana caso a caso: "Confirmo el
    diseño con renombrado ordenado automático."

    Devuelve `(results, removed_folder_count)`: `results` es una lista
    de diccionarios (`blob_name`, `original_name`, `final_name`,
    `destination_parent_path`), uno por archivo realmente movido,
    conservando el `blob_name` real de antes del movimiento para una
    auditoría correcta -- la propia tupla que devuelve `move_entries()`
    lo pierde. `removed_folder_count` es cuántas filas FOLDER huérfanas
    se borraron del índice. Nunca toca Google Cloud Storage (4.12) --
    `blob_name` de cada archivo movido sigue siendo exactamente el de
    su indexación original; solo cambian `parent_path`/`name`, y las
    filas FOLDER que borra esta llamada solo fueron siempre filas de
    base de datos, nunca objetos reales de GCS que esta llamada borre.
    """
    source_folder = source_folder.strip("/")
    destination_folder = destination_folder.strip("/")
    if not source_folder or not destination_folder:
        return [], 0
    if source_folder == destination_folder:
        return [], 0
    if destination_folder == source_folder or \
            destination_folder.startswith(source_folder + "/"):
        # Fusionar una carpeta dentro de su propio subárbol la
        # dejaría persiguiéndose a sí misma (mover archivos hacia un
        # destino que un paso después vuelve a quedar "bajo origen").
        # Nunca supuesto seguro -- se rechaza sin más, quien llama
        # decide otro destino.
        return [], 0

    files = list(
        DocumentIndexEntry.objects.filter(
            bucket=bucket,
            entry_kind=DocumentIndexEntry.KIND_FILE,
            deleted_at__isnull=True, purged_at__isnull=True,
        ).filter(
            Q(parent_path=source_folder)
            | Q(parent_path__startswith=source_folder + "/"),
        )
    )
    if not files:
        return [], 0

    # Agrupar por destino relativo real: un archivo puede vivir en una
    # subcarpeta más profunda que la raíz del origen, y debe aterrizar
    # en la misma subcarpeta relativa bajo destino -- nunca aplanado
    # a la raíz del destino.
    by_destination = {}
    for entry in files:
        relative = entry.parent_path[len(source_folder):].lstrip("/")
        target = (
            "%s/%s" % (destination_folder, relative)
            if relative else destination_folder
        )
        by_destination.setdefault(target, []).append(entry)

    all_results = []
    for target, group in by_destination.items():
        blob_names_by_original_name = {
            entry.name: entry.blob_name for entry in group
        }
        for original_name, final_name in move_entries(group, target):
            all_results.append({
                "blob_name": blob_names_by_original_name[original_name],
                "original_name": original_name,
                "final_name": final_name,
                "destination_parent_path": target,
            })

    orphaned_folders = DocumentIndexEntry.objects.filter(
        bucket=bucket,
        entry_kind=DocumentIndexEntry.KIND_FOLDER,
        deleted_at__isnull=True, purged_at__isnull=True,
    ).filter(
        Q(blob_name=source_folder)
        | Q(blob_name__startswith=source_folder + "/"),
    )
    removed_folder_count = orphaned_folders.count()
    orphaned_folders.delete()

    return all_results, removed_folder_count
