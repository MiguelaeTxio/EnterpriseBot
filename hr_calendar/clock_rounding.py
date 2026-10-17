# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/hr_calendar/clock_rounding.py
"""
Rounding of a clock-in press to the whole or half hour the parte uses
(H24, S129). The press is always stored exact (ClockEvent.pressed_at);
the rounded time is stored too (ClockEvent.rounded_at) and the parte
must match it exactly -- the parte's times are whole and half hours.

Miguel Ángel's rule (S129): within ±5 minutes of a whole or half hour,
that one ("25 está dentro [...] 54 fuera y 55 dentro"); further away,
an OUT goes to the previous half hour and an IN to the next one, so
neither counts time not worked. Examples: IN 8:04 -> 8:00, IN 8:20 ->
8:30, IN 7:55 -> 8:00; OUT 13:56 -> 14:00, OUT 13:50 -> 13:30, OUT
13:25 -> 13:30. Never across midnight (an IN at 23:40 stays 23:30).

---

Redondeo de una pulsación de fichaje a la hora o media hora que usa el
parte (H24, S129). La pulsación se guarda siempre exacta (pressed_at);
también se guarda la redondeada (rounded_at) y el parte tiene que
coincidir con ella exactamente.

Regla de Miguel Ángel (S129): a ±5 minutos o menos de una hora o media,
esa ("25 está dentro [...] 54 fuera y 55 dentro"); más lejos, la SALIDA
va a la media hora anterior y la ENTRADA a la siguiente, para que
ninguna cuente tiempo no trabajado. Ejemplos arriba. Nunca cruza la
medianoche.
"""
import datetime

TOLERANCE_MINUTES = 5


def round_local(value, kind):
    """
    The rounded local datetime of a local datetime; kind "IN" or "OUT".
    ---
    El datetime local redondeado de un datetime local; kind "IN" u
    "OUT".
    """
    value = value.replace(second=0, microsecond=0)
    past = value.minute % 30
    floor = value - datetime.timedelta(minutes=past)
    ceil = floor + datetime.timedelta(minutes=30)
    if past <= TOLERANCE_MINUTES:
        return floor
    if 30 - past <= TOLERANCE_MINUTES or kind == "IN":
        return ceil if ceil.date() == value.date() else floor
    return floor


def round_pressed_at(pressed_at, kind):
    """
    rounded_at for a stored (aware) pressed_at, in local time.
    ---
    rounded_at para un pressed_at guardado (con zona), en hora local.
    """
    from django.utils import timezone

    return round_local(timezone.localtime(pressed_at), kind)
