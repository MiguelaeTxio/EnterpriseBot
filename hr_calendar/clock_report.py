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
any minute after it is a late arrival. Each OUT, likewise, with the
closest end time: any minute before it is an early departure. Real
time, not the rounded one. Doing it on at least half of the days (and
on 3 or more) is flagged as a habit. Saturdays, Sundays and the
holidays of the worker's base are not compared (S130), except for
night guards.

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
partida, la de tarde); un minuto después ya es llegada tarde. Cada
salida, igual, con la hora de salida más cercana: un minuto antes ya
es salida antes de hora. Con la hora real, no con la redondeada.
Hacerlo al menos la mitad de los días (y 3 o más) se marca como
costumbre. Sábados, domingos y festivos de la base del trabajador no
se comparan (S130), salvo en los guardas nocturnos.
"""
import datetime
from dataclasses import dataclass, field

from django.utils import timezone

from hr_calendar.models import ClockEvent

MAX_SHIFT_HOURS = 24
LATE_SEND_SECONDS = 300
HABITUAL_SHARE = 0.5
HABITUAL_MIN_DAYS = 3
MAX_COMPARE_MINUTES = 180
NO_OUT = "Entrada sin salida"
NO_IN = "Salida sin entrada"
OFF_SCHEDULE = "Fuera de horario"
MANUAL_PRESS = "Fichaje manual"


def next_kind(last_event, at):
    """
    The kind of the next press of the single "Fichar" button (S130):
    OUT when the last press before `at` is an IN still open, i.e. no
    more than MAX_SHIFT_HOURS earlier (the same limit build_shifts uses,
    so a night shift crossing midnight closes properly); IN otherwise.
    ---
    El tipo de la siguiente pulsación del botón único "Fichar" (S130):
    SALIDA si la última pulsación antes de `at` es una ENTRADA todavía
    abierta (de hace MAX_SHIFT_HOURS o menos, el mismo límite que
    build_shifts, para que un turno de noche que cruza la medianoche
    cierre bien); ENTRADA en cualquier otro caso.
    """
    if last_event is None or last_event.kind != ClockEvent.Kind.IN:
        return ClockEvent.Kind.IN
    limit = datetime.timedelta(hours=MAX_SHIFT_HOURS)
    if at - last_event.pressed_at > limit:
        return ClockEvent.Kind.IN
    return ClockEvent.Kind.OUT


def _manual_label(event):
    """
    Incident text of a manual press, with its kind, its time and when
    it was registered.
    ---
    Texto de la incidencia de un fichaje manual: "Fichaje manual:
    entrada 08:00, registrada el 19/10 a las 10:12".
    """
    pressed = timezone.localtime(event.pressed_at)
    registered = timezone.localtime(event.received_at)
    return "%s: %s %s, registrada el %s a las %s" % (
        MANUAL_PRESS, event.get_kind_display().lower(),
        pressed.strftime("%H:%M"), registered.strftime("%d/%m"),
        registered.strftime("%H:%M"),
    )


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
    expected_end: datetime.time = None

    @property
    def _raw_early(self):
        if self.clock_out is None or self.expected_end is None:
            return None
        real = timezone.localtime(self.clock_out.pressed_at)
        expected = self.expected_end.hour * 60 + self.expected_end.minute
        return expected - (real.hour * 60 + real.minute)

    @property
    def _raw_late(self):
        if self.clock_in is None or self.expected_start is None:
            return None
        real = timezone.localtime(self.clock_in.pressed_at)
        expected = self.expected_start.hour * 60 + self.expected_start.minute
        return (real.hour * 60 + real.minute) - expected

    @property
    def early_minutes(self):
        """
        Minutes between the real OUT and the scheduled end (positive:
        left early); None without OUT, without schedule or off schedule.
        ---
        Minutos entre la salida real y la hora de salida del horario
        (positivo: salió antes); None sin salida, sin horario o fuera
        de horario.
        """
        return _comparable(self._raw_early)

    @property
    def is_early(self):
        return (self.early_minutes or 0) > 0

    @property
    def late_minutes(self):
        """
        Minutes between the scheduled start and the real IN (negative:
        early); None without IN, without schedule or off schedule.
        ---
        Minutos entre la hora de entrada del horario y la entrada real
        (negativo: antes de hora); None sin entrada, sin horario o fuera
        de horario.
        """
        return _comparable(self._raw_late)

    @property
    def is_late(self):
        return (self.late_minutes or 0) > 0

    @property
    def start_off_schedule(self):
        """
        IN more than MAX_COMPARE_MINUTES away from the schedule: an
        incident (Miguel Ángel, S129: "debería de aparecer en rojo y
        como incidencia").
        ---
        Entrada a más de MAX_COMPARE_MINUTES del horario: incidencia.
        """
        raw = self._raw_late
        return raw is not None and abs(raw) > MAX_COMPARE_MINUTES

    @property
    def end_off_schedule(self):
        raw = self._raw_early
        return raw is not None and abs(raw) > MAX_COMPARE_MINUTES

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
        if self.start_off_schedule or self.end_off_schedule:
            return OFF_SCHEDULE
        return ""

    @property
    def incidents(self):
        """
        Every incident of the shift, spelled out (Miguel Ángel, S129:
        late arrivals and early departures are incidents too, explained
        in the worker's detail): missing pair, manual press (S130), off
        schedule, late, early.
        ---
        Todas las incidencias de la jornada, explicadas: fichaje sin su
        pareja, fichaje manual por olvido (S130), fuera de horario,
        llegada tarde y salida antes de hora.
        """
        def hhmm(event):
            return timezone.localtime(event.pressed_at).strftime("%H:%M")

        found = []
        if self.clock_in is None:
            found.append(NO_IN)
        if self.clock_out is None:
            found.append(NO_OUT)
        # S130: un fichaje manual por olvido es siempre incidencia.
        for event in (self.clock_in, self.clock_out):
            if (event is not None
                    and event.sent_by == ClockEvent.SentBy.MANUAL):
                found.append(_manual_label(event))
        if self.start_off_schedule:
            found.append("Entrada fuera de horario (%s; horario %s)" % (
                hhmm(self.clock_in), self.expected_start.strftime("%H:%M"),
            ))
        if self.end_off_schedule:
            found.append("Salida fuera de horario (%s; horario %s)" % (
                hhmm(self.clock_out), self.expected_end.strftime("%H:%M"),
            ))
        if self.is_late:
            found.append("Llegada tarde: %d min (%s; horario %s)" % (
                self.late_minutes, hhmm(self.clock_in),
                self.expected_start.strftime("%H:%M"),
            ))
        if self.is_early:
            found.append("Salida antes de hora: %d min (%s; horario %s)" % (
                self.early_minutes, hhmm(self.clock_out),
                self.expected_end.strftime("%H:%M"),
            ))
        return found

    @property
    def duration_label(self):
        if self.clock_in is None or self.clock_out is None:
            return ""
        return format_duration(self.seconds)


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
        """
        Shifts with at least one incident.
        ---
        Jornadas con al menos una incidencia.
        """
        return [s for s in self.shifts if s.incidents]

    @property
    def incident_count(self):
        return sum(len(s.incidents) for s in self.shifts)

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
        if not timed:
            return ""
        return "%d de %d" % (len(self.late_arrivals), len(timed))

    @property
    def habitually_late(self):
        return _habitual(len(self.late_arrivals), len(self.timed_arrivals))

    @property
    def timed_departures(self):
        """
        Shifts with an OUT and a schedule to compare it with.
        ---
        Jornadas con salida y con horario con el que compararla.
        """
        return [s for s in self.shifts if s.early_minutes is not None]

    @property
    def early_departures(self):
        return [s for s in self.timed_departures if s.is_early]

    @property
    def early_label(self):
        timed = self.timed_departures
        if not timed:
            return ""
        return "%d de %d" % (len(self.early_departures), len(timed))

    @property
    def habitually_early(self):
        return _habitual(
            len(self.early_departures), len(self.timed_departures),
        )

    @property
    def last_day(self):
        """
        The last day with presses: (day, first IN, last OUT, last press).
        ---
        El último día con pulsaciones: (día, primera entrada, última
        salida, última pulsación).
        """
        if not self.shifts:
            return None
        day = self.shifts[-1].day
        same = [s for s in self.shifts if s.day == day]
        ins = [s.clock_in for s in same if s.clock_in is not None]
        outs = [s.clock_out for s in same if s.clock_out is not None]
        last = max(
            (e for s in same for e in (s.clock_in, s.clock_out) if e),
            key=lambda e: e.pressed_at,
        )
        return {
            "day": day,
            "clock_in": ins[0] if ins else None,
            "clock_out": outs[-1] if outs else None,
            "last": last,
        }

    @property
    def late_events(self):
        return [e for e in self.events
                if e.delay_seconds > LATE_SEND_SECONDS]


def _comparable(minutes):
    """
    None when there is nothing to compare or the press is more than
    MAX_COMPARE_MINUTES away from the schedule: then it is not late nor
    early but an incident, "Fuera de horario" (Shift.issue).
    ---
    None si no hay con qué comparar o la pulsación está a más de
    MAX_COMPARE_MINUTES del horario: entonces no es tarde ni antes,
    sino una incidencia, "Fuera de horario".
    """
    if minutes is None or abs(minutes) > MAX_COMPARE_MINUTES:
        return None
    return minutes


def _habitual(count, total):
    """
    Late/early "out of habit": at least HABITUAL_SHARE of the days that
    can be compared, and at least HABITUAL_MIN_DAYS of them (Miguel
    Ángel: "si un día sales antes de tiempo no pasa nada, pero si lo
    haces de forma habitual [...] ya estamos en un problema").
    ---
    Tarde/antes "por costumbre": al menos la mitad de los días
    comparables y al menos HABITUAL_MIN_DAYS.
    """
    return count >= HABITUAL_MIN_DAYS and count >= total * HABITUAL_SHARE


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


def schedule_ends(schedule):
    """
    The end times of a WorkdaySchedule: morning, and afternoon in a
    split shift.
    ---
    Las horas de salida de un horario: la de mañana y, en jornada
    partida, la de tarde.
    """
    if schedule is None:
        return []
    ends = [schedule.end_time_morning]
    if not schedule.is_intensive and schedule.end_time_afternoon:
        ends.append(schedule.end_time_afternoon)
    return [t for t in ends if t is not None]


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


def _schedule_times_by_user(company, company_user_ids):
    """
    {user id: (start times, end times, is_day_compared)} -- the times of
    the user's schedule, and a function telling whether a day is
    compared with it (S130, Miguel Ángel: Saturdays, Sundays and the
    holidays of the worker's base are not, except for night guards).
    ---
    {id de usuario: (horas de entrada, horas de salida, se_compara)} --
    las horas de su horario y una función que dice si un día se compara
    con él (S130, Miguel Ángel: sábados, domingos y festivos de la base
    del trabajador no, salvo los guardas nocturnos).
    """
    from ivr_config.models import CompanyUser
    from panel.views_operator import _resolve_operator_schedule

    result = {}
    users = CompanyUser.objects.filter(
        pk__in=company_user_ids,
    ).select_related("base")
    for company_user in users:
        schedule = _resolve_operator_schedule(company_user, company)
        result[company_user.pk] = (
            schedule_starts(schedule), schedule_ends(schedule),
            _day_rule(company_user),
        )
    return result


def _day_rule(company_user):
    """
    The is_day_compared function of one user (see
    _schedule_times_by_user): night guards, every day; anyone else, only
    working days of their base's labour calendar (weekends only when the
    user has no base).
    ---
    La función se_compara de un usuario: los guardas nocturnos, todos
    los días; los demás, solo los laborables del calendario laboral de
    su base (sin base, solo se descartan sábados y domingos).
    """
    from budgets.services import _is_holiday
    from ivr_config.models import CompanyUser

    if company_user.role == CompanyUser.ROLE_NIGHTGUARD:
        return lambda day: True
    base = company_user.base
    return lambda day: not _is_holiday(day, base)


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
    times_by_user = _schedule_times_by_user(company, list(grouped))
    reports = {}
    for user_id, user_events in grouped.items():
        report = PersonReport()
        report.shifts = [
            s for s in build_shifts(user_events)
            if date_from <= s.day <= date_to
        ]
        starts, ends, is_day_compared = times_by_user.get(
            user_id, ([], [], lambda day: True),
        )
        for shift in report.shifts:
            if not is_day_compared(shift.day):
                # S130: sábado, domingo o festivo de su base (salvo
                # guardas): sin horario con el que comparar.
                continue
            if shift.clock_in is not None:
                shift.expected_start = expected_start(
                    starts, shift.clock_in.pressed_at,
                )
            if shift.clock_out is not None:
                # La más cercana, igual que la entrada (expected_start
                # sirve para cualquier lista de horas).
                shift.expected_end = expected_start(
                    ends, shift.clock_out.pressed_at,
                )
        report.events = [
            e for e in user_events if start <= e.pressed_at < end
        ]
        reports[user_id] = report
    return reports
