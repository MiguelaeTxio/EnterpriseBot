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
from django.core.paginator import Paginator
from django.db.models import (
    BigIntegerField, Case, DateTimeField, F, Q, Value, When,
)
from django.db.models.functions import Cast, Coalesce
from django.http import (
    Http404, HttpResponseBadRequest, HttpResponseForbidden,
    HttpResponseNotFound, HttpResponseRedirect, JsonResponse,
)
from django.utils.crypto import constant_time_compare
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import get_object_or_404, redirect, render
from django.template.defaultfilters import filesizeformat
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views import View
from django.views.generic import TemplateView

from panel.mixins import CompanyUserRequiredMixin
from django.conf import settings
from django.db import transaction

from spare_parts.gcs_service import (
    delete_file, generate_signed_url, get_storage_client,
)

from document_explorer import friendly_names, index_writer, move_service, permissions
from document_explorer import (
    classification_service, duplicates_service, naming_service, tasks,
)
from document_explorer.buckets import (
    BUCKET_DISPLAY_NAMES, INDEXED_BUCKETS, NO_CONFORMES_PREFIX,
    PRIMARY_BUCKET, QUARANTINE_PREFIX, quarantine_scope_q,
)
from document_explorer.models import (
    DataOperationLog, DataOperationLogEntry, DocumentIndexEntry,
    DocumentTypeCatalog, path_digest,
)

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
            "can_move": permissions.is_unrestricted(company_user),
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
            "is_no_conformes_folder": (
                bucket == PRIMARY_BUCKET
                and folder_path == NO_CONFORMES_PREFIX.rstrip("/")
                and not is_search
            ),
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


class BulkTrashView(ExplorerAccessMixin, View):
    """
    Logical delete into the acting user's own trash, over a LIST of
    entries -- S042, Miguel Ángel's explicit interface-simplification
    directive: one checkbox per row, one "select all", and the
    action buttons (mover, eliminar, reencolar) all work off that
    SAME selection, never a separate parallel one per action.
    Companion to the existing single-file `SendToTrashView`, which
    stays untouched for the quick per-row trash icon -- this is the
    bulk counterpart driven by the shared `entries` checkboxes,
    exactly like `ClassifyView`/`RequeueNoConformesView` already work
    over a list.

    Real incident this avoids repeating (S042, `RequeueNoConformesView`):
    an empty `entries` list is an explicit no-op, never a fallback to
    "delete everything in the folder" -- there is no `all=1` marker
    here at all, on purpose; deleting is destructive enough that a
    silent "select nothing, delete everything" path must never exist
    for it, unlike the deliberate "Reencolar todo" button.

    Unlike `MoveScopeMixin` (admin-only, `PRIMARY_BUCKET`-only),
    delete authority is per-folder (`can_delete_in`) and has no
    bucket restriction -- a selection spanning several folders/
    buckets (only realistic from a flattened search, though search
    already disables `show_delete` entirely) is handled entry by
    entry: whichever ones the acting user lacks delete permission for
    are silently skipped, never fail the whole batch, same principle
    as `MoveScopeMixin._entries_or_404`.

    ---

    Borrado lógico a la papelera del propio usuario que actúa, sobre
    una LISTA de entradas -- S042, directriz explícita de
    simplificación de interfaz de Miguel Ángel: un casillero por fila,
    un "seleccionar todo", y los botones de acción (mover, eliminar,
    reencolar) funcionan todos sobre esa MISMA selección, nunca una
    paralela distinta por acción. Compañera del `SendToTrashView` de
    un solo archivo ya existente, que se queda intacto para el icono
    rápido de papelera por fila -- esta es la versión en bloque sobre
    los mismos casilleros `entries` compartidos, igual que
    `ClassifyView`/`RequeueNoConformesView` ya trabajan sobre una
    lista.

    Incidente real que esto evita repetir (S042,
    `RequeueNoConformesView`): una lista `entries` vacía es un no-op
    explícito, nunca un fallback a "borrar todo lo de la carpeta" --
    aquí no existe ningún marcador `all=1` a propósito; borrar es
    suficientemente destructivo como para que nunca exista un camino
    silencioso de "no selecciones nada, se borra todo", a diferencia
    del botón deliberado "Reencolar todo".

    A diferencia de `MoveScopeMixin` (solo administrador, solo
    `PRIMARY_BUCKET`), la autoridad de borrado es por carpeta
    (`can_delete_in`) y no tiene restricción de cubo -- una selección
    que abarque varias carpetas/cubos (solo realista desde una
    búsqueda aplanada, aunque la búsqueda ya desactiva `show_delete`
    por completo) se resuelve archivo a archivo: los que el usuario
    que actúa no tenga permiso de borrar se omiten en silencio, nunca
    hacen fallar el lote entero, mismo principio que
    `MoveScopeMixin._entries_or_404`.
    """

    def post(self, request):
        pks = request.POST.getlist("entries")
        if not pks:
            messages.info(
                request, "No has seleccionado ningún archivo para "
                "eliminar.",
            )
            return redirect(reverse("document_explorer:explorer"))

        entries = list(
            DocumentIndexEntry.objects.filter(
                pk__in=pks,
                deleted_at__isnull=True, purged_at__isnull=True,
            )
        )
        company_user = request.user.company_user
        deleted = 0
        skipped = 0
        redirect_bucket = None
        redirect_path = None

        for entry in entries:
            if not permissions.can_delete_in(
                company_user, entry.bucket, entry.parent_path,
            ):
                skipped += 1
                continue
            if redirect_bucket is None:
                redirect_bucket = entry.bucket
                redirect_path = entry.parent_path
            entry.deleted_at = timezone.now()
            entry.deleted_by = company_user
            entry.save(update_fields=["deleted_at", "deleted_by"])
            deleted += 1

        if deleted:
            messages.success(
                request,
                "%d archivo(s) movido(s) a tu papelera." % deleted,
            )
        if skipped:
            messages.warning(
                request,
                "%d archivo(s) omitido(s) por falta de permiso de "
                "borrado." % skipped,
            )
        if not deleted and not skipped:
            messages.info(
                request,
                "Ninguno de los archivos seleccionados sigue "
                "disponible.",
            )

        return redirect(
            "%s?bucket=%s&path=%s" % (
                reverse("document_explorer:explorer"),
                redirect_bucket or PRIMARY_BUCKET,
                redirect_path or "",
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


class MoveView(MoveScopeMixin, View):
    """
    Move every selected file in a single request -- no progress
    display. Explicit reversal by Miguel Ángel (S039) after measuring
    that even chunked batches (`MoveBatchView`, the version before
    this one) "seguía tardando bastante", and deciding the trade-off
    was not worth it, verbatim: "que le den a la visibilidad...
    vamos a probar sin visibilidad y hacerlo todo de golpe. Como mucho
    un spinner." The button's own `onsubmit` in `_move_browse.html`
    disables it and shows a Bootstrap spinner for as long as the
    browser is waiting on this view; no AJAX, no JSON, just a normal
    form POST and the same final redirect every other mutating view
    in this app already uses (`SendToTrashView`, `PurgeTrashView`...).

    Even a single request was still measured taking ~75 seconds for
    ~190 files (S039) -- `move_service.move_entries()` (not
    `move_entry()` looped) is what actually fixed that, collapsing the
    whole batch into a handful of queries regardless of size. See its
    own docstring for why.

    ---

    Mueve todos los archivos seleccionados en una única petición -- sin
    visualización de progreso. Marcha atrás explícita de Miguel Ángel
    (S039) tras medir que incluso los bloques (`MoveBatchView`, la
    versión anterior a esta) "seguía tardando bastante", y decidir que
    el compromiso no merecía la pena, verbatim: "que le den a la
    visibilidad... vamos a probar sin visibilidad y hacerlo todo de
    golpe. Como mucho un spinner." El propio `onsubmit` del botón en
    `_move_browse.html` lo desactiva y muestra un spinner de Bootstrap
    mientras el navegador espera esta vista; sin AJAX, sin JSON, solo
    un envío de formulario normal y la misma redirección final que ya
    usa cualquier otra vista mutadora de esta app (`SendToTrashView`,
    `PurgeTrashView`...).

    Incluso una sola petición se midió tardando ~75 segundos para ~190
    archivos (S039) -- `move_service.move_entries()` (no `move_entry()`
    en un bucle) es lo que lo arregló de verdad, reduciendo el lote
    entero a un puñado de consultas sea cual sea su tamaño. Ver su
    propio docstring para el porqué.
    """

    def post(self, request):
        entries = self._entries_or_404(
            request, request.POST.getlist("entries"),
        )
        destination = (request.POST.get("destination_folder") or "").strip()
        bucket = entries[0].bucket

        results = move_service.move_entries(entries, destination)

        moved = [final_name for _, final_name in results]
        renamed = [
            "%s → %s" % (original_name, final_name)
            for original_name, final_name in results
            if final_name != original_name
        ]

        destination_label = destination or "la raíz de Directorio Principal"
        if moved:
            if len(moved) == 1:
                messages.success(
                    request,
                    "«%s» se ha movido a «%s»."
                    % (moved[0], destination_label),
                )
            else:
                messages.success(
                    request,
                    "%d archivo(s) movido(s) a «%s»."
                    % (len(moved), destination_label),
                )
        if renamed:
            messages.warning(
                request,
                "Ya había un archivo con ese nombre en el destino, "
                "renombrado(s) automáticamente con un número: %s"
                % ", ".join(renamed),
            )

        return redirect(
            "%s?bucket=%s&path=%s" % (
                reverse("document_explorer:explorer"),
                bucket, destination,
            )
        )


class ClassifyView(MoveScopeMixin, View):
    """
    Batch classification (H29, S040 -- Miguel Ángel: "comenzamos ya la
    clasificación de las dos carpetas, que habrá que hacerlo ya").
    Same scope mixin as `MoveView` (admin-only, live files in
    `PRIMARY_BUCKET`) since this also fires a real, billable Gemini
    call per file.

    **Applies for real now, but only virtually** -- Miguel Ángel,
    S040: "no vamos a tocar CGS, lo vamos a hacer todo a nivel de
    base de datos." `classification_service.apply_classification()`
    only ever writes `DocumentIndexEntry.name`; the real object in GCS
    is never touched, exactly like `MoveView` above never touches
    `blob_name`. `ClassifyView` never imports anything from
    `document_ingestion`/`machine_documents`/`personal_documents`, per
    the H29 annex 3.15 isolation rule.

    **Runs in the background now, S040 -- real production incident.**
    A recursive batch over ~50 files ran one Gemini call after another
    inside a single synchronous HTTP request and blew past
    PythonAnywhere's load balancer timeout: 504, "Something went
    wrong". This view now only creates the `DataOperationLog` header
    (`status=RUNNING`) and enqueues `tasks.classify_entries_task`,
    returning immediately -- see that task's docstring for the actual
    per-file work and why it writes one `DataOperationLogEntry` right
    after each file instead of buffering to the end (the same
    incident showed that buffering loses the whole audit trail of
    already-applied renames when the request dies mid-batch).

    ---

    Clasificación por lote (H29, S040 -- Miguel Ángel: "comenzamos ya
    la clasificación de las dos carpetas, que habrá que hacerlo ya").
    Mismo mixin de alcance que `MoveView` (solo administrador,
    archivos vivos en `PRIMARY_BUCKET`) porque esto también dispara
    una llamada real y facturable a Gemini por archivo.

    **Ya aplica de verdad, pero solo de forma virtual** -- Miguel
    Ángel, S040: "no vamos a tocar CGS, lo vamos a hacer todo a nivel
    de base de datos." `classification_service.apply_classification()`
    únicamente escribe `DocumentIndexEntry.name`; el objeto real en
    GCS nunca se toca, exactamente igual que `MoveView` de arriba
    nunca toca `blob_name`. `ClassifyView` nunca importa nada de
    `document_ingestion`/`machine_documents`/`personal_documents`,
    según la regla de aislamiento 3.15 del anexo H29.

    **Corre en segundo plano ahora, S040 -- incidente real de
    producción.** Un lote recursivo sobre ~50 archivos encadenó una
    llamada a Gemini tras otra dentro de una sola petición HTTP
    síncrona y superó el tiempo límite del balanceador de
    PythonAnywhere: 504, "Something went wrong". Esta vista ahora solo
    crea la cabecera `DataOperationLog` (`status=RUNNING`) y encola
    `tasks.classify_entries_task`, devolviendo el control al momento
    -- ver el docstring de esa tarea para el trabajo real por archivo
    y por qué escribe una `DataOperationLogEntry` justo después de
    cada archivo en vez de guardarlas hasta el final (el mismo
    incidente demostró que guardarlas hasta el final pierde todo el
    rastro de auditoría de los renombrados ya aplicados cuando la
    petición muere a mitad de lote).
    """

    def post(self, request):
        entries = self._entries_or_404(
            request, request.POST.getlist("entries"),
        )
        bucket = entries[0].bucket
        path = (request.POST.get("path") or "").strip("/")
        company_user = request.user.company_user

        log = DataOperationLog.objects.create(
            operation_type=DataOperationLog.OPERATION_BATCH_CLASSIFICATION,
            performed_by=company_user,
            bucket=bucket,
            path_prefix=path,
            status=DataOperationLog.STATUS_RUNNING,
        )
        entry_pks = [entry.pk for entry in entries]
        tasks.classify_entries_task.delay(log.pk, entry_pks)

        messages.info(
            request,
            "Clasificando %d archivo(s) en segundo plano -- operación "
            "#%d. Puedes seguir el progreso en el Historial; la "
            "página se puede actualizar mientras corre."
            % (len(entry_pks), log.pk),
        )
        return redirect(
            reverse("document_explorer:operation_log_detail", args=[log.pk])
        )


class AnnotateNoConformesView(ExplorerAccessMixin, View):
    """
    Save (or clear) a supervisor annotation on ONE file living inside
    the real "NO CONFORMES" folder (H29, S042 -- roadmap decision
    3.14, extended by Miguel Ángel: an annotation the next Gemini
    call can read to disambiguate a mismatch it could not resolve on
    its own -- his own example, "DNI 74633524I -> 74633524L").

    Restricted to whoever holds delete authority over the NO
    CONFORMES folder itself (`can_delete_in` -- the ADMIN by S037's
    blanket exemption, plus any supervisor explicitly granted delete
    there): the same permission tier Miguel Ángel described as "el
    administrador o un supervisor con permisos suficientes". Scoped
    to files that actually live in that folder right now -- an
    annotation elsewhere in the tree has no defined meaning, since
    only `consume_quarantine_task` reads it, and only for files it is
    reprocessing out of `_CUARENTENA/`.

    ---

    Guarda (o borra) una anotación de supervisor sobre UN archivo que
    vive dentro de la carpeta real "NO CONFORMES" (H29, S042 --
    decisión 3.14 de la hoja de ruta, ampliada por Miguel Ángel: una
    anotación que la siguiente llamada a Gemini pueda leer para
    desambiguar un fallo que no pudo resolver por su cuenta -- su
    propio ejemplo, "DNI 74633524I -> 74633524L").

    Restringido a quien tenga autoridad de borrado sobre la propia
    carpeta NO CONFORMES (`can_delete_in` -- el ADMIN por la exención
    general de S037, más cualquier supervisor con borrado concedido
    ahí): el mismo nivel de permiso que Miguel Ángel describió como
    "el administrador o un supervisor con permisos suficientes".
    Acotado a archivos que viven de verdad en esa carpeta ahora mismo
    -- una anotación en cualquier otro punto del árbol no tiene
    significado definido, porque solo la lee `consume_quarantine_task`,
    y solo para archivos que está reprocesando desde `_CUARENTENA/`.
    """

    def post(self, request, pk):
        no_conformes_path = NO_CONFORMES_PREFIX.rstrip("/")
        entry = get_object_or_404(
            DocumentIndexEntry,
            pk=pk,
            entry_kind=DocumentIndexEntry.KIND_FILE,
            bucket=PRIMARY_BUCKET,
            parent_path=no_conformes_path,
            deleted_at__isnull=True, purged_at__isnull=True,
        )
        company_user = request.user.company_user
        if not permissions.can_delete_in(
            company_user, PRIMARY_BUCKET, no_conformes_path,
        ):
            raise Http404(
                "Sin permiso para anotar archivos de No Conformes."
            )

        note = (request.POST.get("curator_note") or "").strip()
        entry.curator_note = note
        entry.curator_note_by = company_user if note else None
        entry.curator_note_at = timezone.now() if note else None
        entry.save(update_fields=[
            "curator_note", "curator_note_by", "curator_note_at",
        ])

        if note:
            messages.success(
                request, "Anotación guardada en «%s»." % entry.name,
            )
        else:
            messages.info(
                request, "Anotación eliminada de «%s»." % entry.name,
            )
        return redirect(
            "%s?bucket=%s&path=%s" % (
                reverse("document_explorer:explorer"),
                PRIMARY_BUCKET, no_conformes_path,
            )
        )


class RequeueNoConformesView(ExplorerAccessMixin, View):
    """
    Move live files inside "NO CONFORMES" back into `_CUARENTENA/` in
    one shot (H29 roadmap, decision 3.14, corrected S041 -- Miguel
    Ángel's own correction of his first wording: "cuando cuarentena
    esté vacía" was wrong; requeuing is manual, triggered on the
    folder itself, with no relation whatsoever to the state of the
    queue).

    **Two independent trigger paths, S042 -- Miguel Ángel filtered by
    "manual" inside NO CONFORMES, ticked every result, and asked
    whether the single button would requeue everything or only the
    ticked ones.** It requeued everything, since nothing read a
    selection -- a real gap once the folder holds a mix of files that
    deserve different treatment (some belong straight in a real
    folder via a plain move, never back through Gemini). Fixed by
    reading an OPTIONAL `entries` POST list -- **but that first fix
    had its own real incident, same session**: Miguel Ángel ticked 2
    files in the *other* checkbox column (`classify-form`, for Mover/
    Clasificar) by mistake, hit "Reencolar seleccionados" with
    `requeue-selected-form` genuinely empty, and an empty selection
    silently fell through to "requeue everything" -- 133 files moved
    when he wanted 2. An empty selection must never mean "everything"
    by default; "everything" now requires the explicit `all=1` marker
    that only the self-contained "Reencolar todo" `<form>` sends:

    - `entries` present and non-empty (`_rows.html`'s per-row
      checkbox, tied via `form="requeue-selected-form"`, never inside
      the same `<form>` as the "Reencolar todo" button so ticking
      boxes can never change what that other button does) -- only
      those rows, intersected with what is actually still live in NO
      CONFORMES right now (a stale pk from an already-moved/annotated-
      elsewhere row is silently dropped, never 404s the whole batch,
      same principle as `MoveScopeMixin._entries_or_404`).
    - `entries` empty AND `all=1` present (the plain "Reencolar todo"
      button, its own self-contained `<form>` with the hidden marker
      and no checkboxes at all) -- every live file in the folder,
      exactly the original all-or-nothing behaviour.
    - `entries` empty AND no `all=1` (anything else, including a
      genuinely empty `requeue-selected-form` submission) -- explicit
      no-op with a message, never a guess.

    `blob_name` never changes (4.12), so `quarantine_domain_for_entry`
    still reads the correct original domain off it regardless of how
    many times a file has bounced between quarantine and NO
    CONFORMES. Any `curator_note` a supervisor left travels with the
    row untouched -- the next `consume_quarantine_task` pass reads it
    straight off `entry` via `classify_entry`.

    Same permission tier as `AnnotateNoConformesView`
    (`can_delete_in` over the NO CONFORMES folder) -- reencolar is as
    much a management action over that folder as deleting from it.

    ---

    Mueve archivos vivos dentro de "NO CONFORMES" de vuelta a
    `_CUARENTENA/` (hoja de ruta H29, decisión 3.14, corregida en
    S041 -- corrección del propio Miguel Ángel sobre su primera
    redacción: "cuando cuarentena esté vacía" era incorrecto; el
    reencolado es manual, disparado sobre la propia carpeta, sin
    ninguna relación con el estado de la cola).

    **Dos caminos de disparo independientes, S042 -- Miguel Ángel
    filtró por "manual" dentro de NO CONFORMES, marcó todos los
    resultados, y preguntó si el único botón existente reencolaría
    todo o solo lo marcado.** Reencolaba todo, porque nada leía
    ninguna selección -- un hueco real en cuanto la carpeta mezcla
    archivos que merecen trato distinto (algunos van directos a una
    carpeta real mediante un simple mover, sin volver a pasar nunca
    por Gemini). Corregido leyendo una lista `entries` OPCIONAL en el
    POST -- **pero ese primer arreglo tuvo su propio incidente real,
    misma sesión**: Miguel Ángel marcó 2 archivos en la *otra* columna
    de casilleros (`classify-form`, la de Mover/Clasificar) por error,
    pulsó "Reencolar seleccionados" con `requeue-selected-form`
    genuinamente vacío, y una selección vacía caía en silencio a
    "reencolar todo" -- 133 archivos movidos cuando quería 2. Una
    selección vacía nunca debe significar "todo" por defecto; "todo"
    ahora exige el marcador explícito `all=1` que solo envía el
    `<form>` autocontenido de "Reencolar todo":

    - `entries` presente y no vacía (casillero por fila de
      `_rows.html`, ligado vía `form="requeue-selected-form"`, nunca
      dentro del mismo `<form>` que el botón "Reencolar todo" para que
      marcar casilleros nunca pueda cambiar lo que hace ese otro
      botón) -- solo esas filas, cruzadas con lo que sigue vivo de
      verdad en NO CONFORMES ahora mismo (un pk obsoleto de una fila
      ya movida/anotada en otro sitio se descarta en silencio, nunca
      hace fallar el lote entero con un 404, mismo principio que
      `MoveScopeMixin._entries_or_404`).
    - `entries` vacía Y `all=1` presente (el botón simple "Reencolar
      todo", su propio `<form>` autocontenido con el marcador oculto
      y sin ningún casillero) -- todos los archivos vivos de la
      carpeta, exactamente el comportamiento original de todo-o-nada.
    - `entries` vacía Y sin `all=1` (cualquier otro caso, incluido un
      envío de `requeue-selected-form` genuinamente vacío) -- no-op
      explícito con un aviso, nunca una suposición.

    `blob_name` nunca cambia (4.12), así que `quarantine_domain_for_entry`
    sigue leyendo el dominio original correcto sobre él, sea cual sea
    el número de veces que un archivo haya rebotado entre cuarentena
    y NO CONFORMES. Cualquier `curator_note` que haya dejado un
    supervisor viaja intacta con la fila -- la siguiente pasada de
    `consume_quarantine_task` la lee directamente de `entry` vía
    `classify_entry`.

    Mismo nivel de permiso que `AnnotateNoConformesView`
    (`can_delete_in` sobre la carpeta NO CONFORMES) -- reencolar es
    tan una acción de gestión sobre esa carpeta como borrar de ella.
    """

    def post(self, request):
        no_conformes_path = NO_CONFORMES_PREFIX.rstrip("/")
        company_user = request.user.company_user
        if not permissions.can_delete_in(
            company_user, PRIMARY_BUCKET, no_conformes_path,
        ):
            raise Http404(
                "Sin permiso para reencolar archivos de No Conformes."
            )

        query = DocumentIndexEntry.objects.filter(
            bucket=PRIMARY_BUCKET,
            entry_kind=DocumentIndexEntry.KIND_FILE,
            parent_path=no_conformes_path,
            deleted_at__isnull=True, purged_at__isnull=True,
        )
        selected_pks = request.POST.getlist("entries")
        is_all = request.POST.get("all") == "1"
        if selected_pks:
            query = query.filter(pk__in=selected_pks)
        elif not is_all:
            # Incidente real S042: una selección vacía enviada desde
            # "Reencolar seleccionados" (form=requeue-selected-form,
            # sin marcador "all") caía por error en el mismo camino
            # que "Reencolar todo" -- Miguel Ángel marcó 2 archivos en
            # el casillero equivocado (mover/clasificar), el de
            # reencolar llegó vacío, y una selección vacía se trataba
            # en silencio como "todo" -- 133 archivos reencolados sin
            # querer. Ahora "todo" SOLO ocurre con el marcador
            # explícito que únicamente lleva el <form> autocontenido
            # de "Reencolar todo a cuarentena" -- cualquier envío sin
            # entries y sin ese marcador es un no-op explícito, nunca
            # una suposición.
            messages.info(
                request, "No has seleccionado ningún archivo para "
                "reencolar.",
            )
            return redirect(
                "%s?bucket=%s&path=%s" % (
                    reverse("document_explorer:explorer"),
                    PRIMARY_BUCKET, no_conformes_path,
                )
            )
        is_partial = bool(selected_pks)
        entries = list(query)
        if not entries:
            messages.info(
                request,
                "Ninguno de los archivos marcados sigue en No "
                "Conformes." if is_partial else "No Conformes está "
                "vacía.",
            )
            return redirect(
                "%s?bucket=%s&path=%s" % (
                    reverse("document_explorer:explorer"),
                    PRIMARY_BUCKET, no_conformes_path,
                )
            )

        log = DataOperationLog.objects.create(
            operation_type=(
                DataOperationLog.OPERATION_REQUEUE_NO_CONFORMES
            ),
            performed_by=company_user,
            bucket=PRIMARY_BUCKET,
            path_prefix=no_conformes_path,
            status=DataOperationLog.STATUS_RUNNING,
        )
        quarantine_path = QUARANTINE_PREFIX.rstrip("/")
        with transaction.atomic():
            for group_number, entry in enumerate(entries, start=1):
                move_service.move_entry(entry, quarantine_path)
                DataOperationLogEntry.objects.create(
                    log=log,
                    group_number=group_number,
                    action=DataOperationLogEntry.ACTION_RELOCATED,
                    index_entry=entry,
                    bucket=entry.bucket,
                    blob_name=entry.blob_name,
                    name=entry.name,
                    parent_path=entry.parent_path,
                    size_bytes=entry.size_bytes,
                    crc32c=entry.crc32c,
                    detail=(
                        "Reencolada a cuarentena a mano%s"
                        % (
                            " -- con anotación del supervisor "
                            "para Gemini" if entry.curator_note else ""
                        )
                    ),
                )
            log.groups_count = len(entries)
            log.kept_count = len(entries)
            log.status = DataOperationLog.STATUS_COMPLETED
            log.save(update_fields=[
                "groups_count", "kept_count", "status",
            ])

        messages.success(
            request,
            "%d archivo(s) reencolado(s) a cuarentena." % len(entries),
        )
        return redirect(
            reverse("document_explorer:operation_log_detail", args=[log.pk])
        )


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


class DuplicatesView(ExplorerAccessMixin, TemplateView):
    """
    Read-only duplicate report over `PRIMARY_BUCKET`, browsable from
    the panel -- Miguel Ángel, S040: "Eliminar los duplicados de los
    manuales y de bueno y de todo (...) no lo he visto en la
    interfaz." `duplicates_service.find_duplicate_groups()` was built
    earlier this session but never wired to any view -- this closes
    that gap.

    Admin-only, same criterion as moving/classifying (`can_move` /
    `permissions.is_unrestricted`), since acting on a duplicate found
    here can touch files across folders with mixed permissions.

    Deliberately does NOT pre-select anything for deletion -- exact
    duplicates being byte-identical doesn't tell us which path is the
    "right" one to keep, and guessing would violate the platform's own
    "Gemini/el sistema propone, el humano confirma" principle just as
    much as if a machine picked it silently. Every checkbox starts
    unchecked; Miguel Ángel picks which copies go to his trash.

    ---

    Informe de duplicados de solo lectura sobre `PRIMARY_BUCKET`,
    navegable desde el panel -- Miguel Ángel, S040: "Eliminar los
    duplicados de los manuales y de bueno y de todo (...) no lo he
    visto en la interfaz." `duplicates_service.find_duplicate_groups()`
    se construyó antes en esta misma sesión pero nunca se conectó a
    ninguna vista -- esto cierra ese hueco.

    Solo administrador, mismo criterio que mover/clasificar
    (`can_move` / `permissions.is_unrestricted`), porque actuar sobre
    un duplicado encontrado aquí puede tocar archivos de carpetas con
    permisos distintos.

    Deliberadamente NO preselecciona nada para borrar -- que los
    duplicados exactos sean idénticos byte a byte no dice cuál ruta es
    la "correcta" para conservar, y adivinarlo violaría el mismo
    principio de la plataforma de que "el sistema propone, el humano
    confirma" igual que si lo decidiera una máquina en silencio. Todas
    las casillas arrancan sin marcar; Miguel Ángel elige qué copias
    van a su papelera.

    El listado detallado, fila a fila, se acota a `_MANUAL_LIST_LIMIT`
    grupos -- con miles de grupos reales (S040: 3.570), pintar cada
    fila de cada copia de cada grupo en una sola página sería una
    respuesta enorme para un caso de uso que, según el propio Miguel
    Ángel, prefiere resolver todo de golpe. El botón de resolución
    automática (`ResolveDuplicatesView`) no tiene ese límite -- opera
    sobre todos los grupos encontrados, los liste esta vista o no.
    """

    template_name = "document_explorer/duplicates.html"
    _MANUAL_LIST_LIMIT = 200

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        company_user = self.request.user.company_user
        if not permissions.is_unrestricted(company_user):
            raise Http404("Solo el administrador puede ver duplicados.")

        path_prefix = (self.request.GET.get("path") or "").strip("/")
        groups = duplicates_service.find_duplicate_groups(
            PRIMARY_BUCKET, path_prefix,
        )
        total_wasted = sum(
            (group[0].size_bytes or 0) * (len(group) - 1) for group in groups
        )
        context.update({
            "active_nav": "document_explorer",
            "path_prefix": path_prefix,
            "groups": groups[:self._MANUAL_LIST_LIMIT],
            "group_count": len(groups),
            "manual_list_limit": self._MANUAL_LIST_LIMIT,
            "total_wasted": total_wasted,
        })
        return context


class SendDuplicatesToTrashView(ExplorerAccessMixin, View):
    """
    Sends every checked entry to ITS OWN owner's trash -- the same
    logical, two-tier delete `SendToTrashView` already uses for a
    single file (S037 design, 3.6/3.10 of the H29 annex), just batched
    for a set of duplicate rows instead of one row from a click.
    Never a hard delete: still recoverable from the trash, still
    purged only by the administrator.

    One bad row (permission denied, already gone) never aborts the
    rest of the batch -- same tolerance already used by `MoveView`/
    `ClassifyView`.

    ---

    Envía cada entrada marcada a la papelera de SU PROPIO dueño --
    el mismo borrado lógico de dos niveles que ya usa `SendToTrashView`
    para un solo archivo (diseño de S037, 3.6/3.10 del anexo H29), solo
    que en lote para un conjunto de filas duplicadas en vez de una fila
    por clic. Nunca un borrado duro: sigue siendo recuperable desde la
    papelera, sigue vaciándose solo por el administrador.

    Una fila mala (permiso denegado, ya desaparecida) nunca aborta el
    resto del lote -- misma tolerancia que ya usan `MoveView`/
    `ClassifyView`.
    """

    def post(self, request):
        company_user = request.user.company_user
        path_prefix = (request.POST.get("path") or "").strip("/")
        pks = request.POST.getlist("entries")
        entries = DocumentIndexEntry.objects.filter(
            pk__in=pks,
            bucket=PRIMARY_BUCKET,
            entry_kind=DocumentIndexEntry.KIND_FILE,
            deleted_at__isnull=True, purged_at__isnull=True,
        )

        sent, denied = 0, 0
        for entry in entries:
            if not permissions.can_delete_in(
                company_user, entry.bucket, entry.parent_path,
            ):
                denied += 1
                continue
            entry.deleted_at = timezone.now()
            entry.deleted_by = company_user
            entry.save(update_fields=["deleted_at", "deleted_by"])
            sent += 1

        if sent:
            messages.success(
                request,
                "%d duplicado(s) enviado(s) a tu papelera." % sent,
            )
        if denied:
            messages.warning(
                request,
                "%d archivo(s) no se enviaron por falta de permiso en "
                "su carpeta." % denied,
            )
        if not sent and not denied:
            messages.info(request, "No se marcó ningún duplicado.")

        return redirect(
            "%s?path=%s" % (
                reverse("document_explorer:duplicates"), path_prefix,
            )
        )


class ResolveDuplicatesView(ExplorerAccessMixin, View):
    """
    Keep exactly one copy of every duplicate group, send every other
    copy to trash -- all in one click, no per-row checkbox. Miguel
    Ángel, S040, after seeing 3.570 real groups: "Esto es un rollo (...)
    Yo lo que quiero es una única copia de cada uno de los archivos. Y
    todas las demás copias a la papelera (...) me da igual dónde
    estén." Which copy survives is arbitrary and explicitly doesn't
    matter to him -- content is byte-identical by definition (same
    `crc32c`+`size_bytes`), and where a file virtually sits stops
    mattering once classification is done at the machine/person level,
    not by folder.

    Two queries total for the actual trashing, regardless of how many
    thousands of groups there are -- one `UPDATE ... WHERE pk IN (...)`
    (same discipline `move_service.move_entries()` already applies for
    exactly this reason, S039), never one `.save()` per row. The audit
    log (`DataOperationLog`/`DataOperationLogEntry`, see their
    docstrings) is written with two more queries: one `INSERT` for the
    log header, one `bulk_create` for every line.

    Still never a hard delete -- every trashed row is fully
    recoverable until an administrator purges it, same two-tier trash
    as everywhere else in this app.

    ---

    Conserva exactamente una copia de cada grupo de duplicados, envía
    cualquier otra copia a la papelera -- todo en un clic, sin casillas
    una a una. Miguel Ángel, S040, al ver 3.570 grupos reales: "Esto es
    un rollo (...) Yo lo que quiero es una única copia de cada uno de
    los archivos. Y todas las demás copias a la papelera (...) me da
    igual dónde estén." Qué copia sobrevive es arbitrario y
    explícitamente no le importa -- el contenido es idéntico byte a
    byte por definición (mismo `crc32c`+`size_bytes`), y dónde vive
    virtualmente un archivo deja de importar en cuanto la clasificación
    se hace a nivel de máquina/persona, no por carpeta.

    Dos consultas en total para el envío a papelera en sí, sea cual sea
    el número de miles de grupos -- un único `UPDATE ... WHERE pk IN
    (...)` (misma disciplina que ya aplica `move_service.move_entries()`
    por el mismo motivo, S039), nunca un `.save()` por fila. El registro
    de auditoría (`DataOperationLog`/`DataOperationLogEntry`, ver sus
    docstrings) se escribe con dos consultas más: un `INSERT` para la
    cabecera, un `bulk_create` para todas las líneas.

    Sigue sin ser nunca un borrado duro -- cada fila enviada a papelera
    es totalmente recuperable hasta que un administrador la vacíe,
    misma papelera de dos niveles que en el resto de esta app.
    """

    def post(self, request):
        company_user = request.user.company_user
        if not permissions.is_unrestricted(company_user):
            raise Http404("Solo el administrador puede resolver duplicados.")

        path_prefix = (request.POST.get("path") or "").strip("/")
        groups = duplicates_service.find_duplicate_groups(
            PRIMARY_BUCKET, path_prefix,
        )
        if not groups:
            messages.info(request, "No hay duplicados que resolver.")
            return redirect(
                "%s?path=%s" % (
                    reverse("document_explorer:duplicates"), path_prefix,
                )
            )

        kept_entries = []
        trashed_entries = []
        # [(group_number, action, entry), ...] -- built once, linear in
        # total entries. group_number is 1-indexed and is what lets the
        # detail view/template reconstruct "this was kept, these were
        # its trashed siblings" instead of a flat, uncorrelated list
        # (S040 incident: Miguel Ángel couldn't tell what corresponded
        # to what).
        log_lines = []
        for group_number, group in enumerate(groups, start=1):
            keep, *rest = group
            kept_entries.append(keep)
            log_lines.append(
                (group_number, DataOperationLogEntry.ACTION_KEPT, keep),
            )
            for dup in rest:
                trashed_entries.append(dup)
                log_lines.append(
                    (group_number, DataOperationLogEntry.ACTION_TRASHED, dup),
                )

        trash_pks = [entry.pk for entry in trashed_entries]
        bytes_recovered = sum(
            (entry.size_bytes or 0) for entry in trashed_entries
        )
        now = timezone.now()

        DocumentIndexEntry.objects.filter(pk__in=trash_pks).update(
            deleted_at=now, deleted_by=company_user,
        )

        log = DataOperationLog.objects.create(
            operation_type=DataOperationLog.OPERATION_DUPLICATE_RESOLUTION,
            performed_by=company_user,
            bucket=PRIMARY_BUCKET,
            path_prefix=path_prefix,
            groups_count=len(groups),
            kept_count=len(kept_entries),
            trashed_count=len(trashed_entries),
            bytes_recovered=bytes_recovered,
        )
        DataOperationLogEntry.objects.bulk_create([
            DataOperationLogEntry(
                log=log,
                group_number=group_number,
                action=action,
                index_entry=entry,
                bucket=entry.bucket,
                blob_name=entry.blob_name,
                name=entry.name,
                parent_path=entry.parent_path,
                size_bytes=entry.size_bytes,
                crc32c=entry.crc32c,
            )
            for group_number, action, entry in log_lines
        ])

        messages.success(
            request,
            "%d grupo(s) resueltos: %d copia(s) conservadas, %d "
            "enviada(s) a la papelera (%s recuperables). Historial: "
            "operación #%d."
            % (
                len(groups), len(kept_entries), len(trashed_entries),
                filesizeformat(bytes_recovered), log.pk,
            ),
        )
        return redirect(
            reverse("document_explorer:operation_log_detail", args=[log.pk])
        )


class QuarantineStatusView(ExplorerAccessMixin, TemplateView):
    """
    Live status of quarantine and its Always-on Task (H29, S040) --
    Miguel Ángel: "no tenemos ningún visor del trabajo del worker,
    sería más que interesante saber qué ocurre." The Historial already
    records what `consume_quarantine_task` does once it runs (3.33),
    but nothing showed the backlog itself or when the task last ran
    without digging through it -- this page is exactly that at-a-glance
    view: how many files are still waiting, split by domain, plus the
    most recent `QUARANTINE_CONSUME` run's own summary.

    Read-only, cheap -- one count query per domain plus a `.first()`
    on `DataOperationLog`, no different in cost from any other
    explorer page. Admin-only, same as the rest of this module's
    write-adjacent views.

    ---

    Estado en vivo de la cuarentena y su Always-on Task (H29, S040) --
    Miguel Ángel: "no tenemos ningún visor del trabajo del worker,
    sería más que interesante saber qué ocurre." El Historial ya
    registra lo que hace `consume_quarantine_task` una vez corre
    (3.33), pero nada mostraba la cola en sí ni cuándo corrió por
    última vez sin rebuscar -- esta página es justo esa vista de un
    vistazo: cuántos archivos quedan esperando, repartidos por
    dominio, más el resumen de la última pasada real de
    `QUARANTINE_CONSUME`.

    Solo lectura, barata -- una consulta de conteo por dominio más un
    `.first()` sobre `DataOperationLog`, ningún coste distinto al de
    cualquier otra página del explorador. Solo administrador, igual
    que el resto de vistas de este módulo adyacentes a escritura.
    """

    template_name = "document_explorer/quarantine_status.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        company_user = self.request.user.company_user
        if not permissions.is_unrestricted(company_user):
            raise Http404("Solo el administrador puede ver la cuarentena.")

        live_files = DocumentIndexEntry.objects.filter(
            quarantine_scope_q(),
            bucket=PRIMARY_BUCKET,
            entry_kind=DocumentIndexEntry.KIND_FILE,
            deleted_at__isnull=True,
            purged_at__isnull=True,
        )
        machine_prefix = QUARANTINE_PREFIX + "DOC. MAQUINAS/"
        personal_prefix = QUARANTINE_PREFIX + "DOC. PERSONAL/"

        last_run = DataOperationLog.objects.filter(
            operation_type=DataOperationLog.OPERATION_QUARANTINE_CONSUME,
        ).order_by("-performed_at").first()

        # Bug real detectado por Miguel Ángel (S040): mientras la
        # tarea está RUNNING, groups_count/kept_count/trashed_count
        # del propio log siguen a 0 -- solo se cierran al terminar
        # (mismo patrón ya corregido para el detalle, 3.28). Contar
        # las líneas reales, nunca fiarse de esos campos si el estado
        # no es COMPLETED.
        last_run_processed = last_run_relocated = last_run_pending = 0
        if last_run:
            if last_run.status == DataOperationLog.STATUS_COMPLETED:
                last_run_processed = last_run.groups_count
                last_run_relocated = last_run.kept_count
                last_run_pending = last_run.trashed_count
            else:
                entries = DataOperationLogEntry.objects.filter(log=last_run)
                last_run_processed = entries.count()
                last_run_relocated = entries.filter(
                    action=DataOperationLogEntry.ACTION_RELOCATED,
                ).count()
                last_run_pending = last_run_processed - last_run_relocated

        no_conformes_pending = DocumentIndexEntry.objects.filter(
            bucket=PRIMARY_BUCKET,
            entry_kind=DocumentIndexEntry.KIND_FILE,
            deleted_at__isnull=True,
            purged_at__isnull=True,
            parent_path=NO_CONFORMES_PREFIX.rstrip("/"),
        ).count()

        total_pending = live_files.count()
        machine_pending = live_files.filter(
            parent_path__startswith=machine_prefix,
        ).count()
        personal_pending = live_files.filter(
            parent_path__startswith=personal_prefix,
        ).count()

        context.update({
            "active_nav": "document_explorer",
            "total_pending": total_pending,
            "machine_pending": machine_pending,
            "personal_pending": personal_pending,
            "unknown_domain_pending": (
                total_pending - machine_pending - personal_pending
            ),
            "no_conformes_pending": no_conformes_pending,
            "no_conformes_path": NO_CONFORMES_PREFIX.rstrip("/"),
            "primary_bucket": PRIMARY_BUCKET,
            "last_run": last_run,
            "last_run_processed": last_run_processed,
            "last_run_relocated": last_run_relocated,
            "last_run_pending": last_run_pending,
            "batch_size": tasks._QUARANTINE_CONSUME_BATCH_SIZE,
        })
        return context


class DataOperationLogListView(ExplorerAccessMixin, TemplateView):
    """
    History of bulk database-only operations (H29, S040) -- Miguel
    Ángel: "tenemos que dejar un informe (...) un historial de qué
    hemos hecho (...) para poder hacer una auditoría en el momento que
    queramos." Admin-only, same as the operations themselves.

    ---

    Historial de operaciones masivas de solo base de datos (H29,
    S040) -- Miguel Ángel: "tenemos que dejar un informe (...) un
    historial de qué hemos hecho (...) para poder hacer una auditoría
    en el momento que queramos." Solo administrador, igual que las
    propias operaciones.
    """

    template_name = "document_explorer/operation_log_list.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        company_user = self.request.user.company_user
        if not permissions.is_unrestricted(company_user):
            raise Http404("Solo el administrador puede ver el historial.")
        context["active_nav"] = "document_explorer"
        context["logs"] = DataOperationLog.objects.all()[:PAGE_SIZE]
        return context


class DataOperationLogDetailView(ExplorerAccessMixin, TemplateView):
    """
    Group-by-group detail of one `DataOperationLog` -- **not** a flat
    line list. Real incident, S040: the first version paginated and
    ordered by name/path, which scattered a group's "Conservada" line
    away from its own "Enviada a papelera" siblings; Miguel Ángel
    (verbatim): "no te puedo decir a qué corresponde lo que pone que
    está en papelera ni a qué corresponde lo que se ha conservado (...)
    esto (...) lo único que me da a entender es que no sabemos lo que
    hemos hecho." Fixed by pagination over `group_number` (added in
    migration 0006, backfilled for the run that already happened) --
    each page is a fixed number of whole groups, kept entry and all its
    trashed siblings always rendered together, mirroring the same card
    layout `DuplicatesView` already uses so the two screens read the
    same way.

    Paginating over group COUNT (not entry count) means a page's exact
    row count varies with how many copies each group had (a
    triplicate/quadruplicate group renders more rows than a plain
    duplicate) -- intentional, the alternative (splitting a group
    across two pages) would reintroduce exactly the same correlation
    problem this fixes.

    ---

    Detalle grupo a grupo de un `DataOperationLog` -- **no** una lista
    plana de líneas. Incidente real, S040: la primera versión paginaba
    y ordenaba por nombre/ruta, lo que dispersaba la línea "Conservada"
    de un grupo lejos de sus propias líneas "Enviada a papelera"
    hermanas; Miguel Ángel, verbatim: "no te puedo decir a qué
    corresponde lo que pone que está en papelera ni a qué corresponde
    lo que se ha conservado (...) esto (...) lo único que me da a
    entender es que no sabemos lo que hemos hecho." Corregido paginando
    sobre `group_number` (añadido en la migración 0006, rellenado hacia
    atrás para la ejecución que ya había ocurrido) -- cada página es un
    número fijo de grupos completos, la conservada y todas sus
    hermanas de papelera siempre se pintan juntas, replicando la misma
    tarjeta que ya usa `DuplicatesView` para que las dos pantallas se
    lean igual.

    Paginar por número de GRUPOS (no de líneas) significa que el
    número exacto de filas de una página varía según cuántas copias
    tuviera cada grupo (un grupo triplicado/cuadriplicado pinta más
    filas que un duplicado simple) -- intencional, la alternativa
    (partir un grupo entre dos páginas) reintroduciría exactamente el
    mismo problema de correlación que esto corrige.
    """

    template_name = "document_explorer/operation_log_detail.html"
    _GROUPS_PER_PAGE = 50

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        company_user = self.request.user.company_user
        if not permissions.is_unrestricted(company_user):
            raise Http404("Solo el administrador puede ver el historial.")

        log = get_object_or_404(DataOperationLog, pk=kwargs["pk"])

        group_numbers = list(
            log.entries.order_by("group_number")
            .values_list("group_number", flat=True).distinct()
        )
        paginator = Paginator(group_numbers, self._GROUPS_PER_PAGE)
        page_number = self.request.GET.get("page") or 1
        group_page = paginator.get_page(page_number)

        entries = list(
            log.entries
            .filter(group_number__in=list(group_page))
            .order_by("group_number", "action")
        )
        groups = {}
        for entry in entries:
            groups.setdefault(entry.group_number, []).append(entry)

        context.update({
            "active_nav": "document_explorer",
            "log": log,
            "processed_count": len(group_numbers),
            "group_page": group_page,
            "groups": groups,
        })
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


@method_decorator(csrf_exempt, name="dispatch")
class RegisterUploadedObjectView(View):
    """
    Webhook: `POST /panel/documentacion/explorador/agente/registrar/`.
    Called by the H28 migration agent right after it finishes
    uploading one object to GCS -- writes the `DocumentIndexEntry`
    row (and its ancestor folder chain) at that same moment, so the
    panel never depends on any refresh/poll to see a just-uploaded
    file. Miguel Ángel, S040: "cuando se sube, realmente se graba el
    archivo en GCS (...) y a la misma vez anotamos en base de datos
    dónde se encuentra el archivo (...) no debe de ser necesario
    refrescar desde Google Cloud Storage."

    Not a Django session/CompanyUser caller -- the agent only holds a
    GCS service account key, no platform login -- so this is
    authenticated by a separate shared bearer token
    (`settings.H28_AGENT_API_TOKEN`), compared with
    `constant_time_compare` to avoid a timing side-channel, never a
    plain `==`. `csrf_exempt` for the same reason every other webhook
    in this project is (`whatsapp.views.IncomingWhatsAppView`,
    `vox_bridge.views`): the caller is not a browser with a Django
    session, so there is no CSRF token to check in the first place.

    Trusts GCS, not the agent's own claims about the file -- reads the
    blob's real metadata itself (one targeted `get_blob` call, the
    same kind of one-off GCS touch already allowed for opening a
    document) rather than accepting client-supplied size/hash in the
    POST body. The agent only has to say WHICH object it just wrote,
    never describe it.

    Payload/status codes are between the agent and this view only --
    never a browser-facing endpoint, so no `messages`, no template.

    ---

    Webhook: `POST /panel/documentacion/explorador/agente/registrar/`.
    Llamado por el agente de migración H28 justo después de terminar
    de subir un objeto a GCS -- escribe la fila `DocumentIndexEntry`
    (y su cadena de carpetas ancestras) en ese mismo momento, así el
    panel nunca depende de ningún refresco/sondeo para ver un archivo
    recién subido. Miguel Ángel, S040: "cuando se sube, realmente se
    graba el archivo en GCS (...) y a la misma vez anotamos en base de
    datos dónde se encuentra el archivo (...) no debe de ser necesario
    refrescar desde Google Cloud Storage."

    No es un llamante con sesión Django/CompanyUser -- el agente solo
    tiene una clave de cuenta de servicio de GCS, sin inicio de sesión
    en la plataforma -- así que se autentica con un token compartido
    aparte (`settings.H28_AGENT_API_TOKEN`), comparado con
    `constant_time_compare` para evitar un canal lateral de tiempo,
    nunca un `==` plano. `csrf_exempt` por el mismo motivo que
    cualquier otro webhook de este proyecto
    (`whatsapp.views.IncomingWhatsAppView`, `vox_bridge.views`): quien
    llama no es un navegador con sesión Django, así que no hay ningún
    token CSRF que comprobar en primer lugar.

    Confía en GCS, no en lo que el agente diga del archivo -- lee los
    metadatos reales del blob por sí misma (una llamada dirigida a
    `get_blob`, el mismo tipo de toque puntual a GCS ya permitido para
    abrir un documento) en vez de aceptar tamaño/hash que mande el
    propio POST. El agente solo tiene que decir QUÉ objeto acaba de
    escribir, nunca describirlo.

    El payload/códigos de estado son cosa solo entre el agente y esta
    vista -- nunca un endpoint de cara al navegador, así que sin
    `messages`, sin plantilla.
    """

    def post(self, request):
        token = request.headers.get("Authorization", "")
        token = token.removeprefix("Bearer ").strip()
        expected = getattr(settings, "H28_AGENT_API_TOKEN", "") or ""
        if not expected or not constant_time_compare(token, expected):
            return HttpResponseForbidden("Token inválido.")

        bucket_name = (request.POST.get("bucket") or "").strip()
        blob_name = (request.POST.get("blob_name") or "").strip()
        if bucket_name not in INDEXED_BUCKETS or not blob_name:
            return HttpResponseBadRequest(
                "Faltan 'bucket' (indexado) o 'blob_name'."
            )

        client = get_storage_client()
        blob = client.bucket(bucket_name).get_blob(blob_name)
        if blob is None:
            return HttpResponseNotFound(
                "El objeto no existe en el cubo -- ¿subida todavía en "
                "curso, o ya borrado?"
            )

        parent_path, _ = index_writer.split_path(blob_name)
        row = index_writer.file_row(blob)

        with transaction.atomic():
            index_writer.ensure_folder_chain(bucket_name, parent_path)
            created, updated = index_writer.persist_rows(
                bucket_name, [row],
            )
            index_writer.recount_children(
                bucket_name,
                folder_paths=index_writer.ancestors_of(parent_path),
            )

        return JsonResponse({
            "status": "ok",
            "created": bool(created),
            "updated": bool(updated),
        })


class DocumentTypeCatalogListView(ExplorerAccessMixin, TemplateView):
    """
    Admin screen to manage `DocumentTypeCatalog` from the panel,
    without touching code (H29, S040) -- Miguel Ángel, verbatim: *"al
    panel, tenemos que dotar al panel de un sistema para añadir tipo
    (...) con esto quiero evitar tener que tocar código para añadir un
    tipo de documento al catálogo."* Real incident that prompted this:
    several "manual de despiece" (spare-parts catalog) files for
    forklifts stayed unclassified in quarantine even though the
    machine was known with certainty, purely because that document
    type didn't exist yet in the closed vocabulary (3.18: "cerrado
    pero extensible, no congelado permanentemente").

    `classify_entry()`'s prompt already reads `DocumentTypeCatalog`
    live from the database on every call (`_build_prompt`) -- adding a
    row here needs no deploy, no restart, nothing: the very next
    Gemini call already sees it.

    ---

    Pantalla de administrador para gestionar `DocumentTypeCatalog`
    desde el panel, sin tocar código (H29, S040) -- Miguel Ángel,
    verbatim: *"al panel, tenemos que dotar al panel de un sistema
    para añadir tipo (...) con esto quiero evitar tener que tocar
    código para añadir un tipo de documento al catálogo."* Incidente
    real que lo motivó: varios "manual de despiece" (catálogo de
    piezas) de carretillas se quedaban sin clasificar en cuarentena
    aunque la máquina se conocía con total certeza, solo porque ese
    tipo documental todavía no existía en el vocabulario cerrado
    (3.18: "cerrado pero extensible, no congelado permanentemente").

    El prompt de `classify_entry()` ya lee `DocumentTypeCatalog` en
    vivo de la base de datos en cada llamada (`_build_prompt`) --
    añadir una fila aquí no necesita despliegue, ni reinicio, nada: la
    siguiente llamada a Gemini ya la ve.
    """

    template_name = "document_explorer/type_catalog.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        company_user = self.request.user.company_user
        if not permissions.is_unrestricted(company_user):
            raise Http404("Solo el administrador puede ver el catálogo.")
        context["active_nav"] = "document_explorer"
        context["types"] = DocumentTypeCatalog.objects.all()
        context["domain_choices"] = DocumentTypeCatalog.DOMAIN_CHOICES
        return context


class DocumentTypeCatalogCreateView(ExplorerAccessMixin, View):
    """
    Adds one row to `DocumentTypeCatalog` -- see
    `DocumentTypeCatalogListView` for the full story. `code` is run
    through `naming_service._sanitize_token()`, the exact same
    normaliser the renaming engine itself uses, so a code typed here
    can never contain something the filename builder would reject
    later (accents, spaces, punctuation).

    ---

    Añade una fila a `DocumentTypeCatalog` -- ver
    `DocumentTypeCatalogListView` para el contexto completo. El
    `code` pasa por `naming_service._sanitize_token()`, el mismo
    normalizador que usa el propio motor de renombrado, así que un
    código escrito aquí nunca puede contener algo que el constructor
    de nombres de archivo rechace después (acentos, espacios,
    puntuación).
    """

    def post(self, request):
        company_user = request.user.company_user
        if not permissions.is_unrestricted(company_user):
            raise Http404("Solo el administrador puede gestionar el catálogo.")

        raw_code = (request.POST.get("code") or "").strip()
        label = (request.POST.get("label") or "").strip()
        domain = (request.POST.get("domain") or "").strip()

        code = naming_service._sanitize_token(raw_code)
        valid_domains = dict(DocumentTypeCatalog.DOMAIN_CHOICES)
        if not code or not label or domain not in valid_domains:
            messages.error(
                request,
                "Faltan datos -- código, nombre visible y dominio son "
                "obligatorios.",
            )
            return redirect(reverse("document_explorer:type_catalog"))

        _, created = DocumentTypeCatalog.objects.get_or_create(
            code=code, defaults={"label": label, "domain": domain},
        )
        if created:
            messages.success(
                request,
                "«%s» añadido al catálogo -- ya disponible para la "
                "próxima clasificación, sin necesidad de desplegar "
                "nada." % code,
            )
        else:
            messages.warning(
                request, "«%s» ya existía en el catálogo, no se ha "
                "duplicado." % code,
            )
        return redirect(reverse("document_explorer:type_catalog"))


class DocumentTypeCatalogToggleView(ExplorerAccessMixin, View):
    """
    Flips `is_active` on one `DocumentTypeCatalog` row -- deactivating
    (never deleting) keeps the historical record of files already
    renamed with that code intact, per the field's own `help_text`.
    An inactive type simply stops appearing in future Gemini prompts
    (`_build_prompt` filters `is_active=True`).

    ---

    Cambia `is_active` de una fila de `DocumentTypeCatalog` --
    desactivar (nunca borrar) conserva intacto el histórico de
    archivos ya renombrados con ese código, según el propio
    `help_text` del campo. Un tipo inactivo simplemente deja de
    aparecer en los próximos prompts a Gemini (`_build_prompt` filtra
    `is_active=True`).
    """

    def post(self, request, pk):
        company_user = request.user.company_user
        if not permissions.is_unrestricted(company_user):
            raise Http404("Solo el administrador puede gestionar el catálogo.")

        doc_type = get_object_or_404(DocumentTypeCatalog, pk=pk)
        doc_type.is_active = not doc_type.is_active
        doc_type.save(update_fields=["is_active"])
        messages.success(
            request,
            "«%s» ahora está %s."
            % (doc_type.code, "activo" if doc_type.is_active else "inactivo"),
        )
        return redirect(reverse("document_explorer:type_catalog"))
