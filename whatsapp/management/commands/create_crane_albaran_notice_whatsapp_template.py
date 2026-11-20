# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/whatsapp/management/commands/create_crane_albaran_notice_whatsapp_template.py
"""
H11 (S162). Creates in Twilio, submits to Meta approval and registers
in the database the WhatsApp template of the crane work order, with a
button that opens the albarán in the clock-in app.

---

H11 (S162). Crea en Twilio, somete a aprobación de Meta y registra en
BD la plantilla `crane_albaran_notice`: la orden de trabajo del
gruista (número, fecha y hora, obra y cliente, máquina) con un botón
que abre el albarán en la aplicación de fichaje. Se da de alta ya para
que esté aprobada cuando la dirección autorice los albaranes; mientras
LOCATION_ONLY_NOTICE siga activo, no se usa
(crane_albaranes.services.send_worker_notice).

Reutiliza el alta de create_document_notice_whatsapp_templates (S122):
`requests` crudo contra la Content API, categoría UTILITY, idempotente
en BD y log en pantalla y en archivo a la vez (`--log-file`). Tipo
`twilio/call-to-action`: la variable del botón va al final de la URL,
como exige WhatsApp, y lleva el resto de la ruta (`<token>/`).
"""
from django.conf import settings

from crane_albaranes.services import NOTICE_TEMPLATE_NAME
from whatsapp.management.commands import (
    create_document_notice_whatsapp_templates as notice_templates,
)

WORKER_PATH = "/fichaje/albaranes/"
BODY = (
    notice_templates._PREAMBLE
    + "Tiene la orden de trabajo {{2}} para el {{3}}: {{4}}, maquina "
    "{{5}}. Abra el albaran con el boton de este mensaje para "
    "rellenarlo."
)


def _definition():
    """
    Template definition, with the platform URL.

    ---

    Definición de la plantilla, con la URL de la plataforma
    (`settings.PLATFORM_BASE_URL`, la misma que usa `worker_url()`).
    """
    return {
        "name": NOTICE_TEMPLATE_NAME,
        "variables": {
            "1": "Juan",
            "2": "D000001",
            "3": "21/11/2026 07:30",
            "4": "Subestacion Axarquia (Construcciones del Sur, S.L.)",
            "5": "A-65",
            "6": "abc123/",
        },
        "types": {
            "twilio/call-to-action": {
                "body": BODY,
                "actions": [
                    {
                        "type": "URL",
                        "title": "Abrir albarán",
                        "url": (settings.PLATFORM_BASE_URL + WORKER_PATH
                                + "{{6}}"),
                    },
                ],
            },
        },
    }


class Command(notice_templates.Command):
    """
    Create and submit the crane work order template.

    ---

    Crea y somete a aprobación la plantilla de orden de trabajo del
    gruista.
    """

    help = (
        "Crea y somete a aprobacion de Meta la plantilla WhatsApp "
        "crane_albaran_notice (H11, S162)."
    )
    start_message = (
        "Inicio: alta de la plantilla de orden de trabajo del gruista."
    )

    @property
    def templates(self):
        """
        Templates to create.

        ---

        Plantillas a crear.
        """
        return [_definition()]
