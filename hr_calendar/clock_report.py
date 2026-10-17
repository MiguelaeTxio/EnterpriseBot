# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/hr_calendar/clock_report.py
"""
Working days built from the clock-in presses (H24, S129, roadmap point
3): what the supervisors' "Fichajes" tab and its Excel show.

Each IN opens a shift and the next OUT of the same user closes it, also
after midnight (night guards). A second IN while a shift is open leaves
the first one "without OUT"; an OUT with no open shift is "without IN";
a shift still open more than MAX_SHIFT_HOURS after its IN stays
"without OUT". A shift belongs to the day of its IN (or of its OUT when
it has no IN), in the company's local time. Nothing is guessed: a shift
without one of its two presses counts no hours, it is only flagged.

Punctuality: each IN is compared with the closest start time of the
worker's current schedule (morning, or afternoon in a split shift);
any minute after it is a late arrival. Real time, not the rounded one.

---

Jornadas construidas a partir de las pulsaciones de fichaje (H24,
S129, punto 3 de la hoja de ruta): lo que muestran la pestaña
"Fichajes" de los supervisores y su Excel.

Cada ENTRADA abre una jornada y la siguiente SALIDA del mismo usuario
la cierra, también pasada la medianoche (guardas nocturnos). Una
segunda ENTRADA con la jornada abierta deja la primera "sin salida";
una SALIDA sin jornada abierta queda "sin entrada"; una jornada que
sigue abierta más de MAX_SHIFT_HOURS tras su entrada queda "sin
salida". La jornada pertenece al día de su entrada (o de su salida si
no tiene entrada), en hora local. No se inventa nada: una jornada a la
que le falta una de sus dos pulsaciones no suma horas, solo se avisa.

Puntualidad: cada entrada se compara con la hora de entrada más
cercana del horario actual del trabajador (la de mañana o, en jornada
partida, la de tarde); un minuto después ya es llegada tarde. Con la
hora real, no con la redondeada.
"""
import datetime
from dataclasses import dataclass, field

from django.utils import timezone

from hr_calendar.models import ClockEvent

MAX_SHIFT_HOURS = 24
LATE_SEND_SECONDS = 300
NO_OUT = "Entrada sin salida"
NO_IN = "Salida sin entrada"


@dataclass
class Shift:
    """
    One working stretch: IN and OUT presses (either may be missing).
    ---
    Un tramo de trabajo: pulsación de entrada y de salida (puede faltar
    una de las dos).
    """

    clock_in: ClockEvent = None
    clock_out: ClockEvent = None
    expected_start: datetime.time = None

    @property
    def late_minutes(self):
        """
        Minutes between the scheduled start and the real IN (negative:
        early); None without IN or without schedule.
        ---
        Minutos entre la hora de entrada del horario y la entrada real
        (negativo: antes de hora); None sin entrada o sin horario.
        """
        if self.clock_in is None or self.expected_start is None:
            return None
        real = timezone.localtime(self.clock_in.pressed_at)
        real_minutes = real.hour * 60 + real.minute
        expected = self.expected_start.hour * 60 + self.expected_start.minute
        return real_minutes - expected

    @property
    def is_late(self):
        return (self.late_minutes or 0) > 0

    @property
    def day(self):
        event = self.clock_in or self.clock_out
        return timezone.localtime(event.pressed_at).date()

    @property
    def seconds(self):
        if self.clock_in is None or self.clock_out is None:
            return 0
        return int((self.clock_out.pressed_at
                    - self.clock_in.pressed_at).total_seconds())

    @property
    def issue(self):
        if self.clock_in is None:
            return NO_IN
        if self.clock_out is None:
            return NO_OUT
        return ""

    @property
    def duration_label(self):
        return format_duration(self.seconds) if not self.issue else ""


@dataclass
class PersonReport:
    """
    Shifts of one user in a date range, with totals.
    ---
    Jornadas de un usuario en un intervalo de fechas, con totales.
    """

    shifts: list = field(default_factory=list)
    events: list = field(default_factory=list)

    @property
    def total_seconds(self):
        return sum(s.seconds for s in self.shifts)

    @property
    def total_label(self):
        return format_duration(self.total_seconds)

    @property
    def issues(self):
        return [s for s in self.shifts if s.issue]

    @property
    def last_event(self):
        return self.events[-1] if self.events else None

    @property
    def timed_arrivals(self):
        """
        Shifts with an IN and a schedule to compare it with.
        ---
        Jornadas con entrada y con horario con el que compararla.
        """
        return [s for s in self.shifts if s.late_minutes is not None]

    @property
    def late_arrivals(self):
        return [s for s in self.timed_arrivals if s.is_late]

    @property
    def punctuality_label(self):
        timed = self.timed_arrivals
        return "%d de %d" % (len(self.late_arrivals), len(timed)) if timed else ""

    @property
    def late_events(self):
        return [e for e in self.events
                if e.delay_seconds > LATE_SEND_SECONDS]


def format_duration(seconds):
    """
    Seconds as H:MM.
    ---
    Segundos como H:MM (horas sin límite, p. ej. 163:05).
    """
    minutes = max(int(seconds), 0) // 60
    return "%d:%02d" % (minutes // 60, minutes % 60)


def build_shifts(events):
    """
    Pairs the presses of ONE user, ordered by press time, into shifts.
    ---
    Empareja en jornadas las pulsaciones de UN usuario, ordenadas por
    hora de pulsación.
    """
    shifts, open_shift = [], None
    limit = datetime.timedelta(hours=MAX_SHIFT_HOURS)
    for event in events:
        if open_shift is not None and (
            event.pressed_at - open_shift.clock_in.pressed_at > limit
        ):
            shifts.append(open_shift)
            open_shift = None
        if event.kind == ClockEvent.Kind.IN:
            if open_shift is not None:
                shifts.append(open_shift)
            open_shift = Shift(clock_in=event)
        elif open_shift is not None:
            open_shift.clock_out = event
            shifts.append(open_shift)
            open_shift = None
        else:
            shifts.append(Shift(clock_out=event))
    if open_shift is not None:
        shifts.append(open_shift)
    return shifts


def schedule_starts(schedule):
    """
    The start times of a WorkdaySchedule: morning, and afternoon in a
    split shift.
    ---
    Las horas de entrada de un horario: la de mañana y, en jornada
    partida, la de tarde.
    """
    if schedule is None:
        return []
    starts = [schedule.start_time_morning]
    if not schedule.is_intensive and schedule.start_time_afternoon:
        starts.append(schedule.start_time_afternoon)
    return [t for t in starts if t is not None]


def expected_start(starts, pressed_at):
    """
    Of the schedule's start times, the one closest to the IN press
    (the afternoon IN of a split shift is compared with the afternoon
    start, not with the morning one).
    ---
    De las horas de entrada del horario, la más cercana a la pulsación
    de entrada (la entrada de tarde se compara con la hora de tarde).
    """
    if not starts:
        return None
    real = timezone.localtime(pressed_at)
    real_minutes = real.hour * 60 + real.minute
    return min(
        starts, key=lambda t: abs(t.hour * 60 + t.minute - real_minutes),
    )


def _schedule_starts_by_user(company, company_user_ids):
    from ivr_config.models import CompanyUser
    from panel.views_operator import _resolve_operator_schedule

    result = {}
    for company_user in CompanyUser.objects.filter(pk__in=company_user_ids):
        result[company_user.pk] = schedule_starts(
            _resolve_operator_schedule(company_user, company),
        )
    return result


def _range_bounds(date_from, date_to):
    tz = timezone.get_current_timezone()
    start = timezone.make_aware(
        datetime.datetime.combine(date_from, datetime.time.min), tz,
    )
    end = timezone.make_aware(
        datetime.datetime.combine(
            date_to + datetime.timedelta(days=1), datetime.time.min,
        ), tz,
    )
    return start, end


def reports_by_user(company, company_user_ids, date_from, date_to):
    """
    {company_user_id: PersonReport} for the shifts whose day falls in
    [date_from, date_to]. Presses up to MAX_SHIFT_HOURS before and
    after the range are read too, so a shift crossing the edge closes
    with its real pair.
    ---
    {company_user_id: PersonReport} con las jornadas cuyo día cae en
    [date_from, date_to]. Se leen también las pulsaciones hasta
    MAX_SHIFT_HOURS antes y después del intervalo, para que una jornada
    que cruza el borde se cierre con su pareja real.
    """
    start, end = _range_bounds(date_from, date_to)
    margin = datetime.timedelta(hours=MAX_SHIFT_HOURS)
    events = ClockEvent.objects.filter(
        company=company,
        company_user_id__in=list(company_user_ids),
        pressed_at__gte=start - margin,
        pressed_at__lt=end + margin,
    ).order_by("company_user_id", "pressed_at", "pk")
    grouped = {}
    for event in events:
        grouped.setdefault(event.company_user_id, []).append(event)
    starts_by_user = _schedule_starts_by_user(company, list(grouped))
    reports = {}
    for user_id, user_events in grouped.items():
        report = PersonReport()
        report.shifts = [
            s for s in build_shifts(user_events)
            if date_from <= s.day <= date_to
        ]
        starts = starts_by_user.get(user_id, [])
        for shift in report.shifts:
            if shift.clock_in is not None:
                shift.expected_start = expected_start(
                    starts, shift.clock_in.pressed_at,
                )
        report.events = [
            e for e in user_events if start <= e.pressed_at < end
        ]
        reports[user_id] = report
    return reports
