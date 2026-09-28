# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/whatsapp/management/commands/create_document_notice_whatsapp_templates.py
"""
H30 (S122). Creates in Twilio, submits to Meta approval and registers
in the database the two WhatsApp templates of the document notices.

---

H30 (S122). Crea en Twilio, somete a aprobación de Meta y registra en
BD las dos plantillas de WhatsApp de los avisos de documentación
(requisitos de documentación como grupos de aviso):

- `document_expiry_notice`: caducidad de un documento, válida para
  persona o centro de gasto. Sustituye a `document_expiry_alert`, cuyo
  texto dice "de la maquina {{3}}" y sale mal para personal.
- `document_missing_notice`: documento obligatorio que falta.

Mismo patrón verificado que create_circular_notification_whatsapp_
template.py (S115): `requests` crudo contra la Content API (bug #881
del SDK), saludo al principio y texto plano al final (Meta rechazó
dos veces `document_expiry_alert` por terminar en variable),
coletilla ya aprobada reutilizada literalmente.

Idempotente por plantilla a nivel de BD: si el WhatsAppTemplate ya
existe, no toca Twilio (evita Content Templates duplicados). Log
propio en pantalla y en archivo a la vez (`--log-file`).
"""
import os
from datetime import datetime

import requests
from django.core.management.base import BaseCommand, CommandError

from ivr_config.models import Company
from whatsapp.models import WhatsAppTemplate

COMPANY_SLUG = "grupo-alvarez"
CONTENT_API_BASE = "https://content.twilio.com/v1/Content"

# Coletilla ya aprobada por Meta en document_expiry_alert (S025).
_PREAMBLE = (
    "Hola {{1}}. Usted recibe este mensaje porque consta como "
    "trabajador de Grupo Alvarez. "
)

TEMPLATES = [
    {
        "name": "document_expiry_notice",
        "body": (
            _PREAMBLE
            + "El documento {{2}} de {{3}} caduca el {{4}}. Consulte "
            "el panel para mas detalles."
        ),
        "variables": {
            "1": "Juan Perez",
            "2": "ITV",
            "3": "A-45 LIEBHERR LTM 1055",
            "4": "15/11/2026",
        },
    },
    {
        "name": "document_missing_notice",
        "body": (
            _PREAMBLE
            + "Falta el documento obligatorio {{2}} de {{3}}. Consulte "
            "el panel para mas detalles."
        ),
        "variables": {
            "1": "Juan Perez",
            "2": "DNI",
            "3": "GARCIA LOPEZ, ANTONIO",
        },
    },
]


class Command(BaseCommand):
    """
    Create and submit the document notice templates.

    ---

    Crea y somete a aprobación las plantillas de avisos de
    documentación.
    """

    help = (
        "Crea y somete a aprobacion de Meta las plantillas WhatsApp "
        "document_expiry_notice y document_missing_notice (H30, S122)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--log-file",
            required=True,
            help="Ruta del log propio (pantalla y archivo a la vez).",
        )

    def _log(self, message):
        """
        Print and append one line to the log file, flushed.

        ---

        Escribe una línea en pantalla y en el log, con flush.
        """
        line = "[%s] %s" % (datetime.now().strftime("%H:%M:%S"), message)
        print(line, flush=True)
        self._log_handle.write(line + "\n")
        self._log_handle.flush()

    def handle(self, *args, **options):
        with open(options["log_file"], "a", encoding="utf-8") as handle:
            self._log_handle = handle
            self._run()

    def _run(self):
        self._log("Inicio: alta de plantillas de avisos de documentación.")
        company = Company.objects.filter(slug=COMPANY_SLUG).first()
        if company is None:
            self._log("ERROR: no existe Company slug=%s." % COMPANY_SLUG)
            raise CommandError("Empresa no encontrada.")

        try:
            auth = (
                os.environ["TWILIO_API_KEY_SID"],
                os.environ["TWILIO_API_KEY_SECRET"],
            )
        except KeyError as exc:
            self._log("ERROR: variable de entorno ausente: %s" % exc)
            raise CommandError("Variable de entorno ausente.")

        for position, definition in enumerate(TEMPLATES, start=1):
            self._log(
                "Plantilla %d/%d: %s"
                % (position, len(TEMPLATES), definition["name"])
            )
            self._create_one(company, auth, definition)
        self._log("Fin.")

    def _create_one(self, company, auth, definition):
        """
        Create, submit and register one template (idempotent in DB).

        ---

        Crea, somete y registra una plantilla (idempotente en BD).
        """
        name = definition["name"]
        existing = WhatsAppTemplate.objects.filter(
            company=company, name=name,
        ).first()
        if existing is not None:
            self._log(
                "  Ya existe en BD (content_sid=%s) -- no se toca "
                "Twilio." % existing.content_sid
            )
            return

        payload = {
            "friendly_name": name,
            "language": "es",
            "variables": definition["variables"],
            "types": {"twilio/text": {"body": definition["body"]}},
        }
        resp = requests.post(
            CONTENT_API_BASE, json=payload, auth=auth, timeout=30,
        )
        if resp.status_code != 201:
            self._log(
                "  ERROR creando el Content Template (HTTP %s): %s"
                % (resp.status_code, resp.text)
            )
            return
        content_sid = resp.json()["sid"]
        self._log("  Content Template creado: %s" % content_sid)

        approval_url = "%s/%s/ApprovalRequests/whatsapp" % (
            CONTENT_API_BASE, content_sid,
        )
        approval = requests.post(
            approval_url,
            json={"name": name, "category": "UTILITY"},
            auth=auth,
            timeout=30,
        )
        if approval.status_code in (200, 201):
            self._log(
                "  Enviada a aprobacion de Meta. Estado: %s"
                % approval.json().get("status")
            )
        else:
            self._log(
                "  AVISO: creada pero la solicitud de aprobacion fallo "
                "(HTTP %s): %s" % (approval.status_code, approval.text)
            )

        WhatsAppTemplate.objects.create(
            company=company,
            name=name,
            content_sid=content_sid,
            category=WhatsAppTemplate.CATEGORY_UTILITY,
            language="es",
        )
        self._log("  Registrada en BD: %s (%s)." % (name, content_sid))
