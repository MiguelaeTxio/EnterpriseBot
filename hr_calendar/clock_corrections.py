# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/hr_calendar/clock_corrections.py
"""
Corrections of clock presses (H24, S141).

Miguel Ángel (S141): the records cannot be modified, and when one is
modified a history must keep who did it and why, so that the clock-in
program could be certified. A press is never touched: a change creates
a new press (sent_by CORRECTION) that replaces it and a cancellation
leaves it out of the reports; the ClockCorrection row keeps who, when,
the old and new values and the reason.

---

Correcciones de fichajes (H24, S141).

Miguel Ángel (S141): los registros no se pueden modificar y, si se
modifican, tiene que quedar un historial de quién y por qué, para que
el programa de fichaje pueda certificarse. La pulsación no se toca
nunca: un cambio crea una pulsación nueva (sent_by CORRECTION) que la
sustituye y una anulación la deja fuera de los informes; la fila de
ClockCorrection guarda quién, cuándo, el valor anterior, el nuevo y el
motivo.
"""
import uuid
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from hr_calendar.models import ClockCorrection
from hr_calendar.models import ClockEvent
from hr_calendar.models import ClockType

MAX_REASON = 1000


class ClockCorrectionError(Exception):
    """
    The correction is not valid; the message is for the user.
    ---
    La corrección no es válida; el mensaje es para el usuario.
    """


def correct_event(event_id, corrected_by, action, reason, new_kind="",
                  new_pressed_at=None, user_agent="", new_clock_type_id=None,
                  new_location=None):
    """
    Correct one current press. Returns the ClockCorrection.

    ---

    Corrige una pulsación vigente y devuelve la ClockCorrection.
    - CHANGE: hora y/o tipo nuevos; crea la pulsación que la sustituye.
    - CANCEL: la anula; queda fuera de los informes.
    El motivo es obligatorio. Solo se corrigen pulsaciones de la misma
    empresa que quien corrige y que no tengan ya una corrección (para
    corregir otra vez se corrige la pulsación nueva).
    S141: `new_clock_type_id` es el tipo de fichaje de la pulsación nueva
    (entrada o cambio de tipo); la salida nunca lleva tipo.
    S147 (Miguel Ángel): `new_location` = (lat, lon) rectifica la
    ubicación con el mapa; queda en la pulsación nueva (la original
    conserva la suya) y en el historial, como el resto.
    """
    reason = (reason or "").strip()[:MAX_REASON]
    if not reason:
        raise ClockCorrectionError("El motivo de la corrección es "
                                   "obligatorio.")
    if action not in (ClockCorrection.Action.CHANGE,
                      ClockCorrection.Action.CANCEL):
        raise ClockCorrectionError("Corrección no válida.")
    with transaction.atomic():
        event = ClockEvent.objects.select_for_update().filter(
            pk=event_id, company=corrected_by.company,
        ).first()
        if event is None:
            raise ClockCorrectionError("No existe ese fichaje.")
        if ClockCorrection.objects.filter(event=event).exists():
            raise ClockCorrectionError(
                "Ese fichaje ya está corregido; corrija el que lo "
                "sustituye."
            )
        replacement = None
        if action == ClockCorrection.Action.CHANGE:
            if new_kind not in ClockEvent.Kind.values:
                raise ClockCorrectionError("Indique si es entrada o "
                                           "salida.")
            if new_pressed_at is None:
                raise ClockCorrectionError("Indique la hora correcta.")
            new_pressed_at = new_pressed_at.replace(second=0,
                                                    microsecond=0)
            new_clock_type = _clock_type(event, new_kind, new_clock_type_id)
            if (new_kind == event.kind
                    and new_clock_type == event.clock_type
                    and new_location is None
                    and new_pressed_at
                    == event.pressed_at.replace(second=0, microsecond=0)):
                raise ClockCorrectionError("La corrección no cambia nada.")
            replacement = ClockEvent.objects.create(
                company=event.company,
                company_user=event.company_user,
                person=event.person,
                kind=new_kind,
                client_id="corr-%s" % uuid.uuid4().hex,
                pressed_at=new_pressed_at,
                sent_by=ClockEvent.SentBy.CORRECTION,
                user_agent=(user_agent or "")[:200],
                clock_type=new_clock_type,
                **_location_fields(new_location,
                                   "Corrección del supervisor"),
                # S143: la corrección conserva "No he parado para comer".
                no_meal_break=event.no_meal_break,
            )
        else:
            new_kind, new_pressed_at, new_clock_type = "", None, None
        return ClockCorrection.objects.create(
            event=event,
            action=action,
            replacement=replacement,
            old_kind=event.kind,
            old_pressed_at=event.pressed_at,
            new_kind=new_kind,
            new_pressed_at=new_pressed_at,
            old_clock_type=event.clock_type,
            new_clock_type=new_clock_type,
            reason=reason,
            corrected_by=corrected_by,
            user_agent=(user_agent or "")[:200],
        )


def add_event(company_user, person, corrected_by, new_kind, new_pressed_at,
              reason, user_agent="", new_clock_type_id=None,
              new_location=None):
    """
    Add a press the worker did not make. Returns the ClockCorrection.

    ---

    Añade una pulsación que el trabajador no hizo (S144, Miguel Ángel):
    sobre todo un cambio de tipo para partir un tramo que se fichó
    entero como presencia o desplazamiento ("hay que editar esos
    tramos"), y también una entrada o una salida que falta. Como el
    resto de correcciones, no toca ninguna pulsación: crea la nueva
    (sent_by CORRECTION) y la ClockCorrection con quién, cuándo y el
    motivo (obligatorio), sin fichaje corregido ni valor anterior.
    """
    reason = (reason or "").strip()[:MAX_REASON]
    if not reason:
        raise ClockCorrectionError("El motivo de la corrección es "
                                   "obligatorio.")
    if company_user is None or company_user.company_id != (
            corrected_by.company_id):
        raise ClockCorrectionError("Ese trabajador no tiene usuario del "
                                   "panel en esta empresa.")
    if new_kind not in ClockEvent.Kind.values:
        raise ClockCorrectionError("Indique si es entrada, salida o "
                                   "cambio de tipo.")
    if new_pressed_at is None:
        raise ClockCorrectionError("Indique la fecha y la hora.")
    new_pressed_at = new_pressed_at.replace(second=0, microsecond=0)
    probe = ClockEvent(company=company_user.company)
    new_clock_type = _clock_type(probe, new_kind, new_clock_type_id)
    with transaction.atomic():
        added = ClockEvent.objects.create(
            company=company_user.company,
            company_user=company_user,
            person=person,
            kind=new_kind,
            client_id="add-%s" % uuid.uuid4().hex,
            pressed_at=new_pressed_at,
            sent_by=ClockEvent.SentBy.CORRECTION,
            user_agent=(user_agent or "")[:200],
            clock_type=new_clock_type,
            **_location_fields(new_location, "Añadido por el supervisor"),
        )
        return ClockCorrection.objects.create(
            event=None,
            action=ClockCorrection.Action.ADD,
            replacement=added,
            old_kind="",
            old_pressed_at=None,
            new_kind=new_kind,
            new_pressed_at=new_pressed_at,
            old_clock_type=None,
            new_clock_type=new_clock_type,
            reason=reason,
            corrected_by=corrected_by,
            user_agent=(user_agent or "")[:200],
        )


def _location_fields(location, no_location_note):
    """
    Press fields for a location set on the map (or nothing).
    ---
    Campos de la pulsación para la ubicación marcada en el mapa (S147);
    sin ubicación, sin posición y con `no_location_note`, como antes.
    """
    if location is None:
        return {"gps_error": no_location_note}
    return {
        "latitude": Decimal("%.6f" % location[0]),
        "longitude": Decimal("%.6f" % location[1]),
        "accuracy_m": None,
        "gps_error": "Ubicación rectificada en el mapa por el supervisor",
    }


def _clock_type(event, new_kind, clock_type_id):
    """
    The ClockType of the replacement press, or None.
    ---
    El tipo de fichaje de la pulsación nueva, o None. Una salida no lleva
    tipo; un cambio de tipo lo necesita. Debe ser un tipo de la empresa
    (activo, o el mismo que ya tenía la pulsación).
    """
    if new_kind == ClockEvent.Kind.OUT or clock_type_id in (None, ""):
        if new_kind == ClockEvent.Kind.CHANGE:
            raise ClockCorrectionError("Un cambio de tipo tiene que indicar "
                                       "el tipo de fichaje.")
        return None
    try:
        pk = int(clock_type_id)
    except (TypeError, ValueError):
        raise ClockCorrectionError("El tipo de fichaje no es válido.")
    clock_type = ClockType.objects.filter(
        pk=pk, company=event.company,
    ).first()
    if clock_type is None or not (clock_type.is_active
                                  or clock_type.pk == event.clock_type_id):
        raise ClockCorrectionError("El tipo de fichaje no es válido.")
    return clock_type


def meal_break(company_user, person, corrected_by, reason, start, end,
               out_event_id=None, back_event_id=None, entry_event_id=None,
               user_agent=""):
    """
    Add or change the meal break of a shift. Returns how many presses.

    ---

    Añade o corrige la pausa de comida de una jornada (S149, Miguel
    Ángel: "poder modificar la pausa de comida, añadirla,
    modificarla"). Como el resto de correcciones, ninguna pulsación se
    toca: quedan quién, cuándo, antes, después y el motivo.
    - Corregir (`out_event_id` y `back_event_id`): la pulsación que
      empieza la pausa (salida a comer, o el cambio a "Pausa para
      comer") pasa a `start` y la que la acaba (vuelta, o el cambio de
      vuelta) a `end`, cada una con su tipo de siempre.
    - Añadir (`entry_event_id`, la entrada de la jornada): sin tipos, una
      salida a `start` y una entrada a `end`; con tipos, un cambio a
      "Pausa para comer" a `start` y otro de vuelta, al tipo que llevaba,
      a `end`. La pausa cae dentro de la jornada y sin otra pulsación
      en medio. Con la jornada abierta (sin salida todavía), la vuelta
      tiene que ser anterior a ahora (Miguel Ángel, mismo día).
    """
    if start is None or end is None:
        raise ClockCorrectionError("Indique el principio y el final de la "
                                   "pausa.")
    start = start.replace(second=0, microsecond=0)
    end = end.replace(second=0, microsecond=0)
    if end <= start:
        raise ClockCorrectionError("La pausa tiene que acabar después de "
                                   "empezar.")
    if company_user is None:
        raise ClockCorrectionError("Ese trabajador no tiene usuario del "
                                   "panel en esta empresa.")
    events = ClockEvent.objects.current().filter(
        company_user=company_user)
    with transaction.atomic():
        if out_event_id and back_event_id:
            pair = [(events.filter(pk=out_event_id).first(), start),
                    (events.filter(pk=back_event_id).first(), end)]
            if any(event is None for event, _when in pair):
                raise ClockCorrectionError("Esa pausa ya no está; vuelva a "
                                           "cargar la página.")
            changed = 0
            for event, when in pair:
                if event.pressed_at.replace(second=0, microsecond=0) \
                        == when:
                    continue
                correct_event(
                    event.pk, corrected_by, ClockCorrection.Action.CHANGE,
                    reason, new_kind=event.kind, new_pressed_at=when,
                    user_agent=user_agent,
                    new_clock_type_id=event.clock_type_id,
                )
                changed += 1
            if not changed:
                raise ClockCorrectionError("La corrección no cambia nada.")
            return changed
        entry = events.filter(pk=entry_event_id,
                              kind=ClockEvent.Kind.IN).first()
        if entry is None:
            raise ClockCorrectionError("Esa jornada ya no está; vuelva a "
                                       "cargar la página.")
        after = list(events.filter(
            pressed_at__gt=entry.pressed_at).order_by("pressed_at"))
        exit_ = next((e for e in after if e.kind == ClockEvent.Kind.OUT),
                     None)
        limit = exit_.pressed_at if exit_ is not None else timezone.now()
        if not entry.pressed_at < start or not end < limit:
            raise ClockCorrectionError(
                "La pausa tiene que caer dentro de la jornada."
                if exit_ is not None else
                "La pausa tiene que caer dentro de la jornada y acabar "
                "antes de ahora.")
        inside = [e for e in after if e.pressed_at < limit]
        if any(start <= e.pressed_at <= end for e in inside):
            raise ClockCorrectionError("Hay otra pulsación en medio de "
                                       "esa pausa: corrija esa.")
        if entry.clock_type_id is None:
            steps = [(ClockEvent.Kind.OUT, start, None),
                     (ClockEvent.Kind.IN, end, None)]
        else:
            meal = ClockType.objects.filter(
                company=company_user.company, role=ClockType.ROLE_MEAL,
                is_active=True,
            ).order_by("order", "name").first()
            if meal is None:
                raise ClockCorrectionError("No hay ningún tipo de fichaje "
                                           "«Pausa para comer» activo.")
            current = [entry] + [e for e in inside if e.pressed_at < start]
            back_type = current[-1].clock_type_id
            steps = [(ClockEvent.Kind.CHANGE, start, meal.pk),
                     (ClockEvent.Kind.CHANGE, end, back_type)]
        for kind, when, type_id in steps:
            add_event(company_user, person, corrected_by, kind, when,
                      reason, user_agent=user_agent,
                      new_clock_type_id=type_id)
        return len(steps)
