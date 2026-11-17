# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/supplier_invoices/management/commands/requeue_supplier_invoices.py
"""
Queue again the supplier invoices left waiting by the intake pause.

---

H28 (S151, sesión invasora). Mientras la entrada estuvo en pausa
(17/11/2026), las facturas ya registradas se quedaron "En cola" sin
tarea viva, y una se quedó "Procesando" al reiniciarse el worker. Este
comando las vuelve a encolar:

- Las "Procesando" sin ninguna línea guardada vuelven a "En cola" (no
  llegaron a tocar el almacén). Las que ya tienen líneas se listan y no
  se tocan.
- Todas las "En cola" se encolan. Si alguna ya tuviera tarea, el
  reclamo atómico de `process_invoice` impide procesarla dos veces.
- `--log-file` obligatorio: pantalla y archivo a la vez, con flush en
  cada línea.
"""
from datetime import datetime

from django.core.management.base import BaseCommand

from supplier_invoices.models import SupplierInvoice
from supplier_invoices.tasks import process_supplier_invoice_task


class Command(BaseCommand):
    """
    Requeue the open supplier invoices.

    ---

    Vuelve a encolar las facturas de proveedor abiertas.
    """

    help = "Vuelve a encolar las facturas de proveedor en cola (S151)."

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
            stuck = SupplierInvoice.objects.filter(
                status=SupplierInvoice.STATUS_PROCESSING,
            )
            reset = 0
            for invoice in stuck:
                if invoice.lines.exists():
                    self._log(
                        "Se deja como está (ya tiene líneas): %s %s"
                        % (invoice.pk, invoice.original_name)
                    )
                    continue
                invoice.status = SupplierInvoice.STATUS_PENDING
                invoice.save(update_fields=["status"])
                reset += 1
                self._log(
                    "Vuelve a En cola: %s %s"
                    % (invoice.pk, invoice.original_name)
                )
            pending = list(SupplierInvoice.objects.filter(
                status=SupplierInvoice.STATUS_PENDING,
            ).values_list("pk", flat=True))
            for pk in pending:
                process_supplier_invoice_task.delay(pk)
            self._log(
                "Procesando sin líneas devueltas a En cola: %d" % reset
            )
            self._log("Facturas encoladas: %d" % len(pending))
