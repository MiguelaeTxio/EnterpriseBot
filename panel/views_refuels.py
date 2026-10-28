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

S137: selector "Ver" con otras dos vistas sobre los mismos filtros,
Miguel Ángel: "necesito una visión desde el punto de vista de los
vehículos y otra desde el punto de vista de los repostadores". En
Vehículos, una fila por vehículo de GasoGes y en Repostadores una por
usuario de GasoGes, con sus totales en el periodo (repostajes, litros,
último repostaje, dudosos...). Las acciones de unidad y de preguntar al
chófer se aplican en Vehículos a los vehículos marcados.

S137: cuarta vista, "Preguntas", Miguel Ángel: "un poco de estadística,
a ver cuántos mensajes se han enviado [...] que se pudiera ver desde el
propio panel". Una fila por pregunta de WhatsApp enviada en las fechas
del filtro (cuándo, a quién, por qué vehículo, qué tecleó, por qué se
le pregunta, en qué quedó y qué contestó) y, encima, el resumen:
enviadas, chóferes, contestadas por respuesta, esperando y sin
respuesta. Los filtros de estado del repostaje y de "¿se pregunta?" no
aplican a esta vista; las fechas y la búsqueda, sí.

S137, Miguel Ángel: para quitar vehículos de las preguntas o marcar
contadores averiados hacía falta jugar con las fechas hasta que
salieran. Dos filtros nuevos:
- "Todos los activos" (vistas Vehículos y Repostadores): salen todos
  los vehículos de centros de gasto activos (o todos los repostadores),
  hayan repostado o no, sin mirar las fechas; los totales son de todo
  el histórico.
- "Familia": desplegable con las familias del catálogo, en todas las
  vistas, para marcar una familia entera (p. ej. quitarla de las
  preguntas) y luego añadir solo algunos vehículos.
"""
import datetime
import io

from django.db.models import Count, Max, Q, Sum
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views import View

from fleet.gasoges_sync import build_readings, redo_vehicle
from fleet.models import (
    GasoGesSupply,
    GasoGesUser,
    GasoGesVehicle,
    RefuelQuestion,
)
from panel.mixins import CompanyUserRequiredMixin
from panel.navigation_persistence import (
    apply_list_navigation,
    get_saved_state_key,
)
from panel.views_machine_service import can_edit_service
from panel.views_vacation_balance import _param, _parse_date

SCREEN_KEY = "refuels"
FILTER_KEYS = ("view", "search", "status", "ask", "date_from", "date_to",
               "sort", "family", "all_active")
NO_STATUS = "none"
# Filtro "¿Se pregunta al chófer?": sí / no (S135).
# ---
# "Is the driver asked?" filter: yes / no.
ASK_CHOICES = (("yes", "Sí"), ("no", "No"))
_MAX_SORT_KEYS = 4
_MAX_RANGE_DAYS = 366
_DEFAULT_DAYS = 30
_MAX_ROWS = 1000

# S137: tres vistas sobre los mismos suministros filtrados.
# ---
# Three views over the same filtered supplies.
VIEW_SUPPLIES = "supplies"
VIEW_VEHICLES = "vehicles"
VIEW_USERS = "users"
VIEW_QUESTIONS = "questions"
VIEW_CHOICES = (
    (VIEW_SUPPLIES, "Repostajes"),
    (VIEW_VEHICLES, "Vehículos"),
    (VIEW_USERS, "Repostadores"),
    (VIEW_QUESTIONS, "Preguntas por WhatsApp"),
)

_COLUMNS = {
    VIEW_SUPPLIES: (
        ("date", "Fecha y hora", "supplied_at"),
        ("machine", "Centro de gasto", "vehicle__machine__code"),
        ("vehicle", "Vehículo (GasoGes)", "vehicle__plate"),
        ("driver", "Quién repostó", "user__name"),
        ("value", "KM tecleado", "meter_value"),
        ("litres", "Litros", "litres"),
        ("status", "Estado", "status"),
    ),
    VIEW_VEHICLES: (
        ("vmachine", "Centro de gasto", "vehicle__machine__code"),
        ("vplate", "Vehículo (GasoGes)", "vehicle__plate"),
        ("vname", "Nombre (GasoGes)", "vehicle__name"),
        ("vcount", "Repostajes", "n_supplies"),
        ("vlitres", "Litros", "total_litres"),
        ("vlast", "Último repostaje", "last_at"),
        ("vkm", "Últimos KM (GasoGes)", "vehicle__last_km"),
        ("vanomaly", "Dudosos", "n_anomalies"),
        ("vdrivers", "Repostadores", "n_others"),
    ),
    VIEW_USERS: (
        ("uname", "Repostador (GasoGes)", "user__name"),
        ("uperson", "Ficha de trabajador", "user__person__first_surname"),
        ("ucount", "Repostajes", "n_supplies"),
        ("ulitres", "Litros", "total_litres"),
        ("ulast", "Último repostaje", "last_at"),
        ("uanomaly", "Dudosos", "n_anomalies"),
        ("uvehicles", "Vehículos", "n_others"),
    ),
    VIEW_QUESTIONS: (
        ("qsent", "Enviada", "sent_at"),
        ("qdriver", "Chófer", "person__first_surname"),
        ("qmachine", "Centro de gasto", "vehicle__machine__code"),
        ("qkind", "Pregunta", "kind"),
        ("qvalue", "Dato tecleado", "supply__meter_value"),
        ("qreason", "Por qué se pregunta", "reason"),
        ("qstatus", "En qué quedó", "status"),
        ("qanswer", "Respuesta", "answer"),
        ("qanswered", "Respondida", "answered_at"),
    ),
}
_DEFAULT_ORDER = {
    VIEW_SUPPLIES: ["-supplied_at"],
    VIEW_VEHICLES: ["vehicle__machine__code", "vehicle__plate"],
    VIEW_USERS: ["user__name"],
    VIEW_QUESTIONS: ["-sent_at"],
}
_SELECTION_KEYS = {
    VIEW_SUPPLIES: "selection",
    VIEW_VEHICLES: "selection_vehicles",
    VIEW_USERS: "selection_users",
    VIEW_QUESTIONS: "selection_questions",
}
_TOTAL_LABELS = {
    VIEW_SUPPLIES: "Repostajes",
    VIEW_VEHICLES: "Vehículos",
    VIEW_USERS: "Repostadores",
    VIEW_QUESTIONS: "Preguntas",
}
_QUESTION_BADGES = {
    RefuelQuestion.STATUS_SENT: "warning",
    RefuelQuestion.STATUS_AWAITING_VALUE: "info",
    RefuelQuestion.STATUS_CONFIRMED: "success",
    RefuelQuestion.STATUS_CORRECTED: "primary",
    RefuelQuestion.STATUS_UNIT_SET: "primary",
    RefuelQuestion.STATUS_METER_BROKEN: "dark",
    RefuelQuestion.STATUS_EXPIRED: "secondary",
}

_STATUS_BADGES = {
    GasoGesSupply.STATUS_READING: "success",
    GasoGesSupply.STATUS_ANOMALY: "danger",
    GasoGesSupply.STATUS_NO_UNIT: "warning",
    GasoGesSupply.STATUS_NO_MACHINE: "secondary",
    GasoGesSupply.STATUS_PENDING: "light",
    GasoGesSupply.STATUS_BROKEN_METER: "dark",
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


def _ask_values(request):
    """
    "Is the driver asked?" filter, literal checkboxes like the status.

    ---

    Filtro "¿Se pregunta al chófer?" con las casillas en sentido
    literal, como el de estado: las dos = todos, ninguna = ninguno.
    Devuelve los valores de `ask_driver` que se muestran.
    """
    raw = _param(request, "ask")
    if raw == NO_STATUS:
        return []
    chosen = [code for code in raw.split(",")
              if code in dict(ASK_CHOICES)] if raw else ["yes", "no"]
    return [code == "yes" for code in chosen]


def _family(request):
    """
    Chosen machine family ("" = all).

    ---

    Familia elegida en el desplegable ("" = todas).
    """
    return _param(request, "family").strip()


def _family_choices():
    """
    Families of the active machines, sorted.

    ---

    Familias del catálogo de los centros de gasto activos, ordenadas.
    """
    from fleet.models import MachineAsset

    return sorted(set(MachineAsset.objects.filter(is_active=True).exclude(
        family="").values_list("family", flat=True)))


def _all_active(request, view):
    """
    True if "all the active ones" is ticked and applies to the view.

    ---

    True si está marcada "Todos los activos" y la vista es Vehículos o
    Repostadores (en las otras no aplica).
    """
    return (_param(request, "all_active") == "1"
            and view in (VIEW_VEHICLES, VIEW_USERS))


def _view(request):
    """
    Current view: supplies, vehicles or users (default supplies).

    ---

    Vista actual: repostajes, vehículos o repostadores (por defecto,
    repostajes).
    """
    raw = _param(request, "view")
    return raw if raw in dict(VIEW_CHOICES) else VIEW_SUPPLIES


def _sort_fields(view):
    return {key: field for key, _label, field in _COLUMNS[view]}


def _parse_sort(raw, view):
    """
    Valid sort keys of the view, at most four (unknown keys dropped).

    ---

    Claves de orden válidas de la vista, como mucho cuatro; las de otra
    vista se descartan (al cambiar de vista no queda un orden roto).
    """
    fields = _sort_fields(view)
    keys, seen = [], set()
    for token in (raw or "").split(","):
        token = token.strip()
        key = token.lstrip("-")
        if key in fields and key not in seen:
            keys.append((key, token.startswith("-")))
            seen.add(key)
    return keys[:_MAX_SORT_KEYS]


def _sort_controls(raw, view):
    """
    Header links, arrows and priorities (same rules as Fichajes).

    ---

    Enlaces, flechas y prioridad de cada cabecera (mismas reglas que
    Fichajes y Centros de gasto).
    """
    sort_keys = _parse_sort(raw, view)
    active = [key for key, _desc in sort_keys]
    columns = []
    for key, label, _field in _COLUMNS[view]:
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
    Supplies of the filters (dates, statuses, asked, search), unsorted.

    ---

    Suministros de los filtros (fechas, estados, si se pregunta al
    chófer, búsqueda), sin
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
    # S137: se pregunta si el chófer y el vehículo lo tienen marcado.
    asked = Q(vehicle__ask_driver=True, user__ask_driver=True)
    ask_values = _ask_values(request)
    if ask_values == [True]:
        supplies = supplies.filter(asked)
    elif ask_values == [False]:
        supplies = supplies.exclude(asked)
    elif not ask_values:
        supplies = supplies.none()
    family = _family(request)
    if family:
        supplies = supplies.filter(vehicle__machine__family=family)
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
        "ask_driver": vehicle.ask_driver and bool(user and user.ask_driver),
        "meter_broken": vehicle.meter_broken,
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


def _person_label(person):
    """
    "Surnames, Name" of a worker file, or "".

    ---

    "Apellidos, Nombre" de la ficha de trabajador, o "".
    """
    if person is None:
        return ""
    surnames = " ".join(
        part for part in (person.first_surname, person.second_surname)
        if part)
    return ", ".join(part for part in (surnames, person.given_name) if part)


def _vehicle_label(vehicle):
    return vehicle.plate or vehicle.name or "GasoGes %s" % vehicle.gasoges_id


def _grouped(supplies, field, other, order):
    """
    Supplies grouped by `field` with their totals, sorted.

    ---

    Suministros agrupados por `field` (vehículo o repostador) con sus
    totales en el periodo: número, litros, último, dudosos y cuántos
    del otro lado (repostadores distintos de un vehículo, o vehículos
    distintos de un repostador).
    """
    return supplies.order_by().values(field).annotate(
        n_supplies=Count("id"),
        total_litres=Sum("litres"),
        last_at=Max("supplied_at"),
        n_anomalies=Count(
            "id", filter=Q(status=GasoGesSupply.STATUS_ANOMALY)),
        n_others=Count(other, distinct=True),
    ).order_by(*order)


def _all_time_totals(queryset, other):
    """
    The supply totals of `_grouped`, over all history, as annotations.

    ---

    Los mismos totales que `_grouped`, de todo el histórico, como
    anotaciones sobre vehículos o repostadores ("Todos los activos").
    """
    return queryset.annotate(
        n_supplies=Count("supplies", distinct=True),
        total_litres=Sum("supplies__litres"),
        last_at=Max("supplies__supplied_at"),
        n_anomalies=Count("supplies", distinct=True, filter=Q(
            supplies__status=GasoGesSupply.STATUS_ANOMALY)),
        n_others=Count("supplies__%s" % other, distinct=True),
    )


def _own_order(order, prefix):
    """
    Sort fields of a grouped view, for the vehicle or user queryset.

    ---

    Campos de orden de la vista agrupada pasados al queryset de
    vehículos o repostadores ("vehicle__plate" -> "plate").
    """
    return [("-" if field.startswith("-") else "")
            + field.lstrip("-").replace(prefix, "", 1) for field in order]


def _vehicle_groups(request, order, wanted=None):
    """
    Groups of the Vehicles view (from the supplies or all the active).

    ---

    Grupos de la vista Vehículos: los vehículos que repostaron en el
    filtro o, con "Todos los activos", todos los de centros de gasto
    activos, hayan repostado o no (S137). `wanted`: solo esos vehículos.
    """
    if not _all_active(request, VIEW_VEHICLES):
        supplies = _filtered_supplies(request)
        if wanted is not None:
            supplies = supplies.filter(vehicle_id__in=wanted)
        return list(_grouped(supplies, "vehicle", "user", order))
    vehicles = GasoGesVehicle.objects.filter(machine__is_active=True)
    family = _family(request)
    if family:
        vehicles = vehicles.filter(machine__family=family)
    ask_values = _ask_values(request)
    if len(ask_values) == 1:
        vehicles = vehicles.filter(ask_driver=ask_values[0])
    elif not ask_values:
        vehicles = vehicles.none()
    search = _param(request, "search").strip()
    if search:
        vehicles = vehicles.filter(
            Q(machine__code__icontains=search)
            | Q(plate__icontains=search) | Q(name__icontains=search))
    if wanted is not None:
        vehicles = vehicles.filter(pk__in=wanted)
    groups = _all_time_totals(vehicles, "user").values(
        "id", "n_supplies", "total_litres", "last_at", "n_anomalies",
        "n_others").order_by(*_own_order(order, "vehicle__"), "id")
    return [dict(group, vehicle=group.pop("id")) for group in groups]


def _user_groups(request, order, wanted=None):
    """
    Groups of the Refuellers view (from the supplies or all of them).

    ---

    Grupos de la vista Repostadores: los que repostaron en el filtro o,
    con "Todos los activos", todos los usuarios de GasoGes, hayan
    repostado o no (S137). Con familia, los que han repostado alguna
    vez un vehículo de esa familia. `wanted`: solo esos (0 = los
    repostajes sin usuario).
    """
    if not _all_active(request, VIEW_USERS):
        supplies = _filtered_supplies(request)
        if wanted is not None:
            chosen = Q(user_id__in=wanted)
            if 0 in wanted:
                chosen |= Q(user__isnull=True)
            supplies = supplies.filter(chosen)
        return list(_grouped(supplies, "user", "vehicle", order))
    users = GasoGesUser.objects.all()
    family = _family(request)
    if family:
        users = users.filter(pk__in=GasoGesSupply.objects.filter(
            vehicle__machine__family=family).values("user_id"))
    ask_values = _ask_values(request)
    if len(ask_values) == 1:
        users = users.filter(ask_driver=ask_values[0])
    elif not ask_values:
        users = users.none()
    search = _param(request, "search").strip()
    if search:
        users = users.filter(name__icontains=search)
    if wanted is not None:
        users = users.filter(pk__in=wanted)
    groups = _all_time_totals(users, "vehicle").values(
        "id", "n_supplies", "total_litres", "last_at", "n_anomalies",
        "n_others").order_by(*_own_order(order, "user__"), "id")
    return [dict(group, user=group.pop("id")) for group in groups]


def _totals(group):
    return {
        "count": group["n_supplies"],
        "litres": group["total_litres"],
        "last": (timezone.localtime(group["last_at"])
                 if group["last_at"] else None),
        "anomalies": group["n_anomalies"],
        "others": group["n_others"],
    }


def _vehicle_rows(groups):
    """
    One row per GasoGes vehicle (dumb template).

    ---

    Una fila por vehículo de GasoGes, lista para la plantilla.
    """
    vehicles = GasoGesVehicle.objects.select_related("machine").in_bulk(
        [group["vehicle"] for group in groups])
    rows = []
    for group in groups:
        vehicle = vehicles.get(group["vehicle"])
        if vehicle is None:
            continue
        label = _vehicle_label(vehicle)
        rows.append({
            "pk": vehicle.pk,
            "machine": vehicle.machine,
            "vehicle_label": label,
            "vehicle_name": vehicle.name,
            "last_km": vehicle.last_km,
            "unit": vehicle.get_unit_display(),
            "unit_known": vehicle.unit != GasoGesVehicle.UNIT_UNKNOWN,
            "unit_source": _UNIT_SOURCE_LABELS.get(vehicle.unit_source, ""),
            "ask_driver": vehicle.ask_driver,
            "meter_broken": vehicle.meter_broken,
            "meter_broken_since": (
                timezone.localtime(vehicle.meter_broken_since)
                if vehicle.meter_broken_since else None),
            "search": (vehicle.machine.code if vehicle.machine
                       else vehicle.plate or vehicle.name),
            "label": ("%s %s" % (vehicle.machine.code, label)
                      if vehicle.machine else label),
            **_totals(group),
        })
    return rows


def _user_rows(groups):
    """
    One row per GasoGes user (who refuels); unknown users together.

    ---

    Una fila por usuario de GasoGes (quien reposta). Los repostajes sin
    usuario conocido van juntos en una fila.
    """
    users = GasoGesUser.objects.select_related("person").in_bulk(
        [group["user"] for group in groups if group["user"]])
    rows = []
    for group in groups:
        user = users.get(group["user"]) if group["user"] else None
        name = user.name if user else "Sin usuario en GasoGes"
        rows.append({
            "pk": user.pk if user else 0,
            "name": name,
            "known": user is not None,
            "person": user.person if user else None,
            "person_label": _person_label(user.person) if user else "",
            "ask_driver": user.ask_driver if user else False,
            "search": user.name if user else "",
            "label": name,
            **_totals(group),
        })
    return rows


def _local_range(request):
    """
    Aware [start, end) of the date filter, in local time.

    ---

    Intervalo [inicio, fin) del filtro de fechas en hora local, sin
    `__date` (no depende de las tablas de zona horaria de MySQL).
    """
    date_from, date_to = _date_range(request)
    return (
        timezone.make_aware(
            datetime.datetime.combine(date_from, datetime.time.min)),
        timezone.make_aware(datetime.datetime.combine(
            date_to + datetime.timedelta(days=1), datetime.time.min)),
    )


def _filtered_questions(request):
    """
    WhatsApp questions sent in the date range, with the search.

    ---

    Preguntas de WhatsApp enviadas en las fechas del filtro, con la
    búsqueda (centro de gasto, matrícula, vehículo o chófer).
    """
    start, end = _local_range(request)
    questions = RefuelQuestion.objects.select_related(
        "supply", "vehicle", "vehicle__machine", "person",
    ).filter(sent_at__gte=start, sent_at__lt=end)
    family = _family(request)
    if family:
        questions = questions.filter(vehicle__machine__family=family)
    search = _param(request, "search").strip()
    if search:
        questions = questions.filter(
            Q(vehicle__machine__code__icontains=search)
            | Q(vehicle__plate__icontains=search)
            | Q(vehicle__name__icontains=search)
            | Q(person__given_name__icontains=search)
            | Q(person__first_surname__icontains=search)
            | Q(person__second_surname__icontains=search))
    return questions


def _question_stats(questions):
    """
    Summary of the questions: sent, drivers and how many in each state.

    ---

    Resumen de las preguntas del filtro: enviadas, a cuántos chóferes y
    cuántas en cada estado (en el orden de STATUS_CHOICES, solo las que
    tienen alguna), con el porcentaje sobre las enviadas.
    """
    total = questions.count()
    by_status = dict(questions.values_list("status").annotate(
        n=Count("id")).order_by())
    answered = total - by_status.get(RefuelQuestion.STATUS_SENT, 0) - (
        by_status.get(RefuelQuestion.STATUS_EXPIRED, 0))
    return {
        "total": total,
        "drivers": questions.values("person_id").distinct().count(),
        "answered": answered,
        "answered_pct": round(answered * 100 / total) if total else 0,
        "states": [
            {"label": label, "count": by_status[code],
             "badge": _QUESTION_BADGES.get(code, "light"),
             "pct": round(by_status[code] * 100 / total)}
            for code, label in RefuelQuestion.STATUS_CHOICES
            if by_status.get(code)],
    }


def _question_row(question):
    """
    One question ready for the template (dumb template).

    ---

    Una pregunta lista para la plantilla: todo calculado aquí.
    """
    from fleet.refuel_questions import question_reason

    vehicle = question.vehicle
    sent = timezone.localtime(question.sent_at)
    # Las preguntas de antes de S137 no guardaban el motivo: se calcula
    # ahora y se avisa de que no iba en el mensaje.
    reason, reason_sent = question.reason, True
    if not reason and question.kind == RefuelQuestion.KIND_VALUE:
        reason, reason_sent = question_reason(question.supply), False
    return {
        "pk": question.pk,
        "sent": sent,
        "driver": _person_label(question.person),
        "person": question.person,
        "machine": vehicle.machine,
        "vehicle_label": _vehicle_label(vehicle),
        "kind": question.get_kind_display(),
        "value": question.supply.meter_value,
        "unit": vehicle.get_unit_display(),
        "reason": reason,
        "reason_sent": reason_sent,
        "status": question.get_status_display(),
        "status_badge": _QUESTION_BADGES.get(question.status, "light"),
        "answer": question.answer,
        "answered": (timezone.localtime(question.answered_at)
                     if question.answered_at else None),
        "search": vehicle.machine.code if vehicle.machine else (
            vehicle.plate or ""),
        "label": "%s %s %s" % (
            sent.strftime("%d/%m %H:%M"),
            vehicle.machine.code if vehicle.machine else (
                vehicle.plate or vehicle.gasoges_id),
            _person_label(question.person)),
    }


def _list_context(request):
    """
    Context of the table of the current view: filtered, sorted, capped.

    ---

    Contexto de la tabla de la vista actual: filtrada y ordenada, hasta
    1.000 filas (con aviso si hay más).
    """
    view = _view(request)
    supplies = _filtered_supplies(request)
    wanted = None
    if request.GET.get("only_selected") == "1":
        wanted = [int(pk) for pk in request.GET.get(
            "selected_ids", "").split(",") if pk.isdigit()]
    fields = _sort_fields(view)
    sort_keys = _parse_sort(_param(request, "sort"), view)
    order = [("-" if desc else "") + fields[key]
             for key, desc in sort_keys] or _DEFAULT_ORDER[view]
    question_stats = None
    if view == VIEW_QUESTIONS:
        questions = _filtered_questions(request)
        question_stats = _question_stats(questions)
        if wanted is not None:
            questions = questions.filter(pk__in=wanted)
        total = questions.count()
        rows = [_question_row(q) for q in questions.order_by(
            *order, "-id")[:_MAX_ROWS]]
    elif view == VIEW_VEHICLES:
        groups = _vehicle_groups(request, order, wanted)
        total = len(groups)
        rows = _vehicle_rows(groups[:_MAX_ROWS])
    elif view == VIEW_USERS:
        groups = _user_groups(request, order, wanted)
        total = len(groups)
        rows = _user_rows(groups[:_MAX_ROWS])
    else:
        if wanted is not None:
            supplies = supplies.filter(pk__in=wanted)
        total = supplies.count()
        rows = [_row(s) for s in supplies.order_by(*order, "-id")[
            :_MAX_ROWS]]
    date_from, date_to = _date_range(request)
    statuses = _statuses(request)
    asks = _ask_values(request)
    return {
        "view": view,
        "family_choices": _family_choices(),
        "filter_family": _family(request),
        "all_active": _param(request, "all_active") == "1",
        "question_stats": question_stats,
        "view_choices": [
            {"code": code, "label": label, "checked": code == view}
            for code, label in VIEW_CHOICES],
        "total_label": _TOTAL_LABELS[view],
        "rows": rows,
        "total": total,
        "capped": total > _MAX_ROWS,
        "max_rows": _MAX_ROWS,
        "filter_search": _param(request, "search"),
        "status_choices": [
            {"code": code, "label": label, "checked": code in statuses}
            for code, label in GasoGesSupply.STATUS_CHOICES],
        "ask_choices": [
            {"code": code, "label": label,
             "checked": (code == "yes") in asks}
            for code, label in ASK_CHOICES],
        "date_from": date_from,
        "date_to": date_to,
        **_sort_controls(_param(request, "sort"), view),
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
        company_user = request.user.company_user
        # Una selección por vista (S137): "selection" (repostajes, la de
        # siempre), "selection_vehicles" y "selection_users".
        saved_selection = {}
        for view, key in _SELECTION_KEYS.items():
            value = get_saved_state_key(company_user, SCREEN_KEY, key, [])
            saved_selection[view] = value if isinstance(value, list) else []
        return render(request, "panel/refuels/_pane.html", {
            **_list_context(request),
            "screen_key": SCREEN_KEY,
            "saved_selection": saved_selection,
            "selection_keys": _SELECTION_KEYS,
            "can_edit": can_edit_service(company_user),
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


def _selected_vehicle_ids(request):
    """
    Vehicle pks of the marked rows: the vehicles themselves in the
    Vehicles view, or the vehicles of the marked supplies.

    ---

    Vehículos de las filas marcadas: en la vista Vehículos, los propios
    vehículos; en Repostajes, los de los repostajes marcados.
    """
    wanted = [int(pk) for pk in request.POST.get(
        "selected_ids", "").split(",") if pk.isdigit()]
    if request.POST.get("view") == VIEW_VEHICLES:
        return set(wanted)
    return set(GasoGesSupply.objects.filter(
        pk__in=wanted).values_list("vehicle_id", flat=True))


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
        vehicle_ids = _selected_vehicle_ids(request)
        vehicles = GasoGesVehicle.objects.filter(
            pk__in=vehicle_ids, machine__isnull=False)
        # S137: los marcados rehacen su serie entera con la unidad, aunque
        # ya la tuvieran; antes solo se miraban los pendientes y los
        # repostajes ya dudosos con la unidad vieja seguían dudosos
        # (asistencia: de horas a km). Así basta con el botón.
        switched = list(vehicles.select_related("machine"))
        changed = vehicles.update(
            unit=unit, unit_source=GasoGesVehicle.UNIT_SOURCE_MANUAL)
        if not changed:
            return JsonResponse({
                "ok": False,
                "error": "Ninguno de los marcados tiene centro de gasto.",
            }, status=400)
        for vehicle in switched:
            vehicle.unit = unit
            redo_vehicle(vehicle, lambda _line: None)
        counters = build_readings(lambda _line: None)
        return JsonResponse({
            "ok": True,
            "message": "%d vehículo(s) en %s. Series rehechas: %d "
                       "lecturas y %d dudosas." % (
                           changed,
                           "kilómetros" if unit == GasoGesVehicle.UNIT_KM
                           else "horas",
                           counters["lecturas"], counters["dudosos"]),
        })


class RefuelsVehicleAskView(CompanyUserRequiredMixin, View):
    """
    POST: whether WhatsApp questions are sent, per driver or vehicle.

    ---

    POST: si se pregunta o no por WhatsApp. S137 (Miguel Ángel: la marca
    va donde está la vista): en Repostadores, a los chóferes marcados;
    en Repostajes y en Vehículos, a los vehículos (centros de gasto)
    marcados o de los repostajes marcados. Se pregunta si el chófer y el
    vehículo lo tienen marcado. Sus lecturas siguen entrando igual.
    """

    def post(self, request):
        if not can_edit_service(request.user.company_user):
            return JsonResponse(
                {"ok": False, "error": "No tienes permiso para esto."},
                status=403)
        ask = request.POST.get("ask") == "1"
        view = request.POST.get("view")
        wanted = [int(pk) for pk in request.POST.get(
            "selected_ids", "").split(",") if pk.isdigit()]
        if view == VIEW_USERS:
            changed = GasoGesUser.objects.filter(
                pk__in=wanted).update(ask_driver=ask)
            what = "chófer(es)"
        else:
            changed = GasoGesVehicle.objects.filter(
                pk__in=_selected_vehicle_ids(request)).update(
                ask_driver=ask)
            what = "vehículo(s)"
        if not changed:
            return JsonResponse(
                {"ok": False,
                 "error": "Marca antes algún repostaje, chófer o "
                          "vehículo."},
                status=400)
        return JsonResponse({
            "ok": True,
            "message": "%d %s: %s." % (
                changed, what, "se le preguntará" if ask
                else "no se le preguntará"),
        })


def _excel_response(book, prefix, request):
    """
    The workbook as an .xlsx download named with the date range.

    ---

    El libro como descarga .xlsx, con las fechas del filtro en el nombre.
    """
    buffer = io.BytesIO()
    book.save(buffer)
    date_from, date_to = _date_range(request)
    response = HttpResponse(
        buffer.getvalue(),
        content_type=("application/vnd.openxmlformats-officedocument."
                      "spreadsheetml.sheet"))
    response["Content-Disposition"] = (
        'attachment; filename="%s_%s_%s.xlsx"' % (
            prefix, date_from.strftime("%Y%m%d"),
            date_to.strftime("%Y%m%d")))
    return response


def _write_sheet(book, title, headers, lines, date_cols=()):
    """
    One sheet: bold frozen header, column widths, date formats.

    ---

    Una hoja: cabecera en negrita fija, anchos de columna y formato de
    fecha en las columnas indicadas.
    """
    from openpyxl.styles import Font
    from openpyxl.utils import get_column_letter

    sheet = book.active
    sheet.title = title
    sheet.append([header for header, _width in headers])
    for line in lines:
        sheet.append(line)
    for cell in sheet[1]:
        cell.font = Font(bold=True)
    sheet.freeze_panes = "A2"
    for index, (_header, width) in enumerate(headers, start=1):
        sheet.column_dimensions[get_column_letter(index)].width = width
    for letter, number_format in date_cols:
        for cell in sheet[letter][1:]:
            cell.number_format = number_format


def _float(value):
    return float(value) if value is not None else None


class RefuelsVehicleMeterView(CompanyUserRequiredMixin, View):
    """
    POST: mark the meter of the marked vehicles broken or repaired.

    ---

    POST: marca el contador de los vehículos marcados (o de los de los
    repostajes marcados) como averiado o reparado (S137). Averiado: no
    se pregunta al chófer y sus repostajes desde ahora no dan lectura.
    Reparado: sus repostajes vuelven a contar desde que se averió.
    """

    def post(self, request):
        if not can_edit_service(request.user.company_user):
            return JsonResponse(
                {"ok": False, "error": "No tienes permiso para esto."},
                status=403)
        broken = request.POST.get("broken") == "1"
        vehicles = list(GasoGesVehicle.objects.filter(
            pk__in=_selected_vehicle_ids(request)))
        if not vehicles:
            return JsonResponse(
                {"ok": False,
                 "error": "Marca antes algún repostaje o vehículo."},
                status=400)
        for vehicle in vehicles:
            vehicle.meter_broken = broken
            vehicle.meter_broken_since = timezone.now() if broken else None
            vehicle.save(update_fields=[
                "meter_broken", "meter_broken_since", "updated_at"])
            build_readings(lambda _line: None, vehicle=vehicle)
        return JsonResponse({
            "ok": True,
            "message": "%d vehículo(s): contador %s." % (
                len(vehicles), "averiado" if broken else "reparado"),
        })


class RefuelsExportView(CompanyUserRequiredMixin, View):
    """
    GET: Excel of the current view, marked rows or all the filtered.

    ---

    GET: Excel de la vista actual (repostajes, vehículos o
    repostadores): de las filas marcadas o, si no hay ninguna, de todas
    las del filtro (sin el tope de 1.000 de la pantalla).
    """

    def get(self, request):
        from openpyxl import Workbook

        view = _view(request)
        wanted = [int(pk) for pk in request.GET.get(
            "selected_ids", "").split(",") if pk.isdigit()]
        book = Workbook()
        if view == VIEW_VEHICLES:
            return self._vehicles(request, book, wanted)
        if view == VIEW_USERS:
            return self._users(request, book, wanted)
        if view == VIEW_QUESTIONS:
            return self._questions(request, book, wanted)
        supplies = (GasoGesSupply.objects.select_related(
            "vehicle", "vehicle__machine", "user").filter(pk__in=wanted)
            if wanted else _filtered_supplies(request))
        lines = []
        for supply in supplies.order_by("supplied_at", "id"):
            local = timezone.localtime(supply.supplied_at)
            vehicle = supply.vehicle
            lines.append([
                local.date(), local.time().replace(microsecond=0),
                vehicle.machine.code if vehicle.machine else "",
                vehicle.plate, vehicle.name,
                supply.user.name if supply.user else "",
                supply.meter_value, vehicle.get_unit_display(),
                _float(supply.litres), _float(supply.price),
                supply.get_status_display(), supply.status_note,
            ])
        _write_sheet(book, "Repostajes", [
            ("Fecha", 12), ("Hora", 8), ("Centro de gasto", 14),
            ("Matrícula (GasoGes)", 16), ("Nombre (GasoGes)", 28),
            ("Quién repostó", 32), ("KM tecleado", 12), ("Unidad", 11),
            ("Litros", 9), ("Precio", 9), ("Estado", 24), ("Motivo", 48),
        ], lines, (("A", "DD/MM/YYYY"), ("B", "HH:MM")))
        return _excel_response(book, "repostajes", request)

    def _vehicles(self, request, book, wanted):
        rows = _vehicle_rows(_vehicle_groups(
            request, _DEFAULT_ORDER[VIEW_VEHICLES], wanted or None))
        lines = [[
            row["machine"].code if row["machine"] else "",
            row["vehicle_label"], row["vehicle_name"], row["count"],
            _float(row["litres"]),
            row["last"].replace(tzinfo=None) if row["last"] else None,
            row["last_km"], row["unit"], row["anomalies"], row["others"],
            "Sí" if row["ask_driver"] else "No",
            "Sí" if row["meter_broken"] else "No",
        ] for row in rows]
        _write_sheet(book, "Vehículos", [
            ("Centro de gasto", 14), ("Vehículo (GasoGes)", 18),
            ("Nombre (GasoGes)", 28), ("Repostajes", 11), ("Litros", 10),
            ("Último repostaje", 17), ("Últimos KM (GasoGes)", 18),
            ("Unidad", 11), ("Dudosos", 9), ("Repostadores", 12),
            ("Se pregunta al chófer", 18), ("Contador averiado", 16),
        ], lines, (("F", "DD/MM/YYYY HH:MM"),))
        return _excel_response(book, "repostajes_vehiculos", request)

    def _users(self, request, book, wanted):
        rows = _user_rows(_user_groups(
            request, _DEFAULT_ORDER[VIEW_USERS], wanted or None))
        lines = [[
            row["name"], row["person_label"], row["count"],
            _float(row["litres"]),
            row["last"].replace(tzinfo=None) if row["last"] else None,
            row["anomalies"], row["others"],
            "Sí" if row["ask_driver"] else "No",
        ] for row in rows]
        _write_sheet(book, "Repostadores", [
            ("Repostador (GasoGes)", 32), ("Ficha de trabajador", 36),
            ("Repostajes", 11), ("Litros", 10), ("Último repostaje", 17),
            ("Dudosos", 9), ("Vehículos", 10), ("Se le pregunta", 14),
        ], lines, (("E", "DD/MM/YYYY HH:MM"),))
        return _excel_response(book, "repostajes_repostadores", request)

    def _questions(self, request, book, wanted):
        questions = _filtered_questions(request)
        if wanted:
            questions = questions.filter(pk__in=wanted)
        lines = []
        for question in questions.order_by("sent_at", "id"):
            row = _question_row(question)
            lines.append([
                row["sent"].replace(tzinfo=None), row["driver"],
                row["machine"].code if row["machine"] else "",
                row["vehicle_label"], row["kind"], row["value"],
                row["unit"], row["reason"], row["status"], row["answer"],
                row["answered"].replace(tzinfo=None) if row["answered"]
                else None,
            ])
        _write_sheet(book, "Preguntas", [
            ("Enviada", 17), ("Chófer", 34), ("Centro de gasto", 14),
            ("Vehículo (GasoGes)", 18), ("Pregunta", 22),
            ("Dato tecleado", 13), ("Unidad", 11),
            ("Por qué se pregunta", 60), ("En qué quedó", 30),
            ("Respuesta", 20), ("Respondida", 17),
        ], lines, (("A", "DD/MM/YYYY HH:MM"), ("K", "DD/MM/YYYY HH:MM")))
        return _excel_response(book, "repostajes_preguntas", request)
