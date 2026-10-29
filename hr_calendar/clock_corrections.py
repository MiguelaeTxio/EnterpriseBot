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

MAX_REASON = 1000


class ClockCorrectionError(Exception):
    """
    The correction is not valid; the message is for the user.
    ---
    La corrección no es válida; el mensaje es para el usuario.
    """


def correct_event(event_id, corrected_by, action, reason, new_kind="",
                  new_pressed_at=None, user_agent=""):
    """
    Correct one current press. Returns the ClockCorrection.

    ---

    Corrige una pulsación vigente y devuelve la ClockCorrection.
    - CHANGE: hora y/o tipo nuevos; crea la pulsación que la sustituye.
    - CANCEL: la anula; queda fuera de los informes.
    El motivo es obligatorio. Solo se corrigen pulsaciones de la misma
    empresa que quien corrige y que no tengan ya una corrección (para
    corregir otra vez se corrige la pulsación nueva).
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
            if (new_kind == event.kind and new_pressed_at
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
            )
        else:
            new_kind, new_pressed_at = "", None
        return ClockCorrection.objects.create(
            event=event,
            action=action,
            replacement=replacement,
            old_kind=event.kind,
            old_pressed_at=event.pressed_at,
            new_kind=new_kind,
            new_pressed_at=new_pressed_at,
            reason=reason,
            corrected_by=corrected_by,
            user_agent=(user_agent or "")[:200],
        )
