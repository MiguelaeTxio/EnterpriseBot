# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/hr_calendar/balance.py
"""
Vacation balance of each worker (H24, S129): days the worker is
entitled to in a year, days carried over from the previous year,
days taken and days pending.

Rules agreed by Miguel Ángel with Carolina (HR), annex V24 section
7.3, all of them implemented here:

- Days per year are a company setting per section (VacationRule),
  natural or working days; a company-wide rule (section empty) covers
  workers without a section. Changing section mid-year splits the year
  into stretches, each with its own rule.
- Calendar year. Workers who join or leave mid-year get the pro rata
  share: days per year x days employed in the year / days of the year,
  rounded up to the next whole day.
- Natural days count every day; working days count Monday to Friday
  except public holidays (the rule's holiday base, else the base of the
  worker's panel account, else weekends only).
- Days left over pass to the next year if the section's rule says so,
  flagged as previous-year days; they are spent first and, if the rule
  sets a deadline and it passes, the rest are lost and shown as lost.
- Days of medical leave inside a vacation period are not spent
  (art. 38.3 of the Workers' Statute, MedicalLeavePeriod).
- Manual adjustments by a supervisor, always with a reason.
- A negative balance is allowed and flagged.
- The starting balance (days already taken in the year and leftovers
  of the previous year) comes from Carolina's spreadsheet
  (VacationBalanceAdjustment OPENING_*).

The carry-over is only computed from the first year the system has
data for the worker (the year of their first starting-balance row, or
else the year of the company's first rule): earlier years were never
tracked here, so computing them would invent leftovers.

---

Saldo de vacaciones de cada trabajador (H24, S129): días que le
corresponden en un año, días que arrastra del año anterior, días
disfrutados y días pendientes.

Reglas acordadas por Miguel Ángel con Carolina (RRHH), anexo V24
sección 7.3, todas implementadas aquí:

- Los días al año los fija la empresa por sección (VacationRule),
  naturales o laborables; una regla general de la empresa (sin
  sección) cubre a quien aún no tiene sección. Un cambio de sección a
  mitad de año parte el año en tramos, cada uno con su regla.
- Año natural. Quien entra o sale a mitad de año tiene la parte
  proporcional: días al año x días de alta en el año / días del año,
  redondeado al día entero hacia arriba.
- Naturales cuenta todos los días; laborables, de lunes a viernes
  salvo festivos (calendario de la regla; si no, el de la base de la
  cuenta de panel del trabajador; si no, solo fines de semana).
- Los sobrantes pasan al año siguiente si la regla de la sección lo
  dice, anotados como del año anterior; se gastan primero y, si la
  regla fija un plazo y vence, el resto se pierde y se muestra como
  perdido.
- Los días de baja médica dentro de unas vacaciones no se gastan
  (art. 38.3 ET, MedicalLeavePeriod).
- Ajustes manuales del supervisor, siempre con motivo.
- El saldo negativo se permite y se avisa.
- El saldo de partida (disfrutados del año y sobrantes del anterior)
  viene de la hoja de cálculo de Carolina
  (VacationBalanceAdjustment OPENING_*).

El arrastre solo se calcula desde el primer año del que el sistema
tiene datos del trabajador (el año de su primera fila de saldo de
partida o, si no tiene, el de la primera regla de la empresa): los
años anteriores nunca se registraron aquí y calcularlos inventaría
sobrantes.
"""
import calendar
import datetime
import logging
import math
from dataclasses import dataclass, field
from decimal import Decimal

from django.db import transaction

from hr_calendar.models import (
    MedicalLeavePeriod,
    PersonSectionAssignment,
    VacationBalanceAdjustment,
    VacationPeriod,
    VacationRule,
)

logger = logging.getLogger(__name__)

ZERO = Decimal("0")
ONE = Decimal("1")
NO_SECTION_LABEL = "Sin sección (regla general)"


def round_up_day(value):
    """
    Round a positive amount of days up to the next whole day.
    ---
    Redondea una cantidad de días al día entero hacia arriba (los
    valores negativos o cero se dejan como están). H24 (S129): la
    empresa no da medios días (Miguel Ángel), así que la parte
    proporcional tampoco deja medios días.
    """
    if value <= 0:
        return value
    return Decimal(math.ceil(value))


def _year_bounds(year):
    """
    First and last day of a calendar year.
    ---
    Primer y último día de un año natural.
    """
    return datetime.date(year, 1, 1), datetime.date(year, 12, 31)


def _days_in_year(year):
    """
    365 or 366.
    ---
    365 o 366.
    """
    return 366 if calendar.isleap(year) else 365


def _daterange(start, end):
    """
    Every date from start to end, both inclusive.
    ---
    Cada fecha de start a end, ambas inclusive.
    """
    day = start
    while day <= end:
        yield day
        day += datetime.timedelta(days=1)


def carry_over_deadline(rule, year):
    """
    Date (in `year`) until which leftovers generated under `rule` the
    year before can be spent, or None when the rule sets no deadline.
    ---
    Fecha (en `year`) hasta la que se pueden gastar los sobrantes que
    generó `rule` el año anterior, o None si la regla no fija plazo. Un
    29 de febrero en año no bisiesto pasa al 28.
    """
    if rule is None:
        return None
    month = rule.carry_over_deadline_month
    day = rule.carry_over_deadline_day
    if not month or not day:
        return None
    last = calendar.monthrange(year, month)[1]
    return datetime.date(year, month, min(day, last))


class RuleBook:
    """
    The company's vacation rules, loaded once, answering which rule is
    in force for a section on a given day.
    ---
    Las reglas de vacaciones de la empresa, cargadas una vez, que
    responden qué regla rige para una sección un día dado: la de la
    sección con la fecha más reciente no posterior a ese día; si la
    sección no tiene ninguna vigente (o no hay sección), la general.
    """

    def __init__(self, company):
        self.by_section = {}
        self.general = []
        rules = VacationRule.objects.filter(company=company).select_related(
            "section", "holiday_base",
        ).order_by("valid_from")
        for rule in rules:
            if rule.section_id is None:
                self.general.append(rule)
            else:
                self.by_section.setdefault(rule.section_id, []).append(rule)
        all_rules = self.general + [
            r for rules in self.by_section.values() for r in rules
        ]
        self.first_year = (
            min(r.valid_from.year for r in all_rules) if all_rules else None
        )

    @staticmethod
    def _latest(rules, day):
        found = None
        for rule in rules:
            if rule.valid_from <= day:
                found = rule
            else:
                break
        return found

    def rule_on(self, section_id, day):
        """
        Rule in force for `section_id` (None = no section) on `day`.
        ---
        Regla vigente para `section_id` (None = sin sección) el día
        `day`, o None si no hay ninguna.
        """
        if section_id is not None:
            rule = self._latest(self.by_section.get(section_id, []), day)
            if rule is not None:
                return rule
        return self._latest(self.general, day)


@dataclass
class Segment:
    """
    A stretch of the year with the same section and rule.
    ---
    Un tramo del año con la misma sección y la misma regla.
    """
    date_from: datetime.date
    date_to: datetime.date
    section_name: str
    rule: object
    days_employed: int = 0
    entitled: Decimal = ZERO


@dataclass
class PeriodUse:
    """
    Days a vacation period spends in the year.
    ---
    Días que gasta un periodo de vacaciones dentro del año, y cuántos
    no se gastan por coincidir con una baja médica.
    """
    period: object
    days: Decimal = ZERO
    medical_days: Decimal = ZERO


@dataclass
class VacationBalance:
    """
    Balance of one worker in one year (all amounts in days).
    ---
    Saldo de un trabajador en un año (todo en días):
    entitled = los que corresponden (proporcional, redondeado);
    manual = suma de ajustes manuales; carryover = del año anterior;
    carryover_lost = sobrantes perdidos por plazo vencido;
    taken = disfrutados (periodos + saldo de partida);
    pending = entitled + manual + carryover - carryover_lost - taken.
    """
    person: object
    year: int
    entitled: Decimal = ZERO
    manual: Decimal = ZERO
    carryover: Decimal = ZERO
    carryover_deadline: object = None
    carryover_lost: Decimal = ZERO
    taken_periods: Decimal = ZERO
    taken_opening: Decimal = ZERO
    taken_from_carryover: Decimal = ZERO
    carryover_from_import: bool = False
    segments: list = field(default_factory=list)
    period_uses: list = field(default_factory=list)
    adjustments: list = field(default_factory=list)
    warnings: list = field(default_factory=list)

    @property
    def taken(self):
        return self.taken_periods + self.taken_opening

    @property
    def available(self):
        return self.entitled + self.manual + self.carryover

    @property
    def pending(self):
        return self.available - self.carryover_lost - self.taken

    @property
    def is_negative(self):
        return self.pending < 0

    @property
    def current_section_name(self):
        return self.segments[-1].section_name if self.segments else ""


class BalanceCalculator:
    """
    Computes vacation balances for a set of workers, loading every
    related row once (rules, sections, periods, medical leaves,
    adjustments) so the balance list costs a handful of queries.
    ---
    Calcula saldos de vacaciones para un conjunto de trabajadores,
    cargando una sola vez todo lo relacionado (reglas, secciones,
    periodos, bajas médicas, ajustes): el listado de saldos cuesta unas
    pocas consultas, no unas pocas por trabajador.
    """

    def __init__(self, company, people, as_of=None):
        self.company = company
        self.as_of = as_of or datetime.date.today()
        self.rules = RuleBook(company)
        self.people = {p.pk: p for p in people}
        ids = list(self.people)
        self.assignments = {}
        for row in PersonSectionAssignment.objects.filter(
            person_id__in=ids,
        ).select_related("section").order_by("valid_from"):
            self.assignments.setdefault(row.person_id, []).append(row)
        self.periods = {}
        for row in VacationPeriod.objects.filter(
            person_id__in=ids,
        ).order_by("date_start"):
            self.periods.setdefault(row.person_id, []).append(row)
        self.leaves = {}
        for row in MedicalLeavePeriod.objects.filter(person_id__in=ids):
            self.leaves.setdefault(row.person_id, []).append(row)
        self.adjustments = {}
        for row in VacationBalanceAdjustment.objects.filter(
            person_id__in=ids, company=company,
        ).select_related("created_by__user").order_by("year", "created_at"):
            self.adjustments.setdefault(row.person_id, []).append(row)
        self._cache = {}

    # --------------------------------------------------------------
    # Lookups / Consultas
    # --------------------------------------------------------------
    def _assignment_on(self, person_id, day):
        found = None
        for row in self.assignments.get(person_id, []):
            if row.valid_from <= day:
                found = row
            else:
                break
        return found

    def _rule_for(self, person_id, day):
        assignment = self._assignment_on(person_id, day)
        section_id = assignment.section_id if assignment else None
        return self.rules.rule_on(section_id, day), assignment

    def _in_medical_leave(self, person_id, day):
        for leave in self.leaves.get(person_id, []):
            end = leave.date_end or datetime.date.max
            if leave.date_start <= day <= end:
                return True
        return False

    def _holiday_base(self, person, rule):
        if rule is not None and rule.holiday_base_id:
            return rule.holiday_base
        company_user = getattr(person, "company_user", None)
        if company_user is not None and company_user.base_id:
            return company_user.base
        return None

    def _first_tracked_year(self, person_id):
        years = [
            a.year for a in self.adjustments.get(person_id, [])
            if a.kind != VacationBalanceAdjustment.Kind.MANUAL
        ]
        if years:
            return min(years)
        return self.rules.first_year

    def _employment(self, person, year):
        start, end = _year_bounds(year)
        if person.hire_date and person.hire_date > start:
            start = person.hire_date
        if person.termination_date and person.termination_date < end:
            end = person.termination_date
        if start > end:
            return None
        return start, end

    # --------------------------------------------------------------
    # Balance / Saldo
    # --------------------------------------------------------------
    def balance(self, person, year):
        """
        VacationBalance of `person` in `year` (cached per call).
        ---
        VacationBalance de `person` en `year` (memorizado durante la
        vida del calculador; el arrastre llama al año anterior).
        """
        key = (person.pk, year)
        if key not in self._cache:
            self._cache[key] = self._compute(person, year)
        return self._cache[key]

    def _compute(self, person, year):
        from budgets.services import _is_holiday

        result = VacationBalance(person=person, year=year)
        year_start, year_end = _year_bounds(year)

        # 1. Días que corresponden, tramo a tramo.
        employment = self._employment(person, year)
        if person.hire_date is None:
            result.warnings.append(
                "Sin fecha de alta en la empresa: se cuenta desde el 1 "
                "de enero."
            )
        without_rule = 0
        without_section = False
        if employment is not None:
            per_day_total = ZERO
            segment = None
            for day in _daterange(*employment):
                rule, assignment = self._rule_for(person.pk, day)
                if assignment is None:
                    without_section = True
                section_name = (
                    assignment.section.name if assignment else
                    NO_SECTION_LABEL
                )
                if (
                    segment is None
                    or segment.rule is not rule
                    or segment.section_name != section_name
                ):
                    segment = Segment(
                        date_from=day, date_to=day,
                        section_name=section_name, rule=rule,
                    )
                    result.segments.append(segment)
                segment.date_to = day
                segment.days_employed += 1
                if rule is None:
                    without_rule += 1
                    continue
                share = rule.days_per_year / _days_in_year(year)
                segment.entitled += share
                per_day_total += share
            result.entitled = round_up_day(per_day_total)
            for seg in result.segments:
                seg.entitled = seg.entitled.quantize(Decimal("0.01"))
        if without_rule:
            result.warnings.append(
                f"{without_rule} día(s) de alta sin regla de vacaciones "
                "aplicable: no generan días."
            )
        if without_section:
            result.warnings.append(
                "Sin sección asignada en todo o parte del año: se aplica la "
                "regla general de la empresa."
            )

        # 2. Ajustes del año.
        opening_carryover = None
        for adj in self.adjustments.get(person.pk, []):
            if adj.year != year:
                continue
            result.adjustments.append(adj)
            if adj.kind == VacationBalanceAdjustment.Kind.MANUAL:
                result.manual += adj.days
            elif adj.kind == VacationBalanceAdjustment.Kind.OPENING_TAKEN:
                result.taken_opening += adj.days
            else:
                opening_carryover = adj.days

        # 3. Arrastre del año anterior.
        prev_rule, _assignment = self._rule_for(
            person.pk, datetime.date(year - 1, 12, 31),
        )
        if opening_carryover is not None:
            result.carryover = opening_carryover
            result.carryover_from_import = True
        else:
            first_year = self._first_tracked_year(person.pk)
            if first_year is not None and year - 1 >= first_year:
                previous = self.balance(person, year - 1)
                pending = previous.pending
                if pending < 0:
                    # Un saldo negativo se arrastra siempre (son días ya
                    # disfrutados de más), haya o no arrastre de
                    # sobrantes en la regla.
                    result.carryover = pending
                elif pending > 0 and prev_rule and prev_rule.carry_over:
                    result.carryover = pending
        if result.carryover > 0:
            result.carryover_deadline = carry_over_deadline(prev_rule, year)

        # 4. Días disfrutados por los periodos registrados.
        used_by_day = []
        if result.taken_opening:
            used_by_day.append((year_start, result.taken_opening))
        for period in self.periods.get(person.pk, []):
            if period.date_end < year_start or period.date_start > year_end:
                continue
            use = PeriodUse(period=period)
            first = max(period.date_start, year_start)
            last = min(period.date_end, year_end)
            for day in _daterange(first, last):
                rule, _assignment = self._rule_for(person.pk, day)
                if (
                    rule is not None
                    and rule.day_kind == VacationRule.DayKind.WORKING
                ):
                    if day.weekday() >= 5:
                        continue
                    if _is_holiday(day, self._holiday_base(person, rule)):
                        continue
                weight = ONE
                if self._in_medical_leave(person.pk, day):
                    use.medical_days += weight
                    continue
                use.days += weight
                used_by_day.append((day, weight))
            result.period_uses.append(use)
            result.taken_periods += use.days

        # 5. Los del año anterior se gastan primero, hasta su plazo.
        carry_left = max(result.carryover, ZERO)
        deadline = result.carryover_deadline
        for day, amount in sorted(used_by_day, key=lambda item: item[0]):
            if carry_left <= 0:
                break
            if deadline is not None and day > deadline:
                break
            spent = min(carry_left, amount)
            carry_left -= spent
            result.taken_from_carryover += spent
        if (
            carry_left > 0 and deadline is not None
            and min(self.as_of, year_end) > deadline
        ):
            result.carryover_lost = carry_left
        if result.is_negative:
            result.warnings.append("Saldo negativo: ha disfrutado más "
                                   "días de los que le corresponden.")
        return result


# ------------------------------------------------------------------
# Escritura: secciones, ajustes, reglas
# ------------------------------------------------------------------
def assign_section(people, section, valid_from, created_by):
    """
    Assign `section` to every worker of `people` from `valid_from` on.
    ---
    Asigna `section` a cada trabajador de `people` desde `valid_from`:
    si ya tenía una asignación con esa misma fecha, se cambia su
    sección; si no, se añade una nueva (el historial anterior se
    conserva). Devuelve cuántas filas se crearon y cuántas se
    cambiaron.
    """
    created = updated = 0
    with transaction.atomic():
        for person in people:
            manager = PersonSectionAssignment.objects
            _row, was_created = manager.update_or_create(
                person=person, valid_from=valid_from,
                defaults={"section": section, "created_by": created_by},
            )
            if was_created:
                created += 1
            else:
                updated += 1
    return created, updated


def add_manual_adjustment(person, company, year, days, reason, created_by):
    """
    Record a signed manual adjustment; the reason is mandatory.
    ---
    Registra un ajuste manual con signo; el motivo es obligatorio
    (ValueError si falta o si los días son cero).
    """
    reason = (reason or "").strip()
    if not reason:
        raise ValueError("El motivo del ajuste es obligatorio.")
    if days == 0:
        raise ValueError("El ajuste no puede ser de cero días.")
    return VacationBalanceAdjustment.objects.create(
        person=person, company=company, year=year,
        kind=VacationBalanceAdjustment.Kind.MANUAL,
        days=days, reason=reason, created_by=created_by,
    )


def set_opening_balance(person, company, year, kind, days, created_by,
                        reason):
    """
    Create or overwrite the starting-balance row of a worker.
    ---
    Crea o sobrescribe la fila de saldo de partida (OPENING_TAKEN u
    OPENING_CARRYOVER) de un trabajador para un año: una sola por
    trabajador, año y tipo (sin índice parcial en MySQL, se garantiza
    aquí). Devuelve True si la creó.
    """
    with transaction.atomic():
        rows = list(VacationBalanceAdjustment.objects.select_for_update()
                    .filter(person=person, company=company, year=year,
                            kind=kind).order_by("pk"))
        if rows:
            row = rows[0]
            row.days = days
            row.reason = reason
            row.created_by = created_by
            row.save(update_fields=["days", "reason", "created_by"])
            for extra in rows[1:]:
                extra.delete()
            return False
        VacationBalanceAdjustment.objects.create(
            person=person, company=company, year=year, kind=kind,
            days=days, reason=reason, created_by=created_by,
        )
        return True


def validate_rule(company, section, valid_from, days_per_year, day_kind,
                  deadline_month, deadline_day):
    """
    Return a list of user-facing errors for a new rule (empty = ok).
    ---
    Devuelve los errores (en castellano) de una regla nueva; lista
    vacía si es válida. La unicidad sección+fecha de la regla general
    (sección vacía) no la puede garantizar MySQL, se comprueba aquí.
    """
    errors = []
    if valid_from is None:
        errors.append("Indica desde qué fecha rige la regla.")
    if days_per_year is None or days_per_year <= 0:
        errors.append("Los días al año deben ser un número mayor que 0.")
    elif days_per_year > 365:
        errors.append("Los días al año no pueden pasar de 365.")
    if day_kind not in VacationRule.DayKind.values:
        errors.append("Elige si los días son naturales o laborables.")
    if bool(deadline_month) != bool(deadline_day):
        errors.append("El plazo de los sobrantes necesita día y mes, o "
                      "ninguno de los dos.")
    elif deadline_month:
        if not 1 <= deadline_month <= 12:
            errors.append("El mes del plazo debe estar entre 1 y 12.")
        elif not 1 <= deadline_day <= calendar.monthrange(
                2024, deadline_month)[1]:
            errors.append("El día del plazo no existe en ese mes.")
    if valid_from is not None and VacationRule.objects.filter(
        company=company, section=section, valid_from=valid_from,
    ).exists():
        errors.append("Ya hay una regla para esa sección con esa misma "
                      "fecha. Bórrala antes de crear otra.")
    return errors
