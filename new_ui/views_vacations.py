# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/new_ui/views_vacations.py
"""
Vacation balances, periods, absences, rules and import, new interface.

---

Vacaciones y ausencias en la nueva interfaz (S163), copiado de
panel/views_vacation_balance.py y de los tipos de ausencia de
panel/views_workorders.py:
- Personal › Saldo de vacaciones (vista propia): una fila por
  trabajador con los filtros comunes, el año y la sección (botones),
  con lo que le corresponde, del año anterior, ajustes, consumidos y
  pendientes; casilla para marcarlo.
- Acciones de esa vista: registrar vacaciones a los marcados, asignar
  una sección desde una fecha, reglas por sección (crear, borrar),
  importar el saldo de partida (plantilla y subida) y tipos de ausencia
  (crear, modificar, activar/desactivar).
- Personal › Desglose de vacaciones (pestaña de la persona abierta): el
  desglose del año con tramos, periodos (cambiar fechas, borrar),
  ausencias (registrar, borrar), ajustes manuales y días libres por
  horas acumuladas (registrar, borrar) e historial de secciones
  (borrar).
"""
import datetime
import logging
from decimal import Decimal, InvalidOperation

from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.views import View

from budgets.models import Base
from document_explorer.models import PersonIdentity
from hr_calendar.balance import (
    BalanceCalculator, add_free_days,
    add_manual_adjustment, assign_section, validate_rule,
)
from hr_calendar.models import (
    AbsencePeriod, PersonSectionAssignment, VacationBalanceAdjustment,
    VacationPeriod, VacationRule,
)
from hr_calendar.services import absence_categories, create_absence_period
from ivr_config.models import Section
from new_ui.mixins import SuperuserRequiredMixin

logger = logging.getLogger(__name__)

SORTS = {
    "person": lambda r: r.sort_name,
    "dni": lambda r: r.person.dni,
    "section": lambda r: r.balance.current_section_name.upper() or None,
    "taken": lambda r: r.balance.taken,
    "pending": lambda r: r.balance.pending,
}


def _ok(message, pk=None):
    payload = {"ok": True, "message": message}
    if pk:
        payload["id"] = pk
    return JsonResponse(payload)


def _error(message):
    return JsonResponse({"ok": False, "message": message}, status=400)


def _year(raw):
    try:
        year = int(raw)
    except (TypeError, ValueError):
        return datetime.date.today().year
    return year if 2000 <= year <= 2100 else datetime.date.today().year


def _date(raw):
    try:
        return datetime.date.fromisoformat((raw or "").strip())
    except ValueError:
        return None


def _decimal(raw):
    try:
        return Decimal((raw or "").strip().replace(",", "."))
    except InvalidOperation:
        return None


def _int(raw):
    try:
        return int((raw or "").strip())
    except (TypeError, ValueError, AttributeError):
        return None


def _time(raw):
    try:
        return datetime.time.fromisoformat((raw or "").strip()[:5])
    except ValueError:
        return None


def _parse_minutes(raw):
    """"3:30", "3,5" or "3.5" hours -> minutes; None if not valid."""
    raw = (raw or "").strip().replace(",", ".")
    try:
        if ":" in raw:
            hours, minutes = raw.split(":", 1)
            total = int(hours or 0) * 60 + int(minutes or 0)
        else:
            total = int(round(float(raw) * 60))
    except ValueError:
        return None
    return total if total > 0 else None


def _label(person):
    surnames = " ".join(
        p for p in (person.first_surname, person.second_surname) if p)
    return "%s, %s" % (surnames, person.given_name)


def _company(request):
    return request.user.company_user.company


def _sections(company):
    return Section.objects.filter(company=company).order_by("name")


class _Row:
    """Una línea del saldo: la persona, su saldo y su nombre."""

    def __init__(self, person, balance):
        self.person = person
        self.balance = balance
        self.label = _label(person)
        self.sort_name = self.label.upper()


# ------------------------------------------------------------ el saldo
def render_balance(request):
    """
    Personal › Saldo de vacaciones: the balance of the filtered people.

    ---

    La vista «Saldo de vacaciones»: las personas de los filtros comunes
    (estado, empresa, sección, grupo, buscador...), su saldo del año
    elegido, por sección y ordenadas.
    """
    from new_ui.lists import filtered, list_def

    company = _company(request)
    year = _year(request.GET.get("vac_year"))
    section = request.GET.get("vac_section", "")
    people = list(filtered(list_def("per", "general"), company,
                           request.GET, None).select_related(
        "company_user__base"))
    calculator = BalanceCalculator(company, people)
    rows = [_Row(p, calculator.balance(p, year)) for p in people]
    # S163 (23/11): de dónde le vienen los días (propios, su grupo o la
    # empresa), en lugar de la sección del SIME.
    sources = sorted({r.balance.current_section_name for r in rows
                      if r.balance.current_section_name})
    if section:
        rows = [r for r in rows if r.balance.current_section_name == section]
    sort = request.GET.get("vac_sort", "")
    key = sort.lstrip("-")
    rows.sort(key=lambda r: r.sort_name)
    if key in SORTS:
        getter = SORTS[key]
        present = [r for r in rows if getter(r) is not None]
        missing = [r for r in rows if getter(r) is None]
        rows = sorted(present, key=getter,
                      reverse=sort.startswith("-")) + missing
    today = datetime.date.today()
    return render(request, "new_ui/_vacation_balance.html", {
        "rows": rows,
        "year": year,
        "years": range(today.year - 2, today.year + 2),
        "section": section,
        "sources": sources,
        "sort": sort,
        "sorts": [("person", "Trabajador"), ("dni", "DNI"),
                  ("section", "Días de"), ("taken", "Consumidos"),
                  ("pending", "Pendientes")],
    })


def vacations_context(section, company):
    """
    Context of the vacations actions (sections, bases, rules data).

    ---

    Datos de las acciones de vacaciones: secciones, bases, tipos de día
    y años para la plantilla de importación.
    """
    if section != "per":
        return {}
    return {
        "vac_sections": _sections(company),
        "vac_day_kinds": VacationRule.DayKind.choices,
        "vac_years": range(datetime.date.today().year - 1,
                           datetime.date.today().year + 2),
        "vac_this_year": datetime.date.today().year,
        "vac_today": datetime.date.today(),
    }


class VacationRegisterView(SuperuserRequiredMixin, View):
    """
    POST `selected`, `date_start`, `date_end`: vacations of the marked.

    ---

    POST: registra el mismo periodo de vacaciones a cada marcado (el
    alta de siempre: hr_calendar.services.create_vacation_period, con
    su tarea automática si tiene cuenta del panel).
    """

    def post(self, request):
        from hr_calendar.services import create_vacation_period

        cu = request.user.company_user
        date_start = _date(request.POST.get("date_start"))
        date_end = _date(request.POST.get("date_end"))
        ids = [v for v in request.POST.getlist("selected") if v.isdigit()]
        people = list(PersonIdentity.objects.filter(pk__in=ids))
        if date_start is None or date_end is None:
            return _error("Indica la fecha de inicio y la de fin.")
        if not people:
            return _error("Marca primero a los trabajadores.")
        done, problems = 0, []
        for person in people:
            try:
                create_vacation_period(
                    person=person, company=cu.company, created_by=cu,
                    date_start=date_start, date_end=date_end)
                done += 1
            except ValueError as exc:
                problems.append("%s: %s" % (_label(person), exc))
            except Exception as exc:  # noqa: BLE001 -- se registra y avisa
                logger.error(
                    "# [new_ui vacaciones] Error registrando vacaciones de "
                    "person_pk=%s (%s a %s): %s", person.pk, date_start,
                    date_end, exc, exc_info=True)
                problems.append(
                    "%s: falta configuración de la tarea automática "
                    "(centro de gasto PERSONAL o categoría Vacaciones); "
                    "avisa al administrador." % _label(person))
        message = "Vacaciones del %s al %s registradas a %d trabajador(es)." % (
            date_start.strftime("%d/%m/%Y"), date_end.strftime("%d/%m/%Y"),
            done)
        if problems:
            message += " No se pudo a: " + "; ".join(problems)
        return (_ok if done else _error)(message)


class SectionAssignView(SuperuserRequiredMixin, View):
    """
    POST: assign a section from a date to the marked (vacation rules).

    ---

    POST: asigna una sección desde una fecha a los marcados (solo filas
    PersonSectionAssignment; nunca se guarda la sección).
    """

    def post(self, request):
        company = _company(request)
        section = Section.objects.filter(
            pk=_int(request.POST.get("section_id")), company=company).first()
        valid_from = _date(request.POST.get("valid_from"))
        ids = [v for v in request.POST.getlist("selected") if v.isdigit()]
        people = list(PersonIdentity.objects.filter(pk__in=ids))
        if section is None or valid_from is None or not people:
            return _error("Elige la sección, la fecha y al menos un "
                          "trabajador.")
        created, updated = assign_section(
            people, section, valid_from, request.user.company_user)
        return _ok("Sección «%s» asignada desde %s a %d trabajador(es) (%d "
                   "nuevas, %d cambiadas)." % (
                       section.name, valid_from.strftime("%d/%m/%Y"),
                       len(people), created, updated))


# ------------------------------------------------------------ el desglose
def render_detail(request, person):
    """
    Personal › Desglose de vacaciones of the open person, for a year.

    ---

    El desglose del saldo de la persona abierta en un año: cifras,
    avisos, tramos, periodos, ausencias, ajustes e historial de
    secciones, con sus acciones.
    """
    from hr_calendar.clock_extras import overtime_bag, signed_duration

    company = _company(request)
    year = _year(request.GET.get("vac_year"))
    balance = BalanceCalculator(company, [person]).balance(person, year)
    bag_label = ""
    if person.company_user_id is not None:
        bag_label = signed_duration(overtime_bag(
            person.company_user.company, person.company_user,
        )["total_seconds"])
    today = datetime.date.today()
    return render(request, "new_ui/_vacation_detail.html", {
        "person": person,
        "person_label": _label(person),
        "year": year,
        "years": range(today.year - 2, today.year + 2),
        "balance": balance,
        "bag_label": bag_label,
        "assignments": PersonSectionAssignment.objects.filter(
            person=person).select_related(
            "section", "created_by__user").order_by("-valid_from"),
        "absences": AbsencePeriod.objects.filter(
            person=person, date_start__lte=datetime.date(year, 12, 31),
            date_end__gte=datetime.date(year, 1, 1),
        ).select_related("category", "created_by__user").order_by(
            "date_start"),
        "absence_categories": absence_categories(company),
    })


def _person(pk):
    from django.http import Http404

    person = PersonIdentity.objects.select_related(
        "company_user__base").filter(pk=pk).first()
    if person is None:
        raise Http404
    return person


class VacationDetailActionView(SuperuserRequiredMixin, View):
    """
    POST `what`: one action of the breakdown of a person.

    ---

    POST: una acción del desglose: «period_edit», «period_remove»,
    «absence_add», «absence_remove», «adjust_add», «free_days»,
    «adjust_remove» o «assignment_remove».
    """

    def post(self, request, pk):
        person = _person(pk)
        company = _company(request)
        cu = request.user.company_user
        year = _year(request.POST.get("year"))
        what = request.POST.get("what", "")
        if what in ("period_edit", "period_remove"):
            period = VacationPeriod.objects.filter(
                pk=_int(request.POST.get("period")), company=company,
                person=person).first()
            if period is None:
                return _error("Ese periodo ya no existe.")
            if what == "period_remove":
                from hr_calendar.services import delete_vacation_period

                label = "%s a %s" % (period.date_start.strftime("%d/%m/%Y"),
                                     period.date_end.strftime("%d/%m/%Y"))
                delete_vacation_period(period)
                return _ok("Periodo borrado: %s." % label)
            from hr_calendar.services import update_vacation_period

            date_start = _date(request.POST.get("date_start"))
            date_end = _date(request.POST.get("date_end"))
            if date_start is None or date_end is None:
                return _error("Indica la fecha de inicio y la de fin.")
            try:
                update_vacation_period(period, date_start, date_end)
            except ValueError as exc:
                return _error(str(exc))
            return _ok("Periodo guardado: %s a %s." % (
                date_start.strftime("%d/%m/%Y"),
                date_end.strftime("%d/%m/%Y")))
        if what == "absence_add":
            date_start = _date(request.POST.get("date_start"))
            date_end = _date(request.POST.get("date_end"))
            if date_start is None or date_end is None:
                return _error("Indica la fecha de inicio y la de fin.")
            try:
                period = create_absence_period(
                    person, company, cu, _int(request.POST.get("category_id")),
                    date_start, date_end, request.POST.get("note"),
                    _time(request.POST.get("time_from")),
                    _time(request.POST.get("time_to")))
            except ValueError as exc:
                return _error(str(exc))
            logger.info("# [new_ui ausencias] %s registra %s de person_pk=%s:"
                        " %s a %s", cu, period.category.code, person.pk,
                        date_start, date_end)
            return _ok("Ausencia registrada: %s, %s a %s." % (
                period.category.label, date_start.strftime("%d/%m/%Y"),
                date_end.strftime("%d/%m/%Y")))
        if what == "absence_remove":
            period = AbsencePeriod.objects.filter(
                pk=_int(request.POST.get("absence")), company=company,
                person=person).select_related("category").first()
            if period is None:
                return _error("Esa ausencia ya no existe.")
            label = "%s, %s a %s" % (
                period.category.label, period.date_start.strftime("%d/%m/%Y"),
                period.date_end.strftime("%d/%m/%Y"))
            period.delete()
            logger.info("# [new_ui ausencias] %s borra la ausencia de "
                        "person_pk=%s: %s", cu, person.pk, label)
            return _ok("Ausencia borrada: %s." % label)
        if what in ("adjust_add", "free_days"):
            days = _decimal(request.POST.get("days"))
            if days is None or days != days.to_integral_value():
                return _error("Los días deben ser un número entero (p. ej. 2 "
                              "o -1).")
            try:
                if what == "adjust_add":
                    add_manual_adjustment(person, company, year, days,
                                          request.POST.get("reason"), cu)
                    return _ok("Ajuste de %s día(s) registrado en %d." % (
                        days, year))
                add_free_days(person, company, year, days,
                              _parse_minutes(request.POST.get("hours")),
                              request.POST.get("reason"), cu)
            except ValueError as exc:
                return _error(str(exc))
            return _ok("%s día(s) libre(s) por horas acumuladas sumados en "
                       "%d." % (days, year))
        if what == "adjust_remove":
            row = VacationBalanceAdjustment.objects.filter(
                pk=_int(request.POST.get("adjustment")), company=company,
                person=person).first()
            if row is None:
                return _error("Ese ajuste ya no existe.")
            label = "%s (%s días)" % (row.get_kind_display(), row.days)
            if row.kind == VacationBalanceAdjustment.Kind.OVERTIME:
                label += "; las horas vuelven a la bolsa"
            row.delete()
            return _ok("Ajuste borrado: %s." % label)
        if what == "assignment_remove":
            row = PersonSectionAssignment.objects.filter(
                pk=_int(request.POST.get("assignment")),
                person=person).select_related("section").first()
            if row is None:
                return _error("Esa asignación ya no existe.")
            label = "%s desde %s" % (row.section.name,
                                     row.valid_from.strftime("%d/%m/%Y"))
            row.delete()
            return _ok("Asignación borrada: %s." % label)
        return _error("Acción desconocida.")


# ------------------------------------------------- reglas, importar, tipos
class VacationOwnDaysView(SuperuserRequiredMixin, View):
    """
    POST: own vacation days for the marked workers (or remove them).

    ---

    POST (S163, 23/11): días propios de los trabajadores marcados, que
    mandan sobre los de su grupo y los de la empresa (una regla por
    persona, con su fecha); `what=remove` les quita los días propios
    (vuelven a los de su grupo o los de la empresa).
    """

    def post(self, request):
        company = _company(request)
        post = request.POST
        ids = [v for v in post.getlist("selected") if v.isdigit()]
        people = list(PersonIdentity.objects.filter(pk__in=ids))
        if not people:
            return _error("Marca primero a los trabajadores.")
        if post.get("what") == "remove":
            count, _detail = VacationRule.objects.filter(
                company=company, person__in=people).delete()
            return _ok("Días propios quitados (%d regla(s)): vuelven a los "
                       "de su grupo o los de la empresa." % count)
        valid_from = _date(post.get("valid_from"))
        days = _decimal(post.get("days_per_year"))
        kind = post.get("day_kind")
        errors = validate_rule(company, None, valid_from, days, kind,
                               None, None)
        if errors:
            return _error(" ".join(errors))
        done, skipped = 0, []
        for person in people:
            if VacationRule.objects.filter(company=company, person=person,
                                           valid_from=valid_from).exists():
                skipped.append(_label(person))
                continue
            VacationRule.objects.create(
                company=company, person=person, valid_from=valid_from,
                days_per_year=days, day_kind=kind,
                carry_over=post.get("carry_over") == "1",
                created_by=request.user.company_user)
            done += 1
        message = "Días propios (%s al año desde el %s) a %d trabajador(es)." % (
            days, valid_from.strftime("%d/%m/%Y"), done)
        if skipped:
            message += " Ya tenían una con esa fecha: %s." % ", ".join(skipped)
        return _ok(message) if done else _error(message)


def _rule_sheet_context(company, rule=None, base_rule=None):
    """Datos de la ventana de una regla (vista o nueva)."""
    from django.urls import reverse

    from document_explorer.models import PersonGroupTemplate

    today = datetime.date.today()
    return {
        "rule": rule,
        "base": base_rule,
        "groups": PersonGroupTemplate.objects.order_by("name"),
        "bases": Base.objects.filter(company=company).order_by("name"),
        "day_kinds": VacationRule.DayKind.choices,
        "today": today,
        "valid_from": today if base_rule else datetime.date(today.year, 1,
                                                            1),
        "open_tpl": reverse("new_ui:vacation_rule_sheet", args=[0]),
    }


class VacationRuleSheetView(SuperuserRequiredMixin, View):
    """
    GET: one vacation rule in the viewer (0 = a new one, ?from=<pk>
    prefilled from another).

    ---

    GET: una regla de vacaciones en el visor. Las reglas no se
    modifican: la ventana de una regla la enseña y ofrece «Nueva a
    partir de esta» (0 con ?from=) y «Borrar esta regla» (5 s).
    """

    def get(self, request, pk):
        from django.http import Http404

        company = _company(request)
        rules = VacationRule.objects.filter(
            company=company, person__isnull=True).select_related(
            "group", "section", "holiday_base")
        if pk:
            rule = rules.filter(pk=pk).first()
            if rule is None:
                raise Http404
            return render(request, "new_ui/_vacation_rule.html",
                          _rule_sheet_context(company, rule=rule))
        base_rule = rules.filter(pk=_int(request.GET.get("from"))).first() \
            if request.GET.get("from") else None
        return render(request, "new_ui/_vacation_rule.html",
                      _rule_sheet_context(company, base_rule=base_rule))


class AbsenceTypeSheetView(SuperuserRequiredMixin, View):
    """
    GET: one absence type in the viewer (0 = a new one).

    ---

    GET: un tipo de ausencia en el visor, para crearlo o modificarlo,
    activarlo o desactivarlo (no se borran).
    """

    def get(self, request, pk):
        from django.http import Http404
        from django.urls import reverse

        from ivr_config.models import AbsenceCategory

        category = None
        if pk:
            category = AbsenceCategory.objects.filter(
                pk=pk, company=_company(request)).first()
            if category is None:
                raise Http404
        return render(request, "new_ui/_absence_type.html", {
            "category": category,
            "open_tpl": reverse("new_ui:absence_type_sheet", args=[0]),
        })


class VacationSetupSaveView(SuperuserRequiredMixin, View):
    """
    POST `what`: rule_add, rule_remove, rules_remove (selected),
    category_add, category_save, category_toggle, categories_active
    (selected, active=1|0).

    ---

    POST: reglas (una regla nueva es siempre una fila con su fecha,
    nunca se edita la anterior) y tipos de ausencia (crear, modificar,
    activar o desactivar; no se borran).
    """

    def post(self, request):
        from ivr_config.models import AbsenceCategory

        company = _company(request)
        post = request.POST
        what = post.get("what", "")
        if what == "rule_add":
            from document_explorer.models import PersonGroupTemplate

            group = PersonGroupTemplate.objects.filter(
                pk=_int(post.get("group_id"))).first() \
                if post.get("group_id") else None
            valid_from = _date(post.get("valid_from"))
            days = _decimal(post.get("days_per_year"))
            month = _int(post.get("deadline_month"))
            day = _int(post.get("deadline_day"))
            base = Base.objects.filter(
                pk=_int(post.get("holiday_base_id")), company=company,
            ).first() if post.get("holiday_base_id") else None
            errors = validate_rule(company, None, valid_from, days,
                                   post.get("day_kind"), month, day,
                                   group=group)
            if errors:
                return _error(" ".join(errors))
            rule = VacationRule.objects.create(
                company=company, group=group, valid_from=valid_from,
                days_per_year=days, day_kind=post.get("day_kind"),
                carry_over=post.get("carry_over") == "1",
                carry_over_deadline_month=month or None,
                carry_over_deadline_day=day or None, holiday_base=base,
                created_by=request.user.company_user)
            return _ok("Regla guardada: %s desde %s." % (
                "grupo «%s»" % group.name if group else "la empresa",
                valid_from.strftime("%d/%m/%Y")), rule.pk)
        if what == "rules_remove":
            rules = VacationRule.objects.filter(
                company=company, person__isnull=True,
                pk__in=[v for v in post.getlist("selected")
                        if v.isdigit()])
            labels = [str(rule) for rule in rules]
            if not labels:
                return _error("Marca primero las reglas a borrar.")
            rules.delete()
            return _ok("Reglas borradas (%d): %s. Los saldos se "
                       "recalculan con las que quedan." % (
                           len(labels), "; ".join(labels)))
        if what == "rule_remove":
            rule = VacationRule.objects.filter(
                pk=_int(post.get("rule")), company=company).first()
            if rule is None:
                return _error("Esa regla ya no existe.")
            label = str(rule)
            rule.delete()
            return _ok("Regla borrada: %s." % label)
        if what == "category_add":
            label = (post.get("label") or "").strip()
            code = (post.get("code") or "").strip().upper()
            if not label or not code:
                return _error("El nombre y el código son obligatorios.")
            if AbsenceCategory.objects.filter(company=company,
                                              code=code).exists():
                return _error("Ya existe un tipo con el código «%s»." % code)
            category = AbsenceCategory.objects.create(
                company=company, code=code, label=label,
                requires_note=bool(post.get("requires_note")),
                is_justified=bool(post.get("is_justified")),
                order=_int(post.get("order")) or 0, is_active=True)
            return _ok("Tipo de ausencia «%s» creado." % label,
                       category.pk)
        if what == "categories_active":
            active = post.get("active") == "1"
            changed = AbsenceCategory.objects.filter(
                company=company, pk__in=[v for v in post.getlist("selected")
                                         if v.isdigit()]).update(
                is_active=active)
            if not changed:
                return _error("Marca primero los tipos de ausencia.")
            return _ok("%d tipo(s) de ausencia %s." % (
                changed, "activados" if active else "desactivados"))
        if what in ("category_save", "category_toggle"):
            category = AbsenceCategory.objects.filter(
                pk=_int(post.get("category")), company=company).first()
            if category is None:
                return _error("Ese tipo de ausencia ya no existe.")
            if what == "category_toggle":
                category.is_active = not category.is_active
                category.save(update_fields=["is_active"])
                return _ok("«%s» %s." % (category.label, "activado"
                                         if category.is_active
                                         else "desactivado"))
            label = (post.get("label") or "").strip()
            if not label:
                return _error("El nombre es obligatorio.")
            category.label = label
            category.requires_note = bool(post.get("requires_note"))
            category.is_justified = bool(post.get("is_justified"))
            order = _int(post.get("order"))
            category.order = category.order if order is None else order
            category.save(update_fields=["label", "requires_note",
                                         "is_justified", "order"])
            return _ok("Tipo de ausencia «%s» guardado." % label)
        return _error("Acción desconocida.")


class VacationImportTemplateView(SuperuserRequiredMixin, View):
    """GET ?year=: the .xlsx template to load starting balances."""

    def get(self, request):
        from hr_calendar.balance_import import build_template

        year = _year(request.GET.get("year"))
        content = build_template(_company(request), year,
                                 datetime.date.today())
        response = HttpResponse(content, content_type=(
            "application/vnd.openxmlformats-officedocument."
            "spreadsheetml.sheet"))
        response["Content-Disposition"] = (
            'attachment; filename="saldos_vacaciones_%d.xlsx"' % year)
        return response


class VacationImportUploadView(SuperuserRequiredMixin, View):
    """
    POST `file`: load a filled template (loaded and unmatched rows).

    ---

    POST: carga una plantilla rellenada y dice cuántas filas cargó y
    cuáles no casaron, con su motivo.
    """

    def post(self, request):
        from hr_calendar.balance_import import import_template

        uploaded = request.FILES.get("file")
        if uploaded is None:
            return _error("Elige el archivo de la plantilla rellenada.")
        report = import_template(uploaded, _company(request),
                                 request.user.company_user)
        logger.info(
            "# [new_ui vacaciones] Importación de saldos %s por %s: %s "
            "cargados, %s no casados, errores=%s", report.year,
            request.user.company_user, report.loaded,
            len(report.unmatched), report.errors)
        if report.errors:
            return _error(" ".join(str(e) for e in report.errors)
                          + " No se ha cargado nada.")
        message = ("Saldos de %s: %d trabajador(es) cargados (%d datos "
                   "nuevos, %d sobrescritos)" % (
                       report.year, report.loaded, report.created_rows,
                       report.updated_rows))
        if report.unchanged:
            message += ", %d sin datos (celdas vacías)" % report.unchanged
        message += "."
        if report.unmatched:
            message += " Filas sin cargar: " + "; ".join(
                "fila %s, DNI %s: %s" % (row, dni or "—", reason)
                for row, dni, reason in report.unmatched)
        return _ok(message)
