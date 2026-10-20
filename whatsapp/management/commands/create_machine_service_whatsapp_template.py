# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/whatsapp/management/commands/create_machine_service_whatsapp_template.py
"""
H30 (S131). Creates in Twilio, submits to Meta approval and registers
in the database the WhatsApp template of the service notices (hours
and kilometres) of the cost centres.

---

H30 (S131). Crea en Twilio, somete a aprobación de Meta y registra en
BD la plantilla de WhatsApp de los avisos de revisión por horas y km
de los centros de gasto (`machine_service_notice`). Las de
documentación (`document_expiry_notice`) llevan una fecha de
caducidad en {{4}}; una revisión no tiene fecha, sino una lectura y
la lectura a la que toca, así que necesita su propio texto.

Reutiliza íntegro el alta de create_document_notice_whatsapp_templates
(S122): `requests` crudo contra la Content API, categoría UTILITY,
idempotente a nivel de BD, texto plano al final y log propio en
pantalla y en archivo a la vez (`--log-file`). Solo cambia la
plantilla.
"""
from whatsapp.management.commands import (
    create_document_notice_whatsapp_templates as notice_templates,
)

TEMPLATE_NAME = "machine_service_notice"

TEMPLATES = [
    {
        "name": TEMPLATE_NAME,
        "body": (
            notice_templates._PREAMBLE
            + "Aviso de {{2}} de {{3}}: {{4}} Consulte el panel para "
            "mas detalles."
        ),
        "variables": {
            "1": "Juan Perez",
            "2": "Revisión de 800 horas",
            "3": "A-45 -- LIEBHERR LTM 1055",
            "4": "Vencida: lectura 1.650 h, tocaba a 1.600 h.",
        },
    },
]


class Command(notice_templates.Command):
    """
    Create and submit the service notice template.

    ---

    Crea y somete a aprobación la plantilla de avisos de revisión.
    """

    help = (
        "Crea y somete a aprobacion de Meta la plantilla WhatsApp "
        "machine_service_notice (H30, S131)."
    )
    templates = TEMPLATES
    start_message = "Inicio: alta de la plantilla de avisos de revisión."
