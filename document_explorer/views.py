# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/views.py
"""
Explorer views over the document index (H29).

Navigation never touches Google Cloud Storage. Every listing is a
single indexed equality lookup on `parent_path_hash`, ordered folders
first, paginated by cursor. GCS is contacted at exactly two moments:
when a document's content is opened (a signed URL is minted) and when
the administrator empties a trash (the object is really deleted) --
moving (S039, see `move_service`) is NOT a third moment: it is purely
a pointer change in the index, never touches GCS.

Pagination is by cursor, not OFFSET: the cost of page 40 is the same
as page 1. The cursor is now a triple of (entry_kind, sort_field,
id), because ordering is user-selectable (S039) -- folders always
lead the list (Windows-Explorer-style, Miguel Angel's explicit
decision), then the chosen column (name/size/date) in the chosen
direction, then `id` as the final tie-breaker so the triple is always
unique regardless of duplicate names/sizes/dates.

S039 adds three search scopes on top of plain folder browsing:
- `here`: the original behaviour, direct children of one folder.
- `here_recursive`: every descendant under the open folder, filtered
  by name/extension/local flag.
- `global`: the same recursive filter from the bucket root, reachable
  from any folder without navigating there first.

The recursive scopes are the one place this module accepts an
unindexed scan -- a deliberate, occasional search action, not a
page-load-critical navigation path, and bounded by the size of one
bucket (tens of thousands of rows at most, per the H28 inventory).
Since S039's move redesign (`move_service`, pointer-only: a move
writes `parent_path`, never `blob_name`), "is this under folder X"
has two different answers depending on entry kind -- see
`_virtual_descendant_q` for the split (files: `parent_path`; folders,
which never move: `blob_name`). Permission scoping for the recursive
modes still follows the same "resolve once per request" principle as
`permissions.py`: `readable_prefixes()` returns a handful of grant
prefixes, applied as one small OR condition, never as a per-row check
in Python.

Permissions are resolved once per request, in Python, against the
folder being opened -- see `permissions.py` for why rows are never
filtered individually.

Deleting is logical and personal: the row goes to the deleter's own
trash and becomes invisible to everybody else immediately, per the
S037 decision. Only the administrator purges, and purging removes the
object while keeping the row as an audit record. Deletion from a
search result (`here_recursive`/`global`) is disabled -- see
`FolderListingView.get_context_data` -- because a flattened result set
can mix rows from folders with different permissions, and the single
per-request `show_delete` flag this module relies on cannot express a
per-row answer without becoming exactly the per-row check the whole
design avoids.

---

Vistas del explorador sobre el índice documental (H29).

Navegar no toca nunca Google Cloud Storage. Cada listado es una única
búsqueda indexada por igualdad sobre `parent_path_hash`, ordenada con
las carpetas primero y paginada por cursor. Con GCS se habla en
exactamente dos momentos: al abrir el contenido de un documento (se
acuña una URL firmada) y cuando el administrador vacía una papelera
(el objeto se borra de verdad) -- mover (S039, ver `move_service`) NO
es un tercer momento: es puramente un cambio de puntero en el índice,
nunca toca GCS.

La paginación es por cursor, no por OFFSET: la página 40 cuesta lo
mismo que la 1. El cursor es ahora una terna (tipo de entrada, campo
de orden, id), porque el orden es elegible por el usuario (S039) --
las carpetas encabezan siempre la lista (como en el Explorador de
Windows, decisión explícita de Miguel Ángel), luego la columna elegida
(nombre/tamaño/fecha) en la dirección elegida, y por último `id` como
desempate final para que la terna sea siempre única aunque haya
nombres/tamaños/fechas duplicados.

S039 añade tres alcances de búsqueda sobre el simple listado de
carpeta:

- `here`: el comportamiento original, hijos directos de una carpeta.
- `here_recursive`: todos los descendientes bajo la carpeta abierta,
  filtrados por nombre/extensión/bandera local.
- `global`: el mismo filtro recursivo desde la raíz del cubo,
  alcanzable desde cualquier carpeta sin tener que navegar hasta ahí
  primero.

Los alcances recursivos son el único sitio de este módulo donde se
acepta un barrido sin índice -- una acción de búsqueda deliberada y
ocasional, no una ruta de navegación crítica en cada carga de página,
y acotada al tamaño de un cubo (decenas de miles de filas como mucho,
según el inventario de H28). Desde el rediseño de mover de S039
(`move_service`, puramente por puntero: mover escribe `parent_path`,
nunca `blob_name`), "¿esto está bajo la carpeta X?" tiene dos
respuestas distintas según el tipo de entrada -- ver
`_virtual_descendant_q` para el reparto (archivos: `parent_path`;
carpetas, que nunca se mueven: `blob_name`). El acotado de permisos de
los modos recursivos sigue el mismo principio de "resolver una vez por
petición" que `permissions.py`: `readable_prefixes()` devuelve un
puñado de prefijos de concesión, aplicados como una única condición OR
pequeña, nunca como una comprobación fila a fila en Python.

Los permisos se resuelven una vez por petición, en Python, contra la
carpeta que se abre -- ver `permissions.py` para por qué no se filtran
las filas una a una.

Borrar es lógico y personal: la fila va a la papelera de quien borra y
deja de ser visible para todos los demás de inmediato, según la
decisión de S037. Solo el administrador vacía, y vaciar retira el
objeto conservando la fila como registro de auditoría. El borrado
desde un resultado de búsqueda (`here_recursive`/`global`) está
desactivado -- ver `FolderListingView.get_context_data` -- porque un
listado aplanado puede mezclar filas de carpetas con permisos
distintos, y el indicador único `show_delete` por petición en el que
se apoya este módulo no puede expresar una respuesta por fila sin
convertirse justo en la comprobación fila a fila que todo el diseño
evita.

Unificación visual del árbol (S039, decisión explícita de Miguel
Ángel): el explorador deja de mostrar pestañas de cubo. Todo se
presenta como un único árbol que empieza en "Directorio Principal"
(`PRIMARY_BUCKET`, el cubo histórico); las raíces de los demás cubos
indexados (Fotos Partes, Fotos Albaranes) se inyectan como filas de
carpeta sintéticas (`VirtualBucketFolder`) en la primera página de la
raíz de `PRIMARY_BUCKET`, y `build_breadcrumbs` antepone una miga
"Directorio Principal" al entrar en cualquiera de ellas -- "nadie
tiene por qué saber que son cubos diferentes". Ver
`FolderListingView._virtual_root_entries` y `_folder_nav_url`.
"""
from urllib.parse import urlencode
import datetime

from django.contrib import messages
from django.db.models import (
    BigIntegerField, Case, DateTimeField, F, Q, Value, When,
)
from django.db.models.functions import Cast, Coalesce
from django.http import Http404, HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views import View
from django.views.generic import TemplateView

from panel.mixins import CompanyUserRequiredMixin
from spare_parts.gcs_service import delete_file, generate_signed_url

from document_explorer import friendly_names, index_writer, move_service, permissions
from document_explorer.buckets import (
    BUCKET_DISPLAY_NAMES, INDEXED_BUCKETS, PRIMARY_BUCKET,
)
from document_explorer.models import DocumentIndexEntry, path_digest

PAGE_SIZE = 200

# Alcances de búsqueda (S039). `here` es el listado de siempre; los
# otros dos activan el barrido recursivo -- ver el docstring del
# módulo.
SCOPE_HERE = "here"
SCOPE_RECURSIVE = "here_recursive"
SCOPE_GLOBAL = "global"
SCOPE_CHOICES = (SCOPE_HERE, SCOPE_RECURSIVE, SCOPE_GLOBAL)

# Columnas ordenables (S039), pedidas explícitamente por Miguel Ángel:
# fecha, nombre y tamaño. "Contenido" (nº de hijos) no es ordenable --
# solo tiene sentido para carpetas y no se pidió.
SORT_FIELDS = ("name", "size", "date")
DEFAULT_SORT = "name"
DEFAULT_DIR = "asc"

# Centinela para `gcs_updated_at` nulo (carpetas, y algún objeto sin
# metadato). Ordenar y paginar necesitan un valor comparable siempre
# -- nunca comparar contra NULL. Las filas sin fecha real quedan al
# principio en orden ascendente y al final en descendente, igual que
# el resto de valores "más antiguos que cualquier otro". UTC explícito
# de la librería estándar, sin depender de `timezone.get_default_
# timezone()` (Europe/Madrid) -- ni el valor ni el razonamiento sobre
# él deben cambiar si algún día cambia TIME_ZONE en settings.py.
_EPOCH = datetime.datetime(1970, 1, 1, tzinfo=datetime.timezone.utc)


class ExplorerAccessMixin(CompanyUserRequiredMixin):
    """
    Resolve the CompanyUser and its grants once per request.

    ---

    Resuelve el CompanyUser y sus concesiones una vez por petición.
    """

    def setup(self, request, *args, **kwargs):
        super().setup(request, *args, **kwargs)
        self.company_user = None
        self.grants = []

    def load_grants(self, bucket):
        """
        Load this user's grants for a bucket, once.

        ---

        Carga las concesiones del usuario para un cubo, una sola vez.
        """
        self.company_user = self.request.user.company_user
        self.grants = permissions.grants_for(self.company_user, bucket)
        return self.grants


def build_breadcrumbs(bucket, folder_path):
    """
    Build the navigation trail. Logic lives here, never in a template.

    S039, explicit decision of Miguel Angel: the explorer no longer
    shows bucket tabs. Everything is presented as a single tree
    starting at "Directorio Principal" -- "nadie tiene por qué saber
    que son cubos diferentes" ("nobody needs to know these are
    different buckets"). `PRIMARY_BUCKET` (the historical bucket) IS
    that root: browsing its own real root already reads "Directorio
    Principal" via BUCKET_DISPLAY_NAMES, so it needs no extra crumb.
    Any OTHER bucket (Fotos Partes, Fotos Albaranes) gets a
    "Directorio Principal" crumb prepended, pointing back at
    PRIMARY_BUCKET's root -- so from the person's point of view those
    buckets' roots look like ordinary subfolders one level under it,
    exactly like `DOC. MAQUINAS` or `DOC. PERSONAL` do.

    Every crumb carries its own `bucket`, because the trail can now
    span more than one -- the template must never assume a single
    page-level bucket applies to every crumb link.

    ---

    Construye la miga de pan. La lógica vive aquí, nunca en la
    plantilla.

    S039, decisión explícita de Miguel Ángel: el explorador deja de
    mostrar pestañas de cubo. Todo se presenta como un único árbol que
    empieza en "Directorio Principal" -- "nadie tiene por qué saber
    que son cubos diferentes". `PRIMARY_BUCKET` (el cubo histórico) ES
    esa raíz: navegar su propia raíz real ya se lee "Directorio
    Principal" vía BUCKET_DISPLAY_NAMES, así que no necesita miga
    extra. Cualquier OTRO cubo (Fotos Partes, Fotos Albaranes) recibe
    una miga "Directorio Principal" antepuesta, apuntando a la raíz de
    PRIMARY_BUCKET -- así que, desde el punto de vista de la persona,
    las raíces de esos cubos parecen subcarpetas normales un nivel por
    debajo, exactamente igual que `DOC. MAQUINAS` o `DOC. PERSONAL`.

    Cada miga lleva su propio `bucket`, porque el recorrido puede
    abarcar ahora más de uno -- la plantilla nunca debe asumir que un
    único cubo de página aplica a todos los enlaces de migas.
    """
    crumbs = []
    if bucket != PRIMARY_BUCKET:
        crumbs.append({
            "label": BUCKET_DISPLAY_NAMES.get(PRIMARY_BUCKET, PRIMARY_BUCKET),
            "bucket": PRIMARY_BUCKET,
            "path": "",
        })
    crumbs.append({
        "label": BUCKET_DISPLAY_NAMES.get(bucket, bucket),
        "bucket": bucket,
        "path": "",
    })
    if not folder_path:
        return crumbs
    parts = folder_path.split("/")
    for index, part in enumerate(parts):
        crumbs.append({
            "label": part,
            "bucket": bucket,
            "path": "/".join(parts[:index + 1]),
        })
    return crumbs


class ExplorerView(ExplorerAccessMixin, TemplateView):
    """
    Explorer shell: just the container that HTMX-loads the first
    folder listing. Since S039 there is no bucket picker -- browsing
    always starts at `PRIMARY_BUCKET`'s root ("Directorio Principal")
    unless the URL names a specific bucket/path (a deep link, or the
    person continuing where they left off inside a nested bucket).

    ---

    Armazón del explorador: solo el contenedor que carga por HTMX el
    primer listado de carpeta. Desde S039 no hay selector de cubo -- la
    navegación empieza siempre en la raíz de `PRIMARY_BUCKET`
    ("Directorio Principal") salvo que la URL nombre un cubo/ruta
    concreto (un enlace directo, o retomar donde se dejó dentro de un
    cubo anidado).
    """

    template_name = "document_explorer/explorer.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        company_user = self.request.user.company_user
        buckets = permissions.readable_buckets(company_user)

        requested_bucket = self.request.GET.get("bucket")
        if requested_bucket:
            bucket = requested_bucket
        elif PRIMARY_BUCKET in buckets:
            bucket = PRIMARY_BUCKET
        else:
            bucket = buckets[0] if buckets else ""

        if bucket and bucket not in buckets:
            raise Http404("Sin acceso a ese cubo.")

        folder_path = (self.request.GET.get("path") or "").strip("/")
        context.update({
            "active_nav": "document_explorer",
            "bucket": bucket,
            "folder_path": folder_path,
            "has_buckets": bool(buckets),
        })
        return context


class VirtualBucketFolder:
    """
    A synthetic "folder" row standing in for another indexed bucket's
    root, so `PRIMARY_BUCKET`'s root can present Fotos Partes/Fotos
    Albaranes as ordinary subfolders (S039, explicit decision of
    Miguel Angel -- see the module docstring and `build_breadcrumbs`).

    Deliberately duck-types just the attributes `_rows.html` needs from
    a real `DocumentIndexEntry` folder row -- `is_folder`, `name`,
    `display_size`, `child_count`, `gcs_updated_at`, `entry_kind`, and
    `nav_url` (computed the same way as for real folders, see
    `FolderListingView._folder_nav_url`). It is never sorted by the
    database: `FolderListingView._page` always places these ahead of
    the real, queried entries on the first page of `PRIMARY_BUCKET`'s
    root, in a fixed order, because they have no real `size_bytes`/
    `gcs_updated_at` to compare against a chosen sort column.

    ---

    Una fila de "carpeta" sintética que representa la raíz de otro
    cubo indexado, para que la raíz de `PRIMARY_BUCKET` pueda presentar
    Fotos Partes/Fotos Albaranes como subcarpetas normales (S039,
    decisión explícita de Miguel Ángel -- ver el docstring del módulo
    y `build_breadcrumbs`).

    Imita a propósito solo los atributos que `_rows.html` necesita de
    una fila de carpeta real de `DocumentIndexEntry` -- `is_folder`,
    `name`, `display_size`, `child_count`, `gcs_updated_at`,
    `entry_kind`, y `nav_url` (calculado igual que para las carpetas
    reales, ver `FolderListingView._folder_nav_url`). Nunca se ordena
    en base de datos: `FolderListingView._page` siempre las coloca por
    delante de las entradas reales consultadas, en la primera página de
    la raíz de `PRIMARY_BUCKET`, en un orden fijo, porque no tienen
    `size_bytes`/`gcs_updated_at` reales con los que compararse contra
    una columna de orden elegida.
    """

    entry_kind = DocumentIndexEntry.KIND_FOLDER
    is_folder = True
    display_size = "—"
    gcs_updated_at = None

    def __init__(self, name, child_count, nav_url):
        self.name = name
        self.child_count = child_count
        self.nav_url = nav_url


class FolderListingView(ExplorerAccessMixin, TemplateView):
    """
    HTMX fragment: the direct children of one folder, or -- since
    S039 -- a filtered/sorted/recursive result set over one bucket.

    ---

    Fragmento HTMX: los hijos directos de una carpeta, o -- desde S039
    -- un resultado filtrado/ordenado/recursivo sobre un cubo.
    """

    template_name = "document_explorer/_panel.html"

    def get_template_names(self):
        """
        Full fragment normally; rows only when paginating.

        Appending the full fragment on scroll would duplicate the
        breadcrumb trail on every page.

        ---

        Fragmento completo normalmente; solo filas al paginar.

        Anexar el fragmento completo al hacer scroll duplicaria la miga
        de pan en cada pagina.
        """
        if self.request.GET.get("after_id"):
            return ["document_explorer/_rows.html"]
        return [self.template_name]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        request = self.request
        bucket = request.GET.get("bucket") or ""
        folder_path = (request.GET.get("path") or "").strip("/")

        company_user = request.user.company_user
        if bucket not in permissions.readable_buckets(company_user):
            raise Http404("Sin acceso a ese cubo.")

        self.bucket = bucket
        self.folder_path = folder_path
        grants = self.load_grants(bucket)
        self.sort_key, self.sort_dir = self._sort_params()
        self.filters = self._filter_params()
        scope = self.filters["scope"]
        is_search = scope != SCOPE_HERE

        breadcrumbs = build_breadcrumbs(bucket, folder_path)
        for crumb in breadcrumbs:
            crumb["url"] = self._folder_nav_url(
                crumb["bucket"], crumb["path"],
            )

        common = {
            "bucket": bucket,
            "folder_path": folder_path,
            "breadcrumbs": breadcrumbs,
            "is_search": is_search,
            "filters": self.filters,
            "sort_key": self.sort_key,
            "sort_dir": self.sort_dir,
            "sort_columns": self._sort_columns(),
            "can_move": permissions.is_unrestricted(company_user),
            "primary_bucket": PRIMARY_BUCKET,
        }

        if scope == SCOPE_HERE:
            mode, allowed = permissions.visibility(
                company_user, bucket, folder_path, grants=grants,
            )
            denied = mode == permissions.NONE
            show_delete = (not denied) and permissions.can_delete_in(
                company_user, bucket, folder_path, grants=grants,
            )
        else:
            mode, allowed = None, None
            if scope == SCOPE_GLOBAL:
                search_buckets = [
                    name for name in INDEXED_BUCKETS
                    if name in permissions.readable_buckets(company_user)
                ]
                denied = not search_buckets
            else:
                prefixes = permissions.readable_prefixes(
                    company_user, bucket,
                )
                denied = prefixes is not None and not prefixes
            # Borrado desactivado en resultados de búsqueda -- ver
            # docstring del módulo.
            show_delete = False

        has_parent = bool(folder_path) and not is_search
        parent_path = (
            folder_path.rsplit("/", 1)[0] if "/" in folder_path else ""
        )

        if denied:
            context.update(common)
            context.update({
                "entries": [],
                "denied": True,
                "next_page_url": None,
                "show_delete": False,
                "has_parent": has_parent,
                "parent_path": parent_path,
                "parent_nav_url": self._folder_nav_url(bucket, parent_path),
            })
            return context

        entries = self._page(bucket, folder_path, mode, allowed)
        has_more = len(entries) > PAGE_SIZE
        entries = entries[:PAGE_SIZE]

        is_first_page = not request.GET.get("after_id")
        if (
            scope == SCOPE_HERE and bucket == PRIMARY_BUCKET
            and not folder_path and is_first_page
        ):
            entries = self._virtual_root_entries(company_user) + entries

        context.update(common)
        context.update({
            "entries": entries,
            "denied": False,
            "parent_path": parent_path,
            "has_parent": has_parent,
            "parent_nav_url": self._folder_nav_url(bucket, parent_path),
            "show_delete": show_delete,
            "next_page_url": (
                self._build_page_url(self._cursor(entries[-1]))
                if (has_more and entries) else None
            ),
        })
        return context

    def _virtual_root_entries(self, company_user):
        """
        Synthetic folder rows for the other indexed buckets, injected
        ahead of `PRIMARY_BUCKET`'s own real root entries -- see
        `VirtualBucketFolder` and the module docstring. Only for
        buckets the user can actually read; a bucket with zero grants
        simply does not appear, same as it would not have appeared as
        a tab before S039.

        ---

        Filas de carpeta sintéticas para los demás cubos indexados,
        inyectadas por delante de las entradas reales de la propia raíz
        de `PRIMARY_BUCKET` -- ver `VirtualBucketFolder` y el docstring
        del módulo. Solo para los cubos que el usuario puede leer de
        verdad; un cubo sin ninguna concesión simplemente no aparece,
        igual que no habría aparecido como pestaña antes de S039.
        """
        readable = permissions.readable_buckets(company_user)
        virtual = []
        for bucket_name in INDEXED_BUCKETS:
            if bucket_name == PRIMARY_BUCKET or bucket_name not in readable:
                continue
            child_count = DocumentIndexEntry.objects.filter(
                bucket=bucket_name,
                parent_path_hash=path_digest(""),
                deleted_at__isnull=True,
                purged_at__isnull=True,
            ).count()
            virtual.append(VirtualBucketFolder(
                name=BUCKET_DISPLAY_NAMES.get(bucket_name, bucket_name),
                child_count=child_count,
                nav_url=self._folder_nav_url(bucket_name, ""),
            ))
        return virtual

    # -- Orden y filtros (S039) -------------------------------------

    def _sort_params(self):
        """
        Read and validate `sort`/`dir` from the query string, falling
        back to name/asc -- the original behaviour -- for anything
        unrecognised.

        ---

        Lee y valida `sort`/`dir` de la query string, y por defecto
        cae en nombre/ascendente -- el comportamiento original -- ante
        cualquier valor no reconocido.
        """
        sort = self.request.GET.get("sort") or DEFAULT_SORT
        if sort not in SORT_FIELDS:
            sort = DEFAULT_SORT
        direction = self.request.GET.get("dir") or DEFAULT_DIR
        if direction not in ("asc", "desc"):
            direction = DEFAULT_DIR
        return sort, direction

    def _filter_params(self):
        """
        Read and validate the search filters from the query string.

        ---

        Lee y valida los filtros de búsqueda de la query string.
        """
        request = self.request
        scope = request.GET.get("scope") or SCOPE_HERE
        if scope not in SCOPE_CHOICES:
            scope = SCOPE_HERE
        local = request.GET.get("local") or ""
        if local not in ("", "1", "0"):
            local = ""
        return {
            "q": (request.GET.get("q") or "").strip(),
            "ext": (request.GET.get("ext") or "").strip().lstrip("."),
            "local": local,
            "scope": scope,
        }

    def _sort_columns(self):
        """
        Header state for the three sortable columns, fully resolved
        here (URL included) so the template only prints values --
        never decides the next sort direction itself.

        ---

        Estado de cabecera de las tres columnas ordenables, resuelto
        aquí por completo (URL incluida) para que la plantilla solo
        imprima valores -- nunca decida ella misma la siguiente
        dirección de orden.
        """
        labels = {"name": "Nombre", "size": "Tamaño", "date": "Modificado"}
        columns = {}
        for key, label in labels.items():
            active = self.sort_key == key
            toggle_dir = (
                "desc" if (active and self.sort_dir == "asc") else "asc"
            )
            columns[key] = {
                "label": label,
                "active": active,
                "dir": self.sort_dir if active else None,
                "url": self._build_base_url(sort=key, dir=toggle_dir),
            }
        return columns

    def _base_params(self, **overrides):
        params = {
            "bucket": self.bucket,
            "path": self.folder_path,
            "scope": self.filters["scope"],
            "q": self.filters["q"],
            "ext": self.filters["ext"],
            "local": self.filters["local"],
            "sort": self.sort_key,
            "dir": self.sort_dir,
        }
        params.update(overrides)
        return params

    def _build_base_url(self, **overrides):
        params = self._base_params(**overrides)
        return "%s?%s" % (
            reverse("document_explorer:listing"), urlencode(params),
        )

    def _build_page_url(self, cursor):
        params = self._base_params(
            after_kind=cursor["after_kind"],
            after_id=cursor["after_id"],
            after_value=cursor["after_value"],
        )
        return "%s?%s" % (
            reverse("document_explorer:listing"), urlencode(params),
        )

    def _folder_nav_url(self, bucket, path):
        """
        URL for navigating into a folder (real or virtual): bucket and
        path change, sort/direction carry over, everything else
        (scope/q/ext/local) resets -- a fresh location starts a fresh
        listing, same rule as any other folder click already followed
        before S039's virtual root existed.

        ---

        URL para navegar a una carpeta (real o virtual): cambian cubo y
        ruta, se conserva orden/dirección, y se reinicia todo lo demás
        (scope/q/ext/local) -- una ubicación nueva empieza un listado
        nuevo, la misma regla que ya seguía cualquier clic de carpeta
        antes de que existiera la raíz virtual de S039.
        """
        params = {
            "bucket": bucket,
            "path": path,
            "sort": self.sort_key,
            "dir": self.sort_dir,
        }
        return "%s?%s" % (
            reverse("document_explorer:listing"), urlencode(params),
        )

    # -- Consulta -----------------------------------------------------

    def _sort_field(self):
        """
        Map the public sort key to the annotated/real field name used
        in ORDER BY and in the cursor comparison.

        ---

        Traduce la clave de orden pública al nombre de campo real/
        anotado usado en ORDER BY y en la comparación del cursor.
        """
        return {
            "name": "name",
            "size": "sort_size",
            "date": "sort_date",
        }[self.sort_key]

    def _virtual_descendant_q(self, prefix):
        """
        Q matching every entry (file or folder) whose CURRENT,
        VIRTUAL location is `prefix` itself or falls under it.
        Written for `move_service`'s pointer-only redesign (S039):
        `blob_name__startswith` used to answer "is this under folder
        X", correctly, back when moving a file also moved its real
        object. Since move_service.move_entry only ever writes
        `parent_path`, that question now has two different answers
        depending on entry kind:

        - FILES: `parent_path` is the only field a move ever changes,
          so it is the one virtual-location field to trust. `entry`
          itself has no children, so checking its own container is
          enough.
        - FOLDERS: out of scope for moving (Miguel Ángel's decision,
          `move_service` docstring) -- they never move, so their own
          `blob_name` still reliably equals their virtual path.

        Empty `prefix` means "no restriction" (the whole bucket),
        matching `permissions.covers()`'s own convention for an empty
        grant prefix.

        ---

        Q que casa con cualquier entrada (archivo o carpeta) cuya
        ubicación VIRTUAL actual es `prefix` en sí misma o cae bajo
        ella. Escrito para el rediseño de mover puramente por puntero
        (S039): `blob_name__startswith` respondía correctamente "¿esto
        está bajo la carpeta X?" cuando mover un archivo también movía
        su objeto real. Como `move_service.move_entry` ahora solo
        escribe `parent_path`, esa pregunta tiene dos respuestas
        distintas según el tipo de entrada:

        - ARCHIVOS: `parent_path` es el único campo que un movimiento
          cambia, así que es el campo de ubicación virtual del que
          fiarse. La propia entrada no tiene hijos, así que comprobar
          su propio contenedor basta.
        - CARPETAS: fuera de alcance para mover (decisión de Miguel
          Ángel, docstring de `move_service`) -- nunca se mueven, así
          que su propio `blob_name` sigue siendo su ruta virtual de
          fiar.

        `prefix` vacío significa "sin restricción" (el cubo entero),
        misma convención que ya sigue `permissions.covers()` para un
        prefijo de concesión vacío.
        """
        if not prefix:
            return Q()
        return (
            Q(entry_kind=DocumentIndexEntry.KIND_FILE) & (
                Q(parent_path=prefix)
                | Q(parent_path__startswith=prefix + "/")
            )
        ) | (
            Q(entry_kind=DocumentIndexEntry.KIND_FOLDER) & (
                Q(blob_name=prefix)
                | Q(blob_name__startswith=prefix + "/")
            )
        )

    def _page(self, bucket, folder_path, mode, allowed):
        """
        One indexed page of children (scope=here), or one page of a
        recursive search (scope=here_recursive/global), folders
        always first, then the chosen column/direction, then `id` as
        tie-breaker.

        `scope=global` searches across every indexed bucket the user
        can read, not just the current one -- decision of Miguel Angel
        (S039), made once the bucket tabs disappeared: with a single
        unified tree, "todo el cubo" has to mean everything visible,
        or a search from the root would silently miss anything living
        in Fotos Partes/Fotos Albaranes. Pagination stays correct
        across buckets because `id` is unique across the whole table,
        not per bucket.

        ---

        Una página indexada de hijos (scope=here), o una página de una
        búsqueda recursiva (scope=here_recursive/global), siempre con
        las carpetas primero, luego la columna/dirección elegida, y
        por último `id` como desempate.

        `scope=global` busca en todos los cubos indexados que el
        usuario puede leer, no solo en el actual -- decisión de Miguel
        Ángel (S039), tomada al desaparecer las pestañas de cubo: con
        un árbol unificado, "todo el cubo" tiene que significar todo lo
        visible, o una búsqueda desde la raíz se perdería en silencio
        cualquier cosa que viva en Fotos Partes/Fotos Albaranes. La
        paginación sigue siendo correcta entre cubos porque `id` es
        único en toda la tabla, no por cubo.
        """
        scope = self.filters["scope"]

        if scope == SCOPE_GLOBAL:
            search_buckets = [
                name for name in INDEXED_BUCKETS
                if name in permissions.readable_buckets(self.company_user)
            ]
            query = DocumentIndexEntry.objects.filter(
                bucket__in=search_buckets,
                deleted_at__isnull=True, purged_at__isnull=True,
            )
            restriction = Q()
            for search_bucket in search_buckets:
                prefixes = permissions.readable_prefixes(
                    self.company_user, search_bucket,
                )
                if prefixes is None:
                    restriction |= Q(bucket=search_bucket)
                    continue
                for prefix in prefixes:
                    restriction |= Q(bucket=search_bucket) & \
                        self._virtual_descendant_q(prefix)
            query = query.filter(restriction) if search_buckets else \
                query.none()
        else:
            query = DocumentIndexEntry.objects.filter(
                bucket=bucket,
                deleted_at__isnull=True, purged_at__isnull=True,
            )
            if scope == SCOPE_HERE:
                query = query.filter(
                    parent_path_hash=path_digest(folder_path),
                )
                if mode == permissions.PARTIAL:
                    query = query.filter(name__in=list(allowed))
            else:
                if folder_path:
                    query = query.filter(
                        self._virtual_descendant_q(folder_path),
                    )
                prefixes = permissions.readable_prefixes(
                    self.company_user, bucket,
                )
                if prefixes is not None:
                    restriction = Q()
                    for prefix in prefixes:
                        restriction |= self._virtual_descendant_q(prefix)
                    query = query.filter(restriction)

        query = self._apply_filters(query)
        field = self._sort_field()
        query = self._annotate_sort_field(query, field)

        order_field = field if self.sort_dir == "asc" else "-%s" % field
        query = query.order_by("-entry_kind", order_field, "id")
        query = self._apply_cursor(query, field)

        results = list(query[:PAGE_SIZE + 1])
        friendly_names.resolve_display_names(results)
        is_search = scope != SCOPE_HERE
        for entry in results:
            if entry.is_folder:
                # entry.bucket, no el `bucket` de contexto: en
                # scope=global cada fila puede pertenecer a un cubo
                # distinto del que se está pisando.
                entry.nav_url = self._folder_nav_url(
                    entry.bucket, entry.blob_name,
                )
            if is_search:
                entry.display_path = self._display_path(bucket, entry)
        return results

    def _display_path(self, current_bucket, entry):
        """
        Path shown under a search result's name. Bare `parent_path`
        when the row lives in the bucket being browsed; prefixed with
        the bucket's Spanish label when it comes from another one
        (only possible under scope=global) -- otherwise two buckets
        with coincidentally identical relative paths would look like
        the same folder.

        ---

        Ruta que se muestra bajo el nombre de un resultado de
        búsqueda. `parent_path` a secas cuando la fila vive en el cubo
        que se está recorriendo; con la etiqueta en castellano del
        cubo por delante cuando viene de otro (solo posible en
        scope=global) -- si no, dos cubos con una ruta relativa
        coincidente por casualidad parecerían la misma carpeta.
        """
        if entry.bucket == current_bucket:
            return entry.parent_path
        label = BUCKET_DISPLAY_NAMES.get(entry.bucket, entry.bucket)
        return "%s/%s" % (label, entry.parent_path) if entry.parent_path \
            else label

    def _annotate_sort_field(self, query, field):
        """
        Annotate only the column the active sort actually needs.

        Bug found in production (S039, 2026-07-30): the first version
        of this method always annotated both `sort_size` and
        `sort_date` regardless of `sort_key`, so every folder listing
        -- not just date-sorted ones -- evaluated
        `Coalesce(F("gcs_updated_at"), Value(_EPOCH))`. On MySQL, a
        `Value()` with no explicit `output_field` is not adapted
        through `DateTimeField.get_prep_value()`, so the aware
        `_EPOCH` sentinel reached the driver in a shape MySQL typed as
        text rather than `DATETIME`; the result column came back a
        plain `str`, and Django's `make_aware()` converter crashed
        with `AttributeError: 'str' object has no attribute
        'utcoffset'` on every request, in production, for two of the
        three buckets (Albaranes and Directorio Principal). The
        explicit `output_field=DateTimeField()` on the `Value()` below
        is the actual fix; annotating only what the active sort needs
        is the defence in depth that also makes the common case (the
        default name sort) skip this code path entirely, exactly as
        it did before S039.

        ---

        Anota solo la columna que el orden activo necesita de verdad.

        Fallo encontrado en producción (S039, 2026-07-30): la primera
        versión de este método anotaba siempre `sort_size` y
        `sort_date` sin mirar `sort_key`, así que cualquier listado de
        carpeta -- no solo los ordenados por fecha -- evaluaba
        `Coalesce(F("gcs_updated_at"), Value(_EPOCH))`. En MySQL, un
        `Value()` sin `output_field` explícito no se adapta a través
        de `DateTimeField.get_prep_value()`, así que el centinela
        `_EPOCH` (consciente de zona horaria) llegaba al driver en una
        forma que MySQL tipaba como texto en vez de `DATETIME`; la
        columna resultante volvía como `str` plano, y el conversor
        `make_aware()` de Django fallaba con `AttributeError: 'str'
        object has no attribute 'utcoffset'` en cada petición, en
        producción, para dos de los tres cubos (Albaranes y Directorio
        Principal). El `output_field=DateTimeField()` explícito del
        `Value()` de abajo es la corrección real; anotar solo lo que
        el orden activo necesita es la defensa en profundidad que
        además hace que el caso común (el orden por nombre por
        defecto) se salte por completo esta ruta de código, igual que
        antes de S039.

        Segunda vuelta (2026-07-30, mismo día): Miguel Ángel confirmó
        que el `output_field` explícito no bastaba -- el clic en
        "Modificado" seguía sin ordenar en producción. Se añade
        `Cast(..., output_field=DateTimeField())` alrededor del
        `Coalesce` completo: fuerza el tipo `CAST(... AS DATETIME)` en
        el SQL generado, el patrón documentado para este fallo cuando
        el `output_field` por sí solo no es suficiente para que MySQL
        deje de tipar el resultado como texto.
        """
        if field == "sort_size":
            return query.annotate(
                sort_size=Coalesce(
                    Case(
                        When(
                            entry_kind=DocumentIndexEntry.KIND_FOLDER,
                            then=F("total_size_bytes"),
                        ),
                        default=F("size_bytes"),
                        output_field=BigIntegerField(),
                    ),
                    Value(0, output_field=BigIntegerField()),
                    output_field=BigIntegerField(),
                ),
            )
        if field == "sort_date":
            return query.annotate(
                sort_date=Cast(
                    Coalesce(
                        F("gcs_updated_at"),
                        Value(_EPOCH, output_field=DateTimeField()),
                        output_field=DateTimeField(),
                    ),
                    output_field=DateTimeField(),
                ),
            )
        return query

    def _apply_filters(self, query):
        """
        Name/extension/local-flag filters, independent of scope: they
        apply to a plain folder listing exactly the same as to a
        recursive search.

        ---

        Filtros de nombre/extensión/bandera local, independientes del
        alcance: se aplican igual a un listado de carpeta normal que a
        una búsqueda recursiva.
        """
        if self.filters["q"]:
            query = query.filter(name__icontains=self.filters["q"])
        if self.filters["ext"]:
            query = query.filter(
                entry_kind=DocumentIndexEntry.KIND_FILE,
                name__iendswith="." + self.filters["ext"],
            )
        if self.filters["local"] == "1":
            query = query.filter(exists_in_local=True)
        elif self.filters["local"] == "0":
            query = query.filter(exists_in_local=False)
        return query

    def _apply_cursor(self, query, field):
        """
        Restrict to rows strictly after the given cursor, in exactly
        the order the query is sorted by -- see the module docstring
        for why the comparison direction on `field` depends on
        `sort_dir` while `entry_kind` and `id` do not.

        ---

        Acota a las filas estrictamente posteriores al cursor dado, en
        el mismo orden exacto en que está ordenada la consulta -- ver
        el docstring del módulo sobre por qué la dirección de
        comparación de `field` depende de `sort_dir` mientras que
        `entry_kind` e `id` no.
        """
        request = self.request
        after_kind = request.GET.get("after_kind")
        after_id = request.GET.get("after_id")
        after_value = request.GET.get("after_value")
        if not (after_kind and after_id and after_value is not None):
            return query

        value = self._parse_cursor_value(field, after_value)
        value_lookup = "%s__gt" % field if self.sort_dir == "asc" \
            else "%s__lt" % field

        return query.filter(
            Q(entry_kind__lt=after_kind)
            | Q(entry_kind=after_kind, **{value_lookup: value})
            | Q(
                entry_kind=after_kind,
                **{field: value},
                id__gt=int(after_id),
            )
        )

    def _parse_cursor_value(self, field, raw):
        if field == "sort_size":
            return int(raw)
        if field == "sort_date":
            return parse_datetime(raw) or _EPOCH
        return raw

    def _cursor(self, entry):
        """
        Ordering triple of the last row, for the next page.

        ---

        Terna de ordenación de la última fila, para la página
        siguiente.
        """
        field = self._sort_field()
        if field == "sort_size":
            value = entry.sort_size
        elif field == "sort_date":
            value = entry.sort_date.isoformat()
        else:
            value = entry.name
        return {
            "after_kind": entry.entry_kind,
            "after_id": entry.id,
            "after_value": value,
        }


class OpenDocumentView(ExplorerAccessMixin, View):
    """
    Mint a short-lived signed URL and redirect to the object.

    The only navigation-time contact with GCS, and only because the
    user asked to see the content of one specific document.

    ---

    Acuña una URL firmada de vida corta y redirige al objeto.

    El único contacto con GCS durante la navegación, y solo porque el
    usuario ha pedido ver el contenido de un documento concreto.
    """

    def get(self, request, pk):
        entry = get_object_or_404(
            DocumentIndexEntry,
            pk=pk,
            entry_kind=DocumentIndexEntry.KIND_FILE,
            deleted_at__isnull=True,
            purged_at__isnull=True,
        )
        company_user = request.user.company_user
        grants = permissions.grants_for(company_user, entry.bucket)
        mode, _allowed = permissions.visibility(
            company_user, entry.bucket, entry.parent_path,
            grants=grants,
        )
        if mode != permissions.ALL:
            raise Http404("Sin acceso a ese documento.")

        return HttpResponseRedirect(
            generate_signed_url(entry.bucket, entry.blob_name)
        )


class SendToTrashView(ExplorerAccessMixin, View):
    """
    Logical delete into the acting user's own trash.

    ---

    Borrado lógico a la papelera del propio usuario que actúa.
    """

    def post(self, request, pk):
        entry = get_object_or_404(
            DocumentIndexEntry,
            pk=pk,
            deleted_at__isnull=True,
            purged_at__isnull=True,
        )
        company_user = request.user.company_user
        if not permissions.can_delete_in(
            company_user, entry.bucket, entry.parent_path,
        ):
            raise Http404("Sin permiso de borrado en esa carpeta.")

        entry.deleted_at = timezone.now()
        entry.deleted_by = company_user
        entry.save(update_fields=["deleted_at", "deleted_by"])

        messages.success(
            request,
            "«%s» se ha movido a tu papelera. Solo tú puedes verlo "
            "y restaurarlo." % entry.name,
        )
        return redirect(
            "%s?bucket=%s&path=%s" % (
                reverse("document_explorer:explorer"),
                entry.bucket,
                entry.parent_path,
            )
        )


class MoveScopeMixin(ExplorerAccessMixin):
    """
    Shared entry-resolution for every move-related view (H29, S039).

    Two rules, both explicit and PERMANENT decisions of Miguel Angel,
    not a v1 placeholder to loosen later:

    1. Restricted to unrestricted (ADMIN) users, always -- "de momento
       solamente yo voy a poder mover cosas aquí... ni siquiera mi
       jefe... es una decisión de una salvaguarda de seguridad total."
    2. Scoped entirely to `PRIMARY_BUCKET` (Directorio Principal real)
       -- move never touches Fotos Partes/Fotos Albaranes, neither as
       source nor as destination: "eso es inamovible, incluso ni yo
       siquiera puedo mover eso." A file that does not live in
       `PRIMARY_BUCKET` never even shows the move checkbox (see
       `_rows.html`, `entry.bucket == primary_bucket`); resolving by
       `bucket=PRIMARY_BUCKET` below is the server-side backstop for
       that same rule -- an id for a file in another bucket, however it
       reached the request, is silently dropped, never 404s the whole
       batch.

    Works over a LIST of entries throughout, not a single one: added
    for "mover todos los manuales" (S039) -- Miguel Ángel's own idea,
    built on what already existed rather than a new mechanism: filter
    the existing recursive/global search by a keyword, tick the
    checkboxes, move everything ticked in one go through the same
    modal a single file already used.

    ---

    Resolución de entrada compartida por todas las vistas de mover
    (H29, S039).

    Dos reglas, ambas decisiones explícitas y PERMANENTES de Miguel
    Ángel, no un provisional de v1 a relajar después:

    1. Restringido a usuarios sin restricción (ADMIN), siempre -- "de
       momento solamente yo voy a poder mover cosas aquí... ni
       siquiera mi jefe... es una decisión de una salvaguarda de
       seguridad total."
    2. Acotado por completo a `PRIMARY_BUCKET` (Directorio Principal
       real) -- mover nunca toca Fotos Partes/Fotos Albaranes, ni como
       origen ni como destino: "eso es inamovible, incluso ni yo
       siquiera puedo mover eso." Un archivo que no vive en
       `PRIMARY_BUCKET` ni siquiera muestra el casillero de mover (ver
       `_rows.html`, `entry.bucket == primary_bucket`); resolver por
       `bucket=PRIMARY_BUCKET` abajo es el respaldo del lado del
       servidor de esa misma regla -- un id de un archivo de otro
       cubo, llegue como llegue en la petición, se descarta en
       silencio, nunca hace fallar el lote entero con un 404.

    Trabaja sobre una LISTA de entradas de principio a fin, no sobre
    una sola: añadido para "mover todos los manuales" (S039) -- idea
    del propio Miguel Ángel, construida sobre lo que ya existía en vez
    de un mecanismo nuevo: filtrar la búsqueda recursiva/global ya
    existente por una palabra clave, marcar los casilleros, mover todo
    lo marcado de una vez por el mismo modal que ya usaba un solo
    archivo.
    """

    def _entries_or_404(self, request, pks):
        company_user = request.user.company_user
        if not permissions.is_unrestricted(company_user):
            raise Http404("Solo el administrador puede mover archivos.")
        entries = list(
            DocumentIndexEntry.objects.filter(
                pk__in=pks,
                entry_kind=DocumentIndexEntry.KIND_FILE,
                bucket=PRIMARY_BUCKET,
                deleted_at__isnull=True, purged_at__isnull=True,
            )
        )
        if not entries:
            raise Http404(
                "No hay archivos válidos seleccionados para mover."
            )
        return entries

    def _browse_context(self, entries, path):
        """
        Context for `_move_browse.html`: the modal-body fragment used
        by `MoveBrowseView` (navigating) and `MoveCreateFolderView`
        (right after creating a folder, to land inside it). The
        selected entries travel forward as hidden inputs inside the
        fragment itself (`entries` in the template) -- every further
        click inside the modal re-includes them via `hx-include`, so
        the selection never has to be re-read from the checkboxes in
        the page behind the modal after the first request.

        ---

        Contexto para `_move_browse.html`: el fragmento del cuerpo del
        modal que usan `MoveBrowseView` (al navegar) y
        `MoveCreateFolderView` (justo tras crear una carpeta, para
        aterrizar dentro de ella). Las entradas seleccionadas viajan
        hacia adelante como campos ocultos dentro del propio fragmento
        (`entries` en la plantilla) -- cada clic siguiente dentro del
        modal las vuelve a incluir vía `hx-include`, así que la
        selección no tiene que releerse de los casilleros de la
        página que hay detrás del modal después de la primera
        petición.
        """
        subfolders = list(
            DocumentIndexEntry.objects.filter(
                bucket=PRIMARY_BUCKET,
                entry_kind=DocumentIndexEntry.KIND_FOLDER,
                parent_path_hash=path_digest(path),
                deleted_at__isnull=True, purged_at__isnull=True,
            ).order_by("name").values_list("blob_name", "name")
        )
        return {
            "entries": entries,
            "entry_count": len(entries),
            "bucket": PRIMARY_BUCKET,
            "path": path,
            "path_label": path or "(raíz de Directorio Principal)",
            "parent_path": path.rsplit("/", 1)[0] if "/" in path else "",
            "has_parent": bool(path),
            "subfolders": subfolders,
        }


class MoveBrowseView(MoveScopeMixin, View):
    """
    HTMX fragment: the folder tree shown inside the move modal.
    Navigating up/down never leaves the request/response cycle -- each
    click re-fetches this same fragment for the new path and swaps the
    modal body, so the modal itself never closes while browsing.

    ---

    Fragmento HTMX: el árbol de carpetas que se muestra dentro del
    modal de mover. Subir/bajar nunca sale del ciclo petición/
    respuesta -- cada clic vuelve a pedir este mismo fragmento para la
    nueva ruta y sustituye el cuerpo del modal, así que el modal en sí
    nunca se cierra mientras se navega.
    """

    def post(self, request):
        entries = self._entries_or_404(
            request, request.POST.getlist("entries"),
        )
        path = (request.POST.get("path") or "").strip("/")
        return render(
            request, "document_explorer/_move_browse.html",
            self._browse_context(entries, path),
        )


class MoveCreateFolderView(MoveScopeMixin, View):
    """
    Create a new subfolder under the folder currently shown in the
    move modal, then land inside it -- "crear carpeta o pegar aquí,
    como un explorador de archivos."

    ---

    Crea una subcarpeta nueva bajo la carpeta que se muestra ahora
    mismo en el modal de mover, y aterriza dentro de ella -- "crear
    carpeta o pegar aquí, como un explorador de archivos."
    """

    def post(self, request):
        entries = self._entries_or_404(
            request, request.POST.getlist("entries"),
        )
        parent_path = (request.POST.get("path") or "").strip("/")
        name = (request.POST.get("folder_name") or "").strip()

        new_path = parent_path
        if not name or "/" in name:
            messages.error(request, "Nombre de carpeta no válido.")
        else:
            new_path = "%s/%s" % (parent_path, name) if parent_path \
                else name
            index_writer.ensure_folder_chain(PRIMARY_BUCKET, new_path)

        return render(
            request, "document_explorer/_move_browse.html",
            self._browse_context(entries, new_path),
        )


class MoveBatchView(MoveScopeMixin, View):
    """
    Move a batch of files (a chunk, not necessarily the whole
    selection) and report each result as JSON. The move modal's own
    JavaScript splits the full selection into chunks and calls this
    once per chunk, in sequence, painting a progress bar and a live
    log of file names as each chunk comes back -- Miguel Ángel's
    explicit request (S039), verbatim: "hay que incluir la barra de
    progreso con los nombres de archivos que se están copiando... para
    que el usuario sepa que se está haciendo algo... antes estábamos a
    ciegas totalmente."

    One request per file (`MoveOneView`, the first version of this
    endpoint) measured ~350-420 ms of real server time per file in
    production, dominated by `ensure_folder_chain` repeating the same
    existence check on every single call for a destination that, past
    the first file, already exists. Chunking cuts both costs at once:
    fewer HTTP round trips (network + Django request overhead paid
    once per chunk, not once per file), and `ensure_folder_chain` runs
    exactly once per chunk (`move_service.move_entry(..., ensure_
    folder=False)` for the rest) instead of once per file.

    ---

    Mueve un lote de archivos (un bloque, no necesariamente toda la
    selección) e informa de cada resultado en JSON. El propio
    JavaScript del modal de mover divide la selección completa en
    bloques y llama a esto una vez por bloque, en secuencia, pintando
    una barra de progreso y un registro en vivo de nombres de archivo
    según vuelve cada bloque -- petición explícita de Miguel Ángel
    (S039), verbatim: "hay que incluir la barra de progreso con los
    nombres de archivos que se están copiando... para que el usuario
    sepa que se está haciendo algo... antes estábamos a ciegas
    totalmente."

    Una petición por archivo (`MoveOneView`, la primera versión de
    este endpoint) medía ~350-420 ms de tiempo real de servidor por
    archivo en producción, dominado por `ensure_folder_chain`
    repitiendo la misma comprobación de existencia en cada llamada
    para un destino que, a partir del primer archivo, ya existe.
    Agrupar en bloques recorta los dos costes a la vez: menos viajes
    de ida y vuelta HTTP (red + gasto fijo de petición de Django
    pagado una vez por bloque, no una vez por archivo), y
    `ensure_folder_chain` se ejecuta exactamente una vez por bloque
    (`move_service.move_entry(..., ensure_folder=False)` para el
    resto) en vez de una vez por archivo.
    """

    def post(self, request):
        entries = self._entries_or_404(
            request, request.POST.getlist("entries"),
        )
        destination = (request.POST.get("destination_folder") or "").strip()

        index_writer.ensure_folder_chain(PRIMARY_BUCKET, destination)

        results = []
        for entry in entries:
            original_name = entry.name
            move_service.move_entry(
                entry, destination, ensure_folder=False,
            )
            results.append({
                "original_name": original_name,
                "final_name": entry.name,
                "renamed": entry.name != original_name,
            })

        return JsonResponse({"results": results})


class TrashView(ExplorerAccessMixin, TemplateView):
    """
    The acting user's own trash. Nobody sees anybody else's.

    ---

    La papelera del propio usuario. Nadie ve la de otro.
    """

    template_name = "document_explorer/trash.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        company_user = self.request.user.company_user
        context["active_nav"] = "document_explorer"
        context["entries"] = list(
            DocumentIndexEntry.objects.filter(
                deleted_by=company_user,
                deleted_at__isnull=False,
                purged_at__isnull=True,
            ).order_by("-deleted_at")[:PAGE_SIZE]
        )
        context["is_admin"] = permissions.is_unrestricted(company_user)
        return context


class RestoreFromTrashView(ExplorerAccessMixin, View):
    """
    Put an item back. Only its own owner may do it.

    ---

    Devolver un elemento a su sitio. Solo puede su propio dueño.
    """

    def post(self, request, pk):
        company_user = request.user.company_user
        entry = get_object_or_404(
            DocumentIndexEntry,
            pk=pk,
            deleted_by=company_user,
            deleted_at__isnull=False,
            purged_at__isnull=True,
        )
        entry.deleted_at = None
        entry.deleted_by = None
        entry.save(update_fields=["deleted_at", "deleted_by"])

        messages.success(
            request, "«%s» ha vuelto a su carpeta." % entry.name,
        )
        return redirect(reverse("document_explorer:trash"))


class PurgeTrashView(ExplorerAccessMixin, View):
    """
    Empty a trash for real. Administrator only.

    Removes the object from Google Cloud Storage and keeps the row,
    stamped with `purged_at`, as the audit record Miguel Angel asked
    for in S037: "registro histórico puede ser útil para auditorías".

    ---

    Vaciar una papelera de verdad. Solo el administrador.

    Retira el objeto de Google Cloud Storage y conserva la fila,
    sellada con `purged_at`, como el registro de auditoría que pidió
    Miguel Ángel en S037: "registro histórico puede ser útil para
    auditorías".
    """

    def post(self, request, pk):
        company_user = request.user.company_user
        if not permissions.is_unrestricted(company_user):
            raise Http404("Solo el administrador vacía la papelera.")

        entry = get_object_or_404(
            DocumentIndexEntry,
            pk=pk,
            deleted_at__isnull=False,
            purged_at__isnull=True,
        )
        if entry.entry_kind == DocumentIndexEntry.KIND_FILE:
            delete_file(entry.bucket, entry.blob_name)

        entry.purged_at = timezone.now()
        entry.purged_by = company_user
        entry.save(update_fields=["purged_at", "purged_by"])

        messages.warning(
            request,
            "«%s» se ha eliminado de Google Cloud Storage. La fila se "
            "conserva como registro de auditoría." % entry.name,
        )
        return redirect(reverse("document_explorer:trash"))
