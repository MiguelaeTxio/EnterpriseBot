# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/whatsapp/management/commands/create_system_agent_whatsapp_templates.py
"""
H30 (S123). Creates in Twilio, submits to Meta approval and registers
in the database the WhatsApp templates of the system agent heartbeat
alert (agent down / agent recovered).

---

H30 (S123). Crea en Twilio, somete a aprobación de Meta y registra en
BD las plantillas de WhatsApp de la alerta de latido de agentes de
sistema (punto 1 de la hoja de ruta de S123, para el punto 7):

- `system_agent_down_alert`: un agente (p. ej. el agente H28) lleva
  más de 15 minutos sin latido. Variables: saludo, agente y hora del
  último latido.
- `system_agent_recovered_alert`: el mismo agente vuelve a dar
  latido. Necesaria porque el aviso de recuperación también puede
  caer fuera de la ventana de 24 h de WhatsApp.

Ninguna de las 18 plantillas registradas en BD (consulta real, S123)
sirve para un aviso de sistema: todas son de trabajador, documentos,
averías o presencia.

Mismo patrón verificado que create_document_notice_whatsapp_templates
(S122): `requests` crudo contra la Content API (bug #881 del SDK),
saludo al principio y texto plano al final (Meta rechaza variables
al final). Idempotente por plantilla a nivel de BD: si el
WhatsAppTemplate ya existe, no toca Twilio. Log propio en pantalla y
en archivo a la vez (`--log-file`).
"""
import os
from datetime import datetime

import requests
from django.core.management.base import BaseCommand, CommandError

from ivr_config.models import Company
from whatsapp.models import WhatsAppTemplate

COMPANY_SLUG = "grupo-alvarez"
CONTENT_API_BASE = "https://content.twilio.com/v1/Content"

_PREAMBLE = (
    "Hola {{1}}. Usted recibe este mensaje porque consta como "
    "administrador del sistema de Grupo Alvarez. "
)

TEMPLATES = [
    {
        "name": "system_agent_down_alert",
        "body": (
            _PREAMBLE
            + "El agente {{2}} no responde. Ultimo latido registrado: "
            "{{3}}. Revise el equipo donde se ejecuta."
        ),
        "variables": {
            "1": "Miguel Angel",
            "2": "Agente de migracion H28",
            "3": "28/09/2026 13:45",
        },
    },
    {
        "name": "system_agent_recovered_alert",
        "body": (
            _PREAMBLE
            + "El agente {{2}} vuelve a responder. Latido recibido: "
            "{{3}}. No es necesaria ninguna accion."
        ),
        "variables": {
            "1": "Miguel Angel",
            "2": "Agente de migracion H28",
            "3": "28/09/2026 14:05",
        },
    },
]


class Command(BaseCommand):
    """
    Create and submit the system agent alert templates.

    ---

    Crea y somete a aprobación las plantillas de alerta de agentes
    de sistema.
    """

    help = (
        "Crea y somete a aprobacion de Meta las plantillas WhatsApp "
        "system_agent_down_alert y system_agent_recovered_alert "
        "(H30, S123)."
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
        self._log("Inicio: alta de plantillas de alerta de agentes.")
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
