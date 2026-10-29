# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/whatsapp/management/commands/create_clock_reminder_whatsapp_templates.py
"""
H24 (S141). Creates in Twilio, submits to Meta approval and registers
in the database the two WhatsApp templates of the forgotten clock
press reminders.

---

H24 (S141). Crea en Twilio, somete a aprobación de Meta y registra en
BD las dos plantillas de WhatsApp de los recordatorios de fichaje
(hr_calendar/clock_reminders.py). Decisión de Miguel Ángel (S141): dos
plantillas, una para el olvido de la entrada y otra para el de la
salida.

Reutiliza íntegro el alta de create_document_notice_whatsapp_templates
(S122): `requests` crudo contra la Content API, texto plano, categoría
UTILITY, saludo al principio y texto al final (nunca una variable al
principio ni al final, ni dos seguidas), idempotente a nivel de BD y
log propio.
"""
from whatsapp.management.commands import (
    create_document_notice_whatsapp_templates as notice_templates,
)

_SAMPLE = {
    "1": "Juan",
    "2": "29/10",
    "3": "08:00",
}

TEMPLATES = [
    {
        "name": "clock_in_reminder",
        "body": (
            notice_templates._PREAMBLE
            + "Hoy {{2}} su hora de entrada es a las {{3}} y no consta "
            "que haya fichado la entrada. Si ya está trabajando, fiche "
            "la entrada ahora; si se le olvidó, haga un fichaje manual "
            "con la hora real."
        ),
        "variables": _SAMPLE,
    },
    {
        "name": "clock_out_reminder",
        "body": (
            notice_templates._PREAMBLE
            + "Hoy {{2}} su hora de salida es a las {{3}} y no consta "
            "que haya fichado la salida. Si ya ha terminado, fiche la "
            "salida ahora; si se le olvidó, haga un fichaje manual con "
            "la hora real."
        ),
        "variables": dict(_SAMPLE, **{"3": "18:00"}),
    },
]


class Command(notice_templates.Command):
    """
    Create and submit the two clock reminder templates.

    ---

    Crea y somete a aprobación las dos plantillas de recordatorio de
    fichaje.
    """

    help = (
        "Crea y somete a aprobacion de Meta las plantillas WhatsApp "
        "clock_in_reminder y clock_out_reminder (H24, S141); las que ya "
        "están en BD no se tocan."
    )
    templates = TEMPLATES
    start_message = (
        "Inicio: alta de las plantillas de recordatorio de fichaje."
    )
