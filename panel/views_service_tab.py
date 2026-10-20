# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/views_service_tab.py
"""
H30 (S131). "Revisiones" tab of the Documentation hub: one row per cost
centre to bring hours, kilometres, crane hours, service dates and
service intervals up to date by hand, as fast as possible.

---

H30 (S131). Pestaña "Revisiones" del hub de Documentación. Miguel
Ángel: "el objetivo de este CRUD es poder poner al día los kilómetros
y horas de la máquina y si tiene grúa, las horas de la grúa de ese
camión, las fechas, poder poner las fechas de revisión, poder poner si
es cada 800 o cada 1200 horas, poner si es cada 20.000 o 40.000
kilómetros [...] tenemos un problema que es la falta de datos.
Entonces, tenemos que alimentar al sistema de forma manual. Hay que
facilitar al máximo esa tarea."

Mismos filtros y orden que la pestaña Centros de gasto
(`fleet.views._build_queryset`), directriz 4.24 (pantalla fija, solo
la lista con scroll, casillas y acciones masivas) y navegación
persistida por usuario (4.15). Cada fila se edita en la propia tabla y
se guarda sola: plan de revisiones, una lectura nueva y la última
revisión. Todo se decide aquí; las plantillas solo pintan.
"""
import json
from datetime import date

from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.template.loader import render_to_string
from django.views import View

from fleet import service_plan_service as plan
from fleet.models import (
    MachineAsset, MachineMeterReading, MachineServiceRecord,
)
from fleet.views import (
    _build_queryset, _build_sort_controls, _get_families,
)
from panel.mixins import CompanyUserRequiredMixin
from panel.navigation_persistence import (
    apply_list_navigation, get_saved_state_key,
)
from panel.views_machine_service import can_edit_service

SCREEN_KEY = "service_tab"
# S131: sin filtro de requisito (Miguel Ángel: "en esa vista no es
# necesario").
FILTER_KEYS = ("search", "family", "is_active", "sort")
KM_INTERVAL_SUGGESTIONS = (20000, 30000, 40000)
STATE_CLASS = {
    plan.STATE_OVERDUE: "text-danger fw-bold",
    plan.STATE_UPCOMING: "text-warning-emphasis fw-bold",
}


class RowError(Exception):
    """
    Invalid value in a row (message ready to show).

    ---

    Valor no válido en una fila (mensaje listo para mostrar).
    """


def _latest(rows, field_name, date_field):
    """
    Latest row with `field_name` set, or None.

    ---

    La fila más reciente con ese valor informado, o None.
    """
    candidates = [row for row in rows if getattr(row, field_name) is not None]
    if not candidates:
        return None
    return max(
        candidates, key=lambda row: (getattr(row, date_field), row.pk),
    )


def _fmt(value):
    """
    Thousands-separated integer or "".

    ---

    Entero con punto de miles, o "".
    """
    return plan.format_number(value) if value is not None else ""


def _annotate_rows(machines):
    """
    Attach to each machine everything its row shows.

    ---

    Añade a cada máquina lo que pinta su fila: última lectura de cada
    contador (km, horas, horas de grúa) con su fecha, última revisión
    (la más reciente por fecha) y estado de cada revisión del plan.
    Dos consultas para toda la lista, nunca una por fila.
    """
    ids = [machine.pk for machine in machines]
    records_of, readings_of = {}, {}
    for record in MachineServiceRecord.objects.filter(machine_id__in=ids):
        records_of.setdefault(record.machine_id, []).append(record)
    for reading in MachineMeterReading.objects.filter(machine_id__in=ids):
        readings_of.setdefault(reading.machine_id, []).append(reading)
    advances = plan.advance_by_company()
    for machine in machines:
        records = records_of.get(machine.pk, [])
        readings = readings_of.get(machine.pk, [])
        last = {
            name: _latest(readings, name, "reading_date")
            for name in ("km", "hours", "crane_hours")
        }
        machine.last_km = last["km"]
        machine.last_hours = last["hours"]
        machine.last_crane_hours = last["crane_hours"]
        machine.last_km_text = _fmt(last["km"].km) if last["km"] else ""
        machine.last_hours_text = (
            _fmt(last["hours"].hours) if last["hours"] else ""
        )
        machine.last_crane_hours_text = (
            _fmt(last["crane_hours"].crane_hours)
            if last["crane_hours"] else ""
        )
        machine.last_record = max(
            records, key=lambda row: (row.service_date, row.pk),
        ) if records else None
        statuses = plan.schedule_statuses(
            machine, records, readings, advances.get(machine.company_id),
        )
        for status in statuses:
            status.css_class = STATE_CLASS.get(status.state, "text-muted")
        machine.service_statuses = statuses
    return machines


def _row_context(machine, company_user):
    """
    Context of one row (shared by the list and by the row save).

    ---

    Contexto de una fila (lo usan la lista y el guardado de fila).
    """
    return {
        "machine": machine,
        "can_edit": can_edit_service(company_user),
        "hours_choices": MachineAsset.SERVICE_HOURS_CHOICES,
        "today": date.today().isoformat(),
    }


def _list_context(request):
    """
    Filtered, sorted and annotated rows plus filter state.

    ---

    Filas filtradas, ordenadas y anotadas, y el estado de los filtros.
    """
    company_user = request.user.company_user
    company = company_user.company
    machines = _annotate_rows(list(_build_queryset(company, request)))

    def _p(key):
        return request.GET.get(key, "")

    return {
        "machines": machines,
        "families": _get_families(company),
        "filter_family": _p("family"),
        "filter_is_active": _p("is_active"),
        "filter_search": _p("search"),
        "can_edit": can_edit_service(company_user),
        "hours_choices": MachineAsset.SERVICE_HOURS_CHOICES,
        "km_suggestions": KM_INTERVAL_SUGGESTIONS,
        "today": date.today().isoformat(),
        **_build_sort_controls(_p("sort")),
    }


class ServiceTabPaneView(CompanyUserRequiredMixin, View):
    """
    GET: "Revisiones" tab (pane, or only the table with ?fragment=1).

    ---

    GET: pestaña "Revisiones" (panel completo, o solo la tabla con
    ?fragment=1 al cambiar filtros u orden). Guarda y recupera la
    navegación del usuario (filtros, orden y selección).
    """

    def get(self, request):
        apply_list_navigation(request, SCREEN_KEY, FILTER_KEYS)
        context = _list_context(request)
        if request.GET.get("fragment") == "1":
            return render(
                request, "panel/service_tab/_table.html", context,
            )
        selection = get_saved_state_key(
            request.user.company_user, SCREEN_KEY, "selection", [],
        )
        context.update({
            "saved_selection": (
                selection if isinstance(selection, list) else []
            ),
            "screen_key": SCREEN_KEY,
        })
        return render(request, "panel/service_tab/pane.html", context)


def _count(raw, label):
    """
    Non-negative integer from a form value ("" -> None).

    ---

    Entero no negativo ("" -> None); admite punto de miles.
    """
    raw = (raw or "").strip().replace(".", "").replace(" ", "")
    if not raw:
        return None
    if not raw.isdigit():
        raise RowError("%s debe ser un número entero." % label)
    return int(raw)


def _day(raw, label, required=False):
    """
    ISO date ("" -> None unless required); never in the future.

    ---

    Fecha AAAA-MM-DD ("" -> None salvo obligatoria), nunca futura.
    """
    raw = (raw or "").strip()
    if not raw:
        if required:
            raise RowError("Indica la %s." % label)
        return None
    try:
        value = date.fromisoformat(raw)
    except ValueError:
        raise RowError("La %s no es válida." % label)
    if value > date.today():
        raise RowError("La %s no puede ser futura." % label)
    return value


def _hours_interval(raw):
    """
    Hours interval from the select ("" -> None).

    ---

    Intervalo de horas del desplegable ("" -> None, 800 o 1200).
    """
    raw = (raw or "").strip()
    if not raw:
        return None
    valid = {value for value, _label in MachineAsset.SERVICE_HOURS_CHOICES}
    if not raw.isdigit() or int(raw) not in valid:
        raise RowError("La revisión por horas es cada 800 o cada 1200.")
    return int(raw)


def _save_row(machine, data, company_user):
    """
    Apply one row: plan, new reading and latest service.

    ---

    Aplica una fila, todo o nada:
    - Plan: revisión por horas (800/1200) y cada N km.
    - Lectura: si trae km, horas o horas de grúa, se anota con su fecha
      (hoy por defecto). Si ya hay una lectura de ese mismo día, se
      completa esa en vez de duplicarla.
    - Revisión: si trae fecha, y es la de la última revisión, se
      corrigen sus valores; si es otra fecha, se anota una revisión
      nueva. Horas y km son opcionales (solo con fecha no avisa).
    """
    hours_interval = _hours_interval(data.get("hours_interval"))
    km_interval = _count(data.get("km_interval"), "La revisión por km")
    reading = {
        "km": _count(data.get("reading_km"), "Los km de la lectura"),
        "hours": _count(data.get("reading_hours"), "Las horas"),
        "crane_hours": _count(
            data.get("reading_crane_hours"), "Las horas de grúa",
        ),
    }
    reading_date = _day(data.get("reading_date"), "fecha de la lectura")
    service_date = _day(data.get("service_date"), "fecha de la revisión")
    service = {
        "hours": _count(data.get("service_hours"), "Las horas de la revisión"),
        "crane_hours": _count(
            data.get("service_crane_hours"),
            "Las horas de grúa de la revisión",
        ),
        "km": _count(data.get("service_km"), "Los km de la revisión"),
    }
    if not service_date and any(v is not None for v in service.values()):
        raise RowError("Indica la fecha de la revisión.")

    with transaction.atomic():
        machine.service_hours_interval = hours_interval
        machine.service_every_km = km_interval or None
        machine.save(update_fields=[
            "service_hours_interval", "service_every_km", "updated_at",
        ])
        if any(value is not None for value in reading.values()):
            day = reading_date or date.today()
            existing = MachineMeterReading.objects.filter(
                machine=machine, reading_date=day,
            ).order_by("-id").first()
            if existing is None:
                MachineMeterReading.objects.create(
                    machine=machine, reading_date=day,
                    created_by=company_user, **reading,
                )
            else:
                for name, value in reading.items():
                    if value is not None:
                        setattr(existing, name, value)
                existing.save()
        if service_date:
            latest = MachineServiceRecord.objects.filter(
                machine=machine,
            ).order_by("-service_date", "-id").first()
            if latest is not None and latest.service_date == service_date:
                for name, value in service.items():
                    setattr(latest, name, value)
                latest.save()
            else:
                MachineServiceRecord.objects.create(
                    machine=machine, service_date=service_date,
                    created_by=company_user, **service,
                )


class ServiceRowSaveView(CompanyUserRequiredMixin, View):
    """
    POST: save one row and return it re-rendered.

    ---

    POST: guarda una fila y la devuelve ya pintada con los datos
    nuevos (JSON {ok, html} o {ok: false, error}).
    """

    def post(self, request, pk):
        company_user = request.user.company_user
        if not can_edit_service(company_user):
            return JsonResponse(
                {"ok": False, "error": "No tienes permiso para anotar "
                 "revisiones ni lecturas."},
                status=403,
            )
        machine = get_object_or_404(
            MachineAsset, pk=pk, company=company_user.company,
        )
        try:
            _save_row(machine, request.POST, company_user)
        except RowError as exc:
            return JsonResponse({"ok": False, "error": str(exc)}, status=400)
        machine.refresh_from_db()
        _annotate_rows([machine])
        html = render_to_string(
            "panel/service_tab/_row.html",
            _row_context(machine, company_user), request=request,
        )
        return JsonResponse({"ok": True, "html": html})


class ServiceBulkPlanView(CompanyUserRequiredMixin, View):
    """
    POST: set the service plan of several cost centres at once.

    ---

    POST: aplica a la vez a los centros de gasto marcados la revisión
    por horas, la revisión por km o las dos (solo lo que se pida
    aplicar: `apply_hours`, `apply_km`).
    """

    def post(self, request):
        company_user = request.user.company_user
        if not can_edit_service(company_user):
            return JsonResponse(
                {"ok": False, "error": "No tienes permiso para cambiar "
                 "las revisiones."},
                status=403,
            )
        try:
            ids = [
                int(pk) for pk in json.loads(request.POST.get("ids") or "[]")
            ]
        except (TypeError, ValueError):
            return JsonResponse(
                {"ok": False, "error": "Selección no válida."}, status=400,
            )
        apply_hours = request.POST.get("apply_hours") == "1"
        apply_km = request.POST.get("apply_km") == "1"
        if not ids or not (apply_hours or apply_km):
            return JsonResponse(
                {"ok": False, "error": "Marca centros de gasto y qué "
                 "revisión aplicar."},
                status=400,
            )
        try:
            fields = {}
            if apply_hours:
                fields["service_hours_interval"] = _hours_interval(
                    request.POST.get("hours_interval"),
                )
            if apply_km:
                fields["service_every_km"] = _count(
                    request.POST.get("km_interval"), "La revisión por km",
                ) or None
        except RowError as exc:
            return JsonResponse({"ok": False, "error": str(exc)}, status=400)
        updated = MachineAsset.objects.filter(
            pk__in=ids, company=company_user.company,
        ).update(**fields)
        return JsonResponse({"ok": True, "updated": updated})
