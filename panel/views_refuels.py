# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/views_refuels.py
"""
"Repostajes" tab of the Documentation hub (H30, S135): the fuel
supplies read from GasoGes, with the usual list layout (directive
4.24).

---

Pestaña "Repostajes" del hub de Documentación (H30, S135), después de
Centros de gasto y Revisiones. Miguel Ángel: "el CRUD con los
repostajes que se puedan ver desde el panel, con el mismo formato que
ya estamos usando en todas las vistas". Una fila por suministro de
GasoGes (fecha, centro de gasto, vehículo, quién repostó, KM tecleado,
unidad, litros, estado y motivo), con filtros, orden múltiple,
selección, exportación a Excel y una acción masiva: fijar a mano si el
vehículo apunta km u horas (S135: A44 no se pudo deducir). Los
suministros no se editan: el dato correcto lo dará el chófer por
WhatsApp.
"""
import datetime
import io

from django.db.models import Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views import View

from fleet.gasoges_sync import build_readings
from fleet.models import GasoGesSupply, GasoGesVehicle
from panel.mixins import CompanyUserRequiredMixin
from panel.navigation_persistence import (
    apply_list_navigation,
    get_saved_state_key,
)
from panel.views_machine_service import can_edit_service
from panel.views_vacation_balance import _param, _parse_date

SCREEN_KEY = "refuels"
FILTER_KEYS = ("search", "status", "date_from", "date_to", "sort")
NO_STATUS = "none"
_MAX_SORT_KEYS = 4
_MAX_RANGE_DAYS = 366
_DEFAULT_DAYS = 30
_MAX_ROWS = 1000

_COLUMNS = (
    ("date", "Fecha y hora", "supplied_at"),
    ("machine", "Centro de gasto", "vehicle__machine__code"),
    ("vehicle", "Vehículo (GasoGes)", "vehicle__plate"),
    ("driver", "Quién repostó", "user__name"),
    ("value", "KM tecleado", "meter_value"),
    ("litres", "Litros", "litres"),
    ("status", "Estado", "status"),
)
_SORT_FIELDS = {key: field for key, _label, field in _COLUMNS}

_STATUS_BADGES = {
    GasoGesSupply.STATUS_READING: "success",
    GasoGesSupply.STATUS_ANOMALY: "danger",
    GasoGesSupply.STATUS_NO_UNIT: "warning",
    GasoGesSupply.STATUS_NO_MACHINE: "secondary",
    GasoGesSupply.STATUS_PENDING: "light",
}
_UNIT_SOURCE_LABELS = {
    GasoGesVehicle.UNIT_SOURCE_DEDUCED: "deducida",
    GasoGesVehicle.UNIT_SOURCE_DRIVER: "chófer",
    GasoGesVehicle.UNIT_SOURCE_MANUAL: "a mano",
}


def _date_range(request):
    """
    (date_from, date_to); default the last 30 days, at most one year.

    ---

    (desde, hasta); por defecto los últimos 30 días. Un intervalo al
    revés se da la vuelta y uno de más de un año se corta.
    """
    today = timezone.localdate()
    date_from = _parse_date(_param(request, "date_from")) or (
        today - datetime.timedelta(days=_DEFAULT_DAYS - 1))
    date_to = _parse_date(_param(request, "date_to")) or today
    if date_to < date_from:
        date_from, date_to = date_to, date_from
    if (date_to - date_from).days >= _MAX_RANGE_DAYS:
        date_from = date_to - datetime.timedelta(days=_MAX_RANGE_DAYS - 1)
    return date_from, date_to


def _statuses(request):
    """
    Status filter with literal checkbox meaning.

    ---

    Filtro de estado con las casillas en sentido literal (directriz
    4.24, regla 6): todas marcadas = todos, ninguna = ninguno ("none").
    Sin el parámetro (primera carga), todos.
    """
    raw = _param(request, "status")
    valid = [code for code, _label in GasoGesSupply.STATUS_CHOICES]
    if raw == NO_STATUS:
        return []
    chosen = [code for code in raw.split(",") if code in valid]
    return chosen if raw else valid


def _parse_sort(raw):
    keys, seen = [], set()
    for token in (raw or "").split(","):
        token = token.strip()
        key = token.lstrip("-")
        if key in _SORT_FIELDS and key not in seen:
            keys.append((key, token.startswith("-")))
            seen.add(key)
    return keys[:_MAX_SORT_KEYS]


def _sort_controls(raw):
    """
    Header links, arrows and priorities (same rules as Fichajes).

    ---

    Enlaces, flechas y prioridad de cada cabecera (mismas reglas que
    Fichajes y Centros de gasto).
    """
    sort_keys = _parse_sort(raw)
    active = [key for key, _desc in sort_keys]
    columns = []
    for key, label, _field in _COLUMNS:
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


def _filtered_supplies(request):
    """
    Supplies of the filters (dates, statuses, search), unsorted.

    ---

    Suministros de los filtros (fechas, estados, búsqueda), sin
    ordenar. Las fechas van como intervalo de horas locales, sin
    `__date` (no depende de las tablas de zona horaria de MySQL).
    """
    date_from, date_to = _date_range(request)
    start = timezone.make_aware(
        datetime.datetime.combine(date_from, datetime.time.min))
    end = timezone.make_aware(datetime.datetime.combine(
        date_to + datetime.timedelta(days=1), datetime.time.min))
    supplies = GasoGesSupply.objects.select_related(
        "vehicle", "vehicle__machine", "user", "user__person",
    ).filter(supplied_at__gte=start, supplied_at__lt=end,
             status__in=_statuses(request))
    search = _param(request, "search").strip()
    if search:
        supplies = supplies.filter(
            Q(vehicle__machine__code__icontains=search)
            | Q(vehicle__plate__icontains=search)
            | Q(vehicle__name__icontains=search)
            | Q(user__name__icontains=search))
    return supplies


def _row(supply):
    """
    One supply ready for the template (dumb template).

    ---

    Un suministro listo para la plantilla: todo calculado aquí.
    """
    vehicle = supply.vehicle
    user = supply.user
    return {
        "pk": supply.pk,
        "when": timezone.localtime(supply.supplied_at),
        "machine": vehicle.machine,
        "vehicle_label": vehicle.plate or vehicle.name or (
            "GasoGes %s" % vehicle.gasoges_id),
        "vehicle_name": vehicle.name,
        "driver": user.name if user else (
            "Usuario %s" % (supply.gasoges_user_id or "?")),
        "has_person": bool(user and user.person_id),
        "value": supply.meter_value,
        "unit": vehicle.get_unit_display(),
        "unit_known": vehicle.unit != GasoGesVehicle.UNIT_UNKNOWN,
        "unit_source": _UNIT_SOURCE_LABELS.get(vehicle.unit_source, ""),
        "litres": supply.litres,
        "status": supply.get_status_display(),
        "status_badge": _STATUS_BADGES.get(supply.status, "light"),
        "note": supply.status_note,
        "label": "%s %s %s" % (
            timezone.localtime(supply.supplied_at).strftime("%d/%m %H:%M"),
            vehicle.machine.code if vehicle.machine else (
                vehicle.plate or vehicle.gasoges_id),
            supply.meter_value if supply.meter_value is not None else "-"),
    }


def _list_context(request):
    """
    Context of the table: filtered supplies, sorted, capped.

    ---

    Contexto de la tabla: suministros filtrados y ordenados, hasta
    1.000 filas (con aviso si hay más).
    """
    supplies = _filtered_supplies(request)
    if request.GET.get("only_selected") == "1":
        wanted = [int(pk) for pk in request.GET.get(
            "selected_ids", "").split(",") if pk.isdigit()]
        supplies = supplies.filter(pk__in=wanted)
    sort_keys = _parse_sort(_param(request, "sort"))
    order = [("-" if desc else "") + _SORT_FIELDS[key]
             for key, desc in sort_keys] or ["-supplied_at"]
    total = supplies.count()
    date_from, date_to = _date_range(request)
    statuses = _statuses(request)
    return {
        "rows": [_row(s) for s in supplies.order_by(*order, "-id")[
            :_MAX_ROWS]],
        "total": total,
        "capped": total > _MAX_ROWS,
        "max_rows": _MAX_ROWS,
        "filter_search": _param(request, "search"),
        "status_choices": [
            {"code": code, "label": label, "checked": code in statuses}
            for code, label in GasoGesSupply.STATUS_CHOICES],
        "date_from": date_from,
        "date_to": date_to,
        **_sort_controls(_param(request, "sort")),
    }


class RefuelsTabView(CompanyUserRequiredMixin, View):
    """
    GET: "Repostajes" tab (fixed panel, list, selection column).

    ---

    GET: pestaña "Repostajes" (panel fijo, listado y selección), con
    filtros, orden y selección persistidos por usuario (screen_key
    "refuels").
    """

    def get(self, request):
        apply_list_navigation(request, SCREEN_KEY, FILTER_KEYS)
        saved_selection = get_saved_state_key(
            request.user.company_user, SCREEN_KEY, "selection", [])
        if not isinstance(saved_selection, list):
            saved_selection = []
        return render(request, "panel/refuels/_pane.html", {
            **_list_context(request),
            "screen_key": SCREEN_KEY,
            "saved_selection": saved_selection,
            "can_edit": can_edit_service(request.user.company_user),
        })


class RefuelsResultsView(CompanyUserRequiredMixin, View):
    """
    GET: table only.

    ---

    GET: solo la tabla (filtros, fechas, orden).
    """

    def get(self, request):
        apply_list_navigation(request, SCREEN_KEY, FILTER_KEYS)
        return render(request, "panel/refuels/_table.html",
                      _list_context(request))


class RefuelsVehicleUnitView(CompanyUserRequiredMixin, View):
    """
    POST: set by hand whether the vehicles of the marked supplies type
    kilometres or hours, and redo their readings.

    ---

    POST: fija a mano si los vehículos de los repostajes marcados
    apuntan km u horas (queda "a mano": la deducción automática ya no
    la cambia) y convierte en lectura sus suministros pendientes de
    unidad. Solo los roles que anotan revisiones y lecturas.
    """

    def post(self, request):
        if not can_edit_service(request.user.company_user):
            return JsonResponse(
                {"ok": False, "error": "No tienes permiso para esto."},
                status=403)
        unit = request.POST.get("unit")
        if unit not in (GasoGesVehicle.UNIT_KM, GasoGesVehicle.UNIT_HOURS):
            return JsonResponse(
                {"ok": False, "error": "Elige kilómetros u horas."},
                status=400)
        wanted = [int(pk) for pk in request.POST.get(
            "selected_ids", "").split(",") if pk.isdigit()]
        vehicle_ids = set(GasoGesSupply.objects.filter(
            pk__in=wanted).values_list("vehicle_id", flat=True))
        vehicles = GasoGesVehicle.objects.filter(
            pk__in=vehicle_ids, machine__isnull=False)
        changed = vehicles.update(
            unit=unit, unit_source=GasoGesVehicle.UNIT_SOURCE_MANUAL)
        if not changed:
            return JsonResponse({
                "ok": False,
                "error": "Ninguno de los marcados tiene centro de gasto.",
            }, status=400)
        counters = build_readings(lambda _line: None)
        return JsonResponse({
            "ok": True,
            "message": "%d vehículo(s) en %s. Lecturas nuevas: %d; "
                       "dudosas: %d." % (
                           changed,
                           "kilómetros" if unit == GasoGesVehicle.UNIT_KM
                           else "horas",
                           counters["lecturas"], counters["dudosos"]),
        })


class RefuelsExportView(CompanyUserRequiredMixin, View):
    """
    GET: Excel of the marked supplies (or all the filtered ones).

    ---

    GET: Excel de los repostajes marcados o, si no hay ninguno, de
    todos los del filtro (sin el tope de 1.000 de la pantalla).
    """

    def get(self, request):
        from openpyxl import Workbook
        from openpyxl.styles import Font

        wanted = [int(pk) for pk in request.GET.get(
            "selected_ids", "").split(",") if pk.isdigit()]
        supplies = (GasoGesSupply.objects.select_related(
            "vehicle", "vehicle__machine", "user").filter(pk__in=wanted)
            if wanted else _filtered_supplies(request))
        book = Workbook()
        sheet = book.active
        sheet.title = "Repostajes"
        headers = [
            ("Fecha", 12), ("Hora", 8), ("Centro de gasto", 14),
            ("Matrícula (GasoGes)", 16), ("Nombre (GasoGes)", 28),
            ("Quién repostó", 32), ("KM tecleado", 12), ("Unidad", 11),
            ("Litros", 9), ("Precio", 9), ("Estado", 24), ("Motivo", 48),
        ]
        sheet.append([h for h, _w in headers])
        for supply in supplies.order_by("supplied_at", "id"):
            local = timezone.localtime(supply.supplied_at)
            vehicle = supply.vehicle
            sheet.append([
                local.date(), local.time().replace(microsecond=0),
                vehicle.machine.code if vehicle.machine else "",
                vehicle.plate, vehicle.name,
                supply.user.name if supply.user else "",
                supply.meter_value, vehicle.get_unit_display(),
                float(supply.litres) if supply.litres is not None
                else None,
                float(supply.price) if supply.price is not None else None,
                supply.get_status_display(), supply.status_note,
            ])
        for cell in sheet[1]:
            cell.font = Font(bold=True)
        sheet.freeze_panes = "A2"
        for index, (_header, width) in enumerate(headers):
            sheet.column_dimensions[chr(ord("A") + index)].width = width
        for cell in sheet["A"][1:]:
            cell.number_format = "DD/MM/YYYY"
        for cell in sheet["B"][1:]:
            cell.number_format = "HH:MM"
        buffer = io.BytesIO()
        book.save(buffer)
        date_from, date_to = _date_range(request)
        response = HttpResponse(
            buffer.getvalue(),
            content_type=("application/vnd.openxmlformats-officedocument."
                          "spreadsheetml.sheet"))
        response["Content-Disposition"] = (
            'attachment; filename="repostajes_%s_%s.xlsx"' % (
                date_from.strftime("%Y%m%d"), date_to.strftime("%Y%m%d")))
        return response
