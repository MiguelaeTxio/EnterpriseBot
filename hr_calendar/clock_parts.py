# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/hr_calendar/clock_parts.py
"""
Clock-in and work orders ("partes") together (H24, S129). Miguel
Ángel's business rules, verbatim where they matter:

1. Clocking IN touches no parte: "Cuando fichamos al entrar no puede
   haber ningún parte hecho, no hemos trabajado aún."
2. Clocking OUT: if that day's parte was already made (for the lunch
   break or before leaving) and does not match, the parte is adjusted,
   and then closed if it matches (on a split shift, only with the OUT
   of the second period); a parte cannot be closed before the OUT is
   clocked:
   "fichas, se mira si hay parte de ese día y si el fichaje de cierre no
   coincide, el parte debe modificarse para concordar". The last task of
   that stretch ends at the OUT time; no task may end after it "a no ser
   que haya una posterior entrada+salida" (a later clocked stretch).
3. Making the parte afterwards (same day or days later): the clocked
   times are fixed and the tasks fit inside them. "Fichamos de 8 a 13 y
   de 14:30 a 18 [...] las horas prefijadas para la mañana son 8 a 13,
   para la primera tarea, siendo modificable la hora de fin solo si es
   de 8:30 a 12:30. Y la primera tarea de la tarde de 14:30 a 18 siendo
   modificable la hora de fin de tarea siempre que sea hasta las 17:30."
   The existing safeguards (overlaps, gaps) still apply; the gap
   between two clocked stretches is the lunch break. On closing, each
   clocked stretch is covered with no hole: "no debe permitir dejar un
   hueco de media hora sin tarea al cerrar el parte [...] si acabó una
   tarea a las 13:30 es obligatorio una tarea de 13:30 a 14".

S133 (Miguel Ángel): "solo hay que fichar al inicio y fin de la
jornada y que se refleje en los partes". The day is ONE stretch, from
the first IN to the last OUT; the lunch break is not clocked: it is the
parte's, taken from the schedule as before the clock-in and changed by
hand when it was not that one. Rules 2 and 3 apply to that single
stretch with the lunch break as the only allowed gap; the parte closes
with the day's OUT (no more waiting for a second period).

A day's stretch comes from hr_calendar.clock_report (first IN and last
OUT of the day); the parte uses each press's ROUNDED time
(ClockEvent.rounded_at, hr_calendar/clock_rounding.py: ±5 min to the
whole/half hour, otherwise IN to the next half hour and OUT to the
previous one) and must match it exactly. A stretch may
lack its OUT (still working: the parte made before leaving) or its IN.

---

Fichajes y partes juntos (H24, S129). Reglas de negocio de Miguel
Ángel, literales donde importan (arriba, en inglés: 1. fichar entrada
no toca ningún parte; 2. al fichar salida, si el parte de ese día ya
estaba hecho y no cuadra, se ajusta: la última tarea de ese tramo
termina a la hora fichada; 3. el parte hecho después se ajusta a lo
fichado, horas fichadas fijas, y el hueco entre tramos es la comida).

S133: solo se ficha el inicio y el fin de la jornada. El día es UN
tramo, de la primera ENTRADA a la última SALIDA; la pausa de comida no
se ficha: es la del parte (la del horario, como antes de los fichajes,
o la que se meta a mano si no fue esa), y es el único hueco permitido.
El parte se cierra con la salida del día.

El tramo sale de hr_calendar.clock_report (primera ENTRADA y última
SALIDA del día), con las horas redondeadas. Puede no tener SALIDA
(sigue trabajando: el parte hecho antes de salir) o no tener ENTRADA.
"""
import datetime
import logging
from dataclasses import dataclass
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from hr_calendar.clock_report import MAX_SHIFT_HOURS, build_shifts
from hr_calendar.models import ClockEvent

logger = logging.getLogger(__name__)

MIN_TASK_MINUTES = 30


@dataclass
class Stretch:
    """
    One clocked stretch of a day, local times (None = not clocked).
    start/end are the rounded times the parte uses; clocked_start and
    clocked_end the real presses.
    ---
    Un tramo fichado de un día, en hora local (None = sin fichar).
    start/end son las horas redondeadas que usa el parte;
    clocked_start y clocked_end, las pulsaciones reales.
    """

    start: datetime.time = None
    end: datetime.time = None
    clocked_start: datetime.time = None
    clocked_end: datetime.time = None

    def label(self):
        return "%s–%s" % (
            self.start.strftime("%H:%M") if self.start else "?",
            self.end.strftime("%H:%M") if self.end else "…",
        )

    def as_dict(self):
        """
        Real clocked times and the rounded times the parte uses.
        ---
        Horas fichadas reales y las redondeadas que usa el parte.
        """
        def hhmm(value):
            return value.strftime("%H:%M") if value else ""

        return {
            "clocked_start": hhmm(self.clocked_start),
            "clocked_end": hhmm(self.clocked_end),
            "start": hhmm(self.start),
            "end": hhmm(self.end),
        }


def _local_time(value):
    return timezone.localtime(value).time().replace(second=0, microsecond=0)


def _rounded_time(event):
    """
    Rounded local time of a press (rounded_at; computed if missing).
    ---
    Hora local redondeada de una pulsación (rounded_at; se calcula si
    falta).
    """
    from hr_calendar.clock_rounding import round_pressed_at

    if event is None:
        return None
    rounded = event.rounded_at or round_pressed_at(
        event.pressed_at, event.kind,
    )
    return _local_time(rounded)


def _minutes(value):
    return value.hour * 60 + value.minute


def _time_of(minutes):
    return datetime.time(minutes // 60, minutes % 60)


def day_stretches(company_user, work_date):
    """
    The clocked stretches of company_user on work_date, in order.
    ---
    Los tramos fichados de company_user en work_date, en orden.
    """
    if company_user is None or work_date is None:
        return []
    shifts = build_shifts(_day_events(company_user, work_date))
    if not shifts:
        return []
    # S133: only the start and the end of the day are clocked. The day
    # is one stretch from its first IN to its last OUT (none while the
    # last IN is still open); a press in between (old habit of clocking
    # the lunch break) does not split it.
    # S133: solo se ficha el inicio y el fin de la jornada. El día es
    # un tramo de la primera ENTRADA a la última SALIDA (ninguna si la
    # última entrada sigue abierta); una pulsación intermedia (la
    # costumbre de fichar la comida) no lo parte.
    clock_in = next(
        (shift.clock_in for shift in shifts if shift.clock_in), None,
    )
    clock_out = shifts[-1].clock_out
    stretch = Stretch(
        start=_rounded_time(clock_in),
        end=_rounded_time(clock_out),
        clocked_start=_local_time(clock_in.pressed_at)
        if clock_in else None,
        clocked_end=_local_time(clock_out.pressed_at)
        if clock_out else None,
    )
    # Un tramo que redondeado no dura nada (entra 8:20 -> 8:30, sale
    # 8:40 -> 8:30) no lleva tareas.
    if stretch.start and stretch.end and stretch.end <= stretch.start:
        return []
    return [stretch]


def lunch_gaps(lunch):
    """
    The lunch break as an allowed gap in minutes, [(start, end)] or []:
    no task goes there and it is not "uncovered time" (R3). The break
    is the one of the parte (schedule by default, changed by hand when
    it was not that one), not clocked (S133).
    ---
    La pausa de comida como hueco permitido en minutos, [(inicio, fin)]
    o []: ahí no va ninguna tarea y no cuenta como "laguna sin cubrir"
    (R3). Es la del parte (la del horario por defecto, cambiada a mano
    si no fue esa), no se ficha (S133).
    """
    if not lunch or not lunch[0] or not lunch[1]:
        return []
    return [(_minutes(lunch[0]), _minutes(lunch[1]))]


def _fmt(value):
    return value.strftime("%H:%M")


def check_tasks(stretches, tasks, closing=True, lunch=None):
    """
    Errors (Spanish, for the worker) of the tasks against the clocked
    stretches. tasks: [(task number, hc, hf)] with hc < hf. Empty list
    when there are no stretches (a day without clock-in works as
    before). closing=True (closing the parte) also requires each
    stretch to be covered without holes but the lunch break (lunch:
    (start, end) times or None); "Guardar tareas" (progressive save)
    does not.
    ---
    Errores (para el trabajador) de las tareas frente a los tramos
    fichados. tasks: [(número de tarea, hc, hf)] con hc < hf. Lista
    vacía si no hay tramos (un día sin fichajes funciona como antes).
    closing=True (cerrar el parte) exige además que cada tramo quede
    cubierto sin huecos; "Guardar tareas" (guardado progresivo) no.
    """
    if not stretches:
        return []
    gaps = lunch_gaps(lunch)
    errors = []
    clocked = ", ".join(s.label() for s in stretches)
    groups = {i: [] for i in range(len(stretches))}
    for number, hc, hf in tasks:
        home = None
        for i, stretch in enumerate(stretches):
            if (
                (stretch.start is None or stretch.start <= hc)
                and (stretch.end is None or hf <= stretch.end)
            ):
                home = i
                break
        if home is None:
            errors.append(
                "Tarea %d (%s–%s): queda fuera de lo fichado ese día "
                "(%s). Las tareas tienen que caber en lo fichado."
                % (number, _fmt(hc), _fmt(hf), clocked)
            )
            continue
        groups[home].append((number, hc, hf))
    for i, stretch in enumerate(stretches):
        items = sorted(groups[i], key=lambda t: t[1])
        if not items:
            # Si alguna tarea ya se ha dicho que cae fuera, no se repite.
            if not closing or len(errors) > 0:
                continue
            errors.append(
                "No hay ninguna tarea para lo fichado de %s." % stretch.label()
            )
            continue
        first, last = items[0], max(items, key=lambda t: t[2])
        if stretch.start and first[1] != stretch.start:
            errors.append(
                "La primera tarea de %s tiene que empezar a las %s, la "
                "hora de entrada (la tarea %d empieza a las %s)."
                % (stretch.label(), _fmt(stretch.start), first[0],
                   _fmt(first[1]))
            )
        if closing:
            for previous, following in zip(items, items[1:]):
                in_lunch = any(
                    a <= _minutes(previous[2])
                    and _minutes(following[1]) <= b
                    for a, b in gaps
                )
                if following[1] > previous[2] and not in_lunch:
                    errors.append(
                        "Hueco sin tarea de %s a %s dentro de lo fichado "
                        "(%s): al cerrar el parte todo lo fichado tiene "
                        "que tener tarea."
                        % (_fmt(previous[2]), _fmt(following[1]),
                           stretch.label())
                    )
        if stretch.end and last[2] != stretch.end:
            errors.append(
                "La última tarea de %s tiene que terminar a las %s, la "
                "hora de salida (la tarea %d termina a las %s)."
                % (stretch.label(), _fmt(stretch.end), last[0],
                   _fmt(last[2]))
            )
        # Media hora como mínimo para la última y la primera tarea del
        # tramo, contada desde las horas del propio parte.
        if stretch.end and len(items) > 1:
            latest = _time_of(max(_minutes(last[2]) - MIN_TASK_MINUTES, 0))
            if last[1] > latest:
                errors.append(
                    "La última tarea de %s no puede empezar después de "
                    "las %s (media hora antes de la salida)."
                    % (stretch.label(), _fmt(latest))
                )
        if stretch.start and len(items) > 1:
            earliest = _time_of(min(
                _minutes(first[1]) + MIN_TASK_MINUTES, 23 * 60 + 59,
            ))
            if first[2] < earliest:
                errors.append(
                    "La primera tarea de %s no puede terminar antes de "
                    "las %s (media hora después de la entrada)."
                    % (stretch.label(), _fmt(earliest))
                )
    return errors


# ------------------------------------------------------------------
# Who is under the clock-in rule, and can the parte be closed?
# ------------------------------------------------------------------
def clock_required(company_user, work_date):
    """
    True when the parte of company_user for work_date falls under the
    clock-in rules: from the day of the user's first clock-in on.
    Workers who do not clock in yet, and earlier days, keep working as
    before.
    ---
    True si el parte de company_user en work_date entra en las reglas
    del fichaje: desde el día de su primer fichaje. Quien todavía no
    ficha, y los días anteriores, siguen como hasta ahora.
    """
    if company_user is None or work_date is None:
        return False
    first = (
        ClockEvent.objects.current().filter(company_user=company_user)
        .order_by("pressed_at").values_list("pressed_at", flat=True)
        .first()
    )
    return first is not None and timezone.localtime(first).date() <= work_date


def close_blockers(stretches):
    """
    Why the parte cannot be closed yet ([] = it can): Miguel Ángel, "un
    parte no se puede cerrar si no está fichada la salida, las tareas
    si, el parte no". S133: closing it anyway saves it "in progress"
    ("que el botón se quede habilitado, que puedan guardar").
    ---
    Por qué el parte no se puede cerrar todavía ([] = sí se puede). S133:
    al darle a cerrar igualmente se guarda "en curso".
    """
    if not stretches:
        return [
            "No hay fichajes de ese día: el parte se guarda, pero no se "
            "cierra hasta que estén fichadas la entrada y la salida."
        ]
    if any(s.end is None for s in stretches):
        return [
            "Todavía no has fichado la salida: el parte se guarda y se "
            "cerrará solo al fichar la salida si las horas cuadran."
        ]
    return []


# ------------------------------------------------------------------
# S147: the lunch break clocked (an OUT and, later that day, an IN)
# ------------------------------------------------------------------
def _day_events(company_user, work_date):
    tz = timezone.get_current_timezone()
    start = timezone.make_aware(
        datetime.datetime.combine(work_date, datetime.time.min), tz,
    )
    return list(ClockEvent.objects.current().filter(
        company_user=company_user,
        pressed_at__gte=start,
        pressed_at__lt=start + datetime.timedelta(days=1),
    ).order_by("pressed_at", "pk"))


def clocked_pauses(company_user, work_date):
    """
    The clocked pauses of a day: [(OUT event, IN event, start, end)],
    rounded local times, in order. A pause is an OUT followed by an IN
    the same day (Miguel Ángel,
    S147: "el fichaje [de salida] que cuente como pausa para la comida
    y que cuente el de cuando vuelvan como inicio de la tarde").
    ---
    Las pausas fichadas de un día: [(SALIDA, ENTRADA, inicio, fin)], con
    las horas redondeadas, en orden. Una pausa es una SALIDA seguida de
    una ENTRADA el mismo día (quien ficha con tipos no hace partes).
    """
    if company_user is None or work_date is None:
        return []
    shifts = build_shifts(_day_events(company_user, work_date))
    pauses = []
    for before, after in zip(shifts, shifts[1:]):
        if before.clock_out is None or after.clock_in is None:
            continue
        if after.clock_in.kind != ClockEvent.Kind.IN:
            continue
        start = _rounded_time(before.clock_out)
        end = _rounded_time(after.clock_in)
        if start and end and start < end:
            pauses.append((before.clock_out, after.clock_in, start, end))
    return sorted(pauses, key=lambda pause: pause[2])


def clocked_lunch(company_user, work_date):
    """
    (start, end) of the day's clocked lunch break (the first clocked
    pause), or None: the parte takes it instead of the schedule's.
    ---
    (inicio, fin) de la comida fichada del día (la primera pausa
    fichada), o None: el parte la toma en vez de la del horario.
    """
    pauses = clocked_pauses(company_user, work_date)
    if not pauses:
        return None
    return pauses[0][2], pauses[0][3]


def is_lunch_out(entry, out_time):
    """
    True when an OUT is a pause (the lunch one), not the end of the
    day: the parte of that day has its lunch break or a task after the
    OUT (rounded). The parte then waits for the end-of-day OUT. S147:
    not by the schedule, because a mechanic working away may eat at
    another time (Miguel Ángel: "las salidas a comer puede que no
    coincidan con los horarios").
    ---
    True si una SALIDA es una pausa (la de la comida) y no la del final
    de la jornada: el parte de ese día tiene su comida o alguna tarea
    después de la salida (redondeada). El parte espera entonces a la
    salida del final. S147: por el parte, no por el horario.
    """
    from work_order_processor.models import WorkOrderEntryLine

    if (
        not entry.no_lunch_break and entry.lunch_break_end
        and entry.lunch_break_end > out_time
    ):
        return True
    return WorkOrderEntryLine.objects.filter(
        entry=entry, hc__isnull=False, hc__gte=out_time,
    ).exists()


def lunch_problems(company_user, work_date, lunch):
    """
    What fails between the parte's lunch break and the clocked one
    ([] = nothing). S147 (Miguel Ángel): "si tiene la tarea con una
    partida de comida en el parte, la ticada debe coincidir (en hora
    redonda)".
    ---
    Qué falla entre la comida del parte y la fichada ([] = nada).
    """
    if not lunch:
        return []
    pauses = clocked_pauses(company_user, work_date)
    if any((p[2], p[3]) == tuple(lunch) for p in pauses):
        return []
    if pauses:
        return [
            "La comida del parte (%s a %s) no coincide con la fichada "
            "(%s a %s)." % (_fmt(lunch[0]), _fmt(lunch[1]),
                            _fmt(pauses[0][2]), _fmt(pauses[0][3]))
        ]
    return [
        "La comida del parte (%s a %s) no está fichada: hay que fichar "
        "la salida a comer y la vuelta." % (_fmt(lunch[0]), _fmt(lunch[1]))
    ]


# A pause clocked farther than this from the worker's base is a meal
# away from it: the parte gets its diet (S147).
DIET_AWAY_M = 5000


def _away_from_base(event, base):
    from budgets.service_route import distance_m

    if event.latitude is None or event.longitude is None:
        return False
    if base is None or base.latitude is None or base.longitude is None:
        return False
    return distance_m(
        (float(event.latitude), float(event.longitude)),
        (float(base.latitude), float(base.longitude)),
    ) > DIET_AWAY_M


def meal_away_from_base(company_user, work_date, lunch):
    """
    True when the clocked lunch pause (the parte's one or, without it,
    the first) was clocked away from the worker's base: its OUT or its
    IN more than DIET_AWAY_M from it. S147 (Miguel Ángel): "si se le
    olvida poner dieta y los fichajes indican que ha comido fuera de la
    base, marca la dieta de forma automática".
    ---
    True si la pausa de la comida fichada (la del parte o, sin ella, la
    primera) se fichó fuera de su base: la salida o la vuelta a más de
    DIET_AWAY_M de ella.
    """
    pauses = clocked_pauses(company_user, work_date)
    if lunch:
        pauses = [p for p in pauses if (p[2], p[3]) == tuple(lunch)]
    if not pauses:
        return False
    base = getattr(company_user, "base", None)
    return any(_away_from_base(e, base) for e in pauses[0][:2])


def _day_entry(worker, work_date):
    """
    The worker's digital parte of that day not yet reviewed, or None.
    ---
    El parte digital del trabajador de ese día sin revisar, o None.
    """
    from work_order_processor.models import WorkOrder, WorkOrderEntry

    return (
        WorkOrderEntry.objects.select_related("work_order__uploaded_by__user")
        .filter(
            work_order__uploaded_by=worker,
            work_order__source__in=(
                WorkOrder.Source.DIGITAL, WorkOrder.Source.GENERATED,
            ),
            work_order__reviewed=False,
            work_date=work_date,
        )
        .order_by("-work_order__upload_date").first()
    )


# ------------------------------------------------------------------
# S147: what was not clocked is clocked with the parte's times
# ------------------------------------------------------------------
# Miguel Ángel (S147): "El parte nunca corrige a lo fichado. El parte
# corrige cuando no se ha fichado". Las pulsaciones que se añaden van a
# nombre de su usuario del panel, con el motivo (ClockCorrection ADD).
FILL_BY_USERNAME = "alvarez_admin"


def _fill_author(company):
    from ivr_config.models import CompanyUser

    return CompanyUser.objects.filter(
        company=company, user__username=FILL_BY_USERNAME,
    ).first()


def _add_press(worker, kind, work_date, at_time, reason):
    """
    Add a press with the parte's time (ClockCorrection ADD by
    FILL_BY_USERNAME). Returns the new ClockEvent or None.
    ---
    Añade una pulsación con la hora del parte, como corrección.
    """
    from hr_calendar.clock_corrections import ClockCorrectionError
    from hr_calendar.clock_corrections import add_event

    author = _fill_author(worker.company)
    if author is None:
        logger.warning(
            "# [FICHAJE-PARTE] Sin usuario %s: no se añade la %s del "
            "usuario #%d (%s).", FILL_BY_USERNAME, kind, worker.pk,
            work_date,
        )
        return None
    try:
        person = worker.person_identity
    except Exception:
        person = None
    pressed_at = timezone.make_aware(
        datetime.datetime.combine(work_date, at_time),
        timezone.get_current_timezone(),
    )
    try:
        correction = add_event(worker, person, author, kind, pressed_at,
                               reason)
    except ClockCorrectionError as exc:
        logger.warning(
            "# [FICHAJE-PARTE] No se añade la %s del usuario #%d (%s): %s",
            kind, worker.pk, work_date, exc,
        )
        return None
    logger.info(
        "# [FICHAJE-PARTE] usuario #%d, %s: %s añadida a las %s (%s)",
        worker.pk, work_date, kind, _fmt(at_time), reason,
    )
    return correction.replacement


def fill_missing_presses(entry, upto=None, day_over=False):
    """
    Clock, with the parte's times, what the worker did not clock that
    day (S147). Returns the list of what was added (texts).
    - No IN that day (or the day starts with an OUT): an IN at the
      start of the first task.
    - The parte has a lunch break, no clocked pause and the lunch is
      over (before `upto` or `day_over`): the missing OUT (lunch start)
      and/or IN (lunch end). A clocked pause that differs is not
      touched: the clock rules and the parte must be fixed.
    - `day_over` and the day is still open: an OUT at the end of the
      last task.
    ---
    Ficha con las horas del parte lo que el trabajador no fichó ese día
    (S147). Devuelve lo añadido (textos). Una pausa fichada distinta de
    la del parte no se toca: manda lo fichado y se arregla el parte.
    """
    from work_order_processor.models import WorkOrderEntryLine

    worker = entry.work_order.uploaded_by
    work_date = entry.work_date
    if worker is None or work_date is None:
        return []
    if not clock_required(worker, work_date):
        return []
    timed = [
        line for line in WorkOrderEntryLine.objects.filter(entry=entry)
        if line.hc and line.hf
    ]
    if not timed:
        return []
    first_hc = min(line.hc for line in timed)
    last_hf = max(line.hf for line in timed)
    lunch = None
    if not entry.no_lunch_break and (
        entry.lunch_break_start and entry.lunch_break_end
        and entry.lunch_break_start < entry.lunch_break_end
    ):
        lunch = (entry.lunch_break_start, entry.lunch_break_end)
    events = _day_events(worker, work_date)
    ins = [_rounded_time(e) for e in events if e.kind == ClockEvent.Kind.IN]
    outs = [_rounded_time(e) for e in events
            if e.kind == ClockEvent.Kind.OUT]
    added = []
    # Sin entrada ese día, o el día empieza con una salida (se le olvidó
    # la de la mañana y fichó la vuelta de comer).
    missing_in = not ins or (
        events[0].kind == ClockEvent.Kind.OUT
        and first_hc < _rounded_time(events[0]))
    if missing_in and _add_press(
            worker, ClockEvent.Kind.IN, work_date, first_hc,
            "Se le ha olvidado fichar la entrada: se ficha a la hora de "
            "la primera tarea del parte (%s)." % _fmt(first_hc)):
        added.append("entrada %s" % _fmt(first_hc))
        ins.append(first_hc)
    lunch_over = lunch is not None and (
        day_over or (upto is not None and lunch[1] <= upto))
    if lunch_over and not clocked_pauses(worker, work_date):
        start, end = lunch
        first_in = min(ins)
        last_out = max(outs) if outs else None
        reason = (
            "Se le ha olvidado fichar la pausa de la comida: se ficha con "
            "la comida de su parte (%s a %s)." % (_fmt(start), _fmt(end)))
        if not any(first_in < o <= end for o in outs) and _add_press(
                worker, ClockEvent.Kind.OUT, work_date, start, reason):
            added.append("salida a comer %s" % _fmt(start))
        if not any(start <= i and (last_out is None or i < last_out)
                   for i in ins) and _add_press(
                worker, ClockEvent.Kind.IN, work_date, end, reason):
            added.append("vuelta de la comida %s" % _fmt(end))
    if day_over:
        events = _day_events(worker, work_date)
        if events and events[-1].kind != ClockEvent.Kind.OUT and _add_press(
                worker, ClockEvent.Kind.OUT, work_date, last_hf,
                "Se le ha olvidado fichar la salida: se ficha a la hora "
                "en que acaba la última tarea del parte (%s)."
                % _fmt(last_hf)):
            added.append("salida %s" % _fmt(last_hf))
    return added


def clocked_start(company_user, work_date):
    """
    Rounded time of the day's first clocked IN, or None. S147: the
    parte's first task starts at it and cannot be changed ("la primera
    tarea ya va con esa hora inviolable").
    ---
    Hora redondeada de la primera entrada fichada del día, o None.
    """
    if company_user is None or work_date is None:
        return None
    for event in _day_events(company_user, work_date):
        if event.kind == ClockEvent.Kind.IN:
            return _rounded_time(event)
    return None


def _filled_notice(added):
    return ("No fichaste: %s. Se ha fichado con las horas de tu parte y "
            "queda anotado." % ", ".join(added))


def _last_out(worker, work_date):
    events = _day_events(worker, work_date)
    outs = [e for e in events if e.kind == ClockEvent.Kind.OUT]
    return outs[-1] if outs else None


def sync_parte_with_clock(work_order):
    """
    After a parte is saved held by the clock (S147): clock what was not
    clocked with its times and, if the day already has its OUT, check
    it again against the clock (on_clock_out), which closes it if it
    matches. Returns a ClockOutOutcome.
    ---
    Tras guardar un parte que queda "en curso" por el fichaje: ficha lo
    que no se fichó con sus horas y, si el día ya tiene su salida, lo
    vuelve a cotejar (on_clock_out), que lo cierra si cuadra.
    """
    entry = work_order.entries.order_by("page_number").first()
    if entry is None or entry.work_date is None:
        return ClockOutOutcome()
    worker = work_order.uploaded_by
    day_over = entry.work_date < timezone.localdate()
    now_time = timezone.localtime().time()
    added = fill_missing_presses(
        entry, upto=None if day_over else now_time, day_over=day_over)
    clock_out = _last_out(worker, entry.work_date)
    if clock_out is None:
        if added:
            return ClockOutOutcome(text="; ".join(added),
                                   notice=_filled_notice(added))
        return ClockOutOutcome()
    outcome = on_clock_out(clock_out)
    if added:
        outcome.notice = " ".join(filter(
            None, (_filled_notice(added), outcome.notice)))
    return outcome


def fill_forgotten_out(event):
    """
    An IN that finds the previous day still open (the OUT was not
    clocked): if that day has its parte, the OUT is clocked at the end
    of its last task and the parte is checked again (S147, Miguel
    Ángel: "si no ficha a la hora de salida, pero ha hecho el parte
    [...] habrá que cerrarle el parte y cerrar el fichaje y anotarlo").
    ---
    Una ENTRADA que encuentra abierto el día anterior: con parte, se
    ficha su salida a la hora en que acaba su última tarea y se vuelve
    a cotejar el parte.
    """
    worker = event.company_user
    previous = (
        ClockEvent.objects.current().filter(
            company_user=worker, pressed_at__lt=event.pressed_at,
        ).order_by("-pressed_at", "-pk").first()
    )
    if previous is None or previous.kind == ClockEvent.Kind.OUT:
        return ClockOutOutcome()
    day = timezone.localtime(previous.pressed_at).date()
    if day >= timezone.localtime(event.pressed_at).date():
        return ClockOutOutcome()
    entry = _day_entry(worker, day)
    if entry is None:
        return ClockOutOutcome()
    added = fill_missing_presses(entry, day_over=True)
    clock_out = _last_out(worker, day)
    if not added or clock_out is None:
        return ClockOutOutcome()
    outcome = on_clock_out(clock_out)
    days = ("lunes", "martes", "miércoles", "jueves", "viernes",
            "sábado", "domingo")
    outcome.notice = " ".join(filter(None, (
        "No fichaste la salida del %s %s: se ha fichado con las horas de "
        "tu parte (%s) y queda anotado." % (
            days[day.weekday()], day.strftime("%d/%m"), ", ".join(added)),
        outcome.notice)))
    return outcome


def on_clock_in_after_pause(event):
    """
    An IN back from a clocked pause (S147): if the OUT had closed that
    day's parte, it goes back to "in progress"; it closes with the
    end-of-day OUT, checked against what was clocked (lunch included).
    ---
    Una ENTRADA de vuelta de una pausa fichada (S147): si la salida
    había cerrado el parte de ese día, vuelve a "en curso"; se cierra
    con la salida del final de la jornada, cotejado con lo fichado
    (comida incluida).
    """
    from work_order_processor.models import WorkOrder

    worker = event.company_user
    work_date = timezone.localtime(event.pressed_at).date()
    pause = next(
        (p for p in clocked_pauses(worker, work_date) if p[1].pk == event.pk),
        None,
    )
    if pause is None:
        return ClockOutOutcome()
    notice = (
        "Vuelta de la comida registrada (de %s a %s). El parte se cerrará "
        "con la salida del final de la jornada si su comida coincide."
        % (_fmt(pause[2]), _fmt(pause[3]))
    )
    entry = _day_entry(worker, work_date)
    if entry is None:
        return ClockOutOutcome(text="pausa fichada sin parte", notice=notice)
    work_order = entry.work_order
    if work_order.status != WorkOrder.Status.DONE:
        return ClockOutOutcome(text="pausa fichada", notice=notice)
    work_order.status = WorkOrder.Status.IN_PROGRESS
    work_order.save(update_fields=["status"])
    logger.info(
        "# [FICHAJE-PARTE] WorkOrder #%d (usuario #%d, %s) entrada %s: "
        "parte reabierto (vuelta de la pausa %s-%s)",
        work_order.pk, worker.pk, work_date, _fmt(pause[3]),
        _fmt(pause[2]), _fmt(pause[3]),
    )
    return ClockOutOutcome(text="parte reabierto", notice=notice)


# ------------------------------------------------------------------
# A press just stored: which ones touch the parte
# ------------------------------------------------------------------
def on_clock_press(event):
    """
    Parte effects of a press just stored (S130). An OUT, normal or
    manual, runs on_clock_out. A normal IN touches no parte (rule 1). A
    MANUAL IN (a forgotten IN written down later, possibly after the OUT
    of its shift was already clocked) re-runs on_clock_out with that
    OUT, so the parte made beforehand closes if it now matches, or goes
    back to "in progress" if it no longer does (Miguel Ángel, S130:
    "cuando se ficha y tenga un parte con las tareas y esté sin cerrar
    y coincida con el fichaje manual, cierre el parte").
    ---
    Efectos sobre el parte de una pulsación recién guardada (S130). Una
    SALIDA, normal o manual, pasa por on_clock_out. Una ENTRADA normal
    no toca partes (regla 1). Una ENTRADA MANUAL (olvidada y apuntada
    después, quizá cuando la salida de su jornada ya estaba fichada)
    vuelve a pasar por on_clock_out con esa salida: el parte hecho antes
    se cierra si ahora cuadra, o vuelve a "en curso" si deja de cuadrar.
    Devuelve el ClockOutOutcome de on_clock_out (vacío = nada).
    """
    if event.kind == ClockEvent.Kind.OUT:
        return on_clock_out(event)
    if event.kind != ClockEvent.Kind.IN:
        return ClockOutOutcome()
    # S147: la entrada que encuentra abierto el día anterior ficha su
    # salida con las horas de su parte.
    forgotten = fill_forgotten_out(event)
    if forgotten.notice:
        return forgotten
    # S147: la vuelta de la comida reabre el parte si se había cerrado.
    pause = on_clock_in_after_pause(event)
    if event.sent_by != ClockEvent.SentBy.MANUAL:
        return pause
    clock_out = closing_out_of(event)
    if clock_out is None:
        return pause
    return on_clock_out(clock_out)


def closing_out_of(clock_in):
    """
    The OUT that closes the shift of `clock_in` (build_shifts over the
    user's presses up to MAX_SHIFT_HOURS later), or None if that shift
    has no OUT yet.
    ---
    La SALIDA que cierra la jornada de `clock_in` (build_shifts sobre
    las pulsaciones del usuario hasta MAX_SHIFT_HOURS después), o None
    si esa jornada todavía no tiene salida.
    """
    margin = datetime.timedelta(hours=MAX_SHIFT_HOURS)
    events = list(ClockEvent.objects.current().filter(
        company_user_id=clock_in.company_user_id,
        pressed_at__gte=clock_in.pressed_at - margin,
        pressed_at__lte=clock_in.pressed_at + margin,
    ).order_by("pressed_at", "pk"))
    for shift in build_shifts(events):
        if shift.clock_in is not None and shift.clock_in.pk == clock_in.pk:
            return shift.clock_out
    return None


# ------------------------------------------------------------------
# Clocking OUT: adjust the parte made beforehand and try to close it
# ------------------------------------------------------------------
@dataclass
class ClockOutOutcome:
    """
    What an OUT did to the parte of that day: `text` for the log ("" =
    nothing) and `notice` for the worker on the clock-in page (S133,
    Miguel Ángel: "cuando fiche, si hay una discrepancia de hora,
    decirle, no están bien las horas, pero que se quede guardado");
    `ok` is False when the hours do not match.
    ---
    Lo que una SALIDA hizo con el parte de ese día: `text` para el log
    y `notice` para el trabajador en la página de fichaje.
    """

    text: str = ""
    notice: str = ""
    ok: bool = True


def _mismatch_notice(problem):
    return (
        "Las horas del parte no cuadran con el fichaje: %s El parte queda "
        "guardado, sin cerrar: corrige las horas y ciérralo." % problem
    )


def _net_hours(hc, hf, lunch):
    gross = _minutes(hf) - _minutes(hc)
    if lunch:
        gross -= max(0, min(_minutes(hf), _minutes(lunch[1]))
                     - max(_minutes(hc), _minutes(lunch[0])))
    return (Decimal(max(gross, 0)) / Decimal(60)).quantize(Decimal("0.01"))


def _backup_log(work_order, entry, lines, reason):
    """
    Same "# [PARTE-BACKUP]" line the form writes before saving, so the
    server log keeps a full copy of the parte before any automatic
    change (Miguel Ángel: the logs are a safeguard against failed saves).
    ---
    La misma línea "# [PARTE-BACKUP]" que escribe el formulario antes de
    guardar: el log del servidor guarda copia completa del parte antes
    de cualquier cambio automático.
    """
    import json

    try:
        payload = {
            "wo_pk": work_order.pk,
            "company": work_order.company_id,
            "user": work_order.uploaded_by.user.username,
            "worker_name": entry.worker_name,
            "work_date": entry.work_date.isoformat(),
            "lunch_start": entry.lunch_break_start.strftime("%H:%M")
            if entry.lunch_break_start else None,
            "lunch_end": entry.lunch_break_end.strftime("%H:%M")
            if entry.lunch_break_end else None,
            "no_lunch_break": entry.no_lunch_break,
            "status": work_order.status,
            "motivo": reason,
            "blocks": [{
                "n": line.line_number,
                "machine": line.machine_raw,
                "hc": line.hc.strftime("%H:%M") if line.hc else None,
                "hf": line.hf.strftime("%H:%M") if line.hf else None,
                "fault": line.fault_description,
                "repair": line.repair_notes,
            } for line in lines],
        }
        logger.info("# [PARTE-BACKUP] %s",
                    json.dumps(payload, ensure_ascii=False))
    except Exception as exc:
        logger.warning(
            "# [PARTE-BACKUP] No se pudo registrar el respaldo: %s", exc,
        )


def on_clock_out(event):
    """
    After an OUT press (Miguel Ángel: "cuando hacemos el parte antes que
    el fichaje, queda abierto y no se puede cerrar, cuando fichamos la
    salida se intenta cerrar si cumple con el horario"; S133: solo se
    ficha el inicio y el fin de la jornada, así que la salida del día
    cierra el parte):

    1. S147: what was not clocked that day (IN, lunch break) is
       clocked with the parte's times (fill_missing_presses); the
       tasks are no longer stretched or cut: the clock rules and the
       worker adapts the parte. A copy of the parte goes to the log
       first ([PARTE-BACKUP]).
    2. If the parte is still open, it is closed when it matches what was
       clocked (same rules and safeguards as closing it by hand), with
       the parte's lunch break as the only gap. If it does not match
       it stays open: the worker fixes it and closes it, as with any
       parte the safeguards do not let through.
    3. A parte already closed that no longer matches goes back to "in
       progress" so it cannot stay closed with times that disagree with
       the clock-in.
    Returns a ClockOutOutcome (what was done, and the notice for the
    worker).
    ---
    Tras una SALIDA (regla de Miguel Ángel arriba): 1) S147: lo que no
    se fichó ese día (entrada, comida) se ficha con las horas del parte;
    las tareas ya no se alargan ni se recortan (manda lo fichado y el
    parte se adapta; antes, copia al log); 2) si
    el parte sigue abierto, se cierra si cuadra con lo fichado (mismas
    reglas que al cerrarlo a mano), con la pausa de comida del parte
    como único hueco; si no cuadra, sigue abierto y lo arregla
    el trabajador; 3) un parte ya cerrado que deja de cuadrar vuelve a
    "en curso". Devuelve un ClockOutOutcome (lo hecho y el aviso para
    el trabajador).
    """
    from work_order_processor.models import WorkOrder, WorkOrderEntryLine
    from work_order_processor.validators import (
        TimeBlock,
        run_intra_part_validation,
        validate_inter_overlap,
    )

    if event.kind != ClockEvent.Kind.OUT:
        return ClockOutOutcome()
    worker = event.company_user
    work_date = timezone.localtime(event.pressed_at).date()
    out_time = _rounded_time(event)
    entry = _day_entry(worker, work_date)
    if entry is None:
        return ClockOutOutcome()
    # S147: la salida de la comida no toca el parte; se espera a la
    # salida del final de la jornada (salvo que ya haya una entrada
    # posterior: entonces no es la última salida que se espera).
    later_in = ClockEvent.objects.current().filter(
        company_user=worker, kind=ClockEvent.Kind.IN,
        pressed_at__gt=event.pressed_at,
        pressed_at__lt=event.pressed_at + datetime.timedelta(hours=12),
    ).exists()
    if not later_in and is_lunch_out(entry, out_time):
        logger.info(
            "# [FICHAJE-PARTE] WorkOrder #%d (usuario #%d, %s) salida %s: "
            "pausa, el parte espera a la salida del final de la jornada",
            entry.work_order_id, worker.pk, work_date, _fmt(out_time),
        )
        return ClockOutOutcome(
            text="salida para comer",
            notice="Salida para comer registrada. Al volver, ficha la "
                   "entrada; el parte se cerrará con la salida del final "
                   "de la jornada.",
        )
    work_order = entry.work_order
    # S147: lo que no fichó (la entrada, la comida) se ficha con las
    # horas del parte, a nombre de la oficina y con el motivo.
    filled = fill_missing_presses(entry, upto=out_time)
    stretches = day_stretches(worker, work_date)
    lines = list(
        WorkOrderEntryLine.objects.filter(entry=entry)
        .order_by("hc", "line_number")
    )
    timed = [line for line in lines if line.hc and line.hf]
    if not timed:
        return ClockOutOutcome()
    _backup_log(work_order, entry, lines, "fichaje de salida %s"
                % _fmt(out_time))
    # S133: the lunch break is the parte's (schedule or by hand).
    # La pausa de comida es la del parte (horario o a mano).
    lunch = None
    if not entry.no_lunch_break and (
        entry.lunch_break_start and entry.lunch_break_end
    ):
        lunch = (entry.lunch_break_start, entry.lunch_break_end)

    # 1. S147 (Miguel Ángel): lo fichado manda y el parte se adapta a
    # ello; el programa ya no alarga ni recorta tareas. Si falta tarea
    # hasta la salida (o sobra), el parte no se cierra y lo arregla el
    # trabajador.
    done = []

    # Horas netas, sin la pausa de comida del parte.
    with transaction.atomic():
        for line in timed:
            line.delta_hours = _net_hours(line.hc, line.hf, lunch)
            line.save(update_fields=["hf", "delta_hours"])

    # 2/3. ¿Cuadra con lo fichado?
    blocks = [
        TimeBlock(idx=line.line_number, hc=line.hc, hf=line.hf)
        for line in timed
    ]
    intra = run_intra_part_validation(
        blocks, lunch_window=None, allowed_gaps=lunch_gaps(lunch),
    )
    problems = [e.message for e in intra.errors]
    if not problems:
        problems = check_tasks(
            stretches, [(b.idx, b.hc, b.hf) for b in blocks], closing=True,
            lunch=lunch,
        ) + close_blockers(stretches) + lunch_problems(
            worker, work_date, lunch,
        )
    # S147: dieta automática si comió fuera de la base y no la puso.
    if not entry.has_diet and meal_away_from_base(worker, work_date, lunch):
        entry.has_diet = True
        entry.save(update_fields=["has_diet"])
        done.append("dieta marcada: comida fichada fuera de la base")
    result = ""
    notice = ""
    if work_order.status == WorkOrder.Status.DONE:
        if problems:
            work_order.status = WorkOrder.Status.IN_PROGRESS
            work_order.save(update_fields=["status"])
            result = "parte reabierto: ya no cuadra con lo fichado (%s)" % (
                problems[0])
            notice = _mismatch_notice(problems[0])
    elif not problems:
        work_order.status = WorkOrder.Status.DONE
        work_order.save(update_fields=["status"])
        inter = validate_inter_overlap(
            company_user=worker, work_date=work_date, blocks=blocks,
            exclude_work_order_pk=work_order.pk,
        )
        if inter.has_overlap:
            WorkOrder.objects.filter(pk=work_order.pk).update(
                has_overlap_incident=True,
            )
        result = "parte cerrado al fichar la salida"
        notice = "Parte del día cerrado: las horas cuadran con el fichaje."
    else:
        result = "parte abierto: no cuadra con lo fichado (%s)" % (
            problems[0])
        notice = _mismatch_notice(problems[0])
    if filled:
        notice = " ".join(filter(None, (_filled_notice(filled), notice)))
        done = filled + done
    logger.info(
        "# [FICHAJE-PARTE] WorkOrder #%d (usuario #%d, %s) salida %s: %s%s",
        work_order.pk, worker.pk, work_date, _fmt(out_time), result,
        (" | ajustes: " + "; ".join(done)) if done else "",
    )
    if result == "parte cerrado al fichar la salida" or (
        done and work_order.status == WorkOrder.Status.DONE
    ):
        try:
            from work_order_processor.services import (
                generate_work_order_excel,
            )
            generate_work_order_excel(work_order.pk)
        except Exception:
            logger.exception(
                "# [FICHAJE-PARTE] No se pudo generar el Excel del "
                "WorkOrder #%d.", work_order.pk,
            )
    return ClockOutOutcome(text=result, notice=notice, ok=not problems)


# ------------------------------------------------------------------
# S146: a supervisor's correction carries the parte with it
# ------------------------------------------------------------------
def day_bounds(company_user, work_date):
    """
    (start, end) of the day's clocked stretch, rounded local times, or
    (None, None). Taken before a correction to compare afterwards.
    ---
    (inicio, fin) del tramo fichado del día, horas locales redondeadas,
    o (None, None). Se toma antes de una corrección para comparar.
    """
    stretches = day_stretches(company_user, work_date)
    if not stretches:
        return (None, None)
    return (stretches[0].start, stretches[0].end)


def resync_parte_after_correction(company_user, work_date, before):
    """
    After a supervisor corrects the presses of a day (S146, Miguel
    Ángel: he forgot to clock in at 8 and clocked at 10, "en el parte
    las tareas habría que alargarlas porque estuvo haciendo lo mismo"):
    the task that began at the old clocked start now begins at the new
    one, and the task that ended at the old clocked end now ends at the
    new one. The worker's other tasks are not touched. Then the parte is
    checked again against the clock (on_clock_out: closes it if it
    matches, reopens it if it no longer does). `before` is day_bounds()
    taken before the correction. Returns a ClockOutOutcome.
    ---
    Tras corregir el supervisor las pulsaciones de un día: la tarea que
    empezaba en la entrada fichada antigua empieza en la nueva, y la que
    acababa en la salida antigua acaba en la nueva; el resto no se toca.
    Después se vuelve a cotejar el parte con lo fichado (on_clock_out).
    """
    from work_order_processor.models import WorkOrderEntryLine

    entry = _day_entry(company_user, work_date)
    if entry is None:
        return ClockOutOutcome()
    old_start, old_end = before or (None, None)
    new_start, new_end = day_bounds(company_user, work_date)
    lines = list(
        WorkOrderEntryLine.objects.filter(entry=entry)
        .order_by("hc", "line_number")
    )
    timed = [line for line in lines if line.hc and line.hf]
    lunch = None
    if not entry.no_lunch_break and (
        entry.lunch_break_start and entry.lunch_break_end
    ):
        lunch = (entry.lunch_break_start, entry.lunch_break_end)
    changed = []
    if timed:
        first, last = timed[0], timed[-1]
        if (old_start and new_start and new_start != old_start
                and first.hc == old_start and new_start < first.hf):
            changed.append((first, "hc", new_start))
        if (old_end and new_end and new_end != old_end
                and last.hf == old_end and new_end > last.hc):
            changed.append((last, "hf", new_end))
    done = []
    if changed:
        _backup_log(entry.work_order, entry, lines,
                    "corrección de fichajes del supervisor")
        with transaction.atomic():
            for line, field, value in changed:
                old = getattr(line, field)
                setattr(line, field, value)
                line.delta_hours = _net_hours(line.hc, line.hf, lunch)
                line.save(update_fields=[field, "delta_hours"])
                done.append("tarea %d: %s %s → %s" % (
                    line.line_number,
                    "inicio" if field == "hc" else "fin",
                    _fmt(old), _fmt(value)))
        logger.info(
            "# [FICHAJE-PARTE] WorkOrder #%d (usuario #%d, %s) tras "
            "corrección: %s", entry.work_order_id, company_user.pk,
            work_date, "; ".join(done),
        )
    clock_out = _last_out(company_user, work_date)
    outcome = on_clock_out(clock_out) if clock_out else ClockOutOutcome()
    if done:
        outcome.text = "; ".join(filter(None, ["; ".join(done),
                                               outcome.text]))
        entry.work_order.refresh_from_db(fields=["status"])
        if entry.work_order.status == "DONE":
            try:
                from work_order_processor.services import (
                    generate_work_order_excel,
                )
                generate_work_order_excel(entry.work_order_id)
            except Exception:
                logger.exception(
                    "# [FICHAJE-PARTE] No se pudo generar el Excel del "
                    "WorkOrder #%d.", entry.work_order_id,
                )
    return outcome
