# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/views_insurance.py
"""
S152. "Seguros" tab of the Documentation hub: insurance renewal reports.

---

S152. Pestaña "Seguros" del hub de Documentación, formato de la
directriz 4.24 (el mismo que Nóminas): arriba "Buscar y filtrar",
"Nuevo informe" (mes de vencimiento desde/hasta, empresas, libros
mayores ya subidos o subir otros) y las acciones sobre los marcados
(ver, exportar a HTML, Excel, PDF o Word, volver a generar, borrar);
abajo, el listado de informes y "Selección actual". Mientras un informe
se hace, la lista se refresca sola. Solo entra quien tiene
`CompanyUser.insurance_access` (Miguel Ángel: "visible solo para
Yolanda y Alejandro (y yo)"). Lógica: insurance/service.py (lectura de
documentos y montaje), insurance/builder.py y insurance/exports.py.
"""
import datetime
import json
import logging
from urllib.parse import quote

from django.db.models import Q
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views import View

from insurance import companies
from insurance import service
from insurance.models import InsuranceLedger
from insurance.models import InsuranceReport
from insurance.models import InsuranceReportExport
from panel.mixins import CompanyUserRequiredMixin
from panel.navigation_persistence import (
    apply_list_navigation,
    get_saved_state_key,
)

logger = logging.getLogger(__name__)

SCREEN_KEY = "insurance_reports"
FILTER_KEYS = ("search", "status", "date_from", "date_to", "due_from",
               "due_to", "supervisor", "sort")
DEFAULT_SORT = "-created"
_MAX_SORT_KEYS = 4
MAX_LEDGER_BYTES = 20 * 1024 * 1024
_COLUMNS = (
    ("number", "Nº"),
    ("title", "Informe"),
    ("created", "Fecha del informe"),
    ("due", "Mes de vencimiento"),
    ("supervisor", "Supervisor"),
    ("status", "Estado"),
    ("count", "Seguros"),
    ("premium", "Prima anual"),
    ("alerts", "Avisos"),
    ("ledgers", "Libros mayores"),
    ("exported", "Exportado a"),
)
_SORT_VALUES = {
    "number": lambda r: r.pk,
    "title": lambda r: r.title.upper(),
    "created": lambda r: r.created_at,
    "due": lambda r: (r.month_from, r.month_to or datetime.date.max),
    "supervisor": lambda r: r.supervisor_label.upper(),
    "status": lambda r: r.get_status_display(),
    "count": lambda r: r.policy_count,
    "premium": lambda r: r.premium_total,
    "alerts": lambda r: r.alert_count,
    "ledgers": lambda r: r.ledger_count,
    "exported": lambda r: r.exported_label,
}


def can_use_insurance(company_user):
    """
    True if this user may see the insurance reports.
    ---
    True si este usuario ve la pestaña Seguros.
    """
    return bool(company_user is not None
                and getattr(company_user, "insurance_access", False))


class InsuranceAccessMixin(CompanyUserRequiredMixin):
    """
    Only users with insurance access; the rest get a 403.
    ---
    Solo quien tiene acceso a los seguros; el resto recibe un 403 (la
    pestaña ni siquiera se le muestra).
    """

    def dispatch(self, request, *args, **kwargs):
        company_user = getattr(request.user, "company_user", None)
        if (request.user.is_authenticated
                and not can_use_insurance(company_user)):
            return HttpResponse("Acceso denegado: los informes de seguros "
                                "no son para tu usuario.", status=403)
        return super().dispatch(request, *args, **kwargs)


def _param(request, key, default=""):
    if request.method == "POST":
        return request.POST.get("_f_" + key, default)
    return request.GET.get(key, default)


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
    rows = sorted(rows, key=lambda r: r.pk)
    for key, desc in reversed(sort_keys):
        getter = _SORT_VALUES[key]
        present = [r for r in rows if getter(r) is not None]
        missing = [r for r in rows if getter(r) is None]
        rows = sorted(present, key=getter, reverse=desc) + missing
    return rows


def _month(raw):
    try:
        year, month = (int(v) for v in (raw or "").split("-")[:2])
        return datetime.date(year, month, 1)
    except (TypeError, ValueError):
        return None


def _day(raw):
    try:
        return datetime.date.fromisoformat(raw or "")
    except ValueError:
        return None


def _user_label(company_user):
    if company_user is None:
        return ""
    user = company_user.user
    return user.get_full_name() or user.username


def _decorate(report):
    report.supervisor_label = _user_label(report.created_by)
    report.due_label = service.due_label(report)
    report.companies_label = ", ".join(
        companies.label(c) for c in report.companies or []) or "Todas"
    ledgers = list(report.ledgers.all())
    report.ledger_count = len(ledgers)
    report.ledgers_label = "; ".join(
        "%s %s–%s" % (
            companies.label(item.company_code) or "Sin empresa",
            item.date_from.strftime("%m/%Y") if item.date_from else "?",
            item.date_to.strftime("%m/%Y") if item.date_to else "?")
        for item in ledgers)
    exports = list(report.exports.all())
    formats = []
    for export in exports:
        name = export.get_fmt_display()
        if name not in formats:
            formats.append(name)
    report.export_list = exports[:12]
    report.exported_label = ", ".join(formats)
    report.progress_pct = (round(100 * report.progress_done
                                 / report.progress_total)
                           if report.progress_total else 0)
    report.label = "#%s · %s" % (report.pk, report.title)
    return report


def _filtered(request):
    """
    The reports that meet the filters.
    ---
    Los informes que cumplen los filtros: búsqueda, estado, fecha del
    informe, mes de vencimiento y supervisor; o solo los seleccionados.
    """
    if "status" in request.GET or "_f_status" in request.POST:
        statuses = [v for v in _param(request, "status").split(",") if v]
    else:
        statuses = list(InsuranceReport.Status.values)
    qs = InsuranceReport.objects.select_related(
        "created_by__user").prefetch_related("ledgers", "exports")
    filters = {
        "search": _param(request, "search").strip(),
        "status": statuses,
        "date_from": _param(request, "date_from"),
        "date_to": _param(request, "date_to"),
        "due_from": _param(request, "due_from"),
        "due_to": _param(request, "due_to"),
        "supervisor": _param(request, "supervisor"),
    }
    if request.GET.get("only_selected") == "1":
        wanted = [pk for pk in request.GET.get(
            "selected_ids", "").split(",") if pk.isdigit()]
        return qs.filter(pk__in=wanted), filters
    qs = qs.filter(status__in=statuses)
    day_from, day_to = _day(filters["date_from"]), _day(filters["date_to"])
    if day_from:
        qs = qs.filter(created_at__date__gte=day_from)
    if day_to:
        qs = qs.filter(created_at__date__lte=day_to)
    due_from, due_to = _month(filters["due_from"]), _month(filters["due_to"])
    if due_from:
        qs = qs.filter(Q(month_to__isnull=True) | Q(month_to__gte=due_from))
    if due_to:
        qs = qs.filter(month_from__lte=due_to)
    if filters["supervisor"].isdigit():
        qs = qs.filter(created_by_id=int(filters["supervisor"]))
    for word in filters["search"].split():
        qs = qs.filter(Q(title__icontains=word)
                       | Q(created_by__user__first_name__icontains=word)
                       | Q(created_by__user__last_name__icontains=word)
                       ).distinct()
    return qs, filters


def _list_context(request):
    qs, filters = _filtered(request)
    rows = [_decorate(report) for report in qs]
    raw_sort = _param(request, "sort", DEFAULT_SORT)
    rows = _sort_rows(rows, _parse_sort(raw_sort))
    return {
        "rows": rows,
        "any_live": InsuranceReport.objects.filter(status__in=(
            InsuranceReport.Status.QUEUED, InsuranceReport.Status.READING,
            InsuranceReport.Status.BUILDING)).exists(),
        "filter_search": filters["search"],
        "filter_status": filters["status"],
        "filter_date_from": filters["date_from"],
        "filter_date_to": filters["date_to"],
        "filter_due_from": filters["due_from"],
        "filter_due_to": filters["due_to"],
        "filter_supervisor": filters["supervisor"],
        "status_choices": InsuranceReport.Status.choices,
        **_sort_controls(raw_sort),
    }


def _ledger_rows():
    rows = []
    for ledger in InsuranceLedger.objects.select_related(
            "uploaded_by__user"):
        rows.append({
            "pk": ledger.pk,
            "company": ledger.company_code,
            "label": _ledger_label(ledger),
            "entries": ledger.entry_count,
            "total": ledger.total,
        })
    return rows


def _ledger_label(ledger):
    # Sin nombre de archivo (criterio del panel): periodo, apuntes,
    # importe y fecha de impresión del listado.
    return "%s a %s · %d apuntes · %s €%s" % (
        ledger.date_from.strftime("%d/%m/%Y") if ledger.date_from else "?",
        ledger.date_to.strftime("%d/%m/%Y") if ledger.date_to else "?",
        ledger.entry_count,
        "{:,.2f}".format(ledger.total).replace(",", "X").replace(
            ".", ",").replace("X", "."),
        " · impreso el %s" % ledger.printed_at.strftime("%d/%m/%Y")
        if ledger.printed_at else "")


def _table_response(request, message="", error=False):
    response = render(request, "panel/insurance/_table.html",
                      _list_context(request))
    if message:
        response["X-Insurance-Message"] = quote(message)
        if error:
            response["X-Insurance-Error"] = "1"
    return response


def _supervisors():
    from ivr_config.models import CompanyUser

    users = CompanyUser.objects.filter(
        insurance_access=True).select_related("user")
    return [{"pk": u.pk, "label": _user_label(u)} for u in users]


class InsuranceTabView(InsuranceAccessMixin, View):
    """
    GET: the "Seguros" tab (directive 4.24).
    ---
    GET: pestaña "Seguros" del hub; filtros, orden y selección
    persistidos por usuario (screen_key "insurance_reports").
    """

    def get(self, request):
        apply_list_navigation(request, SCREEN_KEY, FILTER_KEYS)
        cu = request.user.company_user
        saved = get_saved_state_key(cu, SCREEN_KEY, "selection", [])
        today = timezone.localdate()
        return render(request, "panel/insurance/_pane.html", {
            **_list_context(request),
            "ledgers": _ledger_rows(),
            "company_choices": companies.CHOICES,
            "company_choices_json": json.dumps(companies.CHOICES),
            "supervisors": _supervisors(),
            "default_month": today.strftime("%Y-%m"),
            "screen_key": SCREEN_KEY,
            "saved_selection": saved if isinstance(saved, list) else [],
        })


class InsuranceResultsView(InsuranceAccessMixin, View):
    """
    GET: the table only (filters, order, live refresh).
    ---
    GET: solo la tabla (filtros, orden y refresco mientras se hace un
    informe).
    """

    def get(self, request):
        apply_list_navigation(request, SCREEN_KEY, FILTER_KEYS)
        return _table_response(request)


class InsuranceLedgerUploadView(InsuranceAccessMixin, View):
    """
    POST: one ledger PDF; JSON with what was read.
    ---
    POST: un PDF del libro mayor de la cuenta 625. Se lee al momento y
    devuelve la empresa detectada, el periodo y los apuntes; si ya se
    había subido el mismo PDF, devuelve el que estaba.
    """

    def post(self, request):
        upload = request.FILES.get("file")
        if upload is None:
            return JsonResponse({"ok": False, "error": "Falta el PDF."},
                                status=400)
        if upload.size > MAX_LEDGER_BYTES:
            return JsonResponse({"ok": False, "error": "%s: pesa más de "
                                 "20 MB." % upload.name}, status=400)
        try:
            ledger, created = service.save_ledger(
                upload.name, upload.read(), request.user.company_user)
        except service.InsuranceError as exc:
            return JsonResponse({"ok": False, "error": str(exc)},
                                status=400)
        return JsonResponse({
            "ok": True, "id": ledger.pk, "created": created,
            "company": ledger.company_code,
            "company_label": companies.label(ledger.company_code),
            "label": _ledger_label(ledger),
        })


class InsuranceLedgerCompanyView(InsuranceAccessMixin, View):
    """
    POST: change the company of a ledger (from the dropdown).
    ---
    POST: cambia la empresa de un libro mayor (desplegable; la empresa
    nunca se escribe a mano).
    """

    def post(self, request, pk):
        ledger = InsuranceLedger.objects.filter(pk=pk).first()
        code = request.POST.get("company", "")
        if ledger is None or code not in companies.LABELS:
            return JsonResponse({"ok": False, "error": "Elige la empresa "
                                 "de la lista."}, status=400)
        ledger.company_code = code
        ledger.save(update_fields=["company_code"])
        return JsonResponse({"ok": True})


class InsuranceReportCreateView(InsuranceAccessMixin, View):
    """
    POST: create a report and start it in the background.
    ---
    POST: crea un informe (mes de vencimiento desde/hasta, empresas,
    libros mayores y título) y lo lanza en segundo plano.
    """

    def post(self, request):
        month_from = _month(request.POST.get("month_from"))
        if month_from is None:
            return JsonResponse({"ok": False, "error": "Pon el mes de "
                                 "vencimiento «desde»."}, status=400)
        month_to = _month(request.POST.get("month_to"))
        codes = [c for c in request.POST.getlist("company")
                 if c in companies.LABELS]
        if len(codes) == len(companies.LABELS):
            codes = []
        ledger_ids = [v for v in request.POST.getlist("ledger")
                      if v.isdigit()]
        try:
            report = service.create_report(
                request.user.company_user, month_from, month_to, codes,
                ledger_ids, request.POST.get("title", ""))
        except service.InsuranceError as exc:
            return JsonResponse({"ok": False, "error": str(exc)},
                                status=400)
        return JsonResponse({"ok": True, "id": report.pk,
                             "title": report.title})


class InsuranceActionView(InsuranceAccessMixin, View):
    """
    POST: retry or delete the marked reports; returns the table.
    ---
    POST: volver a generar o borrar los informes marcados. Devuelve la
    tabla con el mensaje en una cabecera.
    """

    def post(self, request):
        action = request.POST.get("action", "")
        ids = [v for v in request.POST.getlist("selected") if v.isdigit()]
        reports = list(InsuranceReport.objects.filter(pk__in=ids))
        if not reports:
            return _table_response(request, "Marca algún informe.",
                                   error=True)
        if action == "retry":
            busy = [r for r in reports if r.is_live]
            for report in reports:
                if not report.is_live:
                    service.retry(report)
            message = "%d informe(s) en marcha otra vez." % (
                len(reports) - len(busy))
            if busy:
                message += " %d ya se estaba(n) haciendo." % len(busy)
        elif action == "delete":
            count = len(reports)
            for report in reports:
                report.delete()
            message = "%d informe(s) borrado(s)." % count
        else:
            return _table_response(request, "Acción desconocida.",
                                   error=True)
        return _table_response(request, message)


class InsuranceExportView(InsuranceAccessMixin, View):
    """
    GET: one report as HTML (view), HTML, Excel, PDF or Word.
    ---
    GET: un informe en HTML para verlo en el navegador (view=1) o
    descargado en HTML, Excel, PDF o Word. Cada descarga queda anotada
    para la columna «Exportado a».
    """

    def get(self, request, pk, fmt):
        from insurance.exports import EXPORTERS

        report = InsuranceReport.objects.filter(
            pk=pk, status=InsuranceReport.Status.DONE).select_related(
            "created_by__user").first()
        if report is None or fmt not in EXPORTERS:
            raise Http404
        function, content_type, extension = EXPORTERS[fmt]
        try:
            data = function(report)
        except Exception:  # noqa: BLE001 -- se informa al usuario
            logger.exception("# [insurance export] %s %s", pk, fmt)
            return HttpResponse("No se ha podido generar el %s. Avisa a "
                                "Miguel Ángel." % fmt.upper(), status=500)
        response = HttpResponse(data, content_type=content_type)
        if request.GET.get("view") == "1" and fmt == "html":
            return response
        InsuranceReportExport.objects.create(
            report=report, fmt=fmt, exported_by=request.user.company_user)
        name = "Informe_seguros_%s_%s.%s" % (
            report.pk, timezone.localtime(
                report.finished_at or report.created_at).strftime(
                "%Y%m%d"), extension)
        response["Content-Disposition"] = (
            "attachment; filename*=UTF-8''%s" % quote(name))
        response["Cache-Control"] = "private, no-store"
        return response
