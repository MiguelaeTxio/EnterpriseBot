# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/supplier_invoices/management/commands/requeue_supplier_invoices.py
"""
Put back in line the supplier invoices left waiting.

---

H28 (S151, sesión invasora). Vuelve a poner en cola las facturas que se
quedaron esperando (pausa del 17/11/2026, worker reiniciado):

- Las "Procesando" sin ninguna línea guardada vuelven a "En cola" (no
  llegaron a tocar el almacén). Las que ya tienen líneas se listan y no
  se tocan.
- Todas las "En cola" quedan sin mandar y el goteo (feed_queue) manda
  las primeras; el resto sale de una en una al terminar cada factura.
- `--log-file` obligatorio: pantalla y archivo a la vez, con flush en
  cada línea.
"""
from datetime import datetime

from django.core.management.base import BaseCommand

from supplier_invoices.invoice_service import feed_queue
from supplier_invoices.models import SupplierInvoice


class Command(BaseCommand):
    """
    Requeue the open supplier invoices.

    ---

    Vuelve a poner en cola las facturas de proveedor abiertas.
    """

    help = "Vuelve a poner en cola las facturas de proveedor (S151)."

    def add_arguments(self, parser):
        parser.add_argument("--log-file", required=True)

    def _log(self, text):
        line = "[%s] %s" % (datetime.now().strftime("%H:%M:%S"), text)
        print(line, flush=True)
        self._handle.write(line + "\n")
        self._handle.flush()

    def handle(self, *args, **options):
        with open(options["log_file"], "a", encoding="utf-8") as handle:
            self._handle = handle
            reset = 0
            stuck = SupplierInvoice.objects.filter(
                status=SupplierInvoice.STATUS_PROCESSING,
            )
            for invoice in stuck:
                if invoice.lines.exists():
                    self._log(
                        "Se deja como está (ya tiene líneas): %s %s"
                        % (invoice.pk, invoice.original_name)
                    )
                    continue
                invoice.status = SupplierInvoice.STATUS_PENDING
                invoice.queued_at = None
                invoice.save(update_fields=["status", "queued_at"])
                reset += 1
                self._log(
                    "Vuelve a En cola: %s %s"
                    % (invoice.pk, invoice.original_name)
                )
            pending = SupplierInvoice.objects.filter(
                status=SupplierInvoice.STATUS_PENDING,
            ).update(queued_at=None)
            sent = feed_queue()
            self._log(
                "Procesando sin líneas devueltas a En cola: %d" % reset
            )
            self._log("Facturas en cola: %d" % pending)
            self._log("Mandadas ya al worker: %d" % sent)
