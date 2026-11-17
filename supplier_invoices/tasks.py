# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/supplier_invoices/tasks.py
"""
Celery tasks of the warehouse pipeline for supplier invoices.

---

H28 (S151, sesión invasora). Tareas Celery del pipeline del almacén
para las facturas de proveedor: el proceso de cada factura (Gemini
tarda) y el barrido de FACTURACION PROVEEDORES/FACTURAS NUEVAS, donde
las deja el agente de facturas del PC de Ani.
"""
import logging

from celery.contrib.django.task import DjangoTask

from enterprise_core.celery import app

logger = logging.getLogger(__name__)

INVOICE_FINAL_ATTEMPT = 5


@app.task(base=DjangoTask, bind=True, max_retries=INVOICE_FINAL_ATTEMPT)
def process_supplier_invoice_task(self, invoice_id: int) -> str:
    """
    Run the invoice agent over one invoice.

    ---

    Ejecuta el agente sobre una factura (ver invoice_service). Gemini
    saturado se reintenta al minuto; en el último intento queda como
    error visible, nunca en silencio. Al terminar pide la siguiente
    factura (goteo: ver invoice_service.feed_queue).
    """
    from .invoice_service import (
        TransientInvoiceError, feed_queue, process_invoice,
    )

    final = self.request.retries >= INVOICE_FINAL_ATTEMPT
    try:
        status = process_invoice(invoice_id, final=final)
    except TransientInvoiceError:
        raise self.retry(countdown=60)
    feed_queue()
    return status


@app.task(base=DjangoTask, bind=True, max_retries=0)
def sweep_invoice_folder_task(self) -> int:
    """
    Queue the invoices Ani's agent left in "Facturas nuevas".

    ---

    Indexa y registra las facturas que el agente de facturas del PC de
    Ani ha dejado en FACTURACION PROVEEDORES/FACTURAS NUEVAS, y manda
    al worker las siguientes de la cola.
    """
    from .invoice_service import sweep_new_folder

    registered = sweep_new_folder()
    if registered:
        logger.info(
            "# [FACTURAS] %d archivo(s) nuevos registrados.", registered,
        )
    return registered
