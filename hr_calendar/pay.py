# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/hr_calendar/pay.py
"""
Hours to pay per worker and period (S163, "Horas y pagos").

---

Horas a pagar de cada trabajador en un periodo (S163, 23/11). Miguel
Ángel: el supervisor decide qué se paga (presencia, desplazamiento,
trabajo efectivo o cualquier otro tipo) y a qué precio por trabajador,
con precio aparte en festivo y domingo; las horas salen de los partes
digitales para quien los hace y de los fichajes para el resto; la bolsa
se gestiona aquí y un periodo liquidado queda bloqueado. "Tenemos que
dejar que el supervisor pueda configurar todo."

Clases de hora (claves):
- "jornada": lo que cuenta como jornada del fichaje (Shift.seconds:
  entrada a salida redondeadas, sin la comida ni los tipos que no
  cuentan).
- "tipo_<pk>": cada tipo de fichaje que no cuenta como jornada
  (desplazamiento, presencia, fuerza mayor...), con sus tramos.
- "parte": las horas del parte digital del día (suma de delta_hours).

Qué se paga de cada clase (PaySettings.modes): "none" (nada), "all"
(todas sus horas) u "over" (solo lo que pasa de la jornada del día: 8 h
en el fichaje, la jornada de los partes en el parte). En los días que no
son laborables para él (fines de semana, festivos de su base, sus
vacaciones y ausencias) todo lo que se paga va a precio de festivo. Las
horas extra ("over") de los días laborables tienen un tope al mes
(opcional): lo que pasa va a la bolsa, no se paga. Los días ya
liquidados no se vuelven a pagar.
"""
import datetime
from decimal import Decimal

from django.db.models import Sum

from hr_calendar.clock_extras import DAILY_SECONDS
from hr_calendar.models import (
    ClockType, PayLine, PayPeriod, PaySettings, PayWorker,
)

JORNADA = "jornada"
PARTE = "parte"
NONE, ALL, OVER = "none", "all", "over"
MODE_LABELS = (
    (NONE, "No se paga"),
    (ALL, "Todas sus horas"),
    (OVER, "Solo lo que pasa de la jornada (horas extra)"),
)
DEFAULT_MODES = {JORNADA: OVER, PARTE: OVER}
ZERO = Decimal("0")
HOUR = Decimal("3600")


class PayError(ValueError):
    """Un error para el supervisor."""


def settings_of(company):
    """Los ajustes de la empresa (se crean con lo de siempre)."""
    settings, _created = PaySettings.objects.get_or_create(company=company)
    return settings


def hour_classes(company):
    """
    [(key, label)] of the hour classes of the company.

    ---

    Las clases de hora: la jornada, los tipos de fichaje que no cuentan
    como jornada y las horas de parte.
    """
    classes = [(JORNADA, "Jornada (trabajo efectivo)")]
    for clock_type in ClockType.objects.filter(company=company).order_by(
            "order", "name"):
        if (not clock_type.counts_as_work
                or clock_type.role in ClockType.BAG_ROLES):
            classes.append(("tipo_%d" % clock_type.pk, clock_type.name))
    classes.append((PARTE, "Horas de parte"))
    return classes


def mode_of(settings, key):
    return (settings.modes or {}).get(key, DEFAULT_MODES.get(key, NONE))


def _type_keys(company):
    return {
        clock_type.pk: "tipo_%d" % clock_type.pk
        for clock_type in ClockType.objects.filter(company=company)
        if (not clock_type.counts_as_work
            or clock_type.role in ClockType.BAG_ROLES)
    }


def _parte_seconds(company, user_ids, date_from, date_to):
    """{user id: {day: seconds}} de las líneas de parte."""
    from work_order_processor.models import WorkOrderEntryLine

    result = {}
    rows = WorkOrderEntryLine.objects.filter(
        entry__work_order__company=company,
        entry__work_order__uploaded_by_id__in=list(user_ids),
        entry__work_date__gte=date_from, entry__work_date__lte=date_to,
    ).values("entry__work_order__uploaded_by_id", "entry__work_date").annotate(
        hours=Sum("delta_hours"))
    for row in rows:
        if not row["hours"]:
            continue
        result.setdefault(row["entry__work_order__uploaded_by_id"], {})[
            row["entry__work_date"]] = int(Decimal(row["hours"]) * HOUR)
    return result


def _liquidated_days(company, user_ids, date_from, date_to):
    """{user id: [(desde, hasta, periodo)]} ya liquidados que se cruzan."""
    result = {}
    for line in PayLine.objects.filter(
            period__company=company, company_user_id__in=list(user_ids),
            period__date_from__lte=date_to, period__date_to__gte=date_from,
    ).select_related("period"):
        spans = result.setdefault(line.company_user_id, [])
        span = (line.period.date_from, line.period.date_to, line.period)
        if span not in spans:
            spans.append(span)
    return result


def _daterange(start, end):
    day = start
    while day <= end:
        yield day
        day += datetime.timedelta(days=1)


class Result:
    """Lo de un trabajador en el periodo."""

    def __init__(self, company_user, source):
        self.company_user = company_user
        self.source = source
        self.days = []
        # {key: [segundos normales, segundos festivo]}
        self.paid = {}
        self.to_bag = 0
        self.liquidated = []
        self.prices = {}

    @property
    def source_label(self):
        return dict(PayWorker.Source.choices).get(self.source, "")

    def add(self, key, seconds, holiday):
        slot = self.paid.setdefault(key, [0, 0])
        slot[1 if holiday else 0] += seconds

    def hours(self, key, holiday=False):
        return (Decimal(self.paid.get(key, [0, 0])[1 if holiday else 0])
                / HOUR).quantize(Decimal("0.01"))

    @property
    def normal_hours(self):
        return sum((self.hours(k) for k in self.paid), ZERO)

    @property
    def holiday_hours(self):
        return sum((self.hours(k, True) for k in self.paid), ZERO)

    def price(self, key, holiday=False):
        pair = self.prices.get(key) or [0, 0]
        try:
            return Decimal(str(pair[1 if holiday else 0] or 0))
        except (ArithmeticError, ValueError, IndexError):
            return ZERO

    def amount(self, key):
        return (self.hours(key) * self.price(key)
                + self.hours(key, True) * self.price(key, True)).quantize(
            Decimal("0.01"))

    @property
    def total(self):
        return sum((self.amount(k) for k in self.paid), ZERO)

    @property
    def bag_hours(self):
        return (Decimal(self.to_bag) / HOUR).quantize(Decimal("0.01"))


def compute(company, company_users, date_from, date_to):
    """
    {company_user_id: Result} of the hours to pay in the period.

    ---

    Las horas a pagar de cada trabajador en el periodo, día a día, con
    lo que se paga de cada clase (normal y festivo), lo que va a la
    bolsa por el tope mensual y los días que ya estaban liquidados (que
    no se cuentan).
    """
    from hr_calendar.clock_report import (
        _required_days_by_user, reports_by_user,
    )

    settings = settings_of(company)
    users = [cu for cu in company_users if cu is not None]
    ids = [cu.pk for cu in users]
    if not ids:
        return {}
    reports = reports_by_user(company, ids, date_from, date_to)
    required = _required_days_by_user(company, ids, date_from, date_to)
    partes = _parte_seconds(company, ids, date_from, date_to)
    liquidated = _liquidated_days(company, ids, date_from, date_to)
    workers = {w.company_user_id: w for w in PayWorker.objects.filter(
        company_user_id__in=ids)}
    type_keys = _type_keys(company)
    cap = (settings.monthly_cap_minutes * 60
           if settings.monthly_cap_minutes is not None else None)
    parte_day = settings.parte_day_minutes * 60
    out = {}
    for cu in users:
        worker = workers.get(cu.pk)
        source = worker.source if worker else PayWorker.Source.AUTO
        result = Result(cu, source)
        result.prices = worker.prices if worker else {}
        result.liquidated = liquidated.get(cu.pk, [])
        clock = {}
        report = reports.get(cu.pk)
        for shift in (report.shifts if report else []):
            if shift.clock_in is None or shift.clock_out is None:
                continue
            day_keys = clock.setdefault(shift.day, {})
            day_keys[JORNADA] = day_keys.get(JORNADA, 0) + shift.seconds
            for clock_type, start, end in shift.segments:
                key = type_keys.get(getattr(clock_type, "pk", None))
                if key:
                    day_keys[key] = day_keys.get(key, 0) + max(
                        int((end - start).total_seconds()), 0)
        # Laborable para él: de lunes a viernes, sin festivos de su base
        # ni sus vacaciones, bajas o ausencias (la regla del convenio,
        # sin el "desde que ficha", que aquí no cuenta).
        working = required.get(cu.pk) or (lambda day, start=None:
                                          day.weekday() < 5)
        month_extra = {}
        for day in _daterange(date_from, date_to):
            if any(a <= day <= b for a, b, _p in result.liquidated):
                continue
            parte_secs = partes.get(cu.pk, {}).get(day, 0)
            use_parte = (source == PayWorker.Source.PARTE
                         or (source == PayWorker.Source.AUTO
                             and parte_secs))
            if use_parte:
                by_key = {PARTE: parte_secs} if parte_secs else {}
                day_required = parte_day
            else:
                by_key = dict(clock.get(day, {}))
                day_required = DAILY_SECONDS
            if not by_key:
                continue
            holiday = not working(day, start=day)
            row = {"day": day, "holiday": holiday, "by_key": by_key,
                   "source": PARTE if use_parte else "fichaje",
                   "paid": {}, "to_bag": 0}
            if holiday:
                for key, seconds in by_key.items():
                    if mode_of(settings, key) != NONE:
                        row["paid"][key] = seconds
                        result.add(key, seconds, True)
            else:
                over = {k: s for k, s in by_key.items()
                        if mode_of(settings, k) == OVER}
                for key, seconds in by_key.items():
                    if mode_of(settings, key) == ALL:
                        row["paid"][key] = seconds
                        result.add(key, seconds, False)
                excess = sum(over.values()) - day_required
                if excess > 0 and over:
                    month = day.replace(day=1)
                    used = month_extra.get(month, 0)
                    payable = excess
                    if cap is not None:
                        payable = max(min(excess, cap - used), 0)
                    month_extra[month] = used + payable
                    row["to_bag"] = excess - payable
                    result.to_bag += excess - payable
                    total_over = sum(over.values())
                    for key, seconds in over.items():
                        share = int(round(payable * seconds / total_over))
                        if share:
                            row["paid"][key] = row["paid"].get(key, 0) + share
                            result.add(key, share, False)
            result.days.append(row)
        out[cu.pk] = result
    return out


def save_settings(company, modes, cap_minutes, parte_day_minutes):
    settings = settings_of(company)
    settings.modes = {key: value for key, value in modes.items()
                      if value in (NONE, ALL, OVER)}
    settings.monthly_cap_minutes = cap_minutes
    if parte_day_minutes:
        settings.parte_day_minutes = parte_day_minutes
    settings.save()
    return settings


def set_prices(company_users, prices):
    """Pone los precios (solo las clases que vengan) a cada trabajador."""
    for cu in company_users:
        worker, _created = PayWorker.objects.get_or_create(company_user=cu)
        current = dict(worker.prices or {})
        current.update(prices)
        worker.prices = current
        worker.save(update_fields=["prices", "updated_at"])


def set_source(company_users, source):
    if source not in PayWorker.Source.values:
        raise PayError("Elige de dónde salen sus horas.")
    for cu in company_users:
        worker, _created = PayWorker.objects.get_or_create(company_user=cu)
        worker.source = source
        worker.save(update_fields=["source", "updated_at"])


def liquidate(company, company_users, date_from, date_to, by):
    """
    Close the period for these workers: their lines are frozen.

    ---

    Liquida el periodo de estos trabajadores: guarda sus líneas (horas,
    precios e importe de cada clase) y desde entonces esos días no se
    vuelven a calcular ni a pagar. No deja liquidar si alguno ya tiene
    días liquidados en esas fechas.
    """
    if date_from is None or date_to is None or date_from > date_to:
        raise PayError("Indica bien las fechas del periodo.")
    users = [cu for cu in company_users if cu is not None]
    if not users:
        raise PayError("Marca a los trabajadores (con cuenta del panel).")
    clash = _liquidated_days(company, [cu.pk for cu in users], date_from,
                             date_to)
    if clash:
        raise PayError("Hay trabajadores con días ya liquidados en esas "
                       "fechas (%d): ajusta el periodo." % len(clash))
    results = compute(company, users, date_from, date_to)
    labels = dict(hour_classes(company))
    period = PayPeriod.objects.create(company=company, date_from=date_from,
                                      date_to=date_to, closed_by=by)
    count = 0
    for cu in users:
        result = results.get(cu.pk)
        if result is None or not result.paid:
            # Sin nada que pagar: una línea a cero, para que sus días
            # queden también liquidados.
            PayLine.objects.create(period=period, company_user=cu,
                                   key="nada", label="Nada que pagar")
            count += 1
            continue
        for key in result.paid:
            PayLine.objects.create(
                period=period, company_user=cu, key=key,
                label=labels.get(key, key), hours=result.hours(key),
                holiday_hours=result.hours(key, True),
                price=result.price(key),
                holiday_price=result.price(key, True),
                amount=result.amount(key))
            count += 1
    return period, count
