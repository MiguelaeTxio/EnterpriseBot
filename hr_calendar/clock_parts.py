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

A day's clocked stretches come from hr_calendar.clock_report (an IN
with the next OUT); times are the exact clocked minute. A stretch may
lack its OUT (still working: the parte made before leaving) or its IN.

---

Fichajes y partes juntos (H24, S129). Reglas de negocio de Miguel
Ángel, literales donde importan (arriba, en inglés: 1. fichar entrada
no toca ningún parte; 2. al fichar salida, si el parte de ese día ya
estaba hecho y no cuadra, se ajusta: la última tarea de ese tramo
termina a la hora fichada; 3. el parte hecho después se ajusta a lo
fichado, horas fichadas fijas, y el hueco entre tramos es la comida).

Los tramos fichados de un día salen de hr_calendar.clock_report (una
ENTRADA con la siguiente SALIDA), al minuto exacto fichado. Un tramo
puede no tener SALIDA (sigue trabajando: el parte hecho antes de salir)
o no tener ENTRADA.
"""
import datetime
import logging
from dataclasses import dataclass
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from hr_calendar.clock_report import build_shifts
from hr_calendar.models import ClockEvent

logger = logging.getLogger(__name__)

MIN_TASK_MINUTES = 30
# Miguel Ángel (S129): el fichaje va al minuto y el parte de media en
# media hora -- "la 1 con una tolerancia de ±5 minutos. 15 son demasiados
# minutos". Una hora del parte cuadra con la fichada si se separa como
# mucho esto. El fichaje se guarda siempre exacto.
TOLERANCE_MINUTES = 5


@dataclass
class Stretch:
    """
    One clocked stretch of a day, local times (None = not clocked).
    ---
    Un tramo fichado de un día, en hora local (None = sin fichar).
    """

    start: datetime.time = None
    end: datetime.time = None

    def label(self):
        return "%s–%s" % (
            self.start.strftime("%H:%M") if self.start else "?",
            self.end.strftime("%H:%M") if self.end else "…",
        )

    def as_dict(self):
        """
        Clocked times, and the times the parte uses (within ±5 min of a
        half hour, the half hour).
        ---
        Horas fichadas, y las que usa el parte (a ±5 min de una media
        hora, la media hora).
        """
        start, end = parte_time(self.start), parte_time(self.end)
        return {
            "clocked_start": self.start.strftime("%H:%M")
            if self.start else "",
            "clocked_end": self.end.strftime("%H:%M") if self.end else "",
            "start": start.strftime("%H:%M") if start else "",
            "end": end.strftime("%H:%M") if end else "",
        }


def _local_time(value):
    return timezone.localtime(value).time().replace(second=0, microsecond=0)


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
    events = list(ClockEvent.objects.filter(
        company_user=company_user,
        pressed_at__gte=start,
        pressed_at__lt=start + datetime.timedelta(days=1),
    ).order_by("pressed_at", "pk"))
    stretches = []
    for shift in build_shifts(events):
        stretches.append(Stretch(
            start=_local_time(shift.clock_in.pressed_at)
            if shift.clock_in else None,
            end=_local_time(shift.clock_out.pressed_at)
            if shift.clock_out else None,
        ))
    return stretches


def lunch_from_stretches(stretches):
    """
    (start, end) of the first gap between two clocked stretches, or
    None: that gap is the day's lunch break.
    ---
    (inicio, fin) del primer hueco entre dos tramos fichados, o None:
    ese hueco es la pausa de comida del día.
    """
    for previous, following in zip(stretches, stretches[1:]):
        if previous.end and following.start:
            # Con las horas del parte (±5 min a la media hora), para no
            # descontar minutos sueltos de las tareas.
            return parte_time(previous.end), parte_time(following.start)
    return None


def allowed_gaps(stretches):
    """
    Gaps between clocked stretches in minutes, [(start, end)]: no task
    goes there and they are not "uncovered time" (R3).
    ---
    Huecos entre tramos fichados en minutos, [(inicio, fin)]: ahí no va
    ninguna tarea y no cuentan como "laguna sin cubrir" (R3).
    """
    return [
        (_minutes(a.end) - TOLERANCE_MINUTES,
         _minutes(b.start) + TOLERANCE_MINUTES)
        for a, b in zip(stretches, stretches[1:])
        if a.end and b.start
    ]


def _fmt(value):
    return value.strftime("%H:%M")


def _near(a, b):
    """
    True when two times are within the tolerance (±5 min).
    ---
    True si dos horas están dentro de la tolerancia (±5 min).
    """
    return abs(_minutes(a) - _minutes(b)) <= TOLERANCE_MINUTES


def parte_time(value):
    """
    The time the parte uses for a clocked time: the nearest half hour
    when it is within the tolerance (8:04 -> 8:00, 13:55 -> 14:00),
    otherwise the clocked minute (13:40 stays 13:40).
    ---
    La hora que usa el parte para una hora fichada: la media hora más
    cercana si está dentro de la tolerancia (8:04 -> 8:00, 13:55 ->
    14:00); si no, el minuto fichado (13:40 se queda en 13:40).
    """
    if value is None:
        return None
    minutes = _minutes(value)
    nearest = int(round(minutes / 30.0)) * 30
    if abs(nearest - minutes) <= TOLERANCE_MINUTES and nearest < 24 * 60:
        return _time_of(nearest)
    return value


def check_tasks(stretches, tasks, closing=True):
    """
    Errors (Spanish, for the worker) of the tasks against the clocked
    stretches. tasks: [(task number, hc, hf)] with hc < hf. Empty list
    when there are no stretches (a day without clock-in works as
    before). closing=True (closing the parte) also requires each
    stretch to be covered without holes; "Guardar tareas" (progressive
    save) does not.
    ---
    Errores (para el trabajador) de las tareas frente a los tramos
    fichados. tasks: [(número de tarea, hc, hf)] con hc < hf. Lista
    vacía si no hay tramos (un día sin fichajes funciona como antes).
    closing=True (cerrar el parte) exige además que cada tramo quede
    cubierto sin huecos; "Guardar tareas" (guardado progresivo) no.
    """
    if not stretches:
        return []
    errors = []
    clocked = ", ".join(s.label() for s in stretches)
    groups = {i: [] for i in range(len(stretches))}
    for number, hc, hf in tasks:
        home = None
        for i, stretch in enumerate(stretches):
            if (
                (stretch.start is None or stretch.start <= hc
                 or _near(stretch.start, hc))
                and (stretch.end is None or hf <= stretch.end
                     or _near(stretch.end, hf))
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
            if not closing:
                continue
            errors.append(
                "No hay ninguna tarea para lo fichado de %s." % stretch.label()
            )
            continue
        first, last = items[0], max(items, key=lambda t: t[2])
        if stretch.start and not _near(first[1], stretch.start):
            errors.append(
                "La primera tarea de %s tiene que empezar a las %s, la "
                "hora de entrada fichada, ±%d min (la tarea %d empieza a "
                "las %s)."
                % (stretch.label(), _fmt(parte_time(stretch.start)),
                   TOLERANCE_MINUTES, first[0], _fmt(first[1]))
            )
        if closing:
            for previous, following in zip(items, items[1:]):
                if following[1] > previous[2]:
                    errors.append(
                        "Hueco sin tarea de %s a %s dentro de lo fichado "
                        "(%s): al cerrar el parte todo lo fichado tiene "
                        "que tener tarea."
                        % (_fmt(previous[2]), _fmt(following[1]),
                           stretch.label())
                    )
        if stretch.end and not _near(last[2], stretch.end):
            errors.append(
                "La última tarea de %s tiene que terminar a las %s, la "
                "hora de salida fichada, ±%d min (la tarea %d termina a "
                "las %s)."
                % (stretch.label(), _fmt(parte_time(stretch.end)),
                   TOLERANCE_MINUTES, last[0], _fmt(last[2]))
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
        ClockEvent.objects.filter(company_user=company_user)
        .order_by("pressed_at").values_list("pressed_at", flat=True)
        .first()
    )
    return first is not None and timezone.localtime(first).date() <= work_date


def close_blockers(stretches):
    """
    Why the parte cannot be closed yet ([] = it can): Miguel Ángel, "un
    parte no se puede cerrar si no está fichada la salida, las tareas
    si, el parte no".
    ---
    Por qué el parte no se puede cerrar todavía ([] = sí se puede).
    """
    if not stretches:
        return [
            "No hay fichajes de ese día: el parte no se puede cerrar sin "
            "fichar la entrada y la salida. Puedes guardar las tareas."
        ]
    if any(s.end is None for s in stretches):
        return [
            "Todavía no has fichado la salida: el parte no se puede cerrar. "
            "Guarda las tareas; al fichar la salida se cerrará solo si "
            "cuadra con lo fichado."
        ]
    return []


def is_split_shift(company_user):
    """
    True when the worker's schedule is a split shift (morning and
    afternoon): then the parte is not closed on the first OUT but on
    the OUT of the second period.
    ---
    True si el horario del trabajador es de jornada partida (mañana y
    tarde): entonces el parte no se cierra con la primera salida sino
    con la salida del segundo periodo.
    """
    from panel.views_operator import _resolve_operator_schedule

    schedule = _resolve_operator_schedule(
        company_user, company_user.company,
    )
    return bool(
        schedule is not None and not schedule.is_intensive
        and schedule.end_time_morning and schedule.start_time_afternoon
    )


# ------------------------------------------------------------------
# Clocking OUT: adjust the parte made beforehand and try to close it
# ------------------------------------------------------------------
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
    salida se intenta cerrar si cumple con el horario, siempre que no
    sea jornada partida, si es jornada partida no se intenta cerrar
    hasta que se fiche el segundo periodo"):

    1. The worker's parte of that day, if already made and not reviewed,
       gets the last task of the stretch closed by this OUT ending at
       the OUT time (a task ending later is cut). A copy of the parte
       goes to the log first ([PARTE-BACKUP]).
    2. If the parte is still open, it is closed when it matches what was
       clocked (same rules and safeguards as closing it by hand) --
       except on a split shift before the OUT of the second period. If
       it does not match it stays open: the worker fixes it and closes
       it, as with any parte the safeguards do not let through.
    3. A parte already closed that no longer matches goes back to "in
       progress" so it cannot stay closed with times that disagree with
       the clock-in.
    Returns a short text of what was done ("" = nothing).
    ---
    Tras una SALIDA (regla de Miguel Ángel arriba): 1) en el parte de
    ese día ya hecho y no revisado, la última tarea del tramo que cierra
    esta salida pasa a terminar a esa hora (antes, copia al log); 2) si
    el parte sigue abierto, se cierra si cuadra con lo fichado (mismas
    reglas que al cerrarlo a mano), salvo en jornada partida antes de la
    salida del segundo periodo; si no cuadra, sigue abierto y lo arregla
    el trabajador; 3) un parte ya cerrado que deja de cuadrar vuelve a
    "en curso". Devuelve un texto corto de lo hecho ("" = nada).
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
        return ""
    worker = event.company_user
    work_date = timezone.localtime(event.pressed_at).date()
    out_time = _local_time(event.pressed_at)
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
        return ""
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
        return ""
    _backup_log(work_order, entry, lines, "fichaje de salida %s"
                % _fmt(out_time))

    # 1. Ajuste a la hora de salida (solo las tareas de este tramo).
    # Dentro de ±5 min no se toca nada (fichar 13:55 con el parte a las
    # 14:00 cuadra); fuera, la tarea pasa a terminar a la hora fichada.
    in_stretch = [
        line for line in timed
        if (stretch_start is None or line.hc >= stretch_start
            or _near(line.hc, stretch_start))
        and line.hc < out_time
    ]
    done = []
    if in_stretch:
        last = max(in_stretch, key=lambda line: line.hf)
        for line in in_stretch:
            if line is last or line.hf > out_time:
                if not _near(line.hf, out_time):
                    done.append("tarea %d: fin %s -> %s" % (
                        line.line_number, _fmt(line.hf), _fmt(out_time)))
                    line.hf = out_time

    # Pausa de comida = hueco entre tramos fichados; horas netas.
    lunch = lunch_from_stretches(stretches)
    with transaction.atomic():
        entry.lunch_break_start = lunch[0] if lunch else None
        entry.lunch_break_end = lunch[1] if lunch else None
        entry.no_lunch_break = lunch is None
        entry.save(update_fields=[
            "lunch_break_start", "lunch_break_end", "no_lunch_break",
        ])
        for line in timed:
            line.delta_hours = _net_hours(line.hc, line.hf, lunch)
            line.save(update_fields=["hf", "delta_hours"])

    # 2/3. ¿Cuadra con lo fichado?
    blocks = [
        TimeBlock(idx=line.line_number, hc=line.hc, hf=line.hf)
        for line in timed
    ]
    intra = run_intra_part_validation(
        blocks, lunch_window=None, allowed_gaps=allowed_gaps(stretches),
    )
    problems = [e.message for e in intra.errors]
    if not problems:
        problems = check_tasks(
            stretches, [(b.idx, b.hc, b.hf) for b in blocks], closing=True,
        ) + close_blockers(stretches)
    complete = [s for s in stretches if s.start and s.end]
    wait_second = is_split_shift(worker) and len(complete) < 2
    result = ""
    if work_order.status == WorkOrder.Status.DONE:
        if problems:
            work_order.status = WorkOrder.Status.IN_PROGRESS
            work_order.save(update_fields=["status"])
            result = "parte reabierto: ya no cuadra con lo fichado"
    elif not problems and not wait_second:
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
    elif wait_second and not problems:
        result = "jornada partida: se cerrará con la salida de la tarde"
    else:
        result = "parte abierto: no cuadra con lo fichado (%s)" % (
            problems[0])
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
    return result
