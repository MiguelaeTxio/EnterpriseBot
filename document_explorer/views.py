# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/views.py
"""
Explorer views over the document index (H29).

Navigation never touches Google Cloud Storage. Every listing is a
single indexed equality lookup on `parent_path_hash`, ordered folders
first, paginated by cursor. GCS is contacted at exactly two moments:
when a document's content is opened (a signed URL is minted) and when
the administrator empties a trash (the object is really deleted).

Pagination is by cursor, not OFFSET: the cost of page 40 is the same
as page 1. The cursor is the ordering triple of the last row shown,
because ordering by (kind, name) alone is not unique.

Permissions are resolved once per request, in Python, against the
folder being opened -- see `permissions.py` for why rows are never
filtered individually.

Deleting is logical and personal: the row goes to the deleter's own
trash and becomes invisible to everybody else immediately, per the
S037 decision. Only the administrator purges, and purging removes the
object while keeping the row as an audit record.

---

Vistas del explorador sobre el índice documental (H29).

Navegar no toca nunca Google Cloud Storage. Cada listado es una única
búsqueda indexada por igualdad sobre `parent_path_hash`, ordenada con
las carpetas primero y paginada por cursor. Con GCS se habla en
exactamente dos momentos: al abrir el contenido de un documento (se
acuña una URL firmada) y cuando el administrador vacía una papelera
(el objeto se borra de verdad).

La paginación es por cursor, no por OFFSET: la página 40 cuesta lo
mismo que la 1. El cursor es la terna de ordenación de la última fila
mostrada, porque ordenar por (tipo, nombre) no es único.

Los permisos se resuelven una vez por petición, en Python, contra la
carpeta que se abre -- ver `permissions.py` para por qué no se filtran
las filas una a una.

Borrar es lógico y personal: la fila va a la papelera de quien borra y
deja de ser visible para todos los demás de inmediato, según la
decisión de S037. Solo el administrador vacía, y vaciar retira el
objeto conservando la fila como registro de auditoría.
"""
from django.contrib import messages
from django.db.models import Q
from django.http import Http404, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.views import View
from django.views.generic import TemplateView

from panel.mixins import CompanyUserRequiredMixin
from spare_parts.gcs_service import delete_file, generate_signed_url

from document_explorer import permissions
from document_explorer.models import DocumentIndexEntry, path_digest

PAGE_SIZE = 200


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

    ---

    Construye la miga de pan. La lógica vive aquí, nunca en la
    plantilla.
    """
    crumbs = [{"label": bucket, "path": ""}]
    if not folder_path:
        return crumbs
    parts = folder_path.split("/")
    for index, part in enumerate(parts):
        crumbs.append({
            "label": part,
            "path": "/".join(parts[:index + 1]),
        })
    return crumbs


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
            "buckets": buckets,
            "bucket": bucket,
            "folder_path": folder_path,
            "has_buckets": bool(buckets),
            "breadcrumbs": build_breadcrumbs(bucket, folder_path),
        })
        return context


class FolderListingView(ExplorerAccessMixin, TemplateView):
    """
    HTMX fragment: the direct children of one folder.

    ---

    Fragmento HTMX: los hijos directos de una carpeta.
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

        grants = self.load_grants(bucket)
        mode, allowed = permissions.visibility(
            company_user, bucket, folder_path, grants=grants,
        )
        if mode == permissions.NONE:
            context.update({
                "entries": [],
                "denied": True,
                "next_cursor": None,
                "show_delete": False,
                "bucket": bucket,
                "folder_path": folder_path,
                "breadcrumbs": build_breadcrumbs(bucket, folder_path),
                "has_parent": bool(folder_path),
                "parent_path": (
                    folder_path.rsplit("/", 1)[0]
                    if "/" in folder_path else ""
                ),
            })
            return context

        entries = self._page(bucket, folder_path, mode, allowed)
        has_more = len(entries) > PAGE_SIZE
        entries = entries[:PAGE_SIZE]

        context.update({
            "entries": entries,
            "denied": False,
            "bucket": bucket,
            "folder_path": folder_path,
            "breadcrumbs": build_breadcrumbs(bucket, folder_path),
            "parent_path": (
                folder_path.rsplit("/", 1)[0] if "/" in folder_path
                else ""
            ),
            "has_parent": bool(folder_path),
            "show_delete": permissions.can_delete_in(
                company_user, bucket, folder_path, grants=grants,
            ),
            "next_cursor": self._cursor(entries[-1]) if (
                has_more and entries
            ) else None,
        })
        return context

    def _page(self, bucket, folder_path, mode, allowed):
        """
        One indexed page of children, folders first.

        ---

        Una página indexada de hijos, con las carpetas primero.
        """
        query = DocumentIndexEntry.objects.filter(
            bucket=bucket,
            parent_path_hash=path_digest(folder_path),
            deleted_at__isnull=True,
            purged_at__isnull=True,
        )
        if mode == permissions.PARTIAL:
            query = query.filter(name__in=list(allowed))

        after_kind = self.request.GET.get("after_kind")
        after_name = self.request.GET.get("after_name")
        after_id = self.request.GET.get("after_id")
        if after_kind and after_id:
            query = query.filter(
                Q(entry_kind__lt=after_kind)
                | Q(entry_kind=after_kind, name__gt=after_name)
                | Q(
                    entry_kind=after_kind,
                    name=after_name,
                    id__gt=after_id,
                )
            )

        return list(
            query.order_by("-entry_kind", "name", "id")[:PAGE_SIZE + 1]
        )

    def _cursor(self, entry):
        """
        Ordering triple of the last row, for the next page.

        ---

        Terna de ordenación de la última fila, para la página
        siguiente.
        """
        return {
            "after_kind": entry.entry_kind,
            "after_name": entry.name,
            "after_id": entry.id,
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
