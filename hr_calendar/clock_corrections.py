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

from django.db import transaction

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
                  new_pressed_at=None, user_agent="", new_clock_type_id=None):
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
    """
    reason = (reason or "").strip()[:MAX_REASON]
    if not reason:
        raise ClockCorrectionError("El motivo de la corrección es "
                                   "obligatorio.")
    if action not in ClockCorrection.Action.values:
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
                gps_error="Corrección del supervisor",
                sent_by=ClockEvent.SentBy.CORRECTION,
                user_agent=(user_agent or "")[:200],
                clock_type=new_clock_type,
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
