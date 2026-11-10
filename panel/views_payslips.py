# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/views_payslips.py
"""
H24 (S149 invasora). Payslip delivery page (directive 4.24 format).
The logic lives in hr_calendar.payslip_delivery.

---

Entrega de nóminas (H24, S149). Página con el formato de la directriz
4.24: arriba "Buscar y filtrar" (la entrega, búsqueda y estados), la
entrega elegida (estado, nueva entrega eligiendo una carpeta, anular) y
las acciones (dejar fuera, volver a meter, poner el trabajador, visto
bueno y enviar, reintentar el WhatsApp); abajo, el listado de nóminas y
"Selección actual". Mientras se lee o se envía, el listado se refresca
solo. La lógica vive en hr_calendar.payslip_delivery; aquí se lee la
petición, se llama y se pinta. El enlace temporal del que Twilio recoge
cada PDF (PayslipMediaView) es la única vista sin sesión.
"""
import datetime
import logging
from urllib.parse import quote

from django.db.models import Q
from django.http import Http404, HttpResponse, JsonResponse
from django.contrib import messages
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views import View

from document_explorer.models import PersonIdentity
from hr_calendar import payslip_delivery as pd
from hr_calendar.models import PayslipBatch, PayslipItem
from hr_calendar.worker_requests import person_label
from ivr_config.models import CompanyUser
from panel.mixins import CompanyUserRequiredMixin
from panel.navigation_persistence import (
    apply_list_navigation,
    get_saved_state_key,
)
from panel.views_vacation_balance import MANAGE_ROLES

logger = logging.getLogger(__name__)

SCREEN_KEY = "payslips"
FILTER_KEYS = ("batch", "search", "status", "month_from", "month_to",
               "date_from", "date_to", "sort")
DEFAULT_SORT = "-batch,file"
_MAX_SORT_KEYS = 4
_COLUMNS = (
    ("batch", "Entrega"),
    ("file", "Archivo"),
    ("pages", "Páginas"),
    ("person", "Trabajador"),
    ("dni", "DNI/NIE"),
    ("month", "Mes"),
    ("phone", "Móvil"),
    ("status", "Estado"),
    ("sent", "Enviada"),
)
_SORT_VALUES = {
    "batch": lambda r: (r.batch.created_at, r.batch_id),
    "file": lambda r: (r.original_name.upper(), r.page_from),
    "pages": lambda r: r.page_to - r.page_from,
    "person": lambda r: r.person_label.upper(),
    "dni": lambda r: r.dni_found,
    "month": lambda r: r.period_end,
    "phone": lambda r: r.phone_label,
    "status": lambda r: r.get_status_display(),
    "sent": lambda r: r.sent_at,
}
_LIVE = (PayslipBatch.Status.UPLOADING, PayslipBatch.Status.READING,
         PayslipBatch.Status.SENDING)
_CANCELABLE = (PayslipBatch.Status.UPLOADING, PayslipBatch.Status.READING,
               PayslipBatch.Status.READY)


# Los roles que gestionan las solicitudes (los de Vacaciones y
# Solicitudes) y, S149 (Miguel Ángel: "deben de tener tanto Yolanda como
# Jerónimo"), Supervisor de documentación. Las nóminas son confidenciales:
# cada una solo la abren su trabajador y quien la envió.
PAYSLIP_ROLES = set(MANAGE_ROLES) | {CompanyUser.ROLE_DOCS_SUPERVISOR}


def can_send_payslips(company_user):
    """
    True if this user may use the payslip delivery.
    ---
    True si este usuario puede usar la entrega de nóminas.
    """
    return company_user is not None and company_user.role in PAYSLIP_ROLES


class PayslipAccessMixin(CompanyUserRequiredMixin):
    """
    Access for PAYSLIP_ROLES; the rest go back to the panel.
    ---
    Acceso para PAYSLIP_ROLES; el resto vuelve al panel con un aviso.
    """

    def dispatch(self, request, *args, **kwargs):
        company_user = getattr(request.user, "company_user", None)
        if (request.user.is_authenticated and company_user is not None
                and not can_send_payslips(company_user)):
            messages.error(request, "Acceso denegado: la entrega de "
                                    "nóminas no es para tu rol.")
            return redirect("/panel/")
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


def _batches(company):
    return list(PayslipBatch.objects.filter(company=company).select_related(
        "created_by__user", "approved_by__user"))


def _current_batch(request, batches):
    raw = _param(request, "batch")
    for batch in batches:
        if str(batch.pk) == raw:
            return batch
    return None


def _month(raw):
    """
    "YYYY-MM" -> first day of that month, or None.
    ---
    "AAAA-MM" -> primer día de ese mes, o None.
    """
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


def _decorate(item):
    item.person_label = person_label(item.person) if item.person else ""
    if not item.phone and item.person is not None:
        item.phone_label = pd.worker_phone(item.person) or ""
    else:
        item.phone_label = item.phone
    if not item.page_to:
        item.pages_label = ""
    elif item.page_from == item.page_to:
        item.pages_label = str(item.page_from)
    else:
        item.pages_label = "%s–%s" % (item.page_from, item.page_to)
    item.label = "%s — %s (#%s)" % (
        item.person_label or "Sin trabajador",
        item.period_label or item.original_name, item.batch_id)
    item.can_change = item.batch.status == PayslipBatch.Status.READY
    return item


def _batch_summary(batch):
    if batch is None:
        return {}
    counts = {value: 0 for value in PayslipItem.Status.values}
    for status in batch.items.values_list("status", flat=True):
        counts[status] += 1
    return {
        "count_total": sum(counts.values()),
        "count_by_status": [
            (label, counts[value]) for value, label
            in PayslipItem.Status.choices if counts[value]],
        "count_unmatched": counts[PayslipItem.Status.UNMATCHED],
        "count_ready": counts[PayslipItem.Status.READY],
        "count_retry": (counts[PayslipItem.Status.FILED]
                        + counts[PayslipItem.Status.ERROR]),
    }


def _filtered_items(request, company):
    """
    The payslips that meet the filters (all deliveries by default).
    ---
    Las nóminas que cumplen los filtros: entrega (todas por defecto),
    mes de la nómina, fechas de subida, estados y búsqueda; o solo las
    seleccionadas.
    """
    if "status" in request.GET or "_f_status" in request.POST:
        statuses = [v for v in _param(request, "status").split(",") if v]
    else:
        statuses = list(PayslipItem.Status.values)
    qs = PayslipItem.objects.filter(batch__company=company).select_related(
        "batch", "person__company_user")
    filters = {
        "search": _param(request, "search").strip(),
        "status": statuses,
        "month_from": _param(request, "month_from"),
        "month_to": _param(request, "month_to"),
        "date_from": _param(request, "date_from"),
        "date_to": _param(request, "date_to"),
    }
    if request.GET.get("only_selected") == "1":
        wanted = [pk for pk in request.GET.get(
            "selected_ids", "").split(",") if pk.isdigit()]
        return qs.filter(pk__in=wanted), filters
    batch_raw = _param(request, "batch")
    if batch_raw.isdigit():
        qs = qs.filter(batch_id=int(batch_raw))
    qs = qs.filter(status__in=statuses)
    month_from, month_to = (_month(filters["month_from"]),
                            _month(filters["month_to"]))
    if month_from:
        qs = qs.filter(period_end__gte=month_from)
    if month_to:
        qs = qs.filter(period_end__lt=pd._month_end(
            month_to.year, month_to.month) + datetime.timedelta(days=1))
    day_from, day_to = _day(filters["date_from"]), _day(filters["date_to"])
    if day_from:
        qs = qs.filter(batch__created_at__date__gte=day_from)
    if day_to:
        qs = qs.filter(batch__created_at__date__lte=day_to)
    for word in filters["search"].split():
        qs = qs.filter(
            Q(original_name__icontains=word)
            | Q(dni_found__icontains=word)
            | Q(period_label__icontains=word)
            | Q(batch__folder_name__icontains=word)
            | Q(person__first_surname__icontains=word)
            | Q(person__second_surname__icontains=word)
            | Q(person__given_name__icontains=word)
            | Q(person__nickname__icontains=word)
            | Q(person__dni__icontains=word),
        )
    return qs, filters


def _list_context(request):
    company = request.user.company_user.company
    batches = _batches(company)
    batch = _current_batch(request, batches)
    qs, filters = _filtered_items(request, company)
    rows = [_decorate(item) for item in qs]
    raw_sort = _param(request, "sort", DEFAULT_SORT)
    rows = _sort_rows(rows, _parse_sort(raw_sort))
    return {
        "rows": rows,
        "batches": batches,
        "batch": batch,
        "batch_live": batch is not None and batch.status in _LIVE,
        "any_live": any(b.status in _LIVE for b in batches),
        "batch_ready": (batch is not None
                        and batch.status == PayslipBatch.Status.READY),
        "batch_cancelable": (batch is not None
                             and batch.status in _CANCELABLE),
        **_batch_summary(batch),
        "filter_search": filters["search"],
        "filter_status": filters["status"],
        "filter_month_from": filters["month_from"],
        "filter_month_to": filters["month_to"],
        "filter_date_from": filters["date_from"],
        "filter_date_to": filters["date_to"],
        "status_choices": PayslipItem.Status.choices,
        **_sort_controls(raw_sort),
    }


def _people(company):
    return [
        {"pk": p.pk, "label": "%s · %s" % (person_label(p), p.dni)}
        for p in PersonIdentity.objects.filter(company=company).order_by(
            "first_surname", "second_surname", "given_name")
    ]


def _table_response(request, message="", error=False):
    response = render(request, "panel/payslips/_table.html",
                      _list_context(request))
    if message:
        response["X-Payslips-Message"] = quote(message)
        if error:
            response["X-Payslips-Error"] = "1"
    return response


def _pane_context(request):
    from panel.person_groups import group_filter_context

    apply_list_navigation(request, SCREEN_KEY, FILTER_KEYS)
    cu = request.user.company_user
    saved = get_saved_state_key(cu, SCREEN_KEY, "selection", [])
    return {
        **_list_context(request),
        **group_filter_context(request),
        "people": _people(cu.company),
        "screen_key": SCREEN_KEY,
        "saved_selection": saved if isinstance(saved, list) else [],
    }


class PayslipTabView(PayslipAccessMixin, View):
    """
    GET: "Nóminas" tab of the Documentation hub (directive 4.24).
    ---
    GET: pestaña "Nóminas" del hub de Documentación, formato de la
    directriz 4.24; filtros, orden y selección persistidos por usuario
    (screen_key "payslips").
    """

    def get(self, request):
        return render(request, "panel/payslips/_pane.html",
                      _pane_context(request))


class PayslipPageView(PayslipAccessMixin, View):
    """
    GET: the same tab as a page (roles without the hub).
    ---
    GET: la misma pestaña como página propia, para quien no tiene el hub
    de Documentación (Supervisor, Jefe de taller).
    """

    def get(self, request):
        context = _pane_context(request)
        context["active_nav"] = "worker_requests"
        return render(request, "panel/payslips/page.html", context)


class PayslipResultsView(PayslipAccessMixin, View):
    """
    GET: the table only (filters, order, batch, live refresh).
    ---
    GET: solo la tabla (filtros, orden, entrega y refresco mientras se
    lee o se envía).
    """

    def get(self, request):
        apply_list_navigation(request, SCREEN_KEY, FILTER_KEYS)
        return _table_response(request)


def _own_batch(request, pk):
    batch = PayslipBatch.objects.filter(
        pk=pk, company=request.user.company_user.company).first()
    if batch is None:
        raise Http404
    return batch


class PayslipBatchCreateView(PayslipAccessMixin, View):
    """
    POST: starts a new delivery (before uploading its PDFs).
    ---
    POST: crea una entrega nueva ("Subiendo") con el nombre de la
    carpeta elegida; luego se suben sus PDF uno a uno.
    """

    def post(self, request):
        cu = request.user.company_user
        batch = PayslipBatch.objects.create(
            company=cu.company, created_by=cu,
            folder_name=request.POST.get("folder", "")[:255],
            notify_whatsapp=request.POST.get("notify") != "0",
        )
        return JsonResponse({"ok": True, "id": batch.pk})


class PayslipUploadView(PayslipAccessMixin, View):
    """
    POST: one PDF of the chosen folder (kept encrypted until sent).
    ---
    POST: uno de los PDF de la carpeta (se guarda cifrado hasta el
    envío).
    """

    def post(self, request, pk):
        batch = _own_batch(request, pk)
        if batch.status != PayslipBatch.Status.UPLOADING:
            return JsonResponse({"ok": False, "error": "La entrega ya no "
                                 "admite archivos."}, status=400)
        upload = request.FILES.get("file")
        if upload is None:
            return JsonResponse({"ok": False, "error": "Falta el archivo."},
                                status=400)
        try:
            pd.stage_file(batch, upload.name, upload.read())
        except pd.PayslipError as exc:
            return JsonResponse({"ok": False, "error": str(exc)}, status=400)
        return JsonResponse({"ok": True})


class PayslipStartReadingView(PayslipAccessMixin, View):
    """
    POST: all PDFs are up; the background reading starts.
    ---
    POST: ya están todos los PDF; empieza la lectura en segundo plano
    (al acabar, aviso por WhatsApp a quien inició la entrega).
    """

    def post(self, request, pk):
        from hr_calendar.tasks import read_payslip_batch_task

        batch = _own_batch(request, pk)
        if batch.status != PayslipBatch.Status.UPLOADING:
            return JsonResponse({"ok": False, "error": "La entrega ya se "
                                 "está leyendo."}, status=400)
        if not batch.items.exists():
            batch.delete()
            return JsonResponse({"ok": False, "error": "No se ha subido "
                                 "ningún PDF."}, status=400)
        batch.status = PayslipBatch.Status.READING
        batch.save(update_fields=["status"])
        read_payslip_batch_task.delay(batch.pk)
        return JsonResponse({"ok": True, "id": batch.pk})


class PayslipActionView(PayslipAccessMixin, View):
    """
    POST: an action on a batch (batch_id) or on the marked payslips.
    ---
    POST: una acción sobre la entrega (visto bueno y enviar, reintentar
    el WhatsApp, anular, volver a avisar) o sobre las nóminas marcadas
    (dejar fuera, volver a meter, poner el trabajador). Devuelve la
    tabla con el mensaje en una cabecera.
    """

    def post(self, request):
        from hr_calendar.tasks import (
            retry_payslip_whatsapp_task, send_payslip_batch_task,
        )

        cu = request.user.company_user
        raw = request.POST.get("batch_id", "")
        batch = PayslipBatch.objects.filter(
            pk=raw if raw.isdigit() else 0, company=cu.company).first()
        action = request.POST.get("action", "")
        ids = [v for v in request.POST.getlist("selected") if v.isdigit()]
        items = list(PayslipItem.objects.filter(
            pk__in=ids, batch__company=cu.company).select_related("batch"))
        if action in ("approve", "retry", "notify", "cancel") and (
                batch is None):
            return _table_response(
                request, "Elige la entrega en el filtro «Entrega».",
                error=True)
        try:
            if action in ("exclude", "include"):
                if not items:
                    raise pd.PayslipError("Marca alguna nómina.")
                for item in items:
                    pd.set_excluded(item, action == "exclude")
                message = "%d nómina(s) %s." % (
                    len(items), "fuera de la entrega" if action == "exclude"
                    else "otra vez en la entrega")
            elif action == "assign":
                if len(items) != 1:
                    raise pd.PayslipError(
                        "Marca una sola nómina para ponerle el trabajador.")
                person = None
                raw = request.POST.get("person", "")
                if raw:
                    person = PersonIdentity.objects.filter(
                        pk=raw if raw.isdigit() else 0,
                        company=cu.company).first()
                    if person is None:
                        raise pd.PayslipError("Elige el trabajador de la "
                                              "lista.")
                pd.assign(items[0], person)
                message = ("Nómina asignada a %s." % person_label(person)
                           if person else "Nómina sin trabajador.")
            elif action == "approve":
                pd.approve(batch, cu)
                send_payslip_batch_task.delay(batch.pk)
                message = ("Visto bueno dado: se están archivando y "
                           "enviando las nóminas.")
            elif action == "retry":
                retry_payslip_whatsapp_task.delay(batch.pk)
                message = ("Reintentando el WhatsApp de las nóminas que no "
                           "salieron.")
            elif action == "notify":
                message = ("Aviso enviado." if pd.notify_ready(batch)
                           else "No se ha podido avisar: %s"
                           % batch.notify_error)
            elif action == "cancel":
                pd.cancel(batch)
                message = "Entrega anulada; sus copias se han borrado."
            else:
                raise pd.PayslipError("Acción desconocida.")
        except pd.PayslipError as exc:
            return _table_response(request, str(exc), error=True)
        return _table_response(request, message)


class PayslipExportView(PayslipAccessMixin, View):
    """
    POST: Excel, PDF or print of the marked payslips (template).
    ---
    POST: Excel, PDF o imprimir de las nóminas marcadas, con la
    plantilla elegida (modal común de exportación, S148). Solo datos del
    listado; nunca el contenido de las nóminas.
    """

    def post(self, request):
        from openpyxl import Workbook

        from panel.export_formats import workbook_response
        from panel.screen_exports import columns_for, get_screen
        from panel.screen_exports import write_sheet

        cu = request.user.company_user
        ids = [v for v in request.POST.getlist("selected") if v.isdigit()]
        rows = [_decorate(item) for item in PayslipItem.objects.filter(
            pk__in=ids, batch__company=cu.company).select_related(
                "batch", "person__company_user").order_by(
                    "-batch__created_at", "original_name", "page_from")]
        if not rows:
            return HttpResponse("No hay ninguna nómina seleccionada.",
                                status=400)
        columns = columns_for(request, get_screen("payslips"))
        if columns is None:
            return HttpResponse("Plantilla no encontrada.", status=404)
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "NOMINAS"
        write_sheet(sheet, columns, rows)
        return workbook_response(request, workbook, "entrega_nominas")


class PayslipMediaView(View):
    """
    GET (no session): the PDF of one payslip for Twilio, while valid.
    ---
    GET sin sesión: el PDF de una nómina para que Twilio lo recoja y lo
    mande por WhatsApp. Solo con su enlace temporal (token largo
    aleatorio) y antes de que caduque; cada recogida queda en el
    registro de accesos del documento confidencial.
    """

    def get(self, request, token):
        from document_explorer.confidential import decrypt
        from document_explorer.models import ConfidentialAccessLog
        from spare_parts.gcs_service import download_bytes

        item = PayslipItem.objects.filter(
            media_token=token, media_expires__gt=timezone.now(),
            entry__isnull=False,
        ).select_related("entry").first() if len(token) >= 32 else None
        if item is None:
            raise Http404
        entry = item.entry
        ConfidentialAccessLog.objects.create(
            entry=entry, company_user=None, allowed=True)
        data = decrypt(download_bytes(entry.bucket, entry.blob_name))
        response = HttpResponse(data, content_type="application/pdf")
        response["Content-Disposition"] = (
            "inline; filename*=UTF-8''%s" % quote(entry.name))
        response["Cache-Control"] = "private, no-store"
        return response
