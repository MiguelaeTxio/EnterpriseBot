# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/work_order_processor/tasks.py

"""
Celery tasks for the work_order_processor application.
Defines the primary background task that orchestrates the full PDF processing
pipeline: page rasterisation via PyMuPDF, Gemini Vision multi-block extraction
per page, WorkOrderEntry + WorkOrderEntryLine persistence, machine catalogue
resolution and final Excel report generation.

---

Tareas Celery para la aplicación work_order_processor.
Define la tarea de fondo principal que orquesta el pipeline completo de
procesamiento de PDF: rasterización de páginas con PyMuPDF, extracción
multi-bloque Gemini Vision por página, persistencia de WorkOrderEntry +
WorkOrderEntryLine, resolución del catálogo de maquinaria y generación final
del informe Excel.
"""

import logging

import fitz  # PyMuPDF
from celery.contrib.django.task import DjangoTask
from django.db import connection, transaction
from enterprise_core.celery import app

from .models import WorkOrder, WorkOrderEntry, WorkOrderEntryLine
from .services import (
    _coerce_confidence,
    _compute_delta_horas,
    _normalise_machine_code,
    _parse_date,
    _parse_time,
    _resolve_machine_asset,
    _worker_name_from_pdf_path,
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
         b. Derive worker_name from the PDF filename (not from handwritten text).
         c. Call extract_work_order_page() -> multi-block dict from Gemini Vision.
         d. Persist WorkOrderEntry (page header: date, worker, confidence).
         e. For each work block in extracted["entradas"]:
            - Normalise machine code (D4).
            - Resolve MachineAsset from fleet catalogue.
            - Compute delta_horas (net hours after lunch break deduction).
            - Persist WorkOrderEntryLine.
         f. Increment processed_pages counter.
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
         b. Derivar worker_name del nombre del fichero PDF (no del texto manuscrito).
         c. Llamar a extract_work_order_page() -> dict multi-bloque de Gemini Vision.
         d. Persistir WorkOrderEntry (cabecera de página: fecha, operario, confianza).
         e. Por cada bloque de trabajo en extracted["entradas"]:
            - Normalizar código de máquina (D4).
            - Resolver MachineAsset del catálogo de flota.
            - Calcular delta_horas (horas netas tras descuento pausa comida).
            - Persistir WorkOrderEntryLine.
         f. Incrementar el contador processed_pages.
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

        # Derive worker name once from PDF filename for the entire WorkOrder.
        # Derivar el nombre del operario una vez del nombre del fichero PDF
        # para todo el WorkOrder.
        worker_name = _worker_name_from_pdf_path(work_order.source_pdf.name)
        logger.info("# [Tarea] Nombre de operario derivado del PDF: '%s'.", worker_name)

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

            # b/c) Call Gemini Vision extraction service (multi-block).
            # b/c) Llamar al servicio de extracción Gemini Vision (multi-bloque).
            extracted = extract_work_order_page(image_bytes)

            # Close stale DB connection before persisting — MySQL closes idle
            # connections during long Gemini Vision calls (wait_timeout).
            # Django reconnects automatically on the next DB operation.
            # Cerrar la conexión BD obsoleta antes de persistir — MySQL cierra
            # las conexiones inactivas durante las llamadas largas a Gemini
            # Vision (wait_timeout). Django reconecta automáticamente.
            connection.close()

            work_date      = _parse_date(extracted.get("fecha"))
            fecha_incierta = bool(extracted.get("fecha_incierta", False))
            confidence     = _coerce_confidence(extracted.get("extraction_confidence"))
            entradas       = extracted.get("entradas") or []

            # d) Persist WorkOrderEntry (page header).
            # d) Persistir WorkOrderEntry (cabecera de página).
            with transaction.atomic():
                entry, _ = WorkOrderEntry.objects.update_or_create(
                    work_order  = work_order,
                    page_number = page_number_one,
                    defaults    = {
                        "worker_name":           worker_name,
                        "work_date":             work_date,
                        "fecha_incierta":        fecha_incierta,
                        "raw_gemini_response":   extracted,
                        "extraction_confidence": confidence,
                    },
                )

                # e) Persist one WorkOrderEntryLine per work block.
                # e) Persistir un WorkOrderEntryLine por bloque de trabajo.
                for line_idx, bloque in enumerate(entradas, start=1):
                    maquina_raw  = (bloque.get("maquina_raw") or "").strip()
                    maquina_norm = _normalise_machine_code(maquina_raw)
                    machine_asset = _resolve_machine_asset(maquina_norm)

                    hc = _parse_time(bloque.get("hc"))
                    hf = _parse_time(bloque.get("hf"))
                    delta = _compute_delta_horas(hc, hf)

                    flags = bloque.get("flags") or []
                    if not isinstance(flags, list):
                        flags = []

                    WorkOrderEntryLine.objects.update_or_create(
                        entry       = entry,
                        line_number = line_idx,
                        defaults    = {
                            "machine_asset":     machine_asset,
                            "maquina_raw":       maquina_raw,
                            "maquina_norm":      maquina_norm,
                            "descripcion_averia": (
                                bloque.get("descripcion_averia") or ""
                            ),
                            "reparacion":        (bloque.get("reparacion") or ""),
                            "hc":                hc,
                            "hf":                hf,
                            "or_val":            (bloque.get("or_val") or ""),
                            "delta_horas":       delta,
                            "flags":             flags,
                        },
                    )

                    logger.info(
                        "# [Tarea] Pág. %d · Bloque %d: máquina='%s' → '%s' "
                        "(asset=%s) | %s–%s | Δ=%s h",
                        page_number_one,
                        line_idx,
                        maquina_raw,
                        maquina_norm,
                        machine_asset.codigo if machine_asset else "NO RESUELTO",
                        hc.strftime("%H:%M") if hc else "--",
                        hf.strftime("%H:%M") if hf else "--",
                        str(delta) if delta is not None else "?",
                    )

            # f) Increment processed_pages counter.
            # f) Incrementar el contador processed_pages.
            work_order.processed_pages = page_number_one
            work_order.save(update_fields=["processed_pages"])

            logger.info(
                "# [Tarea] Página %d persistida. Confianza: %s | Bloques: %d.",
                page_number_one,
                confidence,
                len(entradas),
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
