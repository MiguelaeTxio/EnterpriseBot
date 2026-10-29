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
    tz = timezone.get_current_timezone()
    start = timezone.make_aware(
        datetime.datetime.combine(work_date, datetime.time.min), tz,
    )
    events = list(ClockEvent.objects.current().filter(
        company_user=company_user,
        pressed_at__gte=start,
        pressed_at__lt=start + datetime.timedelta(days=1),
    ).order_by("pressed_at", "pk"))
    shifts = build_shifts(events)
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
    if event.sent_by != ClockEvent.SentBy.MANUAL:
        return ClockOutOutcome()
    clock_out = closing_out_of(event)
    if clock_out is None:
        return ClockOutOutcome()
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

    1. The worker's parte of that day, if already made and not reviewed,
       gets the last task of the stretch closed by this OUT ending at
       the OUT time (a task ending later is cut). A copy of the parte
       goes to the log first ([PARTE-BACKUP]).
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
    Tras una SALIDA (regla de Miguel Ángel arriba): 1) en el parte de
    ese día ya hecho y no revisado, la última tarea del tramo que cierra
    esta salida pasa a terminar a esa hora (antes, copia al log); 2) si
    el parte sigue abierto, se cierra si cuadra con lo fichado (mismas
    reglas que al cerrarlo a mano), con la pausa de comida del parte
    como único hueco; si no cuadra, sigue abierto y lo arregla
    el trabajador; 3) un parte ya cerrado que deja de cuadrar vuelve a
    "en curso". Devuelve un ClockOutOutcome (lo hecho y el aviso para
    el trabajador).
    """
    from work_order_processor.models import (
        WorkOrder,
        WorkOrderEntry,
        WorkOrderEntryLine,
    )
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
    entry = (
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
    if entry is None:
        return ClockOutOutcome()
    work_order = entry.work_order
    stretches = day_stretches(worker, work_date)
    stretch_start = None
    later = []
    for stretch in stretches:
        if stretch.end == out_time:
            stretch_start = stretch.start
        elif stretch.start and stretch.start >= out_time:
            later.append(stretch)
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

    # 1. Ajuste a la hora de salida (solo las tareas de este tramo).
    # La tarea pasa a terminar a la hora de salida redondeada (fichar
    # 13:55 con el parte a las 14:00 no cambia nada: 13:55 -> 14:00).
    in_stretch = [
        line for line in timed
        if (stretch_start is None or line.hc >= stretch_start)
        and line.hc < out_time
    ]
    done = []
    if in_stretch:
        last = max(in_stretch, key=lambda line: line.hf)
        for line in in_stretch:
            # A morning task is not stretched over the lunch break: the
            # afternoon tasks are missing and the worker adds them.
            # Una tarea de la mañana no se alarga por encima de la
            # comida: faltan las de la tarde y las pone el trabajador.
            if (
                line is last and line.hf < out_time and lunch
                and line.hf <= lunch[0]
            ):
                continue
            if line is last or line.hf > out_time:
                if line.hf != out_time:
                    done.append("tarea %d: fin %s -> %s" % (
                        line.line_number, _fmt(line.hf), _fmt(out_time)))
                    line.hf = out_time

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
        ) + close_blockers(stretches)
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
