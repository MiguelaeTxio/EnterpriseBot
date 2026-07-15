# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/hr_calendar/views.py
"""
Panel views for the hr_calendar app (Hito 24, paso 2 de la hoja de ruta de
continuación del anexo V24 -- formulario de alta/edición de VacationPeriod).

Access role: ADMIN/SUPERVISOR (panel.mixins.SupervisorAccessMixin) -- "rol
a confirmar — candidato natural ADMIN/SUPERVISOR" en la hoja de ruta,
resuelto como afirmativo: es el mismo mixin ya usado por el flujo análogo
más cercano (WorkerAbsence CRUD, panel/views_workorders.py). VacationPeriod.
operator en sí no restringe rol (decisión de diseño S018, ver
hr_calendar/models.py) -- la restricción de rol aplica a quién puede DAR DE
ALTA un periodo, no a de quién puede registrarse el periodo.

Pattern mirrored closely from WorkerAbsenceCreateView/UpdateView/DeleteView
(panel/views_workorders.py) -- server-side validation, redirect-always
(success or error) via django.contrib.messages, company-scoped queries.
Two deliberate differences from that precedent, both because VacationPeriod
drives the automatic ghost-task generation (hr_calendar/services.py) that
WorkerAbsence does not have:

  1. VacationPeriodCreateView wraps the VacationPeriod.objects.create() call
     in a try/except for MachineAsset.DoesNotExist / AbsenceCategory.
     DoesNotExist -- these propagate un-caught from VacationPeriod.save()
     (see hr_calendar/models.py docstring: deliberately not swallowed
     there, this is where they surface to a human with an actionable
     message instead of a raw 500).
  2. VacationPeriodUpdateView/DeleteView must keep the ghost task in sync:
     changing date_start regenerates it on the new last working day (the
     old synthetic WorkOrder is deleted first, cascading its Entry/Line);
     changing date_end alone just refreshes the human-readable repair_notes
     text on the existing line; deleting the VacationPeriod deletes the
     ghost WorkOrder too (a dangling GENERATED WorkOrder would otherwise
     stop being excluded from hour totals the moment its VacationPeriod
     disappears -- the exclusion at the three aggregation points is keyed
     off the reverse relation, see work_order_processor/services.py and
     analytics/views.py, same commit as hr_calendar/services.py).

---

Vistas de panel para la app hr_calendar (Hito 24, paso 2 de la hoja de
ruta de continuación del anexo V24 -- formulario de alta/edición de
VacationPeriod).

Rol de acceso: ADMIN/SUPERVISOR (panel.mixins.SupervisorAccessMixin) --
"rol a confirmar — candidato natural ADMIN/SUPERVISOR" en la hoja de
ruta, resuelto como afirmativo: es el mismo mixin ya usado por el flujo
análogo más cercano (CRUD de WorkerAbsence,
panel/views_workorders.py). VacationPeriod.operator en sí no restringe
rol (decisión de diseño S018, ver hr_calendar/models.py) -- la
restricción de rol aplica a quién puede DAR DE ALTA un periodo, no a de
quién puede registrarse el periodo.

Patrón calcado de WorkerAbsenceCreateView/UpdateView/DeleteView
(panel/views_workorders.py) -- validación en servidor, redirección
siempre (éxito o error) vía django.contrib.messages, consultas acotadas
a empresa. Dos diferencias deliberadas respecto a ese precedente, ambas
porque VacationPeriod dispara la generación automática de la tarea
fantasma (hr_calendar/services.py) que WorkerAbsence no tiene:

  1. VacationPeriodCreateView envuelve la llamada a
     VacationPeriod.objects.create() en un try/except para
     MachineAsset.DoesNotExist / AbsenceCategory.DoesNotExist -- estas
     se propagan sin capturar desde VacationPeriod.save() (ver docstring
     de hr_calendar/models.py: deliberadamente no se capturan ahí, es
     aquí donde deben salir a la luz de una persona con un mensaje
     accionable en vez de un 500 desnudo).
  2. VacationPeriodUpdateView/DeleteView deben mantener sincronizada la
     tarea fantasma: cambiar date_start la regenera en la nueva última
     jornada laboral (el WorkOrder sintético anterior se borra primero,
     arrastrando en cascada su Entry/Line); cambiar solo date_end
     únicamente refresca el texto legible de repair_notes en la línea
     existente; eliminar el VacationPeriod elimina también el WorkOrder
     fantasma (un WorkOrder GENERATED huérfano dejaría de excluirse de
     los cómputos de horas en el momento en que desaparece su
     VacationPeriod -- la exclusión en los tres puntos de agregación
     está referenciada a esa relación inversa, ver
     work_order_processor/services.py y analytics/views.py, mismo
     commit que hr_calendar/services.py).
"""
from datetime import date, datetime, timedelta

from django.contrib import messages as django_messages
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.generic import View

from ivr_config.models import CompanyUser
from panel.mixins import CompanyUserRequiredMixin, SupervisorAccessMixin

from hr_calendar.models import VacationPeriod

import logging

logger = logging.getLogger(__name__)


_MESES_ES = {
    1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril",
    5: "Mayo", 6: "Junio", 7: "Julio", 8: "Agosto",
    9: "Septiembre", 10: "Octubre", 11: "Noviembre", 12: "Diciembre",
}


def _last_day_of_month(year, month):
    """
    Returns the last calendar date of the given year/month.
    ---
    Devuelve la última fecha de calendario del año/mes dado.
    """
    if month == 12:
        return date(year, 12, 31)
    return date(year, month + 1, 1) - timedelta(days=1)


def _build_month_grid(year, month, days_map):
    """
    Builds a Monday-first month grid (list of weeks, each a list of 7
    cells) for the given year/month. Each cell is either None (padding
    outside the month) or a dict with day, date, color and label -- color/
    label come from days_map (see hr_calendar.services.
    compute_calendar_days) when the date falls within the range that was
    actually computed; days of this month outside that range render with
    color=None (e.g. the tail end of a month that belongs to the next
    WorkPeriodGroup).
    ---
    Construye una cuadrícula de mes empezando en lunes (lista de semanas,
    cada una una lista de 7 celdas) para el año/mes dado. Cada celda es
    None (relleno fuera del mes) o un dict con day, date, color y label --
    color/label vienen de days_map (ver hr_calendar.services.
    compute_calendar_days) cuando la fecha cae dentro del rango realmente
    calculado; los días de este mes fuera de ese rango se renderizan con
    color=None (p. ej. la cola de un mes que pertenece al siguiente
    WorkPeriodGroup).
    """
    first_day = date(year, month, 1)
    last_day = _last_day_of_month(year, month)
    # Monday=0 ... Sunday=6 -- ya es el orden de weekday() de Python.
    leading_blanks = first_day.weekday()

    weeks = []
    week = [None] * leading_blanks
    cursor = first_day
    while cursor <= last_day:
        info = days_map.get(cursor, {"color": None, "label": ""})
        week.append({
            "day": cursor.day,
            "date": cursor,
            "color": info["color"],
            "label": info["label"],
            "is_today": cursor == date.today(),
        })
        if len(week) == 7:
            weeks.append(week)
            week = []
        cursor += timedelta(days=1)
    if week:
        week.extend([None] * (7 - len(week)))
        weeks.append(week)

    return {
        "label": f"{_MESES_ES[month]} {year}",
        "weeks": weeks,
    }


def _months_between(date_from, date_to):
    """
    Returns the ordered list of (year, month) tuples touched by
    [date_from, date_to] (inclusive) -- typically 1-3 for a WorkPeriodGroup
    span, per Miguel Ángel: "podemos poner los dos meses, los dos meses"
    (sección 3.3 del anexo, mostrar los meses completos del periodo, no
    solo los días dentro de rango).
    ---
    Devuelve la lista ordenada de tuplas (año, mes) tocadas por
    [date_from, date_to] (ambas inclusive) -- típicamente 1-3 para el
    rango de un WorkPeriodGroup, según Miguel Ángel: "podemos poner los
    dos meses, los dos meses" (sección 3.3 del anexo, mostrar los meses
    completos del periodo, no solo los días dentro de rango).
    """
    months = []
    cursor = date(date_from.year, date_from.month, 1)
    end_marker = date(date_to.year, date_to.month, 1)
    while cursor <= end_marker:
        months.append((cursor.year, cursor.month))
        if cursor.month == 12:
            cursor = date(cursor.year + 1, 1, 1)
        else:
            cursor = date(cursor.year, cursor.month + 1, 1)
    return months


class VacationCalendarView(CompanyUserRequiredMixin, View):
    """
    Calendar view for H24 -- visible to every authenticated role
    (ENTERPRISEBOT_ATTACHED_MILESTONE_V24.md sección 3.2: "Visible para
    todo el mundo (todos los roles autenticados)"). ADMIN/SUPERVISOR get
    an operator selector and can view anyone's calendar; WORKSHOP/DRIVER
    (and any other role) see only their own, no selector -- matches the
    access matrix in the anexo exactly.

    Grouped by WorkPeriodGroup (sección 3.3), with prev/next navigation
    between periods. Falls back to the current natural month when the
    company has no WorkPeriodGroup at all (documented default in the
    anexo).
    ---
    Vista de calendario para H24 -- visible a todo rol autenticado
    (ENTERPRISEBOT_ATTACHED_MILESTONE_V24.md sección 3.2: "Visible para
    todo el mundo (todos los roles autenticados)"). ADMIN/SUPERVISOR
    tienen selector de operario y pueden ver el calendario de cualquiera;
    WORKSHOP/DRIVER (y cualquier otro rol) solo ven el suyo propio, sin
    selector -- coincide exactamente con la matriz de acceso del anexo.

    Agrupado por WorkPeriodGroup (sección 3.3), con navegación anterior/
    siguiente entre periodos. Cae al mes natural actual cuando la empresa
    no tiene ningún WorkPeriodGroup (comportamiento por defecto
    documentado en el anexo).
    """
    template_name = "hr_calendar/calendar.html"

    def get(self, request, *args, **kwargs):
        from hr_calendar.services import (
            compute_calendar_days,
            resolve_period_group_for_calendar,
        )

        cu = request.user.company_user
        company = cu.company
        is_elevated = cu.role in (
            CompanyUser.ROLE_ADMIN, CompanyUser.ROLE_SUPERVISOR,
        )

        operators = None
        if is_elevated:
            operators = list(
                CompanyUser.objects
                .filter(company=company, is_active=True)
                .select_related("user")
                .order_by("user__first_name", "user__last_name", "user__username")
            )
            _op_pk_raw = request.GET.get("operator_pk", "").strip()
            target_operator = None
            if _op_pk_raw.isdigit():
                target_operator = next(
                    (o for o in operators if o.pk == int(_op_pk_raw)), None,
                )
            if target_operator is None and operators:
                target_operator = operators[0]
        else:
            target_operator = cu

        if target_operator is None:
            # Empresa sin ningún CompanyUser activo -- caso límite, nada
            # que pintar.
            return render(request, self.template_name, {
                "active_nav": "vacation_calendar",
                "is_elevated": is_elevated,
                "operators": operators,
                "target_operator": None,
            })

        _group_pk_raw = request.GET.get("group_pk", "").strip()
        group_pk = int(_group_pk_raw) if _group_pk_raw.isdigit() else None
        resolved = resolve_period_group_for_calendar(company, group_pk)

        if resolved is not None:
            group = resolved["group"]
            date_from = group.start_date
            date_to = group.end_date or date.today()
            period_kind = "Periodo liquidado" if group.is_closed else "Periodo activo"
            _start_m = _MESES_ES[date_from.month]
            _end_m = _MESES_ES[date_to.month]
            if date_from.month == date_to.month and date_from.year == date_to.year:
                period_label = f"{period_kind}: {_start_m} {date_from.year}"
            elif date_from.year == date_to.year:
                period_label = (
                    f"{period_kind}: {_start_m} y {_end_m} {date_to.year}"
                )
            else:
                period_label = (
                    f"{period_kind}: {_start_m} {date_from.year} y "
                    f"{_end_m} {date_to.year}"
                )
            prev_group_pk = resolved["prev_group_pk"]
            next_group_pk = resolved["next_group_pk"]
            group_pk_current = group.pk
        else:
            today = date.today()
            date_from = today.replace(day=1)
            date_to = _last_day_of_month(today.year, today.month)
            period_label = f"{_MESES_ES[today.month]} {today.year}"
            prev_group_pk = None
            next_group_pk = None
            group_pk_current = None

        days_map = compute_calendar_days(
            target_operator, company, date_from, date_to,
        )
        months = [
            _build_month_grid(y, m, days_map)
            for (y, m) in _months_between(date_from, date_to)
        ]

        return render(request, self.template_name, {
            "active_nav": "vacation_calendar",
            "is_elevated": is_elevated,
            "operators": operators,
            "target_operator": target_operator,
            "period_label": period_label,
            "prev_group_pk": prev_group_pk,
            "next_group_pk": next_group_pk,
            "group_pk_current": group_pk_current,
            "months": months,
        })


def _parse_iso(value):
    """
    Parses a YYYY-MM-DD string into a date object, returns None on failure.
    ---
    Parsea una cadena YYYY-MM-DD a un objeto date, devuelve None si falla.
    """
    try:
        return datetime.strptime(value.strip(), "%Y-%m-%d").date()
    except (ValueError, AttributeError):
        return None


class VacationPeriodListView(SupervisorAccessMixin, View):
    """
    Lists registered VacationPeriods for the company (most recent
    date_start first) and renders the create form (operator dropdown
    scoped to active CompanyUsers of the company).
    ---
    Lista los VacationPeriod registrados de la empresa (date_start más
    reciente primero) y renderiza el formulario de alta (desplegable de
    operarios acotado a CompanyUsers activos de la empresa).
    """
    template_name = "hr_calendar/vacation_periods.html"

    def get(self, request, *args, **kwargs):
        cu = request.user.company_user
        company = cu.company

        periods = (
            VacationPeriod.objects
            .filter(company=company)
            .select_related("operator__user", "generated_entry_line")
            .order_by("-date_start")
        )
        operators = (
            CompanyUser.objects
            .filter(company=company, is_active=True)
            .select_related("user")
            .order_by("user__first_name", "user__last_name", "user__username")
        )

        return render(request, self.template_name, {
            "active_nav": "vacation_periods",
            "periods": periods,
            "operators": operators,
        })


class VacationPeriodCreateView(SupervisorAccessMixin, View):
    """
    Creates a VacationPeriod from the form in vacation_periods.html.
    Saving triggers the automatic ghost-task generation (VacationPeriod.
    save(), hr_calendar/services.py::generate_vacation_task) inside the
    same atomic transaction -- a failure there rolls back the period too.

    POST /panel/vacaciones/crear/
        Body params:
          operator_pk (int) — pk of the target CompanyUser (must belong to company).
          date_start  (str) — ISO date YYYY-MM-DD.
          date_end    (str) — ISO date YYYY-MM-DD.
    ---
    Crea un VacationPeriod desde el formulario de vacation_periods.html.
    Guardar dispara la generación automática de la tarea fantasma
    (VacationPeriod.save(), hr_calendar/services.py::
    generate_vacation_task) dentro de la misma transacción atómica -- un
    fallo ahí revierte también el periodo.

    POST /panel/vacaciones/crear/
        Parámetros del cuerpo:
          operator_pk (int) — pk del CompanyUser objetivo (debe pertenecer a empresa).
          date_start  (str) — fecha ISO YYYY-MM-DD.
          date_end    (str) — fecha ISO YYYY-MM-DD.
    """

    def post(self, request, *args, **kwargs):
        cu = request.user.company_user
        company = cu.company
        LIST_URL = reverse("hr_calendar:vacation_period_list")

        try:
            operator_pk = int(request.POST.get("operator_pk", ""))
            operator = CompanyUser.objects.get(pk=operator_pk, company=company)
        except (ValueError, TypeError, CompanyUser.DoesNotExist):
            django_messages.error(
                request,
                "Operario/chófer no encontrado o no pertenece a esta empresa.",
            )
            return redirect(LIST_URL)

        date_start = _parse_iso(request.POST.get("date_start", ""))
        date_end = _parse_iso(request.POST.get("date_end", ""))

        if not date_start or not date_end:
            django_messages.error(
                request,
                "Las fechas de inicio y fin son obligatorias y deben "
                "tener formato YYYY-MM-DD.",
            )
            return redirect(LIST_URL)

        if date_start > date_end:
            django_messages.error(
                request,
                "La fecha de inicio no puede ser posterior a la fecha de fin.",
            )
            return redirect(LIST_URL)

        operator_name = operator.user.get_full_name() or operator.user.username

        try:
            VacationPeriod.objects.create(
                company=company,
                operator=operator,
                created_by=cu,
                date_start=date_start,
                date_end=date_end,
            )
        except Exception as exc:
            # MachineAsset.DoesNotExist / AbsenceCategory.DoesNotExist
            # (seed_personal_asset / seed_absence_categories no ejecutados
            # para esta empresa) llegan aquí sin capturar desde
            # VacationPeriod.save() -- deliberado, ver docstring del
            # módulo. Cualquier otro fallo también se muestra tal cual,
            # mismo principio empírico del resto del proyecto: nunca a
            # ciegas.
            logger.error(
                "# [hr_calendar/views] Error creando VacationPeriod. "
                "operator_pk=%r date_start=%r date_end=%r: %s",
                operator_pk, date_start, date_end, exc, exc_info=True,
            )
            django_messages.error(
                request,
                f"Error al registrar el periodo de vacaciones: {exc}. "
                "Si el error menciona PERSONAL o VACATION, contacta con "
                "el administrador de la plataforma -- faltan datos base "
                "de configuración para esta empresa.",
            )
            return redirect(LIST_URL)

        django_messages.success(
            request,
            f"Periodo de vacaciones de {operator_name} registrado "
            f"correctamente ({date_start:%d/%m/%Y} – {date_end:%d/%m/%Y}). "
            "Tarea automática generada en la última jornada laboral "
            "anterior al inicio.",
        )
        return redirect(LIST_URL)


class VacationPeriodUpdateView(SupervisorAccessMixin, View):
    """
    Updates the dates of an existing VacationPeriod. The operator is not
    editable (avoids re-attributing an already-generated ghost task to
    the wrong person -- to change the operator, delete and re-create).

    If date_start changes, the previously generated ghost WorkOrder (if
    any) is deleted (cascading its Entry/Line) and a new one is generated
    for the new last working day. If only date_end changes, the existing
    ghost line's repair_notes is refreshed to the new human-readable date
    (nothing parses it -- see VacationPeriod docstring -- so this is a
    display-only update, safe to do directly).

    POST /panel/vacaciones/<pk>/editar/
        Body params:
          date_start (str) — ISO date YYYY-MM-DD.
          date_end   (str) — ISO date YYYY-MM-DD.
    ---
    Actualiza las fechas de un VacationPeriod existente. El operario no es
    editable (evita reatribuir una tarea fantasma ya generada a la
    persona equivocada -- para cambiar de operario, eliminar y volver a
    crear).

    Si date_start cambia, el WorkOrder fantasma generado previamente (si
    lo hay) se elimina (arrastrando en cascada su Entry/Line) y se genera
    uno nuevo para la nueva última jornada laboral. Si solo cambia
    date_end, se refresca únicamente el repair_notes de la línea fantasma
    existente con la nueva fecha legible (nada la parsea -- ver docstring
    de VacationPeriod -- así que es una actualización solo de
    visualización, segura de hacer directamente).

    POST /panel/vacaciones/<pk>/editar/
        Parámetros del cuerpo:
          date_start (str) — fecha ISO YYYY-MM-DD.
          date_end   (str) — fecha ISO YYYY-MM-DD.
    """

    def post(self, request, pk, *args, **kwargs):
        from django.db import transaction

        cu = request.user.company_user
        company = cu.company
        LIST_URL = reverse("hr_calendar:vacation_period_list")

        try:
            period = VacationPeriod.objects.select_related(
                "operator__user", "generated_entry_line__entry__work_order",
            ).get(pk=pk, company=company)
        except VacationPeriod.DoesNotExist:
            django_messages.error(
                request,
                "Periodo de vacaciones no encontrado o no pertenece a esta empresa.",
            )
            return redirect(LIST_URL)

        date_start = _parse_iso(request.POST.get("date_start", ""))
        date_end = _parse_iso(request.POST.get("date_end", ""))

        if not date_start or not date_end:
            django_messages.error(
                request,
                "Las fechas de inicio y fin son obligatorias y deben "
                "tener formato YYYY-MM-DD.",
            )
            return redirect(LIST_URL)

        if date_start > date_end:
            django_messages.error(
                request,
                "La fecha de inicio no puede ser posterior a la fecha de fin.",
            )
            return redirect(LIST_URL)

        operator_name = (
            period.operator.user.get_full_name()
            or period.operator.user.username
        )
        start_changed = date_start != period.date_start
        end_changed = date_end != period.date_end

        try:
            with transaction.atomic():
                if start_changed and period.generated_entry_line_id:
                    # Borra el WorkOrder sintético completo (cascada
                    # Entry/Line) -- la nueva última jornada laboral puede
                    # no coincidir con la anterior.
                    old_work_order = period.generated_entry_line.entry.work_order
                    period.generated_entry_line = None
                    period.save(update_fields=["generated_entry_line"])
                    old_work_order.delete()

                period.date_start = date_start
                period.date_end = date_end
                period.save(update_fields=["date_start", "date_end"])

                if start_changed and period.generated_entry_line_id is None:
                    from hr_calendar.services import generate_vacation_task
                    generate_vacation_task(period)
                elif end_changed and period.generated_entry_line_id:
                    ghost_line = period.generated_entry_line
                    ghost_line.repair_notes = (
                        f"Vacaciones hasta el {date_end:%d/%m/%Y}."
                    )
                    ghost_line.save(update_fields=["repair_notes"])
        except Exception as exc:
            logger.error(
                "# [hr_calendar/views] Error actualizando VacationPeriod "
                "pk=%r: %s", pk, exc, exc_info=True,
            )
            django_messages.error(
                request,
                f"Error al actualizar el periodo de vacaciones: {exc}.",
            )
            return redirect(LIST_URL)

        django_messages.success(
            request,
            f"Periodo de vacaciones de {operator_name} actualizado "
            f"correctamente ({date_start:%d/%m/%Y} – {date_end:%d/%m/%Y}).",
        )
        return redirect(LIST_URL)


class VacationPeriodDeleteView(SupervisorAccessMixin, View):
    """
    Deletes a VacationPeriod and its generated ghost WorkOrder (if any),
    scoped to the authenticated user's company.

    POST /panel/vacaciones/<pk>/eliminar/
    ---
    Elimina un VacationPeriod y su WorkOrder fantasma generado (si lo
    hay), acotado a la empresa del usuario autenticado.

    POST /panel/vacaciones/<pk>/eliminar/
    """

    def post(self, request, pk, *args, **kwargs):
        cu = request.user.company_user
        company = cu.company
        LIST_URL = reverse("hr_calendar:vacation_period_list")

        try:
            period = VacationPeriod.objects.select_related(
                "operator__user", "generated_entry_line__entry__work_order",
            ).get(pk=pk, company=company)
        except VacationPeriod.DoesNotExist:
            django_messages.error(
                request,
                "Periodo de vacaciones no encontrado o no pertenece a esta empresa.",
            )
            return redirect(LIST_URL)

        operator_name = (
            period.operator.user.get_full_name()
            or period.operator.user.username
        )

        # Borra primero el WorkOrder fantasma completo (cascada Entry/
        # Line) -- si se dejara huérfano, dejaría de excluirse de los
        # cómputos de horas en cuanto desaparezca este VacationPeriod
        # (la exclusión está referenciada a esta misma relación inversa).
        if period.generated_entry_line_id:
            period.generated_entry_line.entry.work_order.delete()

        period.delete()

        django_messages.success(
            request,
            f"Periodo de vacaciones de {operator_name} eliminado correctamente.",
        )
        return redirect(LIST_URL)
