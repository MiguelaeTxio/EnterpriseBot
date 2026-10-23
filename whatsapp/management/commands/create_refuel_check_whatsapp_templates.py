# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/whatsapp/management/commands/create_refuel_check_whatsapp_templates.py
"""
H30 (S135). Creates in Twilio, submits to Meta approval and registers
in the database the two WhatsApp templates that ask the driver about a
fuel supply read from GasoGes.

---

H30 (S135). Crea en Twilio, somete a aprobación de Meta y registra en
BD las dos plantillas de WhatsApp que preguntan al chófer por un
repostaje del surtidor (GasoGes). Decisión de Miguel Ángel (S135): dos
plantillas, cada una con botones de respuesta rápida; al pulsar uno se
abre la ventana de 24 horas y el resto de la conversación va sin
plantilla.

- `refuel_value_check`: el valor tecleado parece erróneo. Botones
  "Sí, es correcto" / "No, lo corrijo" (si no, el robot le pide el
  valor correcto en la misma conversación).
- `refuel_unit_check`: no se sabe si el vehículo apunta km u horas.
  Botones "Kilómetros" / "Horas"; se pregunta una vez por vehículo.

Reutiliza íntegro el alta de create_document_notice_whatsapp_templates
(S122): `requests` crudo contra la Content API, categoría UTILITY,
idempotente a nivel de BD y log propio. Tipo `twilio/quick-reply`,
verificado en línea (twilio.com/docs/content/twilio-quick-reply,
23/10/2026): variables en el texto (nunca al principio ni al final ni
dos seguidas), títulos de 20 caracteres como máximo y el `id` del
botón llega en `ButtonPayload` del webhook.
"""
from whatsapp.management.commands import (
    create_document_notice_whatsapp_templates as notice_templates,
)

VALUE_TEMPLATE = "refuel_value_check"
UNIT_TEMPLATE = "refuel_unit_check"

# `id` de cada botón: llega en ButtonPayload al pulsarlo.
# ---
# Button ids, received in ButtonPayload.
VALUE_OK = "refuel_value_ok"
VALUE_FIX = "refuel_value_fix"
UNIT_KM = "refuel_unit_km"
UNIT_HOURS = "refuel_unit_hours"

_SAMPLE = {
    "1": "Juan Perez",
    "2": "A-44",
    "3": "21/10/2026 18:40",
    "4": "33.333",
}

TEMPLATES = [
    {
        "name": VALUE_TEMPLATE,
        "variables": _SAMPLE,
        "types": {
            "twilio/quick-reply": {
                "body": (
                    notice_templates._PREAMBLE
                    + "En el repostaje de {{2}} del {{3}} anotó {{4}} en "
                    "el surtidor y parece que no es correcto. ¿Es "
                    "correcto el dato?"
                ),
                "actions": [
                    {"title": "Sí, es correcto", "id": VALUE_OK},
                    {"title": "No, lo corrijo", "id": VALUE_FIX},
                ],
            },
        },
    },
    {
        "name": UNIT_TEMPLATE,
        "variables": _SAMPLE,
        "types": {
            "twilio/quick-reply": {
                "body": (
                    notice_templates._PREAMBLE
                    + "En el repostaje de {{2}} del {{3}} anotó {{4}} en "
                    "el surtidor. ¿Son kilómetros u horas?"
                ),
                "actions": [
                    {"title": "Kilómetros", "id": UNIT_KM},
                    {"title": "Horas", "id": UNIT_HOURS},
                ],
            },
        },
    },
]


class Command(notice_templates.Command):
    """
    Create and submit the two refuel check templates.

    ---

    Crea y somete a aprobación las dos plantillas de comprobación de
    repostajes.
    """

    help = (
        "Crea y somete a aprobacion de Meta las plantillas WhatsApp "
        "refuel_value_check y refuel_unit_check (H30, S135)."
    )
    templates = TEMPLATES
    start_message = (
        "Inicio: alta de las plantillas de comprobación de repostajes."
    )
