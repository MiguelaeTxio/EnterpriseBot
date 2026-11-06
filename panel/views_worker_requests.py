# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/views_worker_requests.py
"""
Worker requests (H24, S147): the worker's page "Mis solicitudes" and
the supervisors' "Solicitudes" tab of the Documentation hub (also a
page of its own for Supervisor and Jefe de taller, who have no hub).
The logic lives in hr_calendar.worker_requests; these views read the
request, call it and render.

---

Solicitudes de los trabajadores (H24, S147): la página del trabajador
"Mis solicitudes" y la pestaña "Solicitudes" de los supervisores en el
hub de Documentación (también como página propia para Supervisor y Jefe
de taller, que no tienen el hub). La lógica vive en
hr_calendar.worker_requests; estas vistas leen la petición, la llaman y
pintan.
"""
import datetime
import logging
import mimetypes
from urllib.parse import quote

from django.db.models import Q
from django.http import Http404, HttpResponse
from django.shortcuts import redirect, render
from django.views import View

from document_explorer.models import DocumentTypeCatalog
from hr_calendar.models import WorkerRequest, WorkerRequestFile
from hr_calendar import worker_requests as wr
from panel.mixins import CompanyUserRequiredMixin, SupervisorAccessMixin
from panel.navigation_persistence import (
    apply_list_navigation,
    get_saved_state_key,
)
from panel.views_vacation_balance import MANAGE_ROLES

logger = logging.getLogger(__name__)

SCREEN_KEY = "worker_requests"
FILTER_KEYS = ("search", "status", "kind", "sort")
DEFAULT_STATUS = ["PENDING"]
DEFAULT_SORT = "-created"
_MAX_SORT_KEYS = 4
_COLUMNS = (
    ("created", "Pedida"),
    ("person", "Trabajador"),
    ("kind", "Tipo"),
    ("detail", "Qué pide"),
    ("days", "Días"),
    ("status", "Estado"),
    ("proof", "Justificante"),
    ("resolved", "Resuelta"),
)
_SORT_VALUES = {
    "created": lambda r: r.created_at,
    "person": lambda r: r.person_label.upper(),
    "kind": lambda r: r.get_kind_display(),
    "detail": lambda r: r.date_start or datetime.date.min,
    "days": lambda r: r.days if r.days is not None else -1,
    "status": lambda r: r.get_status_display(),
    "proof": lambda r: r.get_proof_status_display(),
    "resolved": lambda r: r.resolved_at,
}


def _person_of(request):
    """
    The worker file of the logged-in user, or None.
    ---
    La ficha de personal del usuario que entra, o None.
    """
    return getattr(request.user.company_user, "person_identity", None)


def can_manage(request):
    """
    True for the roles that handle requests (those of Vacaciones).
    ---
    True para los roles que gestionan solicitudes (los de Vacaciones).
    """
    return request.user.company_user.role in MANAGE_ROLES


def _decorate(item):
    item.person_label = wr.person_label(item.person)
    item.detail = wr.detail_text(item)
    item.days = wr.day_count(item)
    item.is_pending = item.status == WorkerRequest.Status.PENDING
    item.is_dated = item.kind in wr.DATED_KINDS
    return item


# ------------------------------------------------------------------
# Página del trabajador
# ------------------------------------------------------------------
def _my_context(request, person, message="", error=False):
    from hr_calendar.balance import BalanceCalculator

    company = request.user.company_user.company
    today = datetime.date.today()
    balance = BalanceCalculator(company, [person]).balance(
        person, today.year)
    items = [
        _decorate(item) for item in WorkerRequest.objects.filter(
            person=person,
        ).prefetch_related("files").order_by("-created_at", "-pk")
    ]
    return {
        "person": person,
        "balance": balance,
        "entitled_total": (balance.entitled + balance.manual
                           + balance.free_days),
        "year": today.year,
        "today": today,
        "items": items,
        "kinds": WorkerRequest.Kind.choices,
        "documents": wr.DOCUMENTS,
        "message": message,
        "error": error,
        "active_nav": "my_requests",
    }


class MyRequestsView(CompanyUserRequiredMixin, View):
    """
    GET/POST: "Mis solicitudes" of the logged-in worker.
    ---
    GET: la página del trabajador (saldo de vacaciones, pedir y sus
    peticiones). POST: una petición nueva; vuelve a la página con el
    resultado.
    """

    template_name = "panel/worker_requests/my_requests.html"

    def get(self, request):
        person = _person_of(request)
        if person is None:
            return render(request, self.template_name, {
                "person": None, "active_nav": "my_requests",
            })
        return render(request, self.template_name,
                      _my_context(request, person,
                                  request.GET.get("ok", "")))

    def post(self, request):
        person = _person_of(request)
        if person is None:
            raise Http404
        cu = request.user.company_user
        try:
            wr.create_request(person, cu.company, cu, request.POST)
        except wr.RequestError as exc:
            context = _my_context(request, person, str(exc), True)
            context["form"] = request.POST
            return render(request, self.template_name, context)
        return redirect("/panel/mis-solicitudes/?ok=" + quote(
            "Petición enviada. La verás aquí con su respuesta."))


def _my_request_or_404(request, pk):
    person = _person_of(request)
    item = WorkerRequest.objects.filter(pk=pk, person=person).first()
    if person is None or item is None:
        raise Http404
    return item


class MyRequestCancelView(CompanyUserRequiredMixin, View):
    """
    POST: the worker withdraws one of their pending requests.
    ---
    POST: el trabajador anula una de sus peticiones pendientes.
    """

    def post(self, request, pk):
        item = _my_request_or_404(request, pk)
        try:
            wr.cancel_by_worker(item)
            text = "Petición anulada."
        except wr.RequestError as exc:
            text = str(exc)
        return redirect("/panel/mis-solicitudes/?ok=" + quote(text))


class MyRequestProofView(CompanyUserRequiredMixin, View):
    """
    POST: the worker uploads the proof of a medical request.
    ---
    POST: el trabajador sube el justificante de una petición de médico.
    """

    def post(self, request, pk):
        item = _my_request_or_404(request, pk)
        upload = request.FILES.get("file")
        try:
            if upload is None:
                raise wr.RequestError("Elige el archivo o haz la foto.")
            wr.add_proof(item, upload.read(), upload.name,
                         request.user.company_user)
            text = "Justificante enviado."
        except wr.RequestError as exc:
            text = str(exc)
        except Exception:  # GCS / lectura: nunca un error 500 al trabajador
            logger.exception("[solicitudes] justificante #%s", pk)
            text = ("No se ha podido guardar el justificante. "
                    "Inténtalo otra vez.")
        return redirect("/panel/mis-solicitudes/?ok=" + quote(text))


class RequestFileDownloadView(CompanyUserRequiredMixin, View):
    """
    GET: a file of a request, for its worker or a supervisor.
    ---
    GET: un archivo de una petición, para su trabajador o para un
    supervisor (nunca para otro trabajador).
    """

    def get(self, request, pk):
        from spare_parts.gcs_service import download_bytes

        stored = WorkerRequestFile.objects.select_related(
            "request", "entry").filter(pk=pk).first()
        if stored is None or stored.entry is None:
            raise Http404
        same_company = (stored.request.company_id
                        == request.user.company_user.company_id)
        own = stored.request.person == _person_of(request)
        if not (own or (can_manage(request) and same_company)):
            raise Http404
        entry = stored.entry
        data = download_bytes(entry.bucket, entry.blob_name)
        content_type = (entry.content_type
                        or mimetypes.guess_type(entry.name)[0]
                        or "application/octet-stream")
        response = HttpResponse(data, content_type=content_type)
        response["Content-Disposition"] = (
            "inline; filename*=UTF-8''%s" % quote(entry.name))
        return response


# ------------------------------------------------------------------
# Pestaña de los supervisores
# ------------------------------------------------------------------
def _param(request, key, default=""):
    if request.method == "POST":
        return request.POST.get("_f_" + key, default)
    return request.GET.get(key, default)


def _csv_param(request, key, default):
    if key in request.GET or ("_f_" + key) in request.POST:
        return [v for v in _param(request, key).split(",") if v]
    return list(default)


def _parse_sort(raw):
    keys, seen = [], set()
    for token in (raw or "").split(","):
        token = token.strip()
        key = token.lstrip("-")
        if key in _SORT_VALUES and key not in seen:
            keys.append((key, token.startswith("-")))
            seen.add(key)
    return keys[:_MAX_SORT_KEYS]


def _sort_controls(raw):
    sort_keys = _parse_sort(raw)
    active = [key for key, _desc in sort_keys]
    columns = []
    for key, label in _COLUMNS:
        if key in active:
            idx = active.index(key)
            desc = sort_keys[idx][1]
            arrow = "down" if desc else "up"
            priority = idx + 1 if len(sort_keys) > 1 else ""
            new_desc = (not desc) if idx == 0 else desc
            new_keys = [(key, new_desc)] + [
                (k, d) for k, d in sort_keys if k != key]
        else:
            arrow, priority = "", ""
            new_keys = [(key, False)] + sort_keys
        columns.append({
            "key": key, "label": label, "arrow": arrow,
            "priority": priority,
            "next": ",".join(("-" if d else "") + k
                             for k, d in new_keys[:_MAX_SORT_KEYS]),
        })
    return {
        "sort_columns": columns,
        "sort_active": bool(sort_keys),
        "current_sort": ",".join(("-" if d else "") + k
                                 for k, d in sort_keys),
    }


def _sort_rows(rows, sort_keys):
    rows = sorted(rows, key=lambda r: (r.created_at, r.pk), reverse=True)
    for key, desc in reversed(sort_keys):
        getter = _SORT_VALUES[key]
        present = [r for r in rows if getter(r) is not None]
        missing = [r for r in rows if getter(r) is None]
        rows = sorted(present, key=getter, reverse=desc) + missing
    return rows


def _list_context(request):
    company = request.user.company_user.company
    statuses = _csv_param(request, "status", DEFAULT_STATUS)
    kinds = _csv_param(request, "kind", WorkerRequest.Kind.values)
    search = _param(request, "search").strip()
    qs = WorkerRequest.objects.filter(company=company).select_related(
        "person", "resolved_by__user",
    ).prefetch_related("files")
    selected = request.GET.get("only_selected") == "1"
    if selected:
        wanted = [pk for pk in request.GET.get("selected_ids", "").split(",")
                  if pk.isdigit()]
        qs = qs.filter(pk__in=wanted)
    else:
        qs = qs.filter(status__in=statuses, kind__in=kinds)
        for word in search.split():
            qs = qs.filter(
                Q(person__first_surname__icontains=word)
                | Q(person__second_surname__icontains=word)
                | Q(person__given_name__icontains=word)
                | Q(person__dni__icontains=word)
                | Q(person__nickname__icontains=word)
                | Q(note__icontains=word) | Q(period__icontains=word),
            )
    rows = [_decorate(item) for item in qs]
    raw_sort = _param(request, "sort", DEFAULT_SORT)
    rows = _sort_rows(rows, _parse_sort(raw_sort))
    return {
        "rows": rows,
        "filter_search": search,
        "filter_status": statuses,
        "filter_kind": kinds,
        "status_choices": WorkerRequest.Status.choices,
        "kind_choices": WorkerRequest.Kind.choices,
        "can_manage": can_manage(request),
        **_sort_controls(raw_sort),
    }


def _table_response(request, message="", error=False):
    response = render(request, "panel/worker_requests/_table.html",
                      _list_context(request))
    if message:
        response["X-Requests-Message"] = quote(message)
        if error:
            response["X-Requests-Error"] = "1"
    return response


def _pane_context(request):
    apply_list_navigation(request, SCREEN_KEY, FILTER_KEYS)
    cu = request.user.company_user
    saved_selection = get_saved_state_key(cu, SCREEN_KEY, "selection", [])
    if not isinstance(saved_selection, list):
        saved_selection = []
    pending = WorkerRequest.objects.filter(
        company=cu.company, status=WorkerRequest.Status.PENDING).count()
    return {
        **_list_context(request),
        "screen_key": SCREEN_KEY,
        "saved_selection": saved_selection,
        "pending_count": pending,
    }


class WorkerRequestsTabView(SupervisorAccessMixin, View):
    """
    GET: "Solicitudes" tab of the hub (directive 4.24 format).
    ---
    GET: pestaña "Solicitudes" del hub, formato de la directriz 4.24;
    filtros, orden y selección persistidos por usuario (screen_key
    "worker_requests").
    """

    def get(self, request):
        return render(request, "panel/worker_requests/_pane.html",
                      _pane_context(request))


class WorkerRequestsPageView(SupervisorAccessMixin, View):
    """
    GET: the same tab as a page (Supervisor and Jefe de taller).
    ---
    GET: la misma pestaña como página propia, para Supervisor y Jefe de
    taller (no tienen el hub de Documentación).
    """

    def get(self, request):
        context = _pane_context(request)
        context["active_nav"] = "worker_requests"
        return render(request, "panel/worker_requests/page.html", context)


class WorkerRequestsResultsView(SupervisorAccessMixin, View):
    """
    GET: table only.
    ---
    GET: solo la tabla (filtros y orden).
    """

    def get(self, request):
        apply_list_navigation(request, SCREEN_KEY, FILTER_KEYS)
        return _table_response(request)


def _company_request_or_404(request, pk):
    item = WorkerRequest.objects.select_related(
        "person", "resolved_by__user", "proof_reviewed_by__user",
        "created_by__user",
    ).filter(pk=pk, company=request.user.company_user.company).first()
    if item is None:
        raise Http404
    return item


def _delivery_types():
    return DocumentTypeCatalog.objects.filter(
        domain="PERSONAL", is_active=True,
    ).order_by("label")


def _detail_response(request, item, message="", error=False):
    _decorate(item)
    documents = []
    if item.kind == WorkerRequest.Kind.DOCUMENT:
        documents = list(wr.person_documents(item.person)[:200])
    response = render(request, "panel/worker_requests/_detail.html", {
        "item": item,
        "files": item.files.select_related("uploaded_by__user"),
        "document_label": wr.DOCUMENT_LABELS.get(item.document_code, ""),
        "default_type": wr.DOCUMENT_TYPES.get(item.document_code, ""),
        "delivery_types": (_delivery_types()
                           if item.kind == WorkerRequest.Kind.DOCUMENT
                           else []),
        "person_documents": documents,
        "message": message,
        "error": error,
    })
    response["HX-Trigger"] = "worker-requests-refresh"
    if message:
        response["X-Requests-Message"] = quote(message)
        if error:
            response["X-Requests-Error"] = "1"
    return response


class WorkerRequestDetailView(SupervisorAccessMixin, View):
    """
    GET: one request with its actions (modal body).
    ---
    GET: una petición con sus acciones (cuerpo del modal).
    """

    def get(self, request, pk):
        item = _company_request_or_404(request, pk)
        response = _detail_response(request, item)
        del response["HX-Trigger"]
        return response


class WorkerRequestActionView(SupervisorAccessMixin, View):
    """
    POST: approve, deny, answer, deliver, review the proof or undo.
    ---
    POST: aprobar, denegar, responder, entregar, revisar el justificante
    o deshacer. Devuelve el detalle de nuevo y avisa a la tabla para que
    se repinte.
    """

    def post(self, request, pk):
        item = _company_request_or_404(request, pk)
        cu = request.user.company_user
        action = request.POST.get("action", "")
        response_text = request.POST.get("response", "")
        try:
            if action == "approve":
                wr.approve(item, cu, response_text)
                text = "Aprobada."
            elif action == "deny":
                wr.deny(item, cu, response_text)
                text = "Denegada."
            elif action == "answer":
                wr.answer(item, cu, response_text)
                text = "Respuesta guardada."
            elif action == "deliver":
                upload = request.FILES.get("file")
                entry_id = request.POST.get("entry_id", "")
                wr.deliver(
                    item, cu, response_text,
                    data=upload.read() if upload else None,
                    filename=upload.name if upload else "",
                    type_code=request.POST.get("type_code", ""),
                    entry_id=int(entry_id) if entry_id.isdigit() else None,
                )
                text = "Documento entregado."
            elif action == "proof":
                upload = request.FILES.get("file")
                if upload is None:
                    raise wr.RequestError("Elige el archivo.")
                wr.add_proof(item, upload.read(), upload.name, cu)
                text = "Justificante guardado."
            elif action in ("proof_valid", "proof_invalid"):
                wr.review_proof(item, cu, action == "proof_valid")
                text = "Justificante revisado."
            elif action == "undo":
                wr.undo(item, cu)
                text = "Vuelve a estar pendiente."
            else:
                raise wr.RequestError("Acción desconocida.")
        except wr.RequestError as exc:
            item.refresh_from_db()
            return _detail_response(request, item, str(exc), True)
        except Exception:
            logger.exception("[solicitudes] acción %s en #%s", action, pk)
            item.refresh_from_db()
            return _detail_response(
                request, item, "No se ha podido completar la acción.", True)
        item.refresh_from_db()
        return _detail_response(request, item, text)


class WorkerRequestMassView(SupervisorAccessMixin, View):
    """
    POST: approve, deny or validate the proof of the marked requests.
    ---
    POST: aprobar, denegar (con motivo) o validar el justificante de las
    marcadas. Cada una se hace por separado: las que no se pueden se
    cuentan y se dice por qué. Devuelve la tabla.
    """

    def post(self, request):
        cu = request.user.company_user
        action = request.POST.get("action", "")
        reason = request.POST.get("response", "")
        ids = [pk for pk in request.POST.getlist("selected") if pk.isdigit()]
        items = WorkerRequest.objects.filter(
            company=cu.company, pk__in=ids).select_related("person")
        done, failed = 0, []
        for item in items:
            try:
                if action == "approve":
                    wr.approve(item, cu)
                elif action == "deny":
                    wr.deny(item, cu, reason)
                elif action == "proof_valid":
                    wr.review_proof(item, cu, True)
                else:
                    raise wr.RequestError("Acción desconocida.")
                done += 1
            except wr.RequestError as exc:
                failed.append("%s: %s" % (wr.person_label(item.person), exc))
        message = "%d hechas." % done
        if failed:
            message += " No se pudieron %d: %s" % (
                len(failed), "; ".join(failed[:5]))
        return _table_response(request, message, bool(failed) and not done)
