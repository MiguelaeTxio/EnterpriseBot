# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/whatsapp/management/commands/create_crane_location_notice_whatsapp_template.py
"""
H11 (S162). Creates in Twilio, submits to Meta approval and registers
in the database the WhatsApp template that tells a crane operator the
worksite location and time of his service.

---

H11 (S162). Crea en Twilio, somete a aprobación de Meta y registra en
BD la plantilla `crane_location_notice`: al gruista solo le llega la
fecha y hora del servicio, la obra, su ubicación y el enlace del mapa
(casilla fija del planning hasta que se implanten los albaranes). Solo
se usa fuera de la ventana de 24 h; dentro, el aviso sale en texto
normal (crane_albaranes.services.send_worker_notice).

Reutiliza el alta de create_document_notice_whatsapp_templates (S122):
`requests` crudo contra la Content API, categoría UTILITY, idempotente
en BD y log en pantalla y en archivo a la vez (`--log-file`). El
cuerpo empieza por la coletilla ya aprobada y termina en texto, nunca
en variable (Meta lo rechaza).
"""
from crane_albaranes.services import LOCATION_TEMPLATE_NAME
from whatsapp.management.commands import (
    create_document_notice_whatsapp_templates as notice_templates,
)

BODY = (
    notice_templates._PREAMBLE
    + "Tiene servicio el {{2}} en la obra {{3}}. Ubicacion: {{4}}. "
    "Mapa: {{5}}\nGracias."
)


def _definition():
    """
    Template definition with example values.

    ---

    Definición de la plantilla con valores de ejemplo.
    """
    return {
        "name": LOCATION_TEMPLATE_NAME,
        "body": BODY,
        "variables": {
            "1": "Juan",
            "2": "21/11/2026 a las 07:30",
            "3": "Subestacion Axarquia",
            "4": "Carretera A-7, km 272, Velez-Malaga",
            "5": "https://www.google.com/maps/search/?api=1&query="
                 "36.78012,-4.10043",
        },
    }


class Command(notice_templates.Command):
    """
    Create and submit the crane location notice template.

    ---

    Crea y somete a aprobación la plantilla de aviso de ubicación del
    gruista.
    """

    help = (
        "Crea y somete a aprobacion de Meta la plantilla WhatsApp "
        "crane_location_notice (H11, S162)."
    )
    start_message = (
        "Inicio: alta de la plantilla de ubicacion y hora del gruista."
    )

    @property
    def templates(self):
        """
        Templates to create.

        ---

        Plantillas a crear.
        """
        return [_definition()]
