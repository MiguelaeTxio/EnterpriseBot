# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/whatsapp/management/commands/create_document_request_whatsapp_templates.py
"""
H30 (S125), roadmap item 1. Creates in Twilio, submits to Meta approval
and registers in the database the two WhatsApp templates used to ask a
worker for a document that is missing or expiring.

---

H30 (S125), punto 1 de la hoja de ruta. Crea en Twilio, somete a
aprobación de Meta y registra en BD las dos plantillas de WhatsApp con
las que se pide al propio trabajador un documento que falta o caduca
(las `document_*_notice` de S122 son para el aviso diario a
supervisores y remiten al panel):

- `document_request_missing`: documento que falta en su ficha.
- `document_request_expiry`: documento con caducidad (vencido o por
  vencer) que hay que renovar.

Las dos terminan con la frase exacta de Miguel Ángel (S124):
"Responda a este mensaje con una foto o un PDF del documento." --
texto plano al final, requisito ya conocido de Meta.

Reutiliza íntegro el alta de create_document_notice_whatsapp_templates
(S122): `requests` crudo contra la Content API, categoría UTILITY,
idempotente por plantilla a nivel de BD y log propio en pantalla y en
archivo a la vez (`--log-file`). Solo cambian las plantillas.
"""
from whatsapp.management.commands import (
    create_document_notice_whatsapp_templates as notice_templates,
)

_CLOSING = "Responda a este mensaje con una foto o un PDF del documento."

TEMPLATES = [
    {
        "name": "document_request_missing",
        "body": (
            notice_templates._PREAMBLE
            + "Falta en su ficha el documento {{2}}. "
            + _CLOSING
        ),
        "variables": {
            "1": "Juan Perez",
            "2": "DNI",
        },
    },
    {
        "name": "document_request_expiry",
        "body": (
            notice_templates._PREAMBLE
            + "Su documento {{2}} tiene fecha de caducidad {{3}} y debe "
            "renovarse. "
            + _CLOSING
        ),
        "variables": {
            "1": "Juan Perez",
            "2": "Permiso de conducir",
            "3": "15/11/2026",
        },
    },
]


class Command(notice_templates.Command):
    """
    Create and submit the worker document request templates.

    ---

    Crea y somete a aprobación las plantillas de solicitud de
    documentación al trabajador.
    """

    help = (
        "Crea y somete a aprobacion de Meta las plantillas WhatsApp "
        "document_request_missing y document_request_expiry (H30, S125)."
    )
    templates = TEMPLATES
    start_message = (
        "Inicio: alta de plantillas de solicitud de documentación al "
        "trabajador."
    )
