# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/whatsapp/management/commands/create_assistance_albaran_whatsapp_template.py
"""
H37 (S132). Creates in Twilio, submits to Meta approval and registers
in the database the WhatsApp template that tells an ASSISTANCE
operator which service he has been assigned, with a button that opens
the albarán.

---

H37 (S132). Crea en Twilio, somete a aprobación de Meta y registra en
BD la plantilla de WhatsApp que avisa al operario de ASISTENCIA del
servicio que tiene asignado (`assistance_albaran_notice`), con un
botón que abre el albarán. Sustituye a `chat_session_renewal`, la
plantilla genérica de renovación de sesión, en
`send_operator_albaran_notification()`: el operario sabe a qué se
refiere el mensaje y no tiene que contestar para recibir el enlace.

Reutiliza íntegro el alta de create_document_notice_whatsapp_templates
(S122): `requests` crudo contra la Content API, categoría UTILITY,
idempotente a nivel de BD y log propio en pantalla y en archivo a la
vez (`--log-file`). Solo cambia la plantilla, de tipo
`twilio/call-to-action`: la variable del botón va al final de la URL,
como exige WhatsApp, y lleva el resto de la ruta (`<pk>/albaran/`).
"""
import os

from django.core.management.base import CommandError

from whatsapp.management.commands import (
    create_document_notice_whatsapp_templates as notice_templates,
)

TEMPLATE_NAME = "assistance_albaran_notice"
UNIT_PATH = "/panel/budgets/work-orders/units/"

BODY = (
    notice_templates._PREAMBLE
    + "Tiene asignado el servicio de asistencia {{2}} de {{3}}, con "
    "recogida en {{4}}. Abra el albaran con el boton de este mensaje."
)


def _definition():
    """
    Template definition, with the platform URL of this server.

    ---

    Definición de la plantilla, con la URL de la plataforma de este
    servidor (`PLATFORM_BASE_URL`, la misma que usa
    `albaran_link_text()`).
    """
    base_url = os.environ.get("PLATFORM_BASE_URL", "").rstrip("/")
    if not base_url:
        raise CommandError("Variable de entorno ausente: PLATFORM_BASE_URL")
    return {
        "name": TEMPLATE_NAME,
        "variables": {
            "1": "Juan Perez",
            "2": "OT-2026-0001-01",
            "3": "Allianz",
            "4": "A-4 km 512, Sevilla",
            "5": "1/albaran/",
        },
        "types": {
            "twilio/call-to-action": {
                "body": BODY,
                "actions": [
                    {
                        "type": "URL",
                        "title": "Abrir albarán",
                        "url": base_url + UNIT_PATH + "{{5}}",
                    },
                ],
            },
        },
    }


class Command(notice_templates.Command):
    """
    Create and submit the assistance albarán template.

    ---

    Crea y somete a aprobación la plantilla de aviso de albarán de
    asistencia.
    """

    help = (
        "Crea y somete a aprobacion de Meta la plantilla WhatsApp "
        "assistance_albaran_notice (H37, S132)."
    )
    start_message = (
        "Inicio: alta de la plantilla de aviso de albarán de asistencia."
    )

    @property
    def templates(self):
        """
        Templates to create (built at run time, needs the environment).

        ---

        Plantillas a crear (se construyen al ejecutar: necesitan el
        entorno del servidor).
        """
        return [_definition()]
