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

S137: versión 2 de las dos (`refuel_value_check_v2`,
`refuel_unit_check_v2`) con un tercer botón, "Contador averiado"
(Miguel Ángel: a veces el cuentakilómetros o el horómetro está roto y
hay que saberlo para no preguntar más por ese vehículo). Una plantilla
aprobada no se puede cambiar: son plantillas nuevas, y la versión 1
queda sin usar. Verificado en línea el 26/10/2026
(twilio.com/docs/content/twilio-quick-reply): hasta diez botones en
una plantilla, título de 20 caracteres como máximo.

S137: versión 3 de la del dato (`refuel_value_check_v3`). Miguel
Ángel: hay que recordar al chófer qué tiene que anotar en ese vehículo,
horas o kilómetros. Una variable más, {{5}} ("las horas que marca el
horómetro" o "los kilómetros que marca el cuentakilómetros"), en mitad
del texto. Mientras Meta no la apruebe se sigue usando la v2.

S137: versión 4 de la del dato (`refuel_value_check_v4`). Miguel
Ángel: los chóferes reciben el aviso y no saben por qué está mal. Otra
variable, {{6}}, con el motivo en una frase ("son 1.179 horas más que
el 05/10 (6.681) en 21 días, y un horómetro no sube tanto: parecen
kilómetros, y este vehículo va por horas"). Se usa en cuanto Meta la
aprueba; antes, la v3 y luego la v2.
"""
from whatsapp.management.commands import (
    create_document_notice_whatsapp_templates as notice_templates,
)

VALUE_TEMPLATE = "refuel_value_check_v2"
VALUE_TEMPLATE_V3 = "refuel_value_check_v3"
VALUE_TEMPLATE_V4 = "refuel_value_check_v4"
UNIT_TEMPLATE = "refuel_unit_check_v2"

# `id` de cada botón: llega en ButtonPayload al pulsarlo.
# ---
# Button ids, received in ButtonPayload.
VALUE_OK = "refuel_value_ok"
VALUE_FIX = "refuel_value_fix"
UNIT_KM = "refuel_unit_km"
UNIT_HOURS = "refuel_unit_hours"
METER_BROKEN = "refuel_meter_broken"

_SAMPLE = {
    "1": "Juan Perez",
    "2": "A-44",
    "3": "21/10/2026 18:40",
    "4": "33.333",
}

_SAMPLE_V3 = dict(_SAMPLE, **{"5": "las horas que marca el horómetro"})
_SAMPLE_V4 = dict(_SAMPLE_V3, **{
    "6": ("son 1.179 horas más que el 05/10 (6.681) en 21 días, y un "
          "horómetro no sube tanto: parecen kilómetros, y este vehículo "
          "va por horas"),
})

TEMPLATES = [
    {
        "name": VALUE_TEMPLATE_V4,
        "variables": _SAMPLE_V4,
        "types": {
            "twilio/quick-reply": {
                "body": (
                    notice_templates._PREAMBLE
                    + "En el repostaje de {{2}} del {{3}} anotó {{4}} en "
                    "el surtidor y no parece correcto porque {{6}}. "
                    "Recuerde que en este vehículo hay que anotar {{5}} "
                    "al repostar. ¿Es correcto el dato?"
                ),
                "actions": [
                    {"title": "Sí, es correcto", "id": VALUE_OK},
                    {"title": "No, lo corrijo", "id": VALUE_FIX},
                    {"title": "Contador averiado", "id": METER_BROKEN},
                ],
            },
        },
    },
    {
        "name": VALUE_TEMPLATE_V3,
        "variables": _SAMPLE_V3,
        "types": {
            "twilio/quick-reply": {
                "body": (
                    notice_templates._PREAMBLE
                    + "En el repostaje de {{2}} del {{3}} anotó {{4}} en "
                    "el surtidor y parece que no es correcto: en este "
                    "vehículo hay que anotar {{5}} al repostar. ¿Es "
                    "correcto el dato?"
                ),
                "actions": [
                    {"title": "Sí, es correcto", "id": VALUE_OK},
                    {"title": "No, lo corrijo", "id": VALUE_FIX},
                    {"title": "Contador averiado", "id": METER_BROKEN},
                ],
            },
        },
    },
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
                    {"title": "Contador averiado", "id": METER_BROKEN},
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
                    {"title": "Contador averiado", "id": METER_BROKEN},
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
        "refuel_value_check_v4, _v3, _v2 y refuel_unit_check_v2 (H30, "
        "S137); "
        "las que ya están en BD no se tocan."
    )
    templates = TEMPLATES
    start_message = (
        "Inicio: alta de las plantillas de comprobación de repostajes."
    )
