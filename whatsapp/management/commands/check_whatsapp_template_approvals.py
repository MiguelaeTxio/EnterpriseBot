# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/whatsapp/management/commands/check_whatsapp_template_approvals.py
"""
H30 (S124), roadmap item 5. Read-only: WhatsApp approval status of the
given templates, straight from the Twilio Content API.

---

H30 (S124), punto 5 de la hoja de ruta. Solo lectura: estado de
aprobación de WhatsApp (Meta) de las plantillas indicadas por nombre,
leído de la Content API de Twilio
(`GET https://content.twilio.com/v1/Content/{ContentSid}/ApprovalRequests`,
objeto `whatsapp` con `status`, `category`, `rejection_reason`;
verificado contra la documentación de Twilio en S124). Solo con
`status=approved` se puede iniciar una conversación desde la empresa
(business-initiated).

No escribe nada ni en Twilio ni en la BD. `--log-file` obligatorio:
log propio en pantalla y en archivo a la vez.
"""
import os
from datetime import datetime

import requests
from django.core.management.base import BaseCommand, CommandError

from ivr_config.models import Company
from whatsapp.models import WhatsAppTemplate

COMPANY_SLUG = "grupo-alvarez"
CONTENT_API_BASE = "https://content.twilio.com/v1/Content"


class Command(BaseCommand):
    """
    Show the WhatsApp approval status of templates.

    ---

    Muestra el estado de aprobación de WhatsApp de las plantillas.
    """

    help = (
        "Estado de aprobación de WhatsApp de plantillas por nombre "
        "(H30, S124). Solo lectura."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--name", action="append", required=True, dest="names",
            help="Nombre de la plantilla (repetible).",
        )
        parser.add_argument("--log-file", required=True)

    def _log(self, message):
        """
        Print and append one timestamped line to the log, flushed.

        ---

        Escribe una línea con hora en pantalla y en el log, con flush.
        """
        line = "[%s] %s" % (datetime.now().strftime("%H:%M:%S"), message)
        print(line, flush=True)
        self._log_handle.write(line + "\n")
        self._log_handle.flush()

    def handle(self, *args, **options):
        with open(options["log_file"], "a", encoding="utf-8") as handle:
            self._log_handle = handle
            self._run(options["names"])

    def _run(self, names):
        """
        Query each template and log its status.

        ---

        Consulta cada plantilla y deja su estado en el log.
        """
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

        for position, name in enumerate(names, start=1):
            template = WhatsAppTemplate.objects.filter(
                company=company, name=name,
            ).first()
            if template is None:
                self._log("%d/%d %s: NO EXISTE EN BD." % (
                    position, len(names), name,
                ))
                continue
            response = requests.get(
                "%s/%s/ApprovalRequests" % (
                    CONTENT_API_BASE, template.content_sid,
                ),
                auth=auth, timeout=30,
            )
            if response.status_code != 200:
                self._log("%d/%d %s (%s): ERROR HTTP %s: %s" % (
                    position, len(names), name, template.content_sid,
                    response.status_code, response.text[:300],
                ))
                continue
            whatsapp = response.json().get("whatsapp") or {}
            self._log(
                "%d/%d %s (%s): estado=%s categoria=%s motivo_rechazo=%s "
                "respuesta=%s" % (
                    position, len(names), name, template.content_sid,
                    whatsapp.get("status") or "sin solicitud",
                    whatsapp.get("category") or "-",
                    whatsapp.get("rejection_reason") or "-",
                    whatsapp,
                )
            )
        self._log("Fin.")
