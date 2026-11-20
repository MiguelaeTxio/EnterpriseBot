# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/whatsapp/management/commands/backfill_circular_status_s149.py
"""
Fill the WhatsApp status of the circular sends made before S149.

---

S149 (Miguel Ángel, 20/11, informe del alta en el fichaje: "que la han
recibido"). Hasta hoy no se guardaba el mensaje de WhatsApp de cada
envío de circular. Para cada envío por WhatsApp de las circulares de
alta (o de todas con --all) sin mensaje guardado, busca en Twilio el
mensaje que salió a su móvil en esos minutos y guarda su SID y su
estado (entregada, leída, fallida...). Los que ya tienen SID solo
refrescan el estado si aún no es final. Solo lee de Twilio. Log propio
(com-standards 0bis).
"""
import datetime

from django.core.management.base import BaseCommand
from django.utils import timezone

FINAL = ("read", "failed", "undelivered")


class Command(BaseCommand):
    help = ("Rellena el estado de WhatsApp de los envíos de circulares "
            "anteriores (busca el mensaje en Twilio).")

    def add_arguments(self, parser):
        parser.add_argument("--all", action="store_true",
                            help="Todas las circulares, no solo el alta.")
        parser.add_argument("--log-file", required=True)

    def _log(self, text):
        line = "[%s] %s" % (timezone.localtime().strftime("%H:%M:%S"), text)
        print(line, flush=True)
        self._out.write(line + "\n")
        self._out.flush()

    def handle(self, *args, **options):
        with open(options["log_file"], "a", encoding="utf-8") as out:
            self._out = out
            self._run(options["all"])

    def _run(self, every):
        from document_explorer.models import DocumentAcknowledgment
        from document_explorer.person_phone_service import mobile_of
        from panel.clock_onboarding_report import ONBOARDING_CODES
        from whatsapp.services import _build_twilio_client
        from whatsapp.window_service import to_e164

        acks = DocumentAcknowledgment.objects.filter(
            channel=DocumentAcknowledgment.CHANNEL_WHATSAPP,
        ).exclude(whatsapp_status__in=FINAL).select_related(
            "person", "document_type").order_by("created_at")
        if not every:
            acks = acks.filter(document_type__code__in=ONBOARDING_CODES)
        acks = list(acks)
        self._log("Envíos por revisar: %d" % len(acks))
        client = _build_twilio_client()
        found = refreshed = missing = 0
        for n, ack in enumerate(acks, 1):
            label = "%s %s (%s, %s)" % (
                ack.person.first_surname, ack.person.given_name,
                ack.document_type.code,
                timezone.localtime(ack.created_at).strftime("%d/%m %H:%M")
                if ack.created_at else ack.delivery_date)
            try:
                if ack.whatsapp_sid:
                    message = client.messages(ack.whatsapp_sid).fetch()
                    refreshed += 1
                else:
                    phone = to_e164(mobile_of(ack.person) or "")
                    if not phone or not ack.created_at:
                        missing += 1
                        self._log("  [%d] %s: sin móvil o sin hora" % (
                            n, label))
                        continue
                    candidates = client.messages.list(
                        to="whatsapp:%s" % phone,
                        date_sent_after=ack.created_at
                        - datetime.timedelta(minutes=2),
                        date_sent_before=ack.created_at
                        + datetime.timedelta(minutes=15),
                        limit=10,
                    )
                    if not candidates:
                        missing += 1
                        self._log("  [%d] %s: no está en Twilio" % (
                            n, label))
                        continue
                    message = min(candidates, key=lambda m: abs(
                        (m.date_sent or ack.created_at)
                        - ack.created_at))
                    found += 1
            except Exception as exc:  # Twilio caído o SID borrado
                missing += 1
                self._log("  [%d] %s: error de Twilio: %s" % (n, label, exc))
                continue
            status = (message.status or "")[:20]
            DocumentAcknowledgment.objects.filter(pk=ack.pk).update(
                whatsapp_sid=message.sid, whatsapp_status=status,
                whatsapp_status_at=message.date_updated or timezone.now())
            self._log("  [%d] %s: %s" % (n, label, status))
        self._log("Fin: %d encontrados en Twilio, %d actualizados, %d sin "
                  "dato." % (found, refreshed, missing))
