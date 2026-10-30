# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/whatsapp/management/commands/create_clock_reminder_link_whatsapp_templates.py
"""
H24 (S141). Creates in Twilio, submits to Meta approval and registers
in the database the clock reminder templates with a button that opens
the clocking page.

---

H24 (S141). Crea en Twilio, somete a aprobación de Meta y registra en
BD las plantillas de recordatorio de fichaje con un botón «Fichar
ahora» que abre la página de fichaje (Miguel Ángel, S141: el aviso de
la sala trae botón y el del fichaje no). Son plantillas nuevas
(`clock_in_reminder_link`, `clock_out_reminder_link`): las de texto
plano siguen en uso hasta que Meta apruebe estas
(hr_calendar/clock_reminders.py).

Mismo alta que create_assistance_albaran_whatsapp_template (S132):
`twilio/call-to-action`, categoría UTILITY, idempotente en BD y log
propio (`--log-file`). La URL del botón es fija (la página de fichaje
es la misma para todos), sin variable.
"""
from django.conf import settings

from whatsapp.management.commands import (
    create_document_notice_whatsapp_templates as notice_templates,
)

CLOCKIN_PATH = "/fichaje/"

_SAMPLE = {
    "1": "Juan",
    "2": "29/10",
    "3": "08:00",
}

_BODIES = {
    "clock_in_reminder_link": (
        notice_templates._PREAMBLE
        + "Hoy {{2}} su hora de entrada es a las {{3}} y no consta que "
        "haya fichado la entrada. Si ya está trabajando, fiche la "
        "entrada ahora con el botón de este mensaje; si se le olvidó, "
        "haga un fichaje manual con la hora real."
    ),
    "clock_out_reminder_link": (
        notice_templates._PREAMBLE
        + "Hoy {{2}} su hora de salida es a las {{3}} y no consta que "
        "haya fichado la salida. Si ya ha terminado, fiche la salida "
        "ahora con el botón de este mensaje; si se le olvidó, haga un "
        "fichaje manual con la hora real."
    ),
}


def _definitions():
    """
    Template definitions, with the platform URL.

    ---

    Definiciones de las plantillas, con la URL de la plataforma
    (`settings.PLATFORM_BASE_URL`).
    """
    url = settings.PLATFORM_BASE_URL + CLOCKIN_PATH
    result = []
    for name, body in _BODIES.items():
        sample = dict(_SAMPLE)
        if name == "clock_out_reminder_link":
            sample["3"] = "18:00"
        result.append({
            "name": name,
            "variables": sample,
            "types": {
                "twilio/call-to-action": {
                    "body": body,
                    "actions": [
                        {"type": "URL", "title": "Fichar ahora",
                         "url": url},
                    ],
                },
            },
        })
    return result


class Command(notice_templates.Command):
    """
    Create and submit the clock reminder templates with a button.

    ---

    Crea y somete a aprobación las plantillas de recordatorio de
    fichaje con botón.
    """

    help = (
        "Crea y somete a aprobacion de Meta las plantillas WhatsApp "
        "clock_in_reminder_link y clock_out_reminder_link (H24, S141); "
        "las que ya están en BD no se tocan."
    )
    start_message = (
        "Inicio: alta de las plantillas de recordatorio de fichaje con "
        "botón."
    )

    @property
    def templates(self):
        """
        Templates to create.

        ---

        Plantillas a crear.
        """
        return _definitions()
