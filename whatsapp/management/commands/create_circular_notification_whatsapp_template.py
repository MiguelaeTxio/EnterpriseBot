# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/whatsapp/management/commands/create_circular_notification_whatsapp_template.py
"""
H31 (S115). Crea (si no existe ya) y somete a aprobacion de Meta la
plantilla WhatsApp 'circular_notification' via la Content API de
Twilio, y registra el WhatsAppTemplate resultante en BD -- mismo
patron ya verificado en create_epi_delivery_whatsapp_template.py
(H31, S74).

Tipo de contenido: twilio/card (diseno cerrado en S114). Boton
QUICK_REPLY "Leer aqui" (responde con el texto completo de la
circular dentro de la sesion, via ButtonPayload en el webhook) +
boton URL "Ver en navegador" (lleva a /panel/mi-buzon/ con ?next=
hacia la circular concreta, una vez ajustado TrustDeviceQuickLoginView
en esta misma sesion). Coletilla ya aprobada por Meta en otras
plantillas (document_expiry_alert, epi_delivery_confirmation),
reutilizada literalmente + "si no lo es, ignore este mensaje".
Saludo al principio, nunca variable al final -- lo contrario ya
causo dos rechazos reales en document_expiry_alert.

⛔ USA requests CRUDO, NO client.content.v1.contents.create() del SDK
-- mismo bug real y confirmado de twilio-python (issue #881) que
motivo este mismo patron en create_epi_delivery_whatsapp_template.py.

Idempotente a nivel de BD (get_or_create por company+name, igual que
el resto de seeds) -- NO idempotente a nivel de Twilio: si se
ejecuta dos veces sin que el WhatsAppTemplate ya exista en BD,
crearia un segundo Content Template duplicado en Twilio. Por eso
comprueba primero si ya existe el registro en BD y aborta sin tocar
Twilio si es asi.
"""
import os

import requests
from django.core.management.base import BaseCommand, CommandError

from ivr_config.models import Company
from whatsapp.models import WhatsAppTemplate

TEMPLATE_NAME = "circular_notification"
COMPANY_SLUG = "grupo-alvarez"

# Coletilla ya aprobada por Meta, reutilizada literalmente (mismo
# patron que epi_delivery_confirmation, S74) + cierre "si no lo es,
# ignore este mensaje" acordado en S114. Saludo al principio, nunca
# variable al final.
TEMPLATE_TITLE = (
    "Hola {{1}}. Tiene disponible una nueva circular: {{2}}. Usted "
    "recibe este mensaje porque consta como trabajador de Grupo "
    "Alvarez. Si no lo es, ignore este mensaje."
)
TEMPLATE_SUBTITLE = "Grupo Alvarez"
TEMPLATE_VARIABLES = {
    "1": "Juan Perez",
    "2": "Circular de ejemplo",
}
QUICK_REPLY_ID = "leer_aqui_circular"
# URL provisional a /panel/mi-buzon/ (pantalla nueva de esta misma
# sesion) -- {{3}} se resuelve al enviar cada circular concreta una
# vez este placeholder de ruta este operativo.
URL_BUTTON_TARGET = "https://enterprisebot-miguelaetxio.pythonanywhere.com/panel/mi-buzon/{{3}}"
URL_BUTTON_SAMPLE = "?next=/panel/mi-buzon/"

CONTENT_API_BASE = "https://content.twilio.com/v1/Content"


class Command(BaseCommand):
    help = (
        "Crea y somete a aprobacion de Meta la plantilla WhatsApp "
        "circular_notification (H31, S115)."
    )

    def handle(self, *args, **options):
        company = Company.objects.filter(slug=COMPANY_SLUG).first()
        if company is None:
            raise CommandError(
                f"No existe ivr_config.Company con slug='{COMPANY_SLUG}'."
            )

        existing = WhatsAppTemplate.objects.filter(
            company=company, name=TEMPLATE_NAME,
        ).first()
        if existing is not None:
            self.stdout.write(self.style.WARNING(
                f"Ya existe WhatsAppTemplate '{TEMPLATE_NAME}' "
                f"(content_sid={existing.content_sid}). Nada que hacer "
                f"-- no se toca Twilio para evitar duplicados."
            ))
            return

        try:
            api_key_sid = os.environ["TWILIO_API_KEY_SID"]
            api_key_secret = os.environ["TWILIO_API_KEY_SECRET"]
        except KeyError as exc:
            raise CommandError(f"Variable de entorno ausente: {exc}")

        auth = (api_key_sid, api_key_secret)

        # ── PASO 1: crear el Content Template ──────────────────────
        create_payload = {
            "friendly_name": TEMPLATE_NAME,
            "language": "es",
            "variables": {
                **TEMPLATE_VARIABLES,
                "3": URL_BUTTON_SAMPLE,
            },
            "types": {
                "twilio/card": {
                    "title": TEMPLATE_TITLE,
                    "subtitle": TEMPLATE_SUBTITLE,
                    "actions": [
                        {
                            "type": "QUICK_REPLY",
                            "title": "Leer aqui",
                            "id": QUICK_REPLY_ID,
                        },
                        {
                            "type": "URL",
                            "title": "Ver en navegador",
                            "url": URL_BUTTON_TARGET,
                        },
                    ],
                },
            },
        }
        resp = requests.post(
            CONTENT_API_BASE, json=create_payload, auth=auth, timeout=30,
        )
        if resp.status_code != 201:
            raise CommandError(
                f"Fallo al crear el Content Template (HTTP "
                f"{resp.status_code}): {resp.text}"
            )
        content_sid = resp.json()["sid"]
        self.stdout.write(self.style.SUCCESS(
            f"Content Template creado: {content_sid}"
        ))

        # ── PASO 2: someter a aprobacion de WhatsApp/Meta ──────────
        approval_url = f"{CONTENT_API_BASE}/{content_sid}/ApprovalRequests/whatsapp"
        approval_payload = {"name": TEMPLATE_NAME, "category": "UTILITY"}
        approval_resp = requests.post(
            approval_url, json=approval_payload, auth=auth, timeout=30,
        )
        if approval_resp.status_code not in (200, 201):
            self.stdout.write(self.style.WARNING(
                f"Content Template creado ({content_sid}) pero la "
                f"solicitud de aprobacion fallo (HTTP "
                f"{approval_resp.status_code}): {approval_resp.text}. "
                f"Revisar a mano en el Console de Twilio."
            ))
        else:
            approval_data = approval_resp.json()
            self.stdout.write(self.style.SUCCESS(
                f"Solicitud de aprobacion enviada. Estado: "
                f"{approval_data.get('status')}"
            ))

        # ── PASO 3: registrar en BD (is_active=True, mismo criterio
        # que epi_delivery_confirmation -- el envio real fallara por
        # parte de Twilio/Meta hasta que la aprobacion llegue, no hay
        # gate de estado de aprobacion en este modelo) ─────────────
        WhatsAppTemplate.objects.create(
            company=company,
            name=TEMPLATE_NAME,
            content_sid=content_sid,
            category=WhatsAppTemplate.CATEGORY_UTILITY,
            language="es",
        )
        self.stdout.write(self.style.SUCCESS(
            f"WhatsAppTemplate registrado en BD: {TEMPLATE_NAME} "
            f"({content_sid}). Pendiente de aprobacion real de Meta "
            f"-- consultar estado con GET {approval_url} antes de "
            f"confiar en el primer envio real."
        ))
