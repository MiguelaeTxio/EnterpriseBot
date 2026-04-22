# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/work_order_processor/tasks.py

"""
Celery tasks for the work_order_processor application.
Defines the primary background task that orchestrates the full PDF processing
pipeline: page rasterisation via PyMuPDF, Gemini Vision extraction per page,
WorkOrderEntry persistence and final Excel report generation.

---

Tareas Celery para la aplicación work_order_processor.
Define la tarea de fondo principal que orquesta el pipeline completo de
procesamiento de PDF: rasterización de páginas con PyMuPDF, extracción
Gemini Vision por página, persistencia de WorkOrderEntry y generación final
del informe Excel.
"""

import logging

import fitz  # PyMuPDF
from celery.contrib.django.task import DjangoTask
from django.db import transaction
from enterprise_core.celery import app

from .models import WorkOrder, WorkOrderEntry
from .services import (
    _coerce_confidence,
    _parse_date,
    _parse_time,
    extract_work_order_page,
    generate_work_order_excel,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# DPI for page rasterisation / DPI para rasterización de páginas
# ---------------------------------------------------------------------------
# 200 DPI is the optimal balance between readability for handwritten forms
# and processing speed, as established in the partes-trabajo skill (v1.x).
# 200 DPI es el equilibrio óptimo entre legibilidad para formularios
# manuscritos y velocidad de procesamiento, según la skill partes-trabajo.
_RASTER_DPI    = 200
_RASTER_MATRIX = fitz.Matrix(_RASTER_DPI / 72, _RASTER_DPI / 72)


@app.task(base=DjangoTask, bind=True, max_retries=3, default_retry_delay=30)
def process_work_order_pdf(self, work_order_id: int) -> None:
    """
    Celery task: orchestrates the full PDF processing pipeline for a WorkOrder.

    Flow:
      1. Load WorkOrder from DB and transition status to PROCESSING.
      2. Open the source PDF with PyMuPDF and determine total_pages.
      3. For each page:
         a. Rasterise to PNG bytes in memory at _RASTER_DPI (no disk write).
         b. Call extract_work_order_page() -> structured dict from Gemini Vision.
         c. Persist a WorkOrderEntry with the extracted fields and raw response.
         d. Increment processed_pages counter.
      4. Call generate_work_order_excel() to build and persist the Excel report.
         This service also sets status to DONE.

    On unrecoverable error: sets status to ERROR, logs the traceback and
    re-raises to allow Celery retry logic to engage up to max_retries times.

    ---

    Tarea Celery: orquesta el pipeline completo de procesamiento de PDF para
    un WorkOrder.

    Flujo:
      1. Cargar WorkOrder de la BD y transicionar el estado a PROCESSING.
      2. Abrir el PDF original con PyMuPDF y determinar total_pages.
      3. Por cada página:
         a. Rasterizar a bytes PNG en memoria a _RASTER_DPI (sin escritura en disco).
         b. Llamar a extract_work_order_page() -> dict estructurado de Gemini Vision.
         c. Persistir un WorkOrderEntry con los campos extraídos y la respuesta cruda.
         d. Incrementar el contador processed_pages.
      4. Llamar a generate_work_order_excel() para construir y persistir el Excel.
         Este servicio también establece el estado a DONE.

    En caso de error irrecuperable: establece el estado a ERROR, registra el
    traceback y relanza la excepción para que la lógica de reintentos de Celery
    actúe hasta max_retries veces.
    """
    logger.info(
        "# [Tarea] process_work_order_pdf iniciada para WorkOrder #%d.",
        work_order_id,
    )

    work_order = None

    try:
        # ------------------------------------------------------------------
        # Step 1 — Load and transition to PROCESSING
        # Paso 1 — Cargar y transicionar a PROCESSING
        # ------------------------------------------------------------------
        with transaction.atomic():
            work_order = WorkOrder.objects.select_for_update().get(pk=work_order_id)

        if work_order.status == WorkOrder.Status.DONE:
            # Idempotency guard: already processed, nothing to do.
            # Guardia de idempotencia: ya procesado, nada que hacer.
            logger.warning(
                "# [Tarea] WorkOrder #%d ya está en estado DONE. Tarea abortada.",
                work_order_id,
            )
            return

        work_order.status = WorkOrder.Status.PROCESSING
        work_order.save(update_fields=["status"])

        # ------------------------------------------------------------------
        # Step 2 — Open PDF and count pages
        # Paso 2 — Abrir PDF y contar páginas
        # ------------------------------------------------------------------
        pdf_path = work_order.source_pdf.path
        logger.info("# [Tarea] Abriendo PDF: %s", pdf_path)

        pdf_document = fitz.open(pdf_path)
        total_pages  = len(pdf_document)

        work_order.total_pages     = total_pages
        work_order.processed_pages = 0
        work_order.save(update_fields=["total_pages", "processed_pages"])

        logger.info(
            "# [Tarea] PDF abierto correctamente. Total de páginas: %d.", total_pages
        )

        # ------------------------------------------------------------------
        # Step 3 — Iterate pages: rasterise -> extract -> persist
        # Paso 3 — Iterar páginas: rasterizar -> extraer -> persistir
        # ------------------------------------------------------------------
        for page_number_zero in range(total_pages):

            page_number_one = page_number_zero + 1  # Base-1 for DB storage.
            logger.info(
                "# [Tarea] Procesando página %d / %d.", page_number_one, total_pages
            )

            # a) Rasterise page to PNG bytes in memory.
            # a) Rasterizar página a bytes PNG en memoria.
            page        = pdf_document[page_number_zero]
            pixmap      = page.get_pixmap(matrix=_RASTER_MATRIX)
            image_bytes = pixmap.tobytes("png")

            # b) Call Gemini Vision extraction service.
            # b) Llamar al servicio de extracción Gemini Vision.
            extracted = extract_work_order_page(image_bytes)

            # c) Persist WorkOrderEntry.
            # c) Persistir WorkOrderEntry.
            with transaction.atomic():
                WorkOrderEntry.objects.update_or_create(
                    work_order  = work_order,
                    page_number = page_number_one,
                    defaults    = {
                        "worker_name":           (extracted.get("worker_name") or ""),
                        "work_date":             _parse_date(extracted.get("work_date")),
                        "start_time":            _parse_time(extracted.get("start_time")),
                        "end_time":              _parse_time(extracted.get("end_time")),
                        "vehicle_ref":           (extracted.get("vehicle_ref") or ""),
                        "work_description":      (extracted.get("work_description") or ""),
                        "location":              (extracted.get("location") or ""),
                        "observations":          (extracted.get("observations") or ""),
                        "raw_gemini_response":   extracted,
                        "extraction_confidence": _coerce_confidence(
                            extracted.get("extraction_confidence")
                        ),
                    },
                )

            # d) Increment processed_pages counter.
            # d) Incrementar el contador processed_pages.
            work_order.processed_pages = page_number_one
            work_order.save(update_fields=["processed_pages"])

            logger.info(
                "# [Tarea] Página %d persistida. Confianza: %s.",
                page_number_one,
                extracted.get("extraction_confidence", "DESCONOCIDA"),
            )

        pdf_document.close()

        # ------------------------------------------------------------------
        # Step 4 — Generate Excel report
        # Paso 4 — Generar informe Excel
        # ------------------------------------------------------------------
        logger.info(
            "# [Tarea] Iniciando generación de Excel para WorkOrder #%d.",
            work_order_id,
        )
        generate_work_order_excel(work_order_id)

        logger.info(
            "# [Tarea] process_work_order_pdf completada para WorkOrder #%d.",
            work_order_id,
        )

    except WorkOrder.DoesNotExist:
        logger.error(
            "# [Tarea] WorkOrder #%d no encontrado en BD. Tarea abortada.",
            work_order_id,
        )

    except Exception as exc:
        logger.error(
            "# [Tarea] Error irrecuperable en process_work_order_pdf "
            "para WorkOrder #%d: %s",
            work_order_id,
            exc,
            exc_info=True,
        )
        if work_order is not None:
            work_order.status    = WorkOrder.Status.ERROR
            work_order.error_log = f"Error en procesamiento de PDF: {exc}"
            work_order.save(update_fields=["status", "error_log"])

        # Re-raise so Celery retry logic can engage.
        # Relanzar para que la lógica de reintentos de Celery actúe.
        raise self.retry(exc=exc)
