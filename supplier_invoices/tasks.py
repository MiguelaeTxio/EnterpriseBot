# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/supplier_invoices/tasks.py
"""
Celery tasks of the invoice agent (FACTURACIÓN folder of the inbox).

---

H28 (S151, sesión invasora). Tareas Celery del agente de facturas: el
proceso de cada factura (fuera de la petición web, Gemini tarda) y el
barrido de "Facturas nuevas" para las que lleguen a la carpeta por
cualquier otra vía.
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
    error visible, nunca en silencio.
    """
    from .invoice_service import TransientInvoiceError, process_invoice

    final = self.request.retries >= INVOICE_FINAL_ATTEMPT
    try:
        return process_invoice(invoice_id, final=final)
    except TransientInvoiceError:
        raise self.retry(countdown=60)


@app.task(base=DjangoTask, bind=True, max_retries=0)
def sweep_invoice_folder_task(self) -> int:
    """
    Queue files that reached "Facturas nuevas" by another route.

    ---

    Encola los archivos que han llegado a "Facturas nuevas" por otra
    vía (explorador, agente de OneDrive...) y no tienen factura.
    """
    from .invoice_service import sweep_new_folder

    queued = sweep_new_folder()
    if queued:
        logger.info("# [FACTURAS] %d archivo(s) nuevos encolados.", queued)
    return queued
