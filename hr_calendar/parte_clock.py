# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/hr_calendar/parte_clock.py
"""
Clock-in days corrected from the worker's digital work order (H24,
S153), the same way the crane drivers' days are corrected from their
delivery notes (hr_calendar/albaran_check.py).

---

Fichajes corregidos con el parte de trabajo del trabajador (H24, S153).
Miguel Ángel: "he supeditado la realización de los partes a los
fichajes, y eso ha sido un error [...] los fichajes se van a
autocorregir con los partes de trabajo existentes y van a quedar
marcados como corregidos por el parte de trabajo del trabajador [...]
exactamente igual que hacemos con los albaranes de trabajo de personal
de grúas. Como aquí no tenemos que subir nada, conforme tengamos parte y
fichaje, automáticamente corregimos el fichaje".

Los partes ya no dependen de los fichajes (hr_calendar/clock_parts.py,
PARTES_FOLLOW_CLOCK). Al revés: con el parte digital cerrado de un día,
la jornada fichada se compara con él y se corrige lo que se aparte más
que los minutos de cortesía del horario:

- la entrada, a la hora de inicio de la primera tarea;
- la salida, a la hora de fin de la última;
- si el parte tiene pausa de comida, la salida a comer y la vuelta a sus
  horas;
- lo fichado de más se anula.

Las correcciones quedan con origen «Parte de trabajo», a nombre del
trabajador del parte, y el día como «Corregido por el parte» (o
«Comparado con el parte» si cuadraba), sin visar: el visado sigue siendo
del supervisor. Solo el periodo de pago en curso (del 21 al 20): lo de
periodos ya pagados no se toca. Solo jornadas sin tipos de fichaje (los
mecánicos); quien ficha con tipos no hace partes.

Cuándo: al cerrar el parte (panel/views_operator.py), con cada fichaje
del trabajador (ese día y el anterior; hr_calendar/clock_parts.py) y con
el comando correct_clock_from_partes_s153 para lo ya hecho. Un día se
corrige solo cuando ya ha pasado la hora de fin de su parte.
"""
import datetime
import logging
from dataclasses import dataclass, field

from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)

PERIOD_START_DAY = 21


@dataclass
class ParteCheck:
    """Outcome of one day / Resultado de un día."""

    day: datetime.date
    corrected: bool = False
    lines: list = field(default_factory=list)
    skipped: str = ""

    @property
    def text(self):
        return self.skipped or " ".join(self.lines)


def period_start(today=None):
    """
    First day of the pay period in progress (the 21st).
    ---
    Primer día del periodo de pago en curso: del 21 de un mes al 20 del
    siguiente.
    """
    today = today or timezone.localdate()
    if today.day >= PERIOD_START_DAY:
        return today.replace(day=PERIOD_START_DAY)
    first = today.replace(day=1) - datetime.timedelta(days=1)
    return first.replace(day=PERIOD_START_DAY)


def day_partes(company_user, day):
    """
    The worker's closed digital partes of a day, with entries and lines.
    ---
    Los partes digitales cerrados del trabajador ese día.
    """
    from work_order_processor.models import WorkOrder, WorkOrderEntry

    return list(WorkOrderEntry.objects.filter(
        work_date=day, work_order__uploaded_by=company_user,
        work_order__source=WorkOrder.Source.DIGITAL,
        work_order__status=WorkOrder.Status.DONE,
    ).select_related("work_order").prefetch_related("lines"))


def expected_presses(entries):
    """
    The day as the parte tells it: [(kind, time)] in order, or [].
    ---
    La jornada según el parte: entrada al empezar la primera tarea,
    salida a comer y vuelta si tiene pausa de comida dentro de la
    jornada, y salida al acabar la última tarea.
    """
    tasks = [(line.hc, line.hf) for entry in entries
             for line in entry.lines.all() if line.hc and line.hf]
    if not tasks:
        return []
    start = min(hc for hc, _hf in tasks)
    end = max(hf for _hc, hf in tasks)
    points = [("IN", start)]
    for entry in entries:
        lunch_start, lunch_end = entry.lunch_break_start, \
            entry.lunch_break_end
        if (not entry.no_lunch_break and lunch_start and lunch_end
                and start < lunch_start < lunch_end < end):
            points += [("OUT", lunch_start), ("IN", lunch_end)]
            break
    points.append(("OUT", end))
    return points


def _day_events(company_user, start):
    from hr_calendar.models import ClockEvent

    return list(ClockEvent.objects.current().filter(
        company_user=company_user, pressed_at__gte=start,
        pressed_at__lt=start + datetime.timedelta(days=1),
    ).order_by("pressed_at", "pk"))


def _label(kind):
    return {"IN": "Entrada", "OUT": "Salida", "CHG": "Cambio de tipo"}.get(
        kind, kind)


def correct_day(company_user, day, now=None, dry_run=False):
    """
    Correct one day's presses from its closed parte. Returns ParteCheck.
    ---
    Corrige los fichajes de un día con su parte cerrado y deja el día
    marcado. Devuelve un ParteCheck (skipped = por qué no se miró). Con
    dry_run solo dice qué haría.
    """
    from hr_calendar.albaran_check import tolerance_minutes
    from hr_calendar.clock_corrections import (
        ClockCorrectionError, edit_presses,
    )
    from hr_calendar.models import ClockCorrection, ClockDayAiCheck

    result = ParteCheck(day)
    if company_user is None or day is None:
        result.skipped = "Sin trabajador."
        return result
    if day < period_start():
        result.skipped = "Periodo de pago ya cerrado: no se toca."
        return result
    entries = day_partes(company_user, day)
    wanted = expected_presses(entries)
    if not wanted:
        result.skipped = "Sin parte cerrado con tareas."
        return result
    tz = timezone.get_current_timezone()

    def aware(t):
        return timezone.make_aware(datetime.datetime.combine(day, t), tz)

    now = now or timezone.now()
    if now < aware(wanted[-1][1]):
        result.skipped = "La jornada del parte aún no ha terminado."
        return result
    start = aware(datetime.time.min)
    events = _day_events(company_user, start)
    if not events:
        result.skipped = "Sin fichajes ese día."
        return result
    if any(e.kind == "CHG" or e.clock_type_id for e in events):
        result.skipped = "Ficha con tipos: se compara con sus albaranes."
        return result
    tolerance = tolerance_minutes(company_user)
    tolerance_delta = datetime.timedelta(minutes=tolerance)
    numbers = ", ".join("nº %d" % pk for pk in sorted(
        {e.work_order_id for e in entries}))
    rows, used = [], set()
    targets = [(k, aware(t)) for k, t in wanted]
    # Primero la entrada y la salida de la jornada, luego la comida: la
    # salida fichada al final del día es la salida, no la de comer.
    order = [targets[0], targets[-1]] + targets[1:-1]
    for kind, at in order:
        options = [e for e in events if e.pk not in used and e.kind == kind]
        options.sort(key=lambda e: abs((e.pressed_at - at).total_seconds()))
        match = options[0] if options else None
        if match is None:
            rows.append({"id": None, "kind": kind, "at": at, "type": None})
            result.lines.append("Añadida: %s a las %s." % (
                _label(kind).lower(), timezone.localtime(at).strftime(
                    "%H:%M")))
            continue
        used.add(match.pk)
        if abs(match.pressed_at - at) <= tolerance_delta:
            rows.append({"id": match.pk, "kind": kind,
                         "at": match.pressed_at, "type": None})
            continue
        rows.append({"id": match.pk, "kind": kind, "at": at, "type": None})
        result.lines.append("Corregida: %s de las %s a las %s." % (
            _label(kind).lower(),
            timezone.localtime(match.pressed_at).strftime("%H:%M"),
            timezone.localtime(at).strftime("%H:%M")))
    rows.sort(key=lambda row: row["at"])
    for event in events:
        if event.pk not in used:
            rows.append({"id": event.pk, "delete": True})
            result.lines.append("Anulada: %s de las %s (no está en el "
                                "parte)." % (_label(event.kind).lower(),
                                             timezone.localtime(
                                                 event.pressed_at).strftime(
                                                 "%H:%M")))
    owner = entries[0].work_order.uploaded_by
    if dry_run:
        result.corrected = bool(result.lines)
        return result
    if result.lines:
        reason = ("Corrección según el parte de trabajo %s (cortesía %d "
                  "min)." % (numbers, tolerance))
        try:
            with transaction.atomic():
                edit_presses(company_user, events[0].person, owner, reason,
                             rows, source=ClockCorrection.Source.PARTE)
            result.corrected = True
        except ClockCorrectionError as exc:
            result.lines.insert(0, "No se ha podido corregir: %s" % exc)
    else:
        result.lines.append("Coincide con el parte (dentro de %d min)."
                            % tolerance)
    existing = ClockDayAiCheck.objects.filter(
        company_user=company_user, day=day).first()
    parte_origin = ClockDayAiCheck.Origin.PARTE
    if existing is not None and existing.origin != parte_origin:
        # El día ya lo comparó la IA con albaranes: no se pisa.
        return result
    if existing is not None and not result.corrected and existing.corrected:
        # Ya corregido antes por el parte y ahora cuadra: sigue corregido.
        return result
    ClockDayAiCheck.objects.update_or_create(
        company_user=company_user, day=day,
        defaults={"batch": None, "checked_by": owner,
                  "corrected": result.corrected,
                  "origin": parte_origin,
                  "albaranes": ("Parte %s" % numbers)[:255],
                  "summary": "\n".join(result.lines)},
    )
    return result


def correct_after_press(event):
    """
    After a press: correct that day and the one before from their partes.
    ---
    Tras un fichaje: corrige ese día y el anterior con sus partes (el
    anterior, por si el parte se cerró antes de la salida).
    """
    day = timezone.localtime(event.pressed_at).date()
    for target in (day - datetime.timedelta(days=1), day):
        try:
            correct_day(event.company_user, target)
        except Exception:  # noqa: BLE001 -- un fallo no para el fichaje
            logger.exception("# [PARTE-FICHAJE] Fallo al corregir el %s "
                             "del usuario #%s.", target,
                             event.company_user_id)


def correct_from_work_order(work_order):
    """
    After closing a parte: correct the days it covers.
    ---
    Al cerrar un parte: corrige los días que cubre. Devuelve los
    ParteCheck.
    """
    if work_order.uploaded_by is None:
        return []
    days = sorted(set(work_order.entries.values_list("work_date",
                                                     flat=True)))
    return [correct_day(work_order.uploaded_by, day) for day in days if day]
