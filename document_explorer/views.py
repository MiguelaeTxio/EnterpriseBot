# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/views.py
"""
Explorer views over the document index (H29).

Navigation never touches Google Cloud Storage. Every listing is a
single indexed equality lookup on `parent_path_hash`, ordered folders
first, paginated by cursor. GCS is contacted at exactly two moments:
when a document's content is opened (a signed URL is minted) and when
the administrator empties a trash (the object is really deleted).

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
unindexed `blob_name__startswith` scan -- a deliberate, occasional
search action, not a page-load-critical navigation path, and bounded
by the size of one bucket (tens of thousands of rows at most, per the
H28 inventory). Permission scoping for those two modes still follows
the same "resolve once per request" principle as `permissions.py`:
`readable_prefixes()` returns a handful of grant prefixes, applied as
one small OR condition, never as a per-row check in Python.

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
(el objeto se borra de verdad).

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
acepta un barrido sin índice sobre `blob_name__startswith` -- una
acción de búsqueda deliberada y ocasional, no una ruta de navegación
crítica en cada carga de página, y acotada al tamaño de un cubo
(decenas de miles de filas como mucho, según el inventario de H28). El
acotado de permisos de esos dos modos sigue el mismo principio de
"resolver una vez por petición" que `permissions.py`:
`readable_prefixes()` devuelve un puñado de prefijos de concesión,
aplicados como una única condición OR pequeña, nunca como una
comprobación fila a fila en Python.

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
"""
from urllib.parse import urlencode

from django.contrib import messages
from django.db.models import (
    BigIntegerField, Case, DateTimeField, F, Q, Value, When,
)
from django.db.models.functions import Coalesce
from django.http import Http404, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views import View
from django.views.generic import TemplateView

from panel.mixins import CompanyUserRequiredMixin
from spare_parts.gcs_service import delete_file, generate_signed_url

from document_explorer import permissions
from document_explorer.buckets import BUCKET_DISPLAY_NAMES
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
# el resto de valores "más antiguos que cualquier otro".
_EPOCH = timezone.datetime(1970, 1, 1, tzinfo=timezone.get_default_timezone())


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

    The root crumb shows the Spanish display name (BUCKET_DISPLAY_NAMES)
    when there is one, falling back to the raw bucket name otherwise --
    never blank, never the technical name for buckets that do have a
    Spanish label.

    ---

    Construye la miga de pan. La lógica vive aquí, nunca en la
    plantilla.

    La miga raíz muestra el nombre en castellano
    (BUCKET_DISPLAY_NAMES) cuando existe, y si no, el nombre técnico
    del cubo -- nunca en blanco, nunca el nombre técnico para cubos que
    sí tienen etiqueta en castellano.
    """
    crumbs = [{
        "label": BUCKET_DISPLAY_NAMES.get(bucket, bucket),
        "path": "",
    }]
    if not folder_path:
        return crumbs
    parts = folder_path.split("/")
    for index, part in enumerate(parts):
        crumbs.append({
            "label": part,
            "path": "/".join(parts[:index + 1]),
        })
    return crumbs


def bucket_tabs(buckets, active_bucket):
    """
    Build the tab list: technical name for the URL, Spanish label for
    display, and which one is active. Logic lives here, never in the
    template.

    ---

    Construye la lista de pestañas: nombre técnico para la URL,
    etiqueta en castellano para mostrar, y cuál está activa. La lógica
    vive aquí, nunca en la plantilla.
    """
    return [
        {
            "name": name,
            "label": BUCKET_DISPLAY_NAMES.get(name, name),
            "active": name == active_bucket,
        }
        for name in buckets
    ]


class ExplorerView(ExplorerAccessMixin, TemplateView):
    """
    Explorer shell: bucket picker plus the first folder listing.

    ---

    Armazón del explorador: selector de cubo y primer listado.
    """

    template_name = "document_explorer/explorer.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        company_user = self.request.user.company_user
        buckets = permissions.readable_buckets(company_user)

        bucket = self.request.GET.get("bucket") or (
            buckets[0] if buckets else ""
        )
        if bucket and bucket not in buckets:
            raise Http404("Sin acceso a ese cubo.")

        folder_path = (self.request.GET.get("path") or "").strip("/")
        context.update({
            "active_nav": "document_explorer",
            "buckets": bucket_tabs(buckets, bucket),
            "bucket": bucket,
            "folder_path": folder_path,
            "has_buckets": bool(buckets),
            "breadcrumbs": build_breadcrumbs(bucket, folder_path),
        })
        return context


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

        common = {
            "bucket": bucket,
            "folder_path": folder_path,
            "breadcrumbs": build_breadcrumbs(bucket, folder_path),
            "is_search": is_search,
            "filters": self.filters,
            "sort_key": self.sort_key,
            "sort_dir": self.sort_dir,
            "sort_columns": self._sort_columns(),
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
            prefixes = permissions.readable_prefixes(company_user, bucket)
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
            })
            return context

        entries = self._page(bucket, folder_path, mode, allowed)
        has_more = len(entries) > PAGE_SIZE
        entries = entries[:PAGE_SIZE]

        context.update(common)
        context.update({
            "entries": entries,
            "denied": False,
            "parent_path": parent_path,
            "has_parent": has_parent,
            "show_delete": show_delete,
            "next_page_url": (
                self._build_page_url(self._cursor(entries[-1]))
                if (has_more and entries) else None
            ),
        })
        return context

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

    def _page(self, bucket, folder_path, mode, allowed):
        """
        One indexed page of children (scope=here), or one page of a
        recursive search (scope=here_recursive/global), folders
        always first, then the chosen column/direction, then `id` as
        tie-breaker.

        ---

        Una página indexada de hijos (scope=here), o una página de una
        búsqueda recursiva (scope=here_recursive/global), siempre con
        las carpetas primero, luego la columna/dirección elegida, y
        por último `id` como desempate.
        """
        scope = self.filters["scope"]
        query = DocumentIndexEntry.objects.filter(
            bucket=bucket, deleted_at__isnull=True, purged_at__isnull=True,
        )

        if scope == SCOPE_HERE:
            query = query.filter(parent_path_hash=path_digest(folder_path))
            if mode == permissions.PARTIAL:
                query = query.filter(name__in=list(allowed))
        else:
            scope_path = folder_path if scope == SCOPE_RECURSIVE else ""
            if scope_path:
                query = query.filter(
                    blob_name__startswith=scope_path + "/",
                )
            prefixes = permissions.readable_prefixes(
                self.company_user, bucket,
            )
            if prefixes is not None:
                restriction = Q()
                for prefix in prefixes:
                    restriction |= Q(blob_name=prefix) | Q(
                        blob_name__startswith=prefix + "/",
                    )
                query = query.filter(restriction)

        query = self._apply_filters(query)
        field = self._sort_field()
        query = self._annotate_sort_field(query, field)

        order_field = field if self.sort_dir == "asc" else "-%s" % field
        query = query.order_by("-entry_kind", order_field, "id")
        query = self._apply_cursor(query, field)

        return list(query[:PAGE_SIZE + 1])

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
                sort_date=Coalesce(
                    F("gcs_updated_at"),
                    Value(_EPOCH, output_field=DateTimeField()),
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
