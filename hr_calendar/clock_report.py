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

S133: solo se ficha el inicio y el fin de la jornada; las horas de la
jornada descuentan la pausa de comida del parte de ese día (la del
horario o la metida a mano), como en el parte.

S141: en las secciones que fichan por tipos, un CAMBIO DE TIPO con la
jornada abierta cierra un tramo y abre otro sin salir de la jornada
(Shift.changes). Las horas de la jornada solo suman los tramos de los
tipos que cuentan como jornada (presencia y desplazamiento no);
Shift.type_seconds da el desglose por tipo.

Puntualidad: cada entrada se compara con la hora de entrada más
cercana del horario actual del trabajador (la de mañana o, en jornada
partida, la de tarde); un minuto después ya es llegada tarde. Cada
salida, igual, con la hora de salida más cercana: un minuto antes ya
es salida antes de hora. Con la hora real, no con la redondeada.
Hacerlo al menos la mitad de los días (y 3 o más) se marca como
costumbre. Sábados, domingos y festivos de la base del trabajador no
se comparan (S130), salvo en los guardas nocturnos.

S144 (Miguel Ángel), horario abierto y jornadas excepcionales:
- Con un horario abierto (WorkdaySchedule.is_open) no se compara nada:
  ni llegadas tarde, ni salidas antes, ni fuera de horario. Lo controla
  una persona desde la oficina.
- La jornada es del día de su entrada, aunque la salida sea al día
  siguiente.
- Descanso mínimo (REST_HOURS): si la salida de la jornada anterior
  queda a menos de REST_HOURS de la primera hora de entrada del horario
  del día siguiente, ese día es flexible: no se compara su puntualidad
  (Shift.after_short_rest) ni hay recordatorios
  (hr_calendar/clock_reminders.py). La jornada excepcional en sí sigue
  marcándose como incidencia (fuera de horario) para que se vea.
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
# S144 (Miguel Ángel, "pongamos 10 horas"): descanso mínimo entre la
# salida de una jornada y la entrada del día siguiente.
REST_HOURS = 10
REST_NOTE = ("Día flexible: menos de %d h de descanso desde la jornada "
             "anterior; no se compara con el horario" % REST_HOURS)
# S144 (Miguel Ángel): el día flexible sí debe llegar a las 8 horas; si
# no, incidencia "para revisión si fuese necesaria".
FLEX_MIN_HOURS = 8
NO_OUT = "Entrada sin salida"
NO_IN = "Salida sin entrada"
OFF_SCHEDULE = "Fuera de horario"
MANUAL_PRESS = "Fichaje manual"


# S143: how long before the first start time of the next day an open
# shift begun at its scheduled time counts as forgotten (its next press
# is that day's IN). The same 3 hours as MAX_COMPARE_MINUTES.
# Cuánto antes de la primera hora de entrada del día siguiente una
# jornada abierta a su hora se da por olvidada.
FORGOTTEN_OUT_MARGIN = datetime.timedelta(minutes=180)


def forgotten_after(company_user, opening):
    """
    From when an open shift counts as forgotten, or None.
    ---
    Desde cuándo una jornada abierta se da por olvidada (S143, Miguel
    Ángel: "ficho por la mañana y ya no vuelvo a fichar, y al día
    siguiente cuando voy a fichar por la mañana, ¿qué ocurre?"): 3 horas
    antes de la primera hora de entrada del horario del día siguiente al
    de la entrada. Solo si la entrada fue a su hora (a MAX_COMPARE_MINUTES
    o menos de una hora de entrada de ese día): una entrada fuera de
    horario (un servicio de noche) sigue con el límite de
    MAX_SHIFT_HOURS para poder fichar su salida de madrugada. Sin
    horario (o abierto) esos días, None. Un horario de noche (guardas)
    empieza tarde, así que su salida de la mañana siguiente no cuenta
    como olvido.
    """
    from panel.views_operator import _resolve_operator_schedule

    if company_user is None or opening is None:
        return None
    opened = timezone.localtime(opening.pressed_at)
    company = company_user.company
    starts = schedule_starts(
        _resolve_operator_schedule(company_user, company, opened.date()))
    minutes = opened.hour * 60 + opened.minute
    if not starts or min(
            abs(t.hour * 60 + t.minute - minutes) for t in starts
    ) > MAX_COMPARE_MINUTES:
        return None
    next_day = opened.date() + datetime.timedelta(days=1)
    next_starts = schedule_starts(
        _resolve_operator_schedule(company_user, company, next_day))
    if not next_starts:
        return None
    return timezone.make_aware(
        datetime.datetime.combine(next_day, min(next_starts)),
        timezone.get_current_timezone(),
    ) - FORGOTTEN_OUT_MARGIN


def open_shift_opening(company_user, last_event):
    """
    The IN that opened the shift `last_event` belongs to, or None.
    ---
    La ENTRADA que abrió la jornada de `last_event` (él mismo si es una
    entrada; la última entrada anterior si es un cambio de tipo), o None
    si la jornada no está abierta.
    """
    if last_event is None:
        return None
    if last_event.kind == ClockEvent.Kind.IN:
        return last_event
    if last_event.kind != ClockEvent.Kind.CHANGE:
        return None
    return ClockEvent.objects.current().filter(
        company_user=company_user, kind=ClockEvent.Kind.IN,
        pressed_at__lte=last_event.pressed_at,
    ).order_by("-pressed_at", "-pk").first()


def next_kind(last_event, at, company_user=None):
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
    cierre bien); ENTRADA en cualquier otro caso. S143: con
    `company_user`, también ENTRADA si la jornada abierta se da por
    olvidada (forgotten_after): queda "sin salida" para que la corrija su
    responsable.
    """
    # S141: un cambio de tipo deja la jornada abierta, como la entrada.
    if last_event is None or last_event.kind not in (
            ClockEvent.Kind.IN, ClockEvent.Kind.CHANGE):
        return ClockEvent.Kind.IN
    limit = datetime.timedelta(hours=MAX_SHIFT_HOURS)
    if at - last_event.pressed_at > limit:
        return ClockEvent.Kind.IN
    if company_user is not None:
        since = forgotten_after(
            company_user, open_shift_opening(company_user, last_event))
        if since is not None and at >= since:
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


def _rounded(event):
    """
    The rounded time of a press (rounded_at; computed if missing).
    ---
    La hora redondeada de una pulsación (rounded_at; si una antigua no
    la tiene, se calcula).
    """
    if event.rounded_at is not None:
        return event.rounded_at
    from hr_calendar.clock_rounding import round_pressed_at

    return round_pressed_at(event.pressed_at, event.kind)


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
    # S143: hora de salida del horario que se propone al supervisor
    # cuando falta la salida (la primera después de la entrada).
    suggested_end: datetime.time = None
    # S133: lunch break of that day's parte inside the shift (it is not
    # clocked any more): not worked time.
    # Pausa de comida del parte de ese día dentro de la jornada (ya no
    # se ficha): no es tiempo trabajado.
    lunch_seconds: int = 0
    # S143: comida o cena que no se fichó (fichaje por tipos sin "No he
    # parado para comer"): una hora cada una, no es tiempo trabajado.
    auto_meal_seconds: int = 0
    auto_meals: list = field(default_factory=list)
    # S141: cambios de tipo dentro de la jornada, en orden.
    changes: list = field(default_factory=list)
    # S144: día flexible tras una jornada con poco descanso (REST_HOURS):
    # no se compara con el horario.
    after_short_rest: bool = False
    # S144: incidencia de revisión del día flexible (menos de
    # FLEX_MIN_HOURS en todo el día), en la última jornada de ese día.
    review: str = ""

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
    def segments(self):
        """
        [(ClockType or None, start, end)] of a closed shift (S141).
        ---
        Los tramos de una jornada cerrada: el de la entrada y uno por
        cada cambio de tipo, hasta la salida. [] si falta la entrada o
        la salida.
        """
        if self.clock_in is None or self.clock_out is None:
            return []
        marks = [self.clock_in] + list(self.changes)
        ends = [m.pressed_at for m in marks[1:]] + [
            self.clock_out.pressed_at]
        return [
            (mark.clock_type, mark.pressed_at, end)
            for mark, end in zip(marks, ends)
        ]

    @property
    def segment_marks(self):
        """
        [(opening press, end)] of a closed shift (S144).
        ---
        Cada tramo con la pulsación que lo abre (su tipo, su GPS, si es
        con vehículo propio) y su fin.
        """
        if self.clock_in is None or self.clock_out is None:
            return []
        marks = [self.clock_in] + list(self.changes)
        ends = [m.pressed_at for m in marks[1:]] + [
            self.clock_out.pressed_at]
        return list(zip(marks, ends))

    @property
    def meal_segments(self):
        """
        Stretches of the meal-break type (S144).
        ---
        Tramos de "Pausa para comer".
        """
        from hr_calendar.models import ClockType

        return [
            (mark, end) for mark, end in self.segment_marks
            if mark.clock_type is not None
            and mark.clock_type.role == ClockType.ROLE_MEAL
        ]

    @property
    def type_seconds(self):
        """
        {type name: seconds} of a closed shift with types (S141).
        ---
        {nombre del tipo: segundos} de una jornada cerrada con tipos;
        {} si nadie eligió tipo.
        """
        result = {}
        for clock_type, start, end in self.segments:
            if clock_type is None:
                continue
            seconds = int((end - start).total_seconds())
            result[clock_type.name] = result.get(clock_type.name, 0) + max(
                seconds, 0)
        return result

    @property
    def uncounted_seconds(self):
        """
        Seconds of the types that do not count as working time (S141).
        ---
        Segundos de los tipos que no cuentan como jornada (presencia,
        desplazamiento).
        """
        return sum(
            max(int((end - start).total_seconds()), 0)
            for clock_type, start, end in self.segments
            if clock_type is not None and not clock_type.counts_as_work
        )

    @property
    def seconds(self):
        if self.clock_in is None or self.clock_out is None:
            return 0
        # S143 (Miguel Ángel): "la hora de fichar es la hora redonda a la
        # que fichamos": lo trabajado va de la entrada a la salida
        # redondeadas (rounded_at, hr_calendar/clock_rounding.py), no de
        # la hora exacta; fichar a las 7:58 no da 2 minutos de más.
        gross = int((_rounded(self.clock_out)
                     - _rounded(self.clock_in)).total_seconds())
        return max(gross - self.lunch_seconds - self.auto_meal_seconds
                   - self.uncounted_seconds, 0)

    @property
    def in_progress(self):
        """
        Today's shift with its IN and no OUT yet (S143).
        ---
        La jornada de hoy con la entrada fichada y aún sin salida (S143,
        Miguel Ángel: "El día corriente [...] no lo marcamos como
        incidencia hasta que no termine y se marca en verde").
        """
        return (self.clock_in is not None and self.clock_out is None
                and self.day == timezone.localdate())

    @property
    def issue(self):
        if self.in_progress:
            return ""
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

        # S143: la jornada en curso no tiene incidencias hasta que acaba.
        if self.in_progress:
            return []
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
        if self.review:
            found.append(self.review)
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
    # S144: {día: segundos trabajados por encima del horario}.
    day_excess: dict = field(default_factory=dict)

    @property
    def excess_seconds(self):
        return sum(self.day_excess.values())

    @property
    def excess_label(self):
        return format_duration(self.excess_seconds)

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
        # S141: un cambio de tipo con la jornada abierta es un tramo más
        # de esa jornada; sin jornada abierta, la abre (como una
        # entrada).
        if event.kind == ClockEvent.Kind.CHANGE and open_shift is not None:
            open_shift.changes.append(event)
            continue
        if event.kind in (ClockEvent.Kind.IN, ClockEvent.Kind.CHANGE):
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
    if schedule is None or schedule.is_open:
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
    if schedule is None or schedule.is_open:
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


def suggested_end(ends, pressed_at):
    """
    Of the schedule's end times, the first after the IN press (the last
    one if none is later).
    ---
    De las horas de salida del horario, la primera posterior a la
    entrada (S143: la que se propone al añadir la salida olvidada); si
    ninguna es posterior, la última. Sin horas de salida, None.
    """
    if not ends:
        return None
    real = timezone.localtime(pressed_at).time()
    later = sorted(t for t in ends if t > real)
    return later[0] if later else max(ends)


def short_rest(day, starts, last_out):
    """
    True if `last_out` (an aware datetime, or None) is less than
    REST_HOURS before the first scheduled start of `day`.
    ---
    True si la salida `last_out` queda a menos de REST_HOURS de la
    primera hora de entrada del horario de `day` (S144): ese día es
    flexible. Sin horas de entrada o sin salida anterior, False.
    """
    if not starts or last_out is None:
        return False
    start_at = timezone.make_aware(
        datetime.datetime.combine(day, min(starts)),
        timezone.get_current_timezone(),
    )
    rest = start_at - last_out
    return rest < datetime.timedelta(hours=REST_HOURS)


def _schedule_times_by_user(company, company_user_ids):
    """
    {user id: (times_of, is_day_compared)} -- a function giving the
    (start times, end times) of the user's schedule on a day, and a
    function telling whether a day is compared with it (S130, Miguel
    Ángel: Saturdays, Sundays and the holidays of the worker's base are
    not, except for night guards).
    ---
    {id de usuario: (horas_del_dia, se_compara)} -- una función que da
    (horas de entrada, horas de salida) de su horario un día dado (S141:
    el horario puede ser distinto según el día de la semana) y otra que
    dice si un día se compara con él (S130, Miguel Ángel: sábados,
    domingos y festivos de la base del trabajador no, salvo los guardas
    nocturnos).
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
            _times_of(schedule, company_user.base),
            _day_rule(company_user, schedule),
            # S144: con horario y no abierto, los días tienen horas
            # previstas (bolsa de horas extras).
            schedule is not None and not schedule.is_open,
        )
    return result


def _times_of(schedule, base=None):
    """
    day -> (start times, end times) of `schedule` on that day.
    ---
    día -> (horas de entrada, horas de salida) de `schedule` ese día; un
    día que no se trabaja (horario distinto según el día) no tiene
    ninguna.
    """
    if schedule is not None and schedule.varies_by_day:
        from django.db.models import prefetch_related_objects

        prefetch_related_objects([schedule], "days")

    def times(day):
        # S144: festivo de la base -> fila Festivos del horario.
        on_day = schedule.for_day(
            day, holiday=public_holiday(day, base),
        ) if schedule is not None else None
        return schedule_starts(on_day), schedule_ends(on_day)
    return times


def public_holiday(day, base):
    """
    True if `day` is a public holiday of the base's labour calendar.
    ---
    True si `day` es festivo del calendario laboral de la base (S144),
    sin contar sábados y domingos: misma lectura que
    budgets.services._is_holiday (fecha exacta y, para los festivos de
    fecha fija, mes-día aunque el calendario sea de otro año).
    """
    import json

    if base is None:
        return False
    try:
        holidays = json.loads((base.labor_calendar or "").strip() or "[]")
    except (ValueError, TypeError):
        return False
    iso = day.isoformat()
    return any(h == iso or h[5:] == iso[5:] for h in holidays
               if isinstance(h, str))


def _day_rule(company_user, schedule=None):
    """
    The is_day_compared function of one user (see
    _schedule_times_by_user).
    ---
    La función se_compara de un usuario, según su horario (S144):
    - Festivo del calendario de su base: solo si el horario tiene "Se
      trabaja en festivos" (Miguel Ángel: Ismael no los trabaja,
      Antonio sí).
    - Sábado y domingo: los guardas nocturnos y los horarios "distinto
      según el día" (ahí manda qué días se trabajan); los demás, no.
    - El resto de días, sí.
    """
    from ivr_config.models import CompanyUser

    base = company_user.base
    works_holidays = bool(schedule is not None and schedule.works_holidays)
    weekends = (company_user.role == CompanyUser.ROLE_NIGHTGUARD
                or bool(schedule is not None and schedule.varies_by_day))

    def rule(day):
        if not works_holidays and public_holiday(day, base):
            return False
        return weekends or day.weekday() < 5
    return rule


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


def _deduct_parte_lunch(company, user_id, shifts):
    """
    Set each shift's lunch_seconds from that day's parte.

    ---

    S133 (Miguel Ángel): solo se ficha el inicio y el fin de la jornada
    y "las horas trabajadas dependen del parte de trabajo. Si el parte
    tiene una pausa de comida, la pausa de comida no entra en las horas
    trabajadas" (el descanso del desayuno sí cuenta: no es pausa del
    parte). Se descuenta la parte de la pausa del parte de ese día que
    cae dentro de la jornada; sin parte, o con "No he parado a comer",
    no hay nada que descontar.
    """
    from work_order_processor.models import WorkOrderEntry

    # S144: la jornada que ficha su pausa para comer ya la descuenta
    # (tipo que no cuenta como jornada); el parte no la descuenta otra vez.
    days = {shift.day for shift in shifts
            if shift.seconds and not shift.meal_segments}
    if not days:
        return
    lunches = {}
    for work_date, lunch_start, lunch_end in WorkOrderEntry.objects.filter(
        work_order__company=company,
        work_order__uploaded_by_id=user_id,
        work_date__in=days,
        no_lunch_break=False,
        lunch_break_start__isnull=False,
        lunch_break_end__isnull=False,
    ).values_list("work_date", "lunch_break_start", "lunch_break_end"):
        if lunch_end > lunch_start:
            lunches.setdefault(work_date, (lunch_start, lunch_end))
    tz = timezone.get_current_timezone()
    for shift in shifts:
        lunch = lunches.get(shift.day)
        if lunch is None or not shift.seconds:
            continue
        lunch_from, lunch_to = (
            timezone.make_aware(datetime.datetime.combine(shift.day, t), tz)
            for t in lunch
        )
        overlap = (
            min(shift.clock_out.pressed_at, lunch_to)
            - max(shift.clock_in.pressed_at, lunch_from)
        ).total_seconds()
        shift.lunch_seconds = max(int(overlap), 0)


AUTO_MEAL_SECONDS = 3600
# Lo que tiene que tocar la jornada de la franja de comida o de cena
# (clock_extras.MEAL_LUNCH / MEAL_DINNER) para que se descuente.
AUTO_MEAL_MIN_OVERLAP = 3600
# Un hueco entre dos jornadas del mismo día dentro de la franja de al
# menos esto es la comida (o la cena) sin fichar como pausa.
AUTO_MEAL_GAP = 30 * 60


def _parte_days(company, user_id, shifts):
    """
    (days with a parte, days whose parte says "No he parado a comer").
    ---
    Los días de esas jornadas con parte y, de ellos, los que dicen "No
    he parado a comer" (S143: el parte es fiable; ahí no se descuenta
    la comida sin fichar).
    """
    from work_order_processor.models import WorkOrderEntry

    days = {
        shift.day for shift in shifts
        if shift.clock_out is not None and shift.clock_in is not None
    }
    if not days:
        return set(), set()
    with_parte, no_lunch = set(), set()
    for work_date, flag in WorkOrderEntry.objects.filter(
        work_order__company=company,
        work_order__uploaded_by_id=user_id,
        work_date__in=days,
    ).values_list("work_date", "no_lunch_break"):
        with_parte.add(work_date)
        if flag:
            no_lunch.add(work_date)
    return with_parte, no_lunch


def _deduct_missing_meals(shifts, no_lunch_days=(), parte_days=(),
                          split_day=None):
    """
    One hour for lunch (and one for dinner) not clocked in typed shifts.

    ---

    S143 (Miguel Ángel): en el fichaje por tipos, si no se marca "No he
    parado para comer" y no se ha fichado la pausa, "vamos a descontar
    una hora de comida y una hora de cena si ha pillado en la zona de
    noche". Quien no ficha por tipos (S143): "depende del horario que
    tenga la persona": solo la comida, solo con jornada partida ese día
    (`split_day`: el horario del día tiene mañana y tarde; intensiva o
    sin horario, nada) y solo si ese día no tiene parte (el parte manda:
    su pausa ya se descuenta, o dice que no paró, o es intensiva). Por
    día, con todas sus jornadas cerradas:
    - Nada si alguna pulsación del día lleva "No he parado para comer"
      (ni la comida si el parte del día dice "No he parado a comer").
    - Por cada franja (comida 12-17, cena 19-24, las de las pausas): nada
      si hay una pausa para comer fichada que empieza en esa franja, una
      pausa del parte (solo comida), o un hueco de al menos AUTO_MEAL_GAP
      entre dos jornadas dentro de la franja; si no, y la jornada toca
      la franja al menos AUTO_MEAL_MIN_OVERLAP, una hora menos en la
      jornada que más la toca.
    """
    from hr_calendar.clock_extras import (
        DINNER, LUNCH, MEAL_DINNER, MEAL_LUNCH, meal_kind,
    )

    tz = timezone.get_current_timezone()
    by_day = {}
    for shift in shifts:
        by_day.setdefault(shift.day, []).append(shift)
    for day, same in by_day.items():
        if any(s.clock_in is None or s.clock_out is None for s in same):
            continue
        marks = [e for s in same
                 for e in [s.clock_in] + list(s.changes) + [s.clock_out]]
        if any(getattr(e, "no_meal_break", False) for e in marks):
            continue
        # S143 (Miguel Ángel): "en los que no fichan por tipo hay que
        # descontar la hora de comida"; la cena, en los que fichan por
        # tipo.
        typed = any(e.clock_type_id for e in marks)
        if not typed and (day in parte_days or split_day is None
                          or not split_day(day)):
            continue
        zones = ((LUNCH, MEAL_LUNCH), (DINNER, MEAL_DINNER)) if typed \
            else ((LUNCH, MEAL_LUNCH),)
        same = sorted(same, key=lambda s: s.clock_in.pressed_at)
        for kind, (zone_from, zone_to) in zones:
            zone_start = timezone.make_aware(
                datetime.datetime.combine(day, zone_from), tz)
            zone_end = timezone.make_aware(
                datetime.datetime.combine(day, zone_to), tz)

            def overlap(a, b):
                return max(int((min(b, zone_end) - max(a, zone_start))
                               .total_seconds()), 0)

            if any(meal_kind(mark.pressed_at) == kind
                   for s in same for mark, _end in s.meal_segments):
                continue
            if kind == LUNCH and (any(s.lunch_seconds for s in same)
                                  or day in no_lunch_days):
                continue
            if any(overlap(a.clock_out.pressed_at, b.clock_in.pressed_at)
                   >= AUTO_MEAL_GAP for a, b in zip(same, same[1:])):
                continue
            best = max(same, key=lambda s: overlap(
                s.clock_in.pressed_at, s.clock_out.pressed_at))
            if overlap(best.clock_in.pressed_at,
                       best.clock_out.pressed_at) < AUTO_MEAL_MIN_OVERLAP:
                continue
            best.auto_meal_seconds += AUTO_MEAL_SECONDS
            best.auto_meals.append(kind)


def _review_flexible_days(shifts):
    """
    Flag a finished flexible day with less than FLEX_MIN_HOURS worked.
    ---
    S144 (Miguel Ángel): el día flexible (tras poco descanso) no se
    compara con el horario, pero sí debe sumar FLEX_MIN_HOURS; si no,
    incidencia de revisión en la última jornada de ese día. Solo los
    días ya terminados (antes de hoy), para no marcar uno en curso.
    """
    today = timezone.localdate()
    by_day = {}
    for shift in shifts:
        by_day.setdefault(shift.day, []).append(shift)
    for day, same in by_day.items():
        if day >= today or not any(s.after_short_rest for s in same):
            continue
        worked = sum(s.seconds for s in same)
        if worked < FLEX_MIN_HOURS * 3600:
            same[-1].review = (
                "Revisar: día flexible con %s trabajadas (menos de %d h)"
                % (format_duration(worked), FLEX_MIN_HOURS))


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
    events = ClockEvent.objects.current().filter(
        company=company,
        company_user_id__in=list(company_user_ids),
        pressed_at__gte=start - margin,
        pressed_at__lt=end + margin,
    ).select_related("clock_type").order_by(
        "company_user_id", "pressed_at", "pk",
    )
    grouped = {}
    for event in events:
        grouped.setdefault(event.company_user_id, []).append(event)
    times_by_user = _schedule_times_by_user(company, list(grouped))
    reports = {}
    for user_id, user_events in grouped.items():
        report = PersonReport()
        all_shifts = build_shifts(user_events)
        report.shifts = [
            s for s in all_shifts if date_from <= s.day <= date_to
        ]
        times_of, is_day_compared, has_hours = times_by_user.get(
            user_id, (lambda day: ([], []), lambda day: True, False),
        )
        for shift in report.shifts:
            if not is_day_compared(shift.day):
                # S130: sábado, domingo o festivo de su base (salvo
                # guardas): sin horario con el que comparar.
                continue
            starts, ends = times_of(shift.day)
            if shift.clock_in is not None and shift.clock_out is None:
                shift.suggested_end = suggested_end(
                    ends, shift.clock_in.pressed_at,
                )
            # S144: tras una jornada que acabó con menos de REST_HOURS de
            # descanso, el día es flexible: no se compara.
            previous = [
                s.clock_out.pressed_at for s in all_shifts
                if s.clock_out is not None and s.day < shift.day
            ]
            if short_rest(shift.day, starts,
                          max(previous) if previous else None):
                shift.after_short_rest = True
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
        _deduct_parte_lunch(company, user_id, report.shifts)
        with_parte, no_lunch = _parte_days(company, user_id, report.shifts)
        _deduct_missing_meals(
            report.shifts, no_lunch, with_parte,
            lambda day: len(times_of(day)[0]) >= 2,
        )
        _review_flexible_days(report.shifts)
        # S144: horas extras de cada día (bolsa de horas, comidas y
        # vehículo propio: hr_calendar/clock_extras.py).
        from hr_calendar.clock_extras import day_excess

        report.day_excess = day_excess(
            report.shifts, times_of, is_day_compared, has_hours,
        )
        report.events = [
            e for e in user_events if start <= e.pressed_at < end
        ]
        reports[user_id] = report
    return reports
