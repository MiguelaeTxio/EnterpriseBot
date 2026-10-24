# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/whatsapp/management/commands/create_chat_room_notice_whatsapp_template.py
"""
H37 (S138). Creates in Twilio, submits to Meta approval and registers
in the database the WhatsApp template that tells a worker there is a
new message in a chat room of the platform.

---

H37 (S138). Crea en Twilio, somete a aprobación de Meta y registra en
BD la plantilla `chat_room_notice`: avisa de que hay un mensaje nuevo
en la sala `{{2}}`, con el enlace personal `{{3}}`, y sirve para
cualquier sala (decisiones de S136, anexo H37 sección 10). Solo se usa
fuera de la ventana de 24 h; dentro, el aviso sale en texto normal.

Lleva un botón de RESPUESTA RÁPIDA "Ver mensajes", no de enlace:
pulsarlo cuenta como mensaje del trabajador, abre la ventana de 24 h
y los avisos siguientes van en texto normal. Al pulsarlo, el bot le
contesta con el enlace (`chat.room_service.handle_whatsapp_reply`).

Reutiliza el alta de create_document_notice_whatsapp_templates (S122):
`requests` crudo contra la Content API, categoría UTILITY, idempotente
en BD y log en pantalla y en archivo a la vez (`--log-file`). El
cuerpo empieza por la coletilla ya aprobada y termina en texto, nunca
en variable (Meta lo rechaza).
"""
from django.conf import settings

from chat.room_service import NOTICE_BUTTON_ID, NOTICE_TEMPLATE_NAME
from whatsapp.management.commands import (
    create_document_notice_whatsapp_templates as notice_templates,
)

BODY = (
    notice_templates._PREAMBLE
    + "Hay un mensaje nuevo en la sala {{2}}. Puede verlo en {{3}} o "
    "pulsando Ver mensajes."
)


def _definition():
    """
    Template definition, with an example link of the platform.

    ---

    Definición de la plantilla, con un enlace de ejemplo de la
    plataforma (`settings.PLATFORM_BASE_URL`).
    """
    return {
        "name": NOTICE_TEMPLATE_NAME,
        "variables": {
            "1": "Juan",
            "2": "Asistencia",
            "3": settings.PLATFORM_BASE_URL + "/sala/entrar/abc123/",
        },
        "types": {
            "twilio/quick-reply": {
                "body": BODY,
                "actions": [
                    {"title": "Ver mensajes", "id": NOTICE_BUTTON_ID},
                ],
            },
        },
    }


class Command(notice_templates.Command):
    """
    Create and submit the chat room notice template.

    ---

    Crea y somete a aprobación la plantilla de aviso de la sala.
    """

    help = (
        "Crea y somete a aprobacion de Meta la plantilla WhatsApp "
        "chat_room_notice (H37, S138)."
    )
    start_message = "Inicio: alta de la plantilla de aviso de la sala."

    @property
    def templates(self):
        """
        Templates to create.

        ---

        Plantillas a crear.
        """
        return [_definition()]
