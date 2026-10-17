# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/hr_calendar/clock_parts.py
"""
Clock-in and work orders ("partes") together (H24, S129). Miguel
Ángel's business rules, verbatim where they matter:

1. Clocking IN touches no parte: "Cuando fichamos al entrar no puede
   haber ningún parte hecho, no hemos trabajado aún."
2. Clocking OUT: if that day's parte was already made (for the lunch
   break or before leaving) and does not match, the parte is adjusted:
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
        return {
            "start": self.start.strftime("%H:%M") if self.start else "",
            "end": self.end.strftime("%H:%M") if self.end else "",
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
            return previous.end, following.start
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
        (_minutes(a.end), _minutes(b.start))
        for a, b in zip(stretches, stretches[1:])
        if a.end and b.start
    ]


def _fmt(value):
    return value.strftime("%H:%M")


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
            if not closing:
                continue
            errors.append(
                "No hay ninguna tarea para lo fichado de %s." % stretch.label()
            )
            continue
        first, last = items[0], max(items, key=lambda t: t[2])
        if stretch.start and first[1] != stretch.start:
            errors.append(
                "La primera tarea de %s tiene que empezar a las %s, la "
                "hora de entrada fichada (la tarea %d empieza a las %s)."
                % (stretch.label(), _fmt(stretch.start), first[0],
                   _fmt(first[1]))
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
        if stretch.end and last[2] != stretch.end:
            errors.append(
                "La última tarea de %s tiene que terminar a las %s, la "
                "hora de salida fichada (la tarea %d termina a las %s)."
                % (stretch.label(), _fmt(stretch.end), last[0],
                   _fmt(last[2]))
            )
        if stretch.end and len(items) > 1:
            latest = _time_of(max(_minutes(stretch.end) - MIN_TASK_MINUTES,
                                  0))
            if last[1] > latest:
                errors.append(
                    "La última tarea de %s no puede empezar después de "
                    "las %s (media hora antes de la salida fichada)."
                    % (stretch.label(), _fmt(latest))
                )
        if stretch.start and len(items) > 1:
            earliest = _time_of(min(
                _minutes(stretch.start) + MIN_TASK_MINUTES, 23 * 60 + 59,
            ))
            if first[2] < earliest:
                errors.append(
                    "La primera tarea de %s no puede terminar antes de "
                    "las %s (media hora después de la entrada fichada)."
                    % (stretch.label(), _fmt(earliest))
                )
    return errors


# ------------------------------------------------------------------
# Clocking OUT adjusts a parte already made
# ------------------------------------------------------------------
def _net_hours(hc, hf, entry):
    gross = Decimal(_minutes(hf) - _minutes(hc)) / Decimal(60)
    if (
        not entry.no_lunch_break
        and entry.lunch_break_start and entry.lunch_break_end
    ):
        overlap = max(0, min(_minutes(hf), _minutes(entry.lunch_break_end))
                      - max(_minutes(hc), _minutes(entry.lunch_break_start)))
        gross -= Decimal(overlap) / Decimal(60)
    return max(gross, Decimal(0)).quantize(Decimal("0.01"))


def align_parte_to_clock_out(event):
    """
    After an OUT press: if that day's parte of the worker already
    exists, its tasks of the stretch closed by this OUT are made to
    end at the OUT time (last task ends exactly then; any task ending
    later is cut). Tasks that start at or after the OUT cannot be
    fixed automatically: the parte is marked for the supervisor. A
    reviewed parte is never touched, only marked. Every change is
    written in WorkOrder.clock_review_note. Returns that note ("" when
    nothing was done).
    ---
    Tras una SALIDA: si ya existe el parte de ese día del trabajador,
    sus tareas del tramo que cierra esta SALIDA pasan a terminar a la
    hora fichada (la última termina justo entonces; la que acabe más
    tarde se recorta). Las tareas que empiezan a esa hora o después no
    se pueden arreglar solas: el parte queda marcado para el
    supervisor. Un parte revisado nunca se toca, solo se marca. Cada
    cambio queda escrito en WorkOrder.clock_review_note. Devuelve esa
    nota ("" si no se hizo nada).
    """
    from work_order_processor.models import (
        WorkOrder,
        WorkOrderEntry,
        WorkOrderEntryLine,
    )

    if event.kind != ClockEvent.Kind.OUT:
        return ""
    work_date = timezone.localtime(event.pressed_at).date()
    out_time = _local_time(event.pressed_at)
    entry = (
        WorkOrderEntry.objects.select_related("work_order")
        .filter(
            work_order__uploaded_by=event.company_user,
            work_order__source__in=(
                WorkOrder.Source.DIGITAL, WorkOrder.Source.GENERATED,
            ),
            work_date=work_date,
        )
        .order_by("-work_order__upload_date").first()
    )
    if entry is None:
        return ""
    work_order = entry.work_order
    stretch_start = None
    later = []
    for stretch in day_stretches(event.company_user, work_date):
        if stretch.end == out_time:
            stretch_start = stretch.start
        elif stretch.start and stretch.start >= out_time:
            later.append(stretch)

    def _in_later(line):
        return any(
            line.hc >= s.start and (s.end is None or line.hf <= s.end)
            for s in later
        )

    lines = [
        line for line in WorkOrderEntryLine.objects.filter(entry=entry)
        .order_by("hc", "line_number")
        if line.hc and line.hf
        and (stretch_start is None or line.hc >= stretch_start)
    ]
    if not lines:
        return ""
    notes = []
    before = [line for line in lines if line.hc < out_time]
    # Tras la salida solo vale lo que cae en un tramo fichado posterior.
    after = [
        line for line in lines
        if line.hc >= out_time and not _in_later(line)
    ]
    last = max(before, key=lambda line: line.hf) if before else None
    changes = []
    if last is not None and last.hf != out_time:
        changes.append((last, last.hf))
    for line in before:
        if line is not last and line.hf > out_time:
            changes.append((line, line.hf))
    if after:
        notes.append(
            "Salida fichada a las %s: la(s) tarea(s) %s empieza(n) a esa "
            "hora o después; hay que corregir el parte." % (
                _fmt(out_time),
                ", ".join(str(line.line_number) for line in after),
            )
        )
    if work_order.reviewed:
        if changes or after:
            notes.insert(0, "Parte ya revisado: no se ha cambiado nada.")
            changes = []
        else:
            return ""
    with transaction.atomic():
        for line, old_hf in changes:
            line.hf = out_time
            line.delta_hours = _net_hours(line.hc, out_time, entry)
            line.save(update_fields=["hf", "delta_hours"])
            notes.append(
                "Salida fichada a las %s: la tarea %d terminaba a las %s "
                "y ahora termina a las %s."
                % (_fmt(out_time), line.line_number, _fmt(old_hf),
                   _fmt(out_time))
            )
        if not notes:
            return ""
        stamp = timezone.localtime().strftime("%d/%m/%Y %H:%M")
        text = "\n".join("[%s] %s" % (stamp, note) for note in notes)
        work_order.clock_review_note = (
            (work_order.clock_review_note + "\n" + text).strip()
        )
        work_order.save(update_fields=["clock_review_note"])
    logger.info(
        "# [FICHAJE-PARTE] WorkOrder #%d (usuario #%d, %s): %s",
        work_order.pk, event.company_user_id, work_date, text.replace(
            "\n", " | "),
    )
    if changes and work_order.status == WorkOrder.Status.DONE:
        try:
            from work_order_processor.services import (
                generate_work_order_excel,
            )
            generate_work_order_excel(work_order.pk)
        except Exception:
            logger.exception(
                "# [FICHAJE-PARTE] No se pudo regenerar el Excel del "
                "WorkOrder #%d tras ajustarlo a la salida.", work_order.pk,
            )
    return text
