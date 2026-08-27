# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/whatsapp/management/commands/create_epi_delivery_whatsapp_template.py
"""
H31 (S74). Crea (si no existe ya) y somete a aprobación de Meta la
plantilla WhatsApp 'epi_delivery_confirmation' vía la Content API de
Twilio, y registra el WhatsAppTemplate resultante en BD -- mismo
patrón que las 5 plantillas "PENDING APPROVAL" ya existentes en
seed_whatsapp_templates.py (creadas antes de tener aprobación final,
is_active=True por defecto igual que el resto).

⛔ USA requests CRUDO, NO client.content.v1.contents.create() del SDK
-- bug real y confirmado en twilio-python (issue #881, abierto desde
9.7.2, sin fix reportado a fecha de esta sesión, verificado contra
GitHub el mismo día de este commit): el binding del SDK serializa las
claves de `types` con guion bajo ('twilio_text') en vez de barra
('twilio/text'), y la API las rechaza con 'Invalid types'. La llamada
HTTP cruda con el payload exacto documentado por Twilio sí funciona
-- por eso este comando construye la petición a mano con `requests`
(ya en requirements.txt, dependencia real de twilio==9.10.4).

Idempotente a nivel de BD (get_or_create por company+name, igual que
el resto de seeds) -- NO idempotente a nivel de Twilio: si se
ejecuta dos veces sin que el WhatsAppTemplate ya exista en BD,
crearía un segundo Content Template duplicado en Twilio. Por eso
comprueba primero si ya existe el registro en BD y aborta sin tocar
Twilio si es así.
"""
import os

import requests
from django.core.management.base import BaseCommand, CommandError

from ivr_config.models import Company
from whatsapp.models import WhatsAppTemplate

TEMPLATE_NAME = "epi_delivery_confirmation"
COMPANY_SLUG = "grupo-alvarez"

# Mismo patrón de coletilla de opt-out ya aprobado por Meta en
# document_expiry_alert (HX55da66276bb2025f691c378abff0123e),
# confirmado contra Twilio en esta misma sesión (S74) -- reutilizado
# literalmente, no reconstruido de memoria, para maximizar la
# probabilidad de aprobación.
TEMPLATE_BODY = (
    "Hola {{1}}. Usted recibe este mensaje porque consta como "
    "trabajador de Grupo Alvarez. Se le ha entregado el EPI: {{2}}, "
    "con fecha {{3}}. Si usted no ha recibido este EPI, por favor "
    "contacte con su responsable a traves del panel."
)
TEMPLATE_VARIABLES = {
    "1": "Juan Perez",
    "2": "Casco de seguridad",
    "3": "27/08/2026",
}

CONTENT_API_BASE = "https://content.twilio.com/v1/Content"


class Command(BaseCommand):
    help = (
        "Crea y somete a aprobación de Meta la plantilla WhatsApp "
        "epi_delivery_confirmation (H31, S74)."
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
            "variables": TEMPLATE_VARIABLES,
            "types": {
                "twilio/text": {"body": TEMPLATE_BODY},
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

        # ── PASO 2: someter a aprobación de WhatsApp/Meta ──────────
        approval_url = f"{CONTENT_API_BASE}/{content_sid}/ApprovalRequests/whatsapp"
        approval_payload = {"name": TEMPLATE_NAME, "category": "UTILITY"}
        approval_resp = requests.post(
            approval_url, json=approval_payload, auth=auth, timeout=30,
        )
        if approval_resp.status_code not in (200, 201):
            self.stdout.write(self.style.WARNING(
                f"Content Template creado ({content_sid}) pero la "
                f"solicitud de aprobación falló (HTTP "
                f"{approval_resp.status_code}): {approval_resp.text}. "
                f"Revisar a mano en el Console de Twilio."
            ))
        else:
            approval_data = approval_resp.json()
            self.stdout.write(self.style.SUCCESS(
                f"Solicitud de aprobación enviada. Estado: "
                f"{approval_data.get('status')}"
            ))

        # ── PASO 3: registrar en BD (is_active=True, mismo criterio
        # que el resto de plantillas "PENDING APPROVAL" ya sembradas
        # por seed_whatsapp_templates.py -- el envío real fallará por
        # parte de Twilio/Meta hasta que la aprobación llegue, no hay
        # gate de estado de aprobación en este modelo) ─────────────
        WhatsAppTemplate.objects.create(
            company=company,
            name=TEMPLATE_NAME,
            content_sid=content_sid,
            category=WhatsAppTemplate.CATEGORY_UTILITY,
            language="es",
        )
        self.stdout.write(self.style.SUCCESS(
            f"WhatsAppTemplate registrado en BD: {TEMPLATE_NAME} "
            f"({content_sid}). Pendiente de aprobación real de Meta "
            f"-- consultar estado con GET {approval_url} antes de "
            f"confiar en el primer envío real."
        ))
