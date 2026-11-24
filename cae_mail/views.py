# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/cae_mail/views.py
"""
"Correos CAE" tab of the Documentation hub (S156).

The supervisor (Yolanda, or Juan during her holidays) sees the notices
the CAE platforms sent, what each one asks for, which of those
documents EnterpriseBot already has (current or expired) and which are
missing; downloads the ones to upload to the platform in one go and
marks the notice as attended.

---

Pestaña «Correos CAE» del hub de Documentación (S156). Miguel Ángel:
"que la persona que supervise esto, bien Yolanda o bien Juan, pueda
fácilmente enviar todos los correos y toda la documentación que le
están solicitando". Arriba, filtros y acciones; abajo, los avisos y el
detalle del elegido: qué pide, qué tenemos (vigente o caducado), qué
falta, descarga de lo marcado y «Dar por atendido».
"""
import io
import tempfile
import zipfile

from django.db.models import Count, Q
from django.http import FileResponse, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views import View

from document_explorer.confidential import can_open, open_bytes
from document_explorer.models import DocumentIndexEntry
from ivr_config.models import CompanyUser
from panel.mixins import CompanyUserRequiredMixin

from .models import CaeMail
from .resolution import STATUS_LABELS, resolve_mail

_ALLOWED_ROLES = (
    CompanyUser.ROLE_ADMIN,
    CompanyUser.ROLE_ADMIN_SUPERVISOR,
    CompanyUser.ROLE_SUPERVISOR,
    CompanyUser.ROLE_DOCS_SUPERVISOR,
)
_STATE_PENDING = "pendientes"
_STATE_ATTENDED = "atendidos"
_STATE_ALL = "todos"
_STATES = (
    (_STATE_PENDING, "Por atender"),
    (_STATE_ATTENDED, "Atendidos"),
    (_STATE_ALL, "Todos"),
)
_RESULTS_LIMIT = 300


def can_use_cae(company_user):
    """True if this user may manage the CAE notices.
    ---
    True si el usuario puede gestionar los avisos CAE: administración
    y supervisión (incluida la de documentación).
    """
    return bool(
        company_user is not None and company_user.is_active
        and company_user.role in _ALLOWED_ROLES
    )


class CaeAccessMixin(CompanyUserRequiredMixin):
    """
    Only users who manage the CAE notices; the rest get a 403.
    ---
    Solo quien gestiona los avisos CAE; el resto recibe un 403 (la
    pestaña ni siquiera se le muestra).
    """

    def dispatch(self, request, *args, **kwargs):
        company_user = getattr(request.user, "company_user", None)
        if request.user.is_authenticated and not can_use_cae(company_user):
            return HttpResponse(
                "Acceso denegado: los correos CAE no son para tu usuario.",
                status=403)
        return super().dispatch(request, *args, **kwargs)


def _filtered_mails(params):
    """Notices matching the filters, newest first, with counts.
    ---
    Avisos que cumplen los filtros, los más recientes primero, con el
    número de documentos pedidos.
    """
    mails = CaeMail.objects.annotate(demand_count=Count("demands"))
    state = params.get("state") or _STATE_PENDING
    if state == _STATE_PENDING:
        mails = mails.filter(attended_at__isnull=True)
    elif state == _STATE_ATTENDED:
        mails = mails.filter(attended_at__isnull=False)
    platform = params.get("platform", "")
    if platform:
        mails = mails.filter(platform=platform)
    if params.get("detail") == "1":
        mails = mails.filter(has_detail=True)
    search = (params.get("search") or "").strip()
    if search:
        mails = mails.filter(
            Q(subject__icontains=search) | Q(client__icontains=search)
            | Q(summary__icontains=search)
            | Q(our_company__icontains=search)
            | Q(demands__subject_name__icontains=search)
            | Q(demands__subject_ref__icontains=search)
            | Q(demands__document__icontains=search)
        ).distinct()
    return mails.order_by("-received_at", "-forwarded_at", "-pk")


class CaeTabView(CaeAccessMixin, View):
    """
    GET: the whole tab (filters, actions and the notice list).
    ---
    GET: la pestaña entera (filtros, acciones y lista de avisos).
    """

    def get(self, request):
        platforms = (
            CaeMail.objects.exclude(platform="")
            .values_list("platform", flat=True).distinct()
            .order_by("platform")
        )
        mails = list(_filtered_mails({})[:_RESULTS_LIMIT])
        return render(request, "cae_mail/_pane.html", {
            "platforms": platforms,
            "states": _STATES,
            "filter_state": _STATE_PENDING,
            "mails": mails,
            "limit": _RESULTS_LIMIT,
        })


class CaeResultsView(CaeAccessMixin, View):
    """
    GET: the notice list for the current filters.
    ---
    GET: la lista de avisos con los filtros puestos.
    """

    def get(self, request):
        mails = list(_filtered_mails(request.GET)[:_RESULTS_LIMIT])
        return render(request, "cae_mail/_results.html", {
            "mails": mails,
            "limit": _RESULTS_LIMIT,
        })


class CaeDetailView(CaeAccessMixin, View):
    """
    GET: what one notice asks for and what we have of it.
    ---
    GET: qué pide un aviso y qué tenemos de ello.
    """

    def get(self, request, pk):
        mail = get_object_or_404(CaeMail, pk=pk)
        return _render_detail(request, mail)


def _render_detail(request, mail, message=""):
    rows, counts = resolve_mail(mail)
    return render(request, "cae_mail/_detail.html", {
        "mail": mail,
        "rows": rows,
        "counts": [
            (key, STATUS_LABELS[key], counts[key])
            for key in STATUS_LABELS if counts[key]
        ],
        "downloadable": sum(1 for row in rows if row["entry"]),
        "message": message,
    })


class CaeAttendView(CaeAccessMixin, View):
    """
    POST: mark a notice as attended, or reopen it.
    ---
    POST: da un aviso por atendido o lo reabre.
    """

    def post(self, request, pk):
        mail = get_object_or_404(CaeMail, pk=pk)
        if mail.attended_at is None:
            mail.attended_at = timezone.now()
            mail.attended_by = request.user
            message = "Aviso dado por atendido."
        else:
            mail.attended_at = None
            mail.attended_by = None
            message = "Aviso reabierto."
        mail.save(update_fields=["attended_at", "attended_by"])
        response = _render_detail(request, mail, message)
        response["HX-Trigger"] = "cae-refresh"
        return response


class CaeRereadView(CaeAccessMixin, View):
    """
    POST: read a notice again with Gemini.
    ---
    POST: vuelve a leer un aviso con Gemini (p. ej. tras crear un tipo
    nuevo en el catálogo). Lo que había se sustituye al terminar.
    """

    def post(self, request, pk):
        from django.db import transaction

        from .tasks import process_cae_mail_task

        mail = get_object_or_404(CaeMail, pk=pk)
        mail.status = CaeMail.STATUS_PENDING
        mail.processed_at = None
        mail.save(update_fields=["status", "processed_at"])
        transaction.on_commit(
            lambda: process_cae_mail_task.delay(mail.pk))
        return _render_detail(
            request, mail,
            "Se está volviendo a leer; pulsa el aviso en un minuto.")


class CaeDownloadView(CaeAccessMixin, View):
    """
    POST: download the marked documents, one as is, several in a ZIP.
    ---
    POST: descarga los documentos marcados del aviso: uno tal cual,
    varios en un ZIP con sus nombres. Los confidenciales que el usuario
    no puede abrir se omiten.
    """

    def post(self, request, pk):
        mail = get_object_or_404(CaeMail, pk=pk)
        company_user = request.user.company_user
        entries = [
            entry for entry in DocumentIndexEntry.objects.filter(
                pk__in=request.POST.getlist("entries"),
                entry_kind=DocumentIndexEntry.KIND_FILE,
                deleted_at__isnull=True, purged_at__isnull=True,
            ).order_by("name")
            if can_open(entry, company_user)
        ]
        if not entries:
            return HttpResponse(
                "No has marcado ningún documento que puedas descargar.",
                status=400)
        if len(entries) == 1:
            entry = entries[0]
            return FileResponse(
                io.BytesIO(open_bytes(entry, company_user)),
                as_attachment=True, filename=entry.name)
        spool = tempfile.SpooledTemporaryFile(max_size=50 * 1024 * 1024)
        used = {}
        with zipfile.ZipFile(spool, "w", zipfile.ZIP_DEFLATED) as archive:
            for entry in entries:
                name = entry.name
                count = used.get(name.lower(), 0) + 1
                used[name.lower()] = count
                if count > 1:
                    stem, dot, ext = name.rpartition(".")
                    name = ("%s (%d).%s" % (stem, count, ext) if dot
                            else "%s (%d)" % (name, count))
                archive.writestr(name, open_bytes(entry, company_user))
        spool.seek(0)
        label = "_".join(filter(None, [mail.platform, mail.client]))
        return FileResponse(
            spool, as_attachment=True,
            filename="CAE_%s_%s.zip" % (
                "".join(c for c in label if c.isalnum() or c in "_-")
                or mail.pk,
                timezone.localtime().strftime("%Y%m%d"),
            ))
