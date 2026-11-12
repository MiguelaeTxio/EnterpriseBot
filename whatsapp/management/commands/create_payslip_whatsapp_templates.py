# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/whatsapp/management/commands/create_payslip_whatsapp_templates.py
"""
H24 (S149 invasora). Creates in Twilio, submits to Meta approval and
registers in the database the two WhatsApp templates of the payslip
delivery.

---

H24 (S149 invasora). Crea en Twilio, somete a aprobación de Meta y
registra en BD las dos plantillas de WhatsApp de la entrega de nóminas
(hr_calendar/payslip_delivery.py):
- `payslip_batch_ready` (tarjeta con botón, `twilio/card`): al
  supervisor que inició la entrega, cuando se han terminado de leer las
  nóminas, con el botón "Ver el listado" que abre esa entrega en el
  panel (Miguel Ángel: el visto bueno se da en el panel, viendo el
  listado; `{{3}}` es "?batch=<id>").
- `payslip_delivery` (texto con archivo, `twilio/media`): a cada
  trabajador, con el PDF de su nómina. El archivo lo recoge Twilio del
  enlace temporal de la nómina (`{{3}}` es su token; la dirección fija
  es la del panel).
Mismo patrón verificado que create_system_agent_whatsapp_templates.py:
`requests` crudo contra la Content API, saludo con la coletilla ya
aprobada al principio y texto plano al final (Meta rechaza plantillas
que terminan en variable). Idempotente por plantilla a nivel de BD: si
el WhatsAppTemplate ya existe, no toca Twilio. Log propio en pantalla y
en archivo a la vez (`--log-file`).
"""
import os
from datetime import datetime

import requests
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from ivr_config.models import Company
from whatsapp.models import WhatsAppTemplate

COMPANY_SLUG = "grupo-alvarez"
CONTENT_API_BASE = "https://content.twilio.com/v1/Content"
_PREAMBLE = (
    "Hola {{1}}. Usted recibe este mensaje porque consta como "
    "trabajador de Grupo Alvarez. "
)

TEMPLATES = [
    {
        "name": "payslip_batch_ready",
        "types": {"twilio/card": {
            "title": (
                _PREAMBLE
                + "Ya se han leido las {{2}} nominas de la entrega que "
                "inicio. Revise el listado en el panel y de el visto "
                "bueno para enviarlas."
            ),
            "subtitle": "Grupo Alvarez",
            "actions": [{
                "type": "URL",
                "title": "Ver el listado",
                "url": settings.PLATFORM_BASE_URL + "/panel/nominas/{{3}}",
            }],
        }},
        "variables": {"1": "Juan", "2": "45", "3": "?batch=1"},
    },
    {
        "name": "payslip_delivery",
        "types": {"twilio/media": {
            "body": (
                _PREAMBLE
                + "Le enviamos su nomina de {{2}}. Es un documento "
                "personal y confidencial."
            ),
            "media": [
                settings.PLATFORM_BASE_URL + "/panel/nominas/whatsapp/{{3}}",
            ],
        }},
        "variables": {"1": "Juan", "2": "Octubre 2026",
                      "3": "ejemploDeTokenTemporal"},
    },
    {
        # S153: a quien quien sube la entrega le da acceso (jefe de
        # departamento), con el botón al listado para revisarlas,
        # descargarlas y enviarlas. `{{4}}` es quien la ha subido.
        "name": "payslip_batch_shared",
        "types": {"twilio/card": {
            "title": (
                _PREAMBLE
                + "{{4}} le ha dado acceso a una entrega de {{2}} nominas. "
                "Puede revisarlas, descargarlas y enviarlas en el panel."
            ),
            "subtitle": "Grupo Alvarez",
            "actions": [{
                "type": "URL",
                "title": "Ver el listado",
                "url": settings.PLATFORM_BASE_URL + "/panel/nominas/{{3}}",
            }],
        }},
        "variables": {"1": "Juan", "2": "45", "3": "?batch=1",
                      "4": "Jeronimo"},
    },
]


class Command(BaseCommand):
    """
    Create and submit the payslip delivery templates.

    ---

    Crea y somete a aprobación las plantillas de la entrega de nóminas.
    """

    help = (
        "Crea y somete a aprobacion de Meta las plantillas WhatsApp "
        "payslip_batch_ready, payslip_delivery (H24, S149) y "
        "payslip_batch_shared (S153)."
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
        self._log("Inicio: alta de plantillas de la entrega de nominas.")
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
            self._log("Plantilla %d/%d: %s"
                      % (position, len(TEMPLATES), definition["name"]))
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
            self._log("  Ya existe en BD (content_sid=%s) -- no se toca "
                      "Twilio." % existing.content_sid)
            return
        payload = {
            "friendly_name": name,
            "language": "es",
            "variables": definition["variables"],
            "types": definition["types"],
        }
        resp = requests.post(
            CONTENT_API_BASE, json=payload, auth=auth, timeout=30,
        )
        if resp.status_code != 201:
            self._log("  ERROR creando el Content Template (HTTP %s): %s"
                      % (resp.status_code, resp.text))
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
            self._log("  Enviada a aprobacion de Meta. Estado: %s"
                      % approval.json().get("status"))
        else:
            self._log("  AVISO: creada pero la solicitud de aprobacion "
                      "fallo (HTTP %s): %s"
                      % (approval.status_code, approval.text))
        WhatsAppTemplate.objects.create(
            company=company,
            name=name,
            content_sid=content_sid,
            category=WhatsAppTemplate.CATEGORY_UTILITY,
            language="es",
        )
        self._log("  Registrada en BD: %s (%s)." % (name, content_sid))
