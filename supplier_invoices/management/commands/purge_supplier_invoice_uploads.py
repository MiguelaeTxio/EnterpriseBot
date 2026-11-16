# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/supplier_invoices/management/commands/purge_supplier_invoice_uploads.py
"""
Remove everything uploaded to FACTURACION PROVEEDORES (wrong folder).

---

H28 (S151, sesión invasora). En el PC de Ani se eligió la carpeta de
facturas de años anteriores en vez de "2026 facturas recibidas", y el
agente subió al cubo lo que no tocaba. Este comando borra todo lo que
hay bajo FACTURACION PROVEEDORES/ en el cubo, sus filas del índice y
las facturas registradas sobre ellas, para empezar de cero con la
carpeta correcta.

- Sin `--apply`: solo cuenta y lista (simulación).
- Se niega si alguna factura ya está procesada: eso ya tocó el almacén
  y no se deshace borrando archivos.
- `--log-file` obligatorio: pantalla y archivo a la vez, con flush en
  cada línea, avance cada 100 objetos con ETA.
"""
from datetime import datetime, timedelta

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from document_explorer.models import DocumentIndexEntry
from spare_parts.gcs_service import get_storage_client
from supplier_invoices.invoice_service import BUCKET, INVOICES_ROOT
from supplier_invoices.models import SupplierInvoice

PREFIX = INVOICES_ROOT + "/"
PROGRESS_EVERY = 100


class Command(BaseCommand):
    """
    Purge the uploads of FACTURACION PROVEEDORES.

    ---

    Vacía FACTURACION PROVEEDORES en el cubo, el índice y las facturas.
    """

    help = "Borra todo lo subido a FACTURACION PROVEEDORES (S151)."

    def add_arguments(self, parser):
        parser.add_argument("--log-file", required=True)
        parser.add_argument(
            "--apply", action="store_true",
            help="Borrar de verdad (sin esto, solo simula).",
        )

    def _log(self, text):
        line = "[%s] %s" % (datetime.now().strftime("%H:%M:%S"), text)
        print(line, flush=True)
        self._handle.write(line + "\n")
        self._handle.flush()

    def _log_plain(self, text):
        print(text, flush=True)
        self._handle.write(text + "\n")
        self._handle.flush()

    def handle(self, *args, **options):
        self._handle = open(options["log_file"], "a", encoding="utf-8")
        apply = options["apply"]
        self._log("Modo: %s" % ("APLICAR" if apply else "SIMULACIÓN"))
        invoices = SupplierInvoice.objects.filter(
            entry__blob_name__startswith=PREFIX,
        )
        processed = invoices.filter(status=SupplierInvoice.STATUS_PROCESSED)
        if processed.exists():
            raise CommandError(
                "%d factura(s) ya procesadas: tocaron el almacén, no se "
                "borra nada." % processed.count()
            )
        blobs = list(get_storage_client().bucket(BUCKET).list_blobs(
            prefix=PREFIX,
        ))
        entries = DocumentIndexEntry.objects.filter(
            bucket=BUCKET, blob_name__startswith=PREFIX,
        )
        self._log("Objetos en el cubo bajo %s: %d" % (PREFIX, len(blobs)))
        self._log("Filas del índice: %d" % entries.count())
        self._log("Facturas registradas: %d" % invoices.count())
        for blob in blobs[:50]:
            self._log("  %s (%d bytes)" % (blob.name, blob.size or 0))
        if len(blobs) > 50:
            self._log("  ... y %d más" % (len(blobs) - 50))
        if not apply:
            self._log_plain("RESUMEN: simulación, no se ha borrado nada.")
            return
        with transaction.atomic():
            removed_invoices = invoices.delete()[0]
            removed_entries = entries.delete()[0]
        self._log("Borradas %d fila(s) de facturas y %d del índice." % (
            removed_invoices, removed_entries,
        ))
        start = datetime.now()
        deleted = failed = 0
        for number, blob in enumerate(blobs, start=1):
            try:
                blob.delete()
                deleted += 1
            except Exception as exc:  # noqa: BLE001
                failed += 1
                self._log("ERROR borrando %s: %s" % (blob.name, exc))
            if number % PROGRESS_EVERY == 0 or number == len(blobs):
                elapsed = (datetime.now() - start).total_seconds()
                eta = elapsed / number * (len(blobs) - number)
                end = datetime.now() + timedelta(seconds=eta)
                self._log(
                    "Progreso: %d/%d (%d%%) -- ETA %dm%02ds (fin aprox. "
                    "%s) -- borrados=%d errores=%d" % (
                        number, len(blobs), number * 100 // len(blobs),
                        eta // 60, eta % 60, end.strftime("%H:%M:%S"),
                        deleted, failed,
                    )
                )
        self._log_plain(
            "RESUMEN: %d objeto(s) borrados del cubo, %d con error." % (
                deleted, failed,
            )
        )
