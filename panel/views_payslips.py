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
from hr_calendar import payslip_access as access
from hr_calendar import payslip_delivery as pd
from hr_calendar.models import PayslipBatch, PayslipItem
from hr_calendar.worker_requests import person_label
from panel.mixins import CompanyUserRequiredMixin
from panel.navigation_persistence import (
    apply_list_navigation,
    get_saved_state_key,
)

logger = logging.getLogger(__name__)

SCREEN_KEY = "payslips"
FILTER_KEYS = ("batch", "search", "status", "month_from", "month_to",
               "date_from", "date_to", "sort", "active", "company", "group",
               "section")
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


def can_upload_payslips(company_user):
    """
    True if this user may start payslip deliveries.
    ---
    True si este usuario puede subir entregas de nóminas. S153, Miguel
    Ángel: "Sólo cargan Jerónimo y Alejandro. Yo para pruebas." -- solo
    quien tiene `CompanyUser.payslip_uploader` (antes, en S149, cualquier
    rol de Vacaciones/Solicitudes y Supervisor de documentación).
    """
    return bool(company_user is not None
                and getattr(company_user, "payslip_uploader", False))


def can_send_payslips(company_user):
    """
    True if this user may use the payslip screen.
    ---
    True si este usuario puede entrar en Nóminas: quien sube entregas
    y, S153, quien tiene acceso a todas o al que le han compartido
    alguna (aunque su rol no suba nóminas).
    """
    return can_upload_payslips(company_user) or access.has_any_batch(
        company_user)


class PayslipAccessMixin(CompanyUserRequiredMixin):
    """
    Access for who may use payslips; the rest go back to the panel.
    ---
    Acceso para quien puede entrar en Nóminas (can_send_payslips); el
    resto vuelve al panel con un aviso. Dentro, cada uno solo ve las
    entregas que subió, las que le comparten o, con acceso a todas,
    todas (S153).
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


def _batches(company_user):
    # S153: solo las entregas que este usuario ve.
    return list(access.visible_batches(company_user).select_related(
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


def _batch_summary(batch, company_user=None):
    if batch is None:
        return {}
    shares = list(batch.shares.select_related("company_user__user"))
    for share in shares:
        share.label = access.user_label(share.company_user)
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
        # S153: con quién está compartida y si quien mira puede cambiarlo.
        "batch_shares": shares,
        "batch_share_ids": {share.company_user_id for share in shares},
        "batch_can_share": access.can_share(batch, company_user),
    }


def _filtered_items(request, company_user):
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
    # S153: solo las nóminas de las entregas que este usuario ve.
    qs = PayslipItem.objects.filter(
        batch__in=access.visible_batches(company_user),
    ).select_related("batch", "person__company_user")
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
    # S153 (directriz 4.27): bloque común de las pestañas de personas
    # sobre el trabajador de cada nómina; las que aún no tienen
    # trabajador (sin casar) se ven siempre.
    from panel.common_filters import common_people

    people, _active, _companies = common_people(request)
    qs = qs.filter(Q(person__in=[person.pk for person in people])
                   | Q(person__isnull=True))
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
    company_user = request.user.company_user
    batches = _batches(company_user)
    batch = _current_batch(request, batches)
    qs, filters = _filtered_items(request, company_user)
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
        **_batch_summary(batch, company_user),
        "share_candidates": _share_candidates(company_user, batch),
        "filter_search": filters["search"],
        "filter_status": filters["status"],
        "filter_month_from": filters["month_from"],
        "filter_month_to": filters["month_to"],
        "filter_date_from": filters["date_from"],
        "filter_date_to": filters["date_to"],
        "status_choices": PayslipItem.Status.choices,
        **_sort_controls(raw_sort),
    }


def _share_candidates(company_user, batch=None):
    """
    Users a batch can be shared with, labelled.
    ---
    S153: los supervisores a los que se puede dar acceso (sin quien
    subió la entrega).
    """
    users = access.share_candidates(
        company_user.company,
        exclude=batch.created_by if batch is not None else company_user,
    )
    for user in users:
        user.label = access.user_label(user)
    return users


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
    from panel.common_filters import person_filter_context
    from panel.person_groups import group_filter_context
    from panel.views_documentation_h30 import COMPANY_FILTER_CHOICES
    from panel.views_vacation_balance import _csv_param

    apply_list_navigation(request, SCREEN_KEY, FILTER_KEYS)
    cu = request.user.company_user
    saved = get_saved_state_key(cu, SCREEN_KEY, "selection", [])
    return {
        # S153 (4.27): bloque común de filtros de personas.
        **person_filter_context(request),
        "filter_active": _csv_param(request, "active", ["true"]),
        "filter_company": _csv_param(request, "company", [
            slug for slug, _l, _r in COMPANY_FILTER_CHOICES]),
        **_list_context(request),
        **group_filter_context(request),
        "people": _people(cu.company),
        "can_upload": can_upload_payslips(cu),
        "new_share_candidates": _share_candidates(cu),
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
    batch = access.visible_batches(request.user.company_user).filter(
        pk=pk).first()
    if batch is None:
        raise Http404
    return batch


def _chosen_users(request, company_user, batch=None):
    """
    The share candidates ticked in the request ("share" values).
    ---
    S153: los usuarios marcados en "Acceso para" (valores "share"),
    siempre de la lista de candidatos (nunca otro usuario cualquiera).
    """
    wanted = set(request.POST.getlist("share"))
    return [user for user in _share_candidates(company_user, batch)
            if str(user.pk) in wanted]


class PayslipBatchCreateView(PayslipAccessMixin, View):
    """
    POST: starts a new delivery (before uploading its PDFs).
    ---
    POST: crea una entrega nueva ("Subiendo") con el nombre de la
    carpeta elegida; luego se suben sus PDF uno a uno.
    """

    def post(self, request):
        cu = request.user.company_user
        if not can_upload_payslips(cu):
            return JsonResponse({"ok": False, "error": "Tu rol no sube "
                                 "nóminas."}, status=403)
        batch = PayslipBatch.objects.create(
            company=cu.company, created_by=cu,
            folder_name=request.POST.get("folder", "")[:255],
            notify_whatsapp=request.POST.get("notify") != "0",
        )
        # S153: acceso para los supervisores marcados (se les avisa al
        # terminar la lectura).
        access.set_shares(batch, _chosen_users(request, cu), cu)
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
        visible = access.visible_batches(cu)
        batch = visible.filter(pk=raw if raw.isdigit() else 0).first()
        action = request.POST.get("action", "")
        ids = [v for v in request.POST.getlist("selected") if v.isdigit()]
        items = list(PayslipItem.objects.filter(
            pk__in=ids, batch__in=visible).select_related("batch"))
        if action in ("approve", "retry", "notify", "cancel", "share") and (
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
            elif action == "share":
                # S153: quién más ve, descarga y envía esta entrega.
                if not access.can_share(batch, cu):
                    raise pd.PayslipError(
                        "Solo quien subió la entrega puede cambiar el "
                        "acceso.")
                added, removed = access.set_shares(
                    batch, _chosen_users(request, cu, batch), cu)
                message = "Acceso guardado (%d nuevo%s, %d quitado%s)." % (
                    added, "" if added == 1 else "s",
                    removed, "" if removed == 1 else "s")
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
            pk__in=ids, batch__in=access.visible_batches(cu)).select_related(
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


def _download_name(item):
    """
    File name of one payslip when downloaded.
    ---
    S153: nombre del PDF descargado: apellidos y nombre del trabajador,
    mes y número de nómina ("RUIZ_GIL_ANA_Nomina_Octubre_2026_15.pdf").
    """
    import re

    parts = [item.person_label or "Sin_trabajador", "Nomina",
             item.period_label or "", str(item.pk)]
    text = "_".join(part for part in parts if part)
    return re.sub(r"[^A-Za-z0-9]+", "_", pd._plain(text)).strip("_") + ".pdf"


def _item_bytes(item, company_user):
    """
    The PDF of one payslip for this user.
    ---
    S153: el PDF de una nómina: el archivado en la ficha del trabajador
    si ya se envió (confidencial: queda en su registro de accesos) o,
    si no, sus páginas de la copia cifrada de la subida.
    """
    from document_explorer.confidential import ConfidentialError, open_bytes

    if item.entry_id is not None:
        try:
            return open_bytes(item.entry, company_user)
        except ConfidentialError as exc:
            raise pd.PayslipError(str(exc)) from exc
    if not item.staged_path:
        raise pd.PayslipError("La nómina %s no tiene PDF guardado."
                              % item.pk)
    return pd.item_pdf(item)


class PayslipDownloadView(PayslipAccessMixin, View):
    """
    POST: the marked payslips as a PDF (one) or a ZIP (several).
    ---
    POST: descarga las nóminas marcadas -- una, su PDF; varias, un ZIP
    con un PDF por nómina. S153, Miguel Ángel: el supervisor podrá
    "descargarlas también a su directorio local para poder usarlas,
    para subirlas a plataformas". Solo de las entregas que ve.
    """

    def post(self, request):
        import io
        import zipfile

        cu = request.user.company_user
        ids = [v for v in request.POST.getlist("selected") if v.isdigit()]
        items = [_decorate(item) for item in PayslipItem.objects.filter(
            pk__in=ids, batch__in=access.visible_batches(cu),
        ).exclude(page_to=0).select_related(
            "batch", "entry", "person__company_user").order_by(
                "period_end", "person__first_surname", "pk")]
        if not items:
            return HttpResponse("No hay ninguna nómina seleccionada que "
                                "se pueda descargar.", status=400)
        try:
            if len(items) == 1:
                data = _item_bytes(items[0], cu)
                response = HttpResponse(data, content_type="application/pdf")
                name = _download_name(items[0])
            else:
                buffer = io.BytesIO()
                with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
                    for item in items:
                        zf.writestr(_download_name(item),
                                    _item_bytes(item, cu))
                response = HttpResponse(buffer.getvalue(),
                                        content_type="application/zip")
                name = "Nominas_%s.zip" % timezone.localdate().strftime(
                    "%Y%m%d")
        except pd.PayslipError as exc:
            return HttpResponse(str(exc), status=400)
        response["Content-Disposition"] = (
            "attachment; filename*=UTF-8''%s" % quote(name))
        response["Cache-Control"] = "private, no-store"
        return response


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

        # S163 (25/11): Meta descarga la muestra de la plantilla para
        # aprobarla (payslip_delivery se rechazó por un enlace de ejemplo
        # que no devolvía nada). La muestra es un PDF sin datos.
        if token == pd.SAMPLE_MEDIA_NAME:
            response = HttpResponse(pd.sample_pdf(),
                                    content_type="application/pdf")
            response["Content-Disposition"] = (
                'inline; filename="%s"' % pd.SAMPLE_MEDIA_NAME)
            return response
        # Los enlaces terminan en «.pdf» (Twilio exige la extensión).
        if token.endswith(".pdf"):
            token = token[:-4]
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
