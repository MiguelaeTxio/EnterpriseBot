# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/views_vacation_balance.py
"""
"Vacaciones" tab of the Documentation hub (H24, S129, roadmap point 1
of annex V24 section 7.5): the list of active workers in the format of
directive 4.24, with their days entitled, carried over, taken and
pending; start and end date in the fixed panel to register vacations
for the marked workers; section of each worker, vacation rules per
section, manual adjustments and the starting balance imported from
Carolina's spreadsheet; and, in each worker's breakdown, the absences
that are neither vacation nor leave (S130). The computation lives in
hr_calendar.balance; these views only read the request, call it and
render.

Documentation is the supervisors' tool (Miguel Ángel, S129): nothing
here is scoped to the logged-in worker. Each worker will see their own
vacations in a viewer of their own, outside Documentation. Reading
follows the other hub tabs (any panel user); every action is limited
to the roles that already managed vacation periods
(SupervisorAccessMixin: ADMIN, SUPERVISOR, WORKSHOPBOSS).

---

Pestaña "Vacaciones" del hub de Documentación (H24, S129, punto 1 de
la hoja de ruta 7.5 del anexo V24): el listado de trabajadores activos
con el formato de la directriz 4.24, con los días que corresponden, del
año anterior, consumidos y pendientes; fecha de inicio y de fin en el
panel fijo para dar de alta las vacaciones de los marcados; sección de
cada trabajador, reglas por sección, ajustes manuales y saldo de
partida importado de la hoja de Carolina; y, en el desglose de cada
trabajador, las ausencias que no son vacaciones ni baja (S130). El
cálculo vive en hr_calendar.balance; estas vistas solo leen la
petición, lo llaman y pintan.

Documentación es la herramienta de los supervisores (Miguel Ángel,
S129): nada aquí se acota al trabajador que entra. Cada trabajador verá
sus vacaciones en un visor propio, fuera de Documentación. La lectura
sigue a las demás pestañas del hub (cualquier usuario del panel); toda
acción queda para los roles que ya gestionaban periodos
(SupervisorAccessMixin: ADMIN, SUPERVISOR, WORKSHOPBOSS).
"""
import datetime
import logging
from decimal import Decimal, InvalidOperation
from urllib.parse import quote

from django.http import Http404, HttpResponse
from django.shortcuts import render
from django.views import View

from budgets.models import Base
from document_explorer.models import PersonIdentity
from hr_calendar.balance import (
    NO_SECTION_LABEL,
    BalanceCalculator,
    add_free_days,
    add_manual_adjustment,
    assign_section,
    validate_rule,
)
from hr_calendar.balance_import import build_template, import_template
from hr_calendar.services import absence_categories, create_absence_period
from hr_calendar.models import (
    AbsencePeriod,
    PersonSectionAssignment,
    VacationBalanceAdjustment,
    VacationPeriod,
    VacationRule,
)
from ivr_config.models import CompanyUser, Section
from panel.mixins import CompanyUserRequiredMixin, SupervisorAccessMixin
from panel.navigation_persistence import (
    apply_list_navigation,
    get_saved_state_key,
)

logger = logging.getLogger(__name__)

SCREEN_KEY = "vacation_balance"
# Mismos filtros que la pestaña Personal (Estado y Empresa, aquí como
# listas separadas por comas para poder persistirlas) + sección y año.
FILTER_KEYS = ("search", "active", "company", "section", "year", "sort",
               "group")
MANAGE_ROLES = {
    CompanyUser.ROLE_ADMIN,
    CompanyUser.ROLE_ADMIN_SUPERVISOR,
    CompanyUser.ROLE_SUPERVISOR,
    CompanyUser.ROLE_WORKSHOPBOSS,
}
NO_SECTION = "none"
_MAX_SORT_KEYS = 4

_SORT_VALUES = {
    "person": lambda r: r.sort_name,
    "dni": lambda r: r.person.dni,
    "section": lambda r: r.balance.current_section_name.upper() or None,
    "taken": lambda r: r.balance.taken,
    "pending": lambda r: r.balance.pending,
}
_COLUMNS = (
    ("person", "Apellidos, Nombre"),
    ("dni", "DNI"),
    ("section", "Sección"),
    ("taken", "Consumidos"),
    ("pending", "Pendientes"),
)


# ------------------------------------------------------------------
# Helpers / Utilidades
# ------------------------------------------------------------------
def can_manage(request):
    """
    True for the roles that manage vacations.
    ---
    True para los roles que gestionan vacaciones (mismos que
    SupervisorAccessMixin).
    """
    return request.user.company_user.role in MANAGE_ROLES


def _person_or_404(pk):
    """
    A worker by pk, or 404.
    ---
    Un trabajador por pk, o 404 (también uno ya inactivo, para ver o
    corregir su histórico desde el desglose).
    """
    person = PersonIdentity.objects.select_related(
        "company_user__base",
    ).filter(pk=pk).first()
    if person is None:
        raise Http404
    return person


def _param(request, key, default=""):
    """
    GET value, or the _f_ copy posted by the actions.
    ---
    Valor de GET o, si no está, la copia _f_ que envían las acciones
    (mismo mecanismo que Accesorios de elevación).
    """
    return request.GET.get(key) or request.POST.get("_f_" + key, default)


def _year(raw):
    """
    Year from the request, the current one when missing or invalid.
    ---
    Año de la petición; el actual si falta o no es válido.
    """
    try:
        year = int(raw)
    except (TypeError, ValueError):
        return datetime.date.today().year
    return year if 2000 <= year <= 2100 else datetime.date.today().year


def _parse_date(raw):
    try:
        return datetime.datetime.strptime((raw or "").strip(),
                                          "%Y-%m-%d").date()
    except ValueError:
        return None


def _parse_decimal(raw):
    try:
        return Decimal((raw or "").strip().replace(",", "."))
    except InvalidOperation:
        return None


def _parse_int(raw):
    try:
        return int((raw or "").strip())
    except (TypeError, ValueError):
        return None


def _person_label(person):
    surnames = " ".join(
        p for p in (person.first_surname, person.second_surname) if p
    )
    return "%s, %s" % (surnames, person.given_name)


def _parse_sort(raw):
    """
    "key,-key" -> [(key, descending)], valid unique keys only.
    ---
    "clave,-clave" -> [(clave, descendente)], solo claves válidas y sin
    repetir, como máximo cuatro (formato S116/S117).
    """
    keys, seen = [], set()
    for token in (raw or "").split(","):
        token = token.strip()
        key = token.lstrip("-")
        if key in _SORT_VALUES and key not in seen:
            keys.append((key, token.startswith("-")))
            seen.add(key)
    return keys[:_MAX_SORT_KEYS]


def _sort_controls(raw):
    """
    Next "sort" value, arrow and priority of each column header.
    ---
    Valor de "sort" de cada cabecera, su flecha y su prioridad -- mismas
    reglas que Centros de gasto (S117), resueltas aquí.
    """
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
                (k, d) for k, d in sort_keys if k != key
            ]
        else:
            arrow, priority = "", ""
            new_keys = [(key, False)] + sort_keys
        columns.append({
            "key": key, "label": label, "arrow": arrow,
            "priority": priority,
            "next": ",".join(
                ("-" if d else "") + k for k, d in new_keys[:_MAX_SORT_KEYS]
            ),
        })
    return {
        "sort_columns": columns,
        "sort_active": bool(sort_keys),
        "current_sort": ",".join(
            ("-" if d else "") + k for k, d in sort_keys
        ),
    }


class _Row:
    """
    One line of the balance list.
    ---
    Una línea del listado de saldos.
    """

    def __init__(self, person, balance):
        self.person = person
        self.balance = balance
        self.label = _person_label(person)
        self.sort_name = self.label.upper()


def _sort_rows(rows, sort_keys):
    rows = sorted(rows, key=lambda r: r.sort_name)
    for key, desc in reversed(sort_keys):
        getter = _SORT_VALUES[key]
        present = [r for r in rows if getter(r) is not None]
        missing = [r for r in rows if getter(r) is None]
        rows = sorted(present, key=getter, reverse=desc) + missing
    return rows


def _csv_param(request, key, default):
    """
    Comma-separated list filter; the default only when never sent.
    ---
    Filtro de lista separada por comas. Si nunca se ha enviado (primera
    visita) vale el valor por defecto; si se envía vacío, vacío (como
    en Personal: ninguna casilla marcada = ningún resultado).
    """
    if key in request.GET or ("_f_" + key) in request.POST:
        raw = _param(request, key)
        return [v for v in raw.split(",") if v]
    return list(default)


def _filtered_people(request):
    """
    Workers matching the filters of the Personal tab.
    ---
    Trabajadores que cumplen los filtros de la pestaña Personal
    (Estado y Empresa con la misma lógica, _apply_personal_filters) y
    la búsqueda por palabras de Personal (cada palabra en algún campo).
    Por defecto: activos de todas las empresas.
    """
    from django.db.models import Q
    from django.http import QueryDict

    from panel.views_documentation_h30 import (
        COMPANY_FILTER_CHOICES,
        _apply_personal_filters,
    )

    active = _csv_param(request, "active", ["true"])
    companies = _csv_param(
        request, "company", [slug for slug, _l, _r in COMPANY_FILTER_CHOICES],
    )
    fake = QueryDict(mutable=True)
    fake.setlist("active", active)
    fake.setlist("company", companies)
    # S153 (4.27): el filtro "Grupo", común a todas las pestañas.
    fake["group"] = _param(request, "group")
    proxy = type("FilterRequest", (), {"GET": fake})()
    qs = _apply_personal_filters(
        PersonIdentity.objects.select_related("company_user__base"), proxy,
    )
    search = _param(request, "search").strip()
    for word in search.split():
        qs = qs.filter(
            Q(first_surname__icontains=word)
            | Q(second_surname__icontains=word)
            | Q(given_name__icontains=word) | Q(dni__icontains=word)
            | Q(nickname__icontains=word),
        )
    return list(qs), active, companies, search


def _list_context(request):
    """
    Context of the vacation table: filtered, computed, sorted rows.
    ---
    Contexto de la tabla de vacaciones: filas filtradas, calculadas y
    ordenadas.
    """
    company = request.user.company_user.company
    year = _year(_param(request, "year"))
    section = _param(request, "section")
    if request.GET.get("only_selected") == "1":
        wanted_ids = [
            pk for pk in request.GET.get("selected_ids", "").split(",")
            if pk.isdigit()
        ]
        people = list(PersonIdentity.objects.select_related(
            "company_user__base",
        ).filter(pk__in=wanted_ids))
        _all, active, companies, search = _filtered_people(request)
    else:
        people, active, companies, search = _filtered_people(request)
    calculator = BalanceCalculator(company, people)
    rows = [_Row(p, calculator.balance(p, year)) for p in people]
    if section == NO_SECTION:
        rows = [
            r for r in rows
            if r.balance.current_section_name == NO_SECTION_LABEL
        ]
    elif section.isdigit():
        wanted = Section.objects.filter(
            pk=int(section), company=company,
        ).values_list("name", flat=True).first()
        rows = [r for r in rows if r.balance.current_section_name == wanted]
    rows = _sort_rows(rows, _parse_sort(_param(request, "sort")))
    return {
        "rows": rows,
        "filter_year": year,
        "filter_search": search,
        "filter_active": active,
        "filter_company": companies,
        "filter_section": section,
        "can_manage": can_manage(request),
        "today": datetime.date.today(),
        **_sort_controls(_param(request, "sort")),
    }


def _table_response(request, message="", error=False):
    """
    Table fragment, with an optional message in a header.
    ---
    Fragmento de tabla, con un mensaje opcional en cabecera (lo pinta el
    aviso flotante del panel; ninguna acción en silencio).
    """
    response = render(
        request, "panel/vacation_balance/_table.html",
        _list_context(request),
    )
    if message:
        response["X-Vacation-Message"] = quote(message)
        if error:
            response["X-Vacation-Error"] = "1"
    return response


def _sections(company):
    return Section.objects.filter(company=company).order_by("name")


# ------------------------------------------------------------------
# Saldos
# ------------------------------------------------------------------
class VacationBalanceTabView(CompanyUserRequiredMixin, View):
    """
    GET: "Vacaciones" tab (fixed panel, list, detail column).
    ---
    GET: pestaña "Vacaciones" (panel fijo, lista y columna de detalle),
    formato de la directriz 4.24, filtros/orden/selección persistidos
    por usuario (screen_key "vacation_balance").
    """

    def get(self, request):
        apply_list_navigation(request, SCREEN_KEY, FILTER_KEYS)
        cu = request.user.company_user
        saved_selection = get_saved_state_key(cu, SCREEN_KEY, "selection", [])
        if not isinstance(saved_selection, list):
            saved_selection = []
        from panel.common_filters import person_filter_context
        from panel.person_groups import group_filter_context
        from panel.views_documentation_h30 import COMPANY_FILTER_CHOICES

        today = datetime.date.today()
        context = {
            **_list_context(request),
            "screen_key": SCREEN_KEY,
            "saved_selection": saved_selection,
            "sections": _sections(cu.company),
            "no_section": NO_SECTION,
            "years": range(today.year - 2, today.year + 2),
            "company_filter_choices": COMPANY_FILTER_CHOICES,
            **group_filter_context(request),
            # S153 (4.27): bloque común de filtros de personas.
            **person_filter_context(request),
        }
        return render(request, "panel/vacation_balance/_pane.html", context)


class VacationBalanceResultsView(CompanyUserRequiredMixin, View):
    """
    GET: table only (filters, sort, year).
    ---
    GET: solo la tabla (filtros, orden, año).
    """

    def get(self, request):
        apply_list_navigation(request, SCREEN_KEY, FILTER_KEYS)
        return _table_response(request)


def _detail_context(request, person, year, message="", error=False):
    company = request.user.company_user.company
    calculator = BalanceCalculator(company, [person])
    balance = calculator.balance(person, year)
    assignments = PersonSectionAssignment.objects.filter(
        person=person,
    ).select_related("section", "created_by__user").order_by("-valid_from")
    # S130: ausencias del año (las que tocan algún día de ese año).
    absences = AbsencePeriod.objects.filter(
        person=person,
        date_start__lte=datetime.date(year, 12, 31),
        date_end__gte=datetime.date(year, 1, 1),
    ).select_related("category", "created_by__user").order_by("date_start")
    # S143: horas acumuladas, para dar días libres a cambio.
    bag_label = ""
    if can_manage(request) and person.company_user_id is not None:
        from hr_calendar.clock_extras import overtime_bag, signed_duration

        bag_label = signed_duration(overtime_bag(
            person.company_user.company, person.company_user,
        )["total_seconds"])
    return {
        "person": person,
        "person_label": _person_label(person),
        "year": year,
        "balance": balance,
        "bag_label": bag_label,
        "assignments": assignments,
        "absences": absences,
        "absence_categories": absence_categories(company),
        "can_manage": can_manage(request),
        "message": message,
        "message_is_error": error,
    }


def _detail_response(request, person, year, message="", error=False,
                     refresh_table=False):
    response = render(
        request, "panel/vacation_balance/_detail.html",
        _detail_context(request, person, year, message, error),
    )
    if refresh_table:
        response["HX-Trigger"] = "vacation-balance-refresh"
    return response


class VacationBalanceDetailView(CompanyUserRequiredMixin, View):
    """
    GET: breakdown of one worker's balance for a year.
    ---
    GET: desglose del saldo de un trabajador en un año: tramos con su
    sección y regla, periodos con los días que gastan, ajustes,
    historial de secciones y avisos.
    """

    def get(self, request, pk):
        person = _person_or_404(pk)
        year = _year(request.GET.get("year"))
        return _detail_response(request, person, year)


class VacationSectionAssignView(SupervisorAccessMixin, View):
    """
    POST: assign a section from a date to the selected workers.
    ---
    POST: asigna una sección desde una fecha a los trabajadores
    marcados. Nunca guarda la Section (eso regeneraría su flujo de la
    centralita); solo filas PersonSectionAssignment.
    """

    def post(self, request):
        company = request.user.company_user.company
        section = Section.objects.filter(
            pk=_parse_int(request.POST.get("section_id")), company=company,
        ).first()
        valid_from = _parse_date(request.POST.get("valid_from"))
        ids = [pk for pk in request.POST.getlist("selected") if pk.isdigit()]
        people = list(PersonIdentity.objects.filter(pk__in=ids))
        if section is None or valid_from is None or not people:
            return _table_response(
                request, "Elige la sección, la fecha y al menos un "
                         "trabajador.", error=True,
            )
        created, updated = assign_section(
            people, section, valid_from, request.user.company_user,
        )
        return _table_response(
            request,
            f"Sección «{section.name}» asignada desde "
            f"{valid_from:%d/%m/%Y} a {len(people)} trabajador(es) "
            f"({created} nuevas, {updated} cambiadas).",
        )


class VacationSectionAssignmentDeleteView(SupervisorAccessMixin, View):
    """
    POST: delete one section assignment (wrong entry).
    ---
    POST: borra una asignación de sección (dada por error) y repinta el
    detalle; la tabla se refresca sola.
    """

    def post(self, request, pk):
        row = PersonSectionAssignment.objects.select_related(
            "person", "section",
        ).filter(pk=pk).first()
        if row is None:
            raise Http404
        person, year = row.person, _year(request.POST.get("year"))
        label = f"{row.section.name} desde {row.valid_from:%d/%m/%Y}"
        row.delete()
        return _detail_response(
            request, person, year, f"Asignación borrada: {label}.",
            refresh_table=True,
        )


class VacationAdjustmentCreateView(SupervisorAccessMixin, View):
    """
    POST: manual adjustment (signed days, mandatory reason).
    ---
    POST: ajuste manual (días con signo, motivo obligatorio).
    """

    def post(self, request, pk):
        person = _person_or_404(pk)
        year = _year(request.POST.get("year"))
        days = _parse_decimal(request.POST.get("days"))
        if days is None or days != days.to_integral_value():
            return _detail_response(
                request, person, year,
                "Los días deben ser un número entero (p. ej. 2 o -1).",
                error=True,
            )
        try:
            add_manual_adjustment(
                person, request.user.company_user.company, year, days,
                request.POST.get("reason"), request.user.company_user,
            )
        except ValueError as exc:
            return _detail_response(request, person, year, str(exc),
                                    error=True)
        return _detail_response(
            request, person, year,
            f"Ajuste de {days} día(s) registrado en {year}.",
            refresh_table=True,
        )


class VacationFreeDaysCreateView(SupervisorAccessMixin, View):
    """
    POST: free days for accumulated hours.
    ---
    POST: días libres a cambio de horas acumuladas (S143): suman al
    saldo del año y las horas escritas se restan de la bolsa.
    """

    def post(self, request, pk):
        from panel.views_clock_extras import _parse_minutes

        person = _person_or_404(pk)
        year = _year(request.POST.get("year"))
        days = _parse_decimal(request.POST.get("days"))
        if days is None or days != days.to_integral_value():
            return _detail_response(
                request, person, year,
                "Los días libres deben ser un número entero (p. ej. 2).",
                error=True,
            )
        try:
            add_free_days(
                person, request.user.company_user.company, year, days,
                _parse_minutes(request.POST.get("hours")),
                request.POST.get("reason"), request.user.company_user,
            )
        except ValueError as exc:
            return _detail_response(request, person, year, str(exc),
                                    error=True)
        return _detail_response(
            request, person, year,
            f"{days} día(s) libre(s) por horas acumuladas sumados en "
            f"{year}.",
            refresh_table=True,
        )


class VacationAdjustmentDeleteView(SupervisorAccessMixin, View):
    """
    POST: delete an adjustment (manual or starting balance).
    ---
    POST: borra un ajuste (manual o de saldo de partida).
    """

    def post(self, request, pk):
        row = VacationBalanceAdjustment.objects.select_related(
            "person",
        ).filter(pk=pk, company=request.user.company_user.company).first()
        if row is None:
            raise Http404
        person, year = row.person, row.year
        label = f"{row.get_kind_display()} ({row.days} días)"
        # S143: con los días libres se borran también las horas que se
        # descontaron de la bolsa (en cascada).
        if row.kind == VacationBalanceAdjustment.Kind.OVERTIME:
            label += "; las horas vuelven a la bolsa"
        row.delete()
        return _detail_response(
            request, person, year, f"Ajuste borrado: {label}.",
            refresh_table=True,
        )


# ------------------------------------------------------------------
# Periodos de vacaciones
# ------------------------------------------------------------------
class VacationRowRegisterView(SupervisorAccessMixin, View):
    """
    POST: register a vacation period from a worker's row.
    ---
    POST: da de alta un periodo con la fecha de inicio y la de fin
    escritas en la fila del trabajador y
    devuelve esa misma fila recalculada, con el resultado en la
    cabecera (aviso flotante: ninguna acción en silencio). El alta es
    la de siempre (hr_calendar.services.create_vacation_period, con su
    tarea fantasma si el trabajador tiene cuenta de panel).
    """

    def post(self, request, pk):
        from hr_calendar.services import create_vacation_period

        cu = request.user.company_user
        person = _person_or_404(pk)
        year = _year(request.POST.get("year"))
        date_start = _parse_date(request.POST.get("date_start"))
        date_end = _parse_date(request.POST.get("date_end"))
        message, error = "", False
        if date_start is None or date_end is None:
            message, error = (
                "Indica la fecha de inicio y la de fin.", True,
            )
        else:
            try:
                create_vacation_period(
                    person=person, company=cu.company, created_by=cu,
                    date_start=date_start, date_end=date_end,
                )
                message = (
                    f"Vacaciones de {_person_label(person)} registradas: "
                    f"{date_start:%d/%m/%Y} a {date_end:%d/%m/%Y}."
                )
            except ValueError as exc:
                message, error = str(exc), True
            except Exception as exc:
                logger.error(
                    "# [vacation_balance] Error registrando vacaciones "
                    "de person_pk=%s (%s a %s): %s",
                    person.pk, date_start, date_end, exc, exc_info=True,
                )
                message, error = (
                    "No se han podido registrar: falta configuración de "
                    "la tarea automática (centro de gasto PERSONAL o "
                    "categoría Vacaciones). Avisa al administrador.",
                    True,
                )
        calculator = BalanceCalculator(cu.company, [person])
        response = render(request, "panel/vacation_balance/_row.html", {
            "row": _Row(person, calculator.balance(person, year)),
            "filter_year": year,
            "can_manage": can_manage(request),
            "today": datetime.date.today(),
        })
        response["X-Vacation-Message"] = quote(message)
        if error:
            response["X-Vacation-Error"] = "1"
        return response


def _period_or_404(request, pk):
    period = VacationPeriod.objects.select_related(
        "person", "generated_entry_line__entry__work_order",
    ).filter(pk=pk, company=request.user.company_user.company).first()
    if period is None:
        raise Http404
    return period


class VacationPeriodEditView(SupervisorAccessMixin, View):
    """
    POST: change the dates (and half days) of a period.
    ---
    POST: cambia las fechas de un periodo desde el
    desglose del trabajador (hr_calendar.services
    .update_vacation_period, que rehace la tarea fantasma si cambia el
    inicio).
    """

    def post(self, request, pk):
        from hr_calendar.services import update_vacation_period

        period = _period_or_404(request, pk)
        year = _year(request.POST.get("year"))
        date_start = _parse_date(request.POST.get("date_start"))
        date_end = _parse_date(request.POST.get("date_end"))
        if date_start is None or date_end is None:
            return _detail_response(
                request, period.person, year,
                "Indica la fecha de inicio y la de fin.", error=True,
            )
        try:
            update_vacation_period(period, date_start, date_end)
        except ValueError as exc:
            return _detail_response(request, period.person, year, str(exc),
                                    error=True)
        return _detail_response(
            request, period.person, year,
            f"Periodo guardado: {date_start:%d/%m/%Y} a "
            f"{date_end:%d/%m/%Y}.", refresh_table=True,
        )


class VacationPeriodRemoveView(SupervisorAccessMixin, View):
    """
    POST: delete a period (and its ghost task).
    ---
    POST: borra un periodo y su tarea fantasma
    (hr_calendar.services.delete_vacation_period).
    """

    def post(self, request, pk):
        from hr_calendar.services import delete_vacation_period

        period = _period_or_404(request, pk)
        person, year = period.person, _year(request.POST.get("year"))
        label = (
            f"{period.date_start:%d/%m/%Y} a {period.date_end:%d/%m/%Y}"
        )
        delete_vacation_period(period)
        return _detail_response(
            request, person, year, f"Periodo borrado: {label}.",
            refresh_table=True,
        )


# ------------------------------------------------------------------
# Ausencias (S130, punto 4 de la hoja de ruta 7.5)
# ------------------------------------------------------------------
def _parse_time(raw):
    """
    "HH:MM" to a time, or None.
    ---
    "HH:MM" a hora, o None si viene vacío o mal.
    """
    try:
        return datetime.time.fromisoformat((raw or "").strip()[:5])
    except ValueError:
        return None


class AbsencePeriodCreateView(SupervisorAccessMixin, View):
    """
    POST: register an absence for a worker from their breakdown.
    ---
    POST: registra una ausencia (tipo, del, al y nota) desde el desglose
    del trabajador (hr_calendar.services.create_absence_period) y repinta
    el desglose con el resultado.
    """

    def post(self, request, pk):
        person = _person_or_404(pk)
        year = _year(request.POST.get("year"))
        date_start = _parse_date(request.POST.get("date_start"))
        date_end = _parse_date(request.POST.get("date_end"))
        if date_start is None or date_end is None:
            return _detail_response(
                request, person, year,
                "Indica la fecha de inicio y la de fin.", error=True,
            )
        cu = request.user.company_user
        try:
            period = create_absence_period(
                person, cu.company, cu,
                _parse_int(request.POST.get("category_id")),
                date_start, date_end, request.POST.get("note"),
                _parse_time(request.POST.get("time_from")),
                _parse_time(request.POST.get("time_to")),
            )
        except ValueError as exc:
            return _detail_response(request, person, year, str(exc),
                                    error=True)
        logger.info(
            "# [ausencias] %s registra %s de person_pk=%s: %s a %s",
            cu, period.category.code, person.pk, date_start, date_end,
        )
        return _detail_response(
            request, person, year,
            f"Ausencia registrada: {period.category.label}, "
            f"{date_start:%d/%m/%Y} a {date_end:%d/%m/%Y}.",
        )


class AbsencePeriodRemoveView(SupervisorAccessMixin, View):
    """
    POST: delete an absence registered by mistake.
    ---
    POST: borra una ausencia dada por error y repinta el desglose.
    """

    def post(self, request, pk):
        period = AbsencePeriod.objects.select_related(
            "person", "category",
        ).filter(pk=pk, company=request.user.company_user.company).first()
        if period is None:
            raise Http404
        person, year = period.person, _year(request.POST.get("year"))
        label = (
            f"{period.category.label}, {period.date_start:%d/%m/%Y} a "
            f"{period.date_end:%d/%m/%Y}"
        )
        period.delete()
        logger.info(
            "# [ausencias] %s borra la ausencia de person_pk=%s: %s",
            request.user.company_user, person.pk, label,
        )
        return _detail_response(
            request, person, year, f"Ausencia borrada: {label}.",
        )


# ------------------------------------------------------------------
# Reglas por sección
# ------------------------------------------------------------------
def _rules_context(request, message="", error=False, errors=None,
                   form_data=None):
    company = request.user.company_user.company
    rules = VacationRule.objects.filter(company=company).select_related(
        "section", "holiday_base", "created_by__user",
    ).order_by("section__name", "-valid_from")
    today = datetime.date.today()
    in_force = {}
    for rule in sorted(rules, key=lambda r: r.valid_from):
        if rule.valid_from <= today:
            in_force[rule.section_id] = rule.pk
    for rule in rules:
        rule.is_in_force = in_force.get(rule.section_id) == rule.pk
    return {
        "rules": rules,
        "sections": _sections(company),
        "bases": Base.objects.filter(company=company).order_by("name"),
        "day_kinds": VacationRule.DayKind.choices,
        "can_manage": can_manage(request),
        "message": message,
        "message_is_error": error,
        "errors": errors or [],
        "form": form_data or {
            "valid_from": f"{today.year}-01-01", "carry_over": True,
        },
    }


class VacationRulesPaneView(CompanyUserRequiredMixin, View):
    """
    GET: "Reglas por sección" window.
    ---
    GET: ventana "Reglas por sección" (lectura para todos, alta y
    borrado para quien gestiona).
    """

    def get(self, request):
        return render(
            request, "panel/vacation_balance/_rules.html",
            _rules_context(request),
        )


class VacationRuleCreateView(SupervisorAccessMixin, View):
    """
    POST: new rule (a change of rule is always a new row).
    ---
    POST: regla nueva (un cambio de regla es siempre una fila nueva con
    su fecha, nunca la edición de la anterior).
    """

    def post(self, request):
        company = request.user.company_user.company
        post = request.POST
        section = None
        if post.get("section_id"):
            section = Section.objects.filter(
                pk=_parse_int(post.get("section_id")), company=company,
            ).first()
        valid_from = _parse_date(post.get("valid_from"))
        days = _parse_decimal(post.get("days_per_year"))
        month = _parse_int(post.get("deadline_month"))
        day = _parse_int(post.get("deadline_day"))
        base = None
        if post.get("holiday_base_id"):
            base = Base.objects.filter(
                pk=_parse_int(post.get("holiday_base_id")), company=company,
            ).first()
        errors = validate_rule(
            company, section, valid_from, days, post.get("day_kind"),
            month, day,
        )
        if errors:
            return render(
                request, "panel/vacation_balance/_rules.html",
                _rules_context(request, errors=errors, form_data=post),
            )
        VacationRule.objects.create(
            company=company, section=section, valid_from=valid_from,
            days_per_year=days, day_kind=post.get("day_kind"),
            carry_over=post.get("carry_over") == "1",
            carry_over_deadline_month=month or None,
            carry_over_deadline_day=day or None,
            holiday_base=base, created_by=request.user.company_user,
        )
        name = section.name if section else "General de la empresa"
        response = render(
            request, "panel/vacation_balance/_rules.html",
            _rules_context(
                request, f"Regla guardada: {name} desde "
                         f"{valid_from:%d/%m/%Y}.",
            ),
        )
        response["HX-Trigger"] = "vacation-balance-refresh"
        return response


class VacationRuleDeleteView(SupervisorAccessMixin, View):
    """
    POST: delete a rule.
    ---
    POST: borra una regla (dada por error): los saldos se recalculan
    con las que quedan.
    """

    def post(self, request, pk):
        rule = VacationRule.objects.filter(
            pk=pk, company=request.user.company_user.company,
        ).select_related("section").first()
        if rule is None:
            raise Http404
        label = str(rule)
        rule.delete()
        response = render(
            request, "panel/vacation_balance/_rules.html",
            _rules_context(request, f"Regla borrada: {label}."),
        )
        response["HX-Trigger"] = "vacation-balance-refresh"
        return response


# ------------------------------------------------------------------
# Importación del saldo de partida
# ------------------------------------------------------------------
class VacationImportPaneView(SupervisorAccessMixin, View):
    """
    GET: "Importar saldos" window.
    ---
    GET: ventana "Importar saldos": plantilla descargable y subida.
    """

    def get(self, request):
        today = datetime.date.today()
        return render(request, "panel/vacation_balance/_import.html", {
            "years": range(today.year - 1, today.year + 2),
            "current_year": today.year,
        })


class VacationImportTemplateView(SupervisorAccessMixin, View):
    """
    GET: download the .xlsx template for a year.
    ---
    GET: descarga la plantilla .xlsx de un año.
    """

    def get(self, request):
        year = _year(request.GET.get("year"))
        content = build_template(
            request.user.company_user.company, year,
            datetime.date.today(),
        )
        response = HttpResponse(
            content,
            content_type=(
                "application/vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet"
            ),
        )
        response["Content-Disposition"] = (
            f'attachment; filename="saldos_vacaciones_{year}.xlsx"'
        )
        return response


class VacationImportUploadView(SupervisorAccessMixin, View):
    """
    POST: load a filled template and show the report.
    ---
    POST: carga una plantilla rellenada y muestra el informe (filas
    cargadas y filas no casadas, con su motivo).
    """

    def post(self, request):
        uploaded = request.FILES.get("file")
        if uploaded is None:
            report = None
            error = "Elige el archivo de la plantilla rellenada."
        else:
            report = import_template(
                uploaded, request.user.company_user.company,
                request.user.company_user,
            )
            error = ""
            logger.info(
                "# [vacation_balance] Importación de saldos %s por %s: "
                "%s cargados, %s no casados, errores=%s",
                report.year, request.user.company_user, report.loaded,
                len(report.unmatched), report.errors,
            )
        response = render(
            request, "panel/vacation_balance/_import_report.html",
            {"report": report, "error": error},
        )
        if report is not None and report.loaded:
            response["HX-Trigger"] = "vacation-balance-refresh"
        return response
