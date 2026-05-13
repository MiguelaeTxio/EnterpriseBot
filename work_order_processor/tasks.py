# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/work_order_processor/tasks.py

"""
Celery tasks for the work_order_processor application.
Defines two background tasks:
  - process_work_order_pdf(): orchestrates the full PDF processing pipeline:
    page rasterisation via PyMuPDF, Gemini Vision multi-block extraction per
    page, WorkOrderEntry + WorkOrderEntryLine persistence, machine catalogue
    resolution and final Excel report generation.
  - classify_fault_line(): receives a WorkOrderEntryLine pk, calls
    classify_fault() from services.py and persists the returned
    (fault_category, fault_subcategory) pair. Enqueued automatically after
    every WorkOrderEntryLine INSERT (Hito 7 / S023).

---

Tareas Celery para la aplicación work_order_processor.
Define dos tareas de fondo:
  - process_work_order_pdf(): orquesta el pipeline completo de procesamiento
    de PDF: rasterización de páginas con PyMuPDF, extracción multi-bloque
    Gemini Vision por página, persistencia de WorkOrderEntry +
    WorkOrderEntryLine, resolución del catálogo de maquinaria y generación
    final del informe Excel.
  - classify_fault_line(): recibe el pk de una WorkOrderEntryLine, llama a
    classify_fault() de services.py y persiste el par devuelto
    (fault_category, fault_subcategory). Se encola automáticamente tras cada
    INSERT de WorkOrderEntryLine (Hito 7 / S023).
"""

import logging
import os
import re
import time
from datetime import date, timedelta

import fitz  # PyMuPDF
from celery.contrib.django.task import DjangoTask
from django.db import connection, transaction
from enterprise_core.celery import app

from .models import WorkOrder, WorkOrderEntry, WorkOrderEntryLine
from .services import (
    _coerce_confidence,
    _compute_delta_hours,
    _normalise_machine_code,
    _parse_date,
    _parse_time,
    _resolve_machine_asset,
    _worker_name_from_pdf_path,
    classify_fault,
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


def _extract_period_from_pdf_name(pdf_name: str) -> tuple[date | None, date | None]:
    """
    Extracts the work period (start_date, end_date) from the PDF filename.
    Canonical format: NAME DD-MM-YY AL DD-MM-YY.pdf
    The year is given explicitly as a 2-digit suffix (e.g. 25 -> 2025).
    Separators between tokens may be spaces or underscores interchangeably.

    Returns (None, None) if the filename does not match the expected format.

    ---

    Extrae el periodo de trabajo (fecha_inicio, fecha_fin) del nombre del PDF.
    Formato canónico: NOMBRE DD-MM-AA AL DD-MM-AA.pdf
    El año viene explícito como sufijo de 2 dígitos (ej. 25 -> 2025).
    Los separadores entre tokens pueden ser espacios o guiones bajos indistintamente.

    Devuelve (None, None) si el nombre no coincide con el formato esperado.
    """
    stem = os.path.splitext(os.path.basename(pdf_name))[0]

    # Accept spaces or underscores as token separators.
    # Aceptar espacios o guiones bajos como separadores de tokens.
    # Format: DD-MM-YY AL DD-MM-YY (case-insensitive AL)
    pattern = r'(\d{2})-(\d{2})-(\d{2})[_\s]+[Aa][Ll][_\s]+(\d{2})-(\d{2})-(\d{2})'
    m       = re.search(pattern, stem)
    if not m:
        return None, None

    start_day, start_month, start_yy = int(m.group(1)), int(m.group(2)), int(m.group(3))
    end_day,   end_month,   end_yy   = int(m.group(4)), int(m.group(5)), int(m.group(6))

    # Convert 2-digit year to 4-digit: assume 2000s.
    # Convertir año de 2 dígitos a 4 dígitos: asumir siglo XXI.
    start_year = 2000 + start_yy
    end_year   = 2000 + end_yy

    try:
        start_date = date(start_year, start_month, start_day)
        end_date   = date(end_year,   end_month,   end_day)
        return start_date, end_date
    except ValueError:
        return None, None


def _infer_dates_from_context(
    work_order_id: int,
    period_start: date | None,
    period_end:   date | None,
) -> None:
    """
    Post-extraction date correction pass.

    For each WorkOrderEntry belonging to this WorkOrder, attempts to infer
    missing or out-of-range dates using:
      - The work period extracted from the PDF filename.
      - The chronological sequence of entries (pages are ordered).
      - The constraint that work days are Monday–Friday.
      - Context from neighbouring entries with known dates.

    Inference rules (applied in order):
      R1. If work_date is not None and within the period, accept it as-is.
      R2. If work_date is None or outside the period:
          a. Determine the previous known date (prev) and next known date (nxt).
          b. Enumerate all weekdays between prev+1 and nxt-1.
          c. If exactly one weekday candidate exists, assign it unambiguously
             (uncertain_date=False).
          d. If multiple candidates exist, assign the first one and set
             uncertain_date=True (human review required).
          e. If no candidates exist (holiday gap, absence), leave as-is
             and set uncertain_date=True.

    Updates are persisted directly via QuerySet.update() to avoid
    triggering signals.

    ---

    Pase de corrección de fechas post-extracción.

    Para cada WorkOrderEntry de este WorkOrder, intenta inferir fechas
    ausentes o fuera de rango usando:
      - El periodo de trabajo extraído del nombre del PDF.
      - La secuencia cronológica de entradas (las páginas van ordenadas).
      - La restricción de que los días laborables son de lunes a viernes.
      - El contexto de entradas vecinas con fechas conocidas.

    Reglas de inferencia (aplicadas en orden):
      R1. Si work_date no es None y está dentro del periodo, se acepta.
      R2. Si work_date es None o está fuera del periodo:
          a. Determinar la fecha conocida anterior (prev) y la siguiente (nxt).
          b. Enumerar todos los días laborables entre prev+1 y nxt-1.
          c. Si existe exactamente un candidato, asignarlo sin ambigüedad
             (uncertain_date=False).
          d. Si hay varios candidatos, asignar el primero y marcar
             uncertain_date=True (revisión humana necesaria).
          e. Si no hay candidatos (festivo, ausencia), dejar como está
             y marcar uncertain_date=True.

    Las actualizaciones se persisten via QuerySet.update() para no
    disparar señales.
    """
    entries = list(
        WorkOrderEntry.objects
        .filter(work_order_id=work_order_id)
        .order_by("page_number")
        .values("id", "work_date", "uncertain_date", "page_number")
    )

    if not entries:
        return

    n = len(entries)

    def _is_valid(d: date | None) -> bool:
        """True if d is a known weekday strictly within the work period.
        Rejects dates whose year does not match the period year to prevent
        OCR year misreads (e.g. 2020 instead of 2025) from polluting the
        date sequence.
        --- True si d es un día laborable estrictamente dentro del periodo.
        Rechaza fechas cuyo año no coincida con el del periodo para evitar
        que errores de OCR en el año (ej. 2020 en lugar de 2025) contaminen
        la secuencia de fechas.
        """
        if d is None:
            return False
        if d.weekday() >= 5:   # Saturday=5, Sunday=6
            return False
        if period_start and d < period_start:
            return False
        if period_end and d > period_end:
            return False
        # Reject if year does not match the period year(s).
        # Rechazar si el año no coincide con el año del periodo.
        if period_start and period_end:
            valid_years = {period_start.year, period_end.year}
            if d.year not in valid_years:
                return False
        return True

    def _weekdays_between(d_start: date, d_end: date) -> list[date]:
        """Returns weekdays strictly between d_start and d_end.
        --- Devuelve días laborables estrictamente entre d_start y d_end.
        """
        result = []
        cursor = d_start + timedelta(days=1)
        while cursor < d_end:
            if cursor.weekday() < 5:
                result.append(cursor)
            cursor += timedelta(days=1)
        return result

    # Build list of known dates indexed by position.
    # Construir lista de fechas conocidas indexadas por posición.
    known: list[date | None] = [
        e["work_date"] if _is_valid(e["work_date"]) else None
        for e in entries
    ]

    # Add period boundaries as synthetic anchors if available.
    # Añadir límites del periodo como anclas sintéticas si están disponibles.
    anchor_start = period_start if period_start else None
    anchor_end   = period_end   if period_end   else None

    updates: list[tuple[int, date, bool]] = []  # (entry_id, new_date, uncertain_date)

    for i, entry in enumerate(entries):
        if _is_valid(known[i]):
            # R1: already valid, nothing to do.
            # R1: ya es válida, nada que hacer.
            continue

        # Find previous known date (real neighbour only, not synthetic anchor).
        # Encontrar fecha conocida anterior (sólo vecino real, no ancla sintética).
        prev: date | None = None
        has_real_prev = False
        for j in range(i - 1, -1, -1):
            if known[j] is not None:
                prev = known[j]
                has_real_prev = True
                break

        # Find next known date (real neighbour only, not synthetic anchor).
        # Encontrar fecha conocida siguiente (sólo vecino real, no ancla sintética).
        nxt: date | None = None
        has_real_nxt = False
        for j in range(i + 1, n):
            if known[j] is not None:
                nxt = known[j]
                has_real_nxt = True
                break

        # Enumerate candidates.
        # Enumerar candidatos.
        if has_real_prev and has_real_nxt:
            # Both real neighbours known: infer strictly between them.
            # Ambos vecinos reales conocidos: inferir estrictamente entre ellos.
            candidates = _weekdays_between(prev, nxt)
        elif has_real_prev and not has_real_nxt:
            # No real next neighbour: try period_end as upper bound if available,
            # otherwise take the next weekday after prev.
            # Sin vecino siguiente real: usar period_end como cota superior si
            # está disponible, si no, tomar el siguiente día laborable tras prev.
            if anchor_end is not None:
                candidates = _weekdays_between(prev, anchor_end)
                if not candidates:
                    # prev IS anchor_end or adjacent: take next weekday after prev.
                    # prev ES anchor_end o adyacente: tomar el siguiente laborable.
                    cursor = prev + timedelta(days=1)
                    while cursor.weekday() >= 5:
                        cursor += timedelta(days=1)
                    candidates = [cursor]
            else:
                cursor = prev + timedelta(days=1)
                while cursor.weekday() >= 5:
                    cursor += timedelta(days=1)
                candidates = [cursor]
        elif not has_real_prev and has_real_nxt:
            # No real previous neighbour: use period_start as the candidate if it
            # is a valid weekday strictly before nxt, otherwise take the weekday
            # immediately before nxt.
            # Sin vecino anterior real: usar period_start como candidato si es un
            # día laborable estrictamente anterior a nxt; si no, el laborable
            # inmediatamente anterior a nxt.
            if anchor_start is not None and anchor_start < nxt and anchor_start.weekday() < 5:
                candidates = [anchor_start]
            else:
                cursor = nxt - timedelta(days=1)
                while cursor.weekday() >= 5:
                    cursor -= timedelta(days=1)
                candidates = [cursor]
        elif not has_real_prev and not has_real_nxt:
            # No real neighbours at all: use period_start if available and valid.
            # Sin vecinos reales en absoluto: usar period_start si está disponible
            # y es válido.
            if anchor_start is not None and anchor_start.weekday() < 5:
                candidates = [anchor_start]
            else:
                candidates = []
        else:
            candidates = []

        if len(candidates) == 1:
            # Unambiguous inference.
            # Inferencia unívoca.
            inferred        = candidates[0]
            uncertain_date  = False
            known[i]        = inferred
            updates.append((entry["id"], inferred, uncertain_date))
            logger.info(
                "# [Fechas] Pág. %d: fecha inferida inequívocamente → %s.",
                entry["page_number"], inferred.isoformat(),
            )
        elif len(candidates) > 1:
            # Ambiguous: assign first candidate, flag for review.
            # Ambiguo: asignar el primer candidato, marcar para revisión.
            inferred        = candidates[0]
            uncertain_date  = True
            known[i]        = inferred
            updates.append((entry["id"], inferred, uncertain_date))
            logger.warning(
                "# [Fechas] Pág. %d: %d candidatos — asignado %s (incierto).",
                entry["page_number"], len(candidates), inferred.isoformat(),
            )
        else:
            # No candidates: cannot infer. Log and leave unchanged.
            # Sin candidatos: no se puede inferir. Registrar y dejar sin cambios.
            logger.warning(
                "# [Fechas] Pág. %d: sin candidatos laborables — fecha no inferida.",
                entry["page_number"],
            )

    # Persist inferred dates / Persistir fechas inferidas.
    connection.close()
    for entry_id, new_date, uncertain_date in updates:
        WorkOrderEntry.objects.filter(pk=entry_id).update(
            work_date      = new_date,
            uncertain_date = uncertain_date,
        )

    logger.info(
        "# [Fechas] Pase de corrección completado. %d entradas actualizadas.",
        len(updates),
    )


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
            - Compute delta_hours (net hours after lunch break deduction).
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
            - Calcular delta_hours (horas netas tras descuento pausa comida).
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
            uncertain_date = bool(extracted.get("fecha_incierta", False))
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
                        "uncertain_date":        uncertain_date,
                        "raw_gemini_response":   extracted,
                        "extraction_confidence": confidence,
                    },
                )

                # e) Persist one WorkOrderEntryLine per work block.
                # e) Persistir un WorkOrderEntryLine por bloque de trabajo.
                for line_idx, bloque in enumerate(entradas, start=1):
                    machine_raw  = (bloque.get("maquina_raw") or "").strip()
                    machine_norm = _normalise_machine_code(machine_raw)
                    machine_asset = _resolve_machine_asset(machine_norm)

                    hc = _parse_time(bloque.get("hc"))
                    hf = _parse_time(bloque.get("hf"))
                    delta = _compute_delta_hours(hc, hf)

                    flags = bloque.get("flags") or []
                    if not isinstance(flags, list):
                        flags = []

                    WorkOrderEntryLine.objects.update_or_create(
                        entry       = entry,
                        line_number = line_idx,
                        defaults    = {
                            "machine_asset":     machine_asset,
                            "machine_raw":       machine_raw,
                            "machine_norm":      machine_norm,
                            "fault_description": (
                                bloque.get("descripcion_averia") or ""
                            ),
                            "repair_notes":      (bloque.get("reparacion") or ""),
                            "hc":                hc,
                            "hf":                hf,
                            "or_val":            (bloque.get("or_val") or ""),
                            "delta_hours":       delta,
                            "flags":             flags,
                        },
                    )

                    logger.info(
                        "# [Tarea] Pág. %d · Bloque %d: máquina='%s' → '%s' "
                        "(asset=%s) | %s–%s | Δ=%s h",
                        page_number_one,
                        line_idx,
                        machine_raw,
                        machine_norm,
                        machine_asset.code if machine_asset else "NO RESUELTO",
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

            # Rate-limit guard: Vertex AI gemini-2.5-flash enforces a per-minute
            # request quota. A fixed pause between pages prevents RESOURCE_EXHAUSTED
            # (HTTP 429) errors when processing multi-page PDFs.
            # Guardia de rate limit: Vertex AI gemini-2.5-flash aplica una cuota
            # de peticiones por minuto. Una pausa fija entre páginas evita errores
            # RESOURCE_EXHAUSTED (HTTP 429) al procesar PDFs de múltiples páginas.
            time.sleep(15)

        pdf_document.close()

        # ------------------------------------------------------------------
        # Step 3.5 — Date correction pass
        # Paso 3.5 — Pase de corrección de fechas
        # ------------------------------------------------------------------
        # Infer missing or out-of-range dates using the work period from the
        # PDF filename and the chronological sequence of pages (Mon-Fri rule).
        # Inferir fechas ausentes o fuera de rango usando el periodo del nombre
        # del PDF y la secuencia cronológica de páginas (regla lunes-viernes).
        logger.info(
            "# [Tarea] Iniciando pase de corrección de fechas para WorkOrder #%d.",
            work_order_id,
        )
        _period_start, _period_end = _extract_period_from_pdf_name(
            work_order.source_pdf.name
        )
        if _period_start:
            logger.info(
                "# [Fechas] Periodo detectado: %s → %s.",
                _period_start.isoformat(),
                _period_end.isoformat() if _period_end else "desconocido",
            )
        else:
            logger.warning(
                "# [Fechas] No se pudo extraer el periodo del nombre del PDF. "
                "Corrección de fechas omitida.",
            )
        _infer_dates_from_context(work_order_id, _period_start, _period_end)

        # ------------------------------------------------------------------
        # Step 4 — Generate Excel report
        # Paso 4 — Generar informe Excel
        # ------------------------------------------------------------------
        logger.info(
            "# [Tarea] Iniciando generación de Excel para WorkOrder #%d.",
            work_order_id,
        )
        generate_work_order_excel(work_order_id)

        # ------------------------------------------------------------------
        # Step 5 — Delete source PDF from disk (Paso 14 — Hito 8)
        # Paso 5 — Eliminar el PDF original del disco (Paso 14 — Hito 8)
        #
        # The source PDF is consumed by this point: all pages have been
        # rasterised, extracted, persisted in DB and the Excel has been
        # generated. Retaining the file provides no further value and
        # wastes PythonAnywhere storage quota.
        #
        # Strategy:
        #   - Obtain the physical path from source_pdf before clearing the
        #     field, so the file can be removed even if the field is later
        #     cleared by another process.
        #   - Delete the physical file via Django's storage backend
        #     (source_pdf.delete(save=False)) which handles both local and
        #     cloud storage transparently.
        #   - Set source_pdf to '' (empty) in the DB so that any code that
        #     checks `if wo.source_pdf` correctly evaluates to False.
        #   - The source_pdf_hash field is deliberately kept intact: it is
        #     the sole mechanism for Level-1 exact-duplicate detection and
        #     must survive the PDF deletion.
        #
        # El PDF de origen queda consumido en este punto: todas las páginas
        # han sido rasterizadas, extraídas, persistidas en BD y el Excel ha
        # sido generado. Conservar el fichero no aporta valor y desperdicia
        # cuota de almacenamiento en PythonAnywhere.
        #
        # Estrategia:
        #   - Obtener la ruta física desde source_pdf antes de limpiar el
        #     campo, de modo que el fichero pueda eliminarse aunque otra
        #     parte del código limpie el campo posteriormente.
        #   - Eliminar el fichero físico via el backend de almacenamiento de
        #     Django (source_pdf.delete(save=False)), que gestiona tanto
        #     almacenamiento local como en nube de forma transparente.
        #   - Vaciar source_pdf en BD para que el código que comprueba
        #     `if wo.source_pdf` evalúe correctamente a False.
        #   - El campo source_pdf_hash se conserva deliberadamente intacto:
        #     es el único mecanismo de detección de duplicados exactos
        #     (Nivel 1) y debe sobrevivir al borrado del PDF.
        # ------------------------------------------------------------------
        work_order.refresh_from_db(fields=["source_pdf"])

        if work_order.source_pdf:
            pdf_physical_path = work_order.source_pdf.path
            try:
                work_order.source_pdf.delete(save=False)
                work_order.source_pdf = ""
                work_order.save(update_fields=["source_pdf"])
                logger.info(
                    "# [Tarea] PDF original eliminado del disco: %s "
                    "(WorkOrder #%d).",
                    pdf_physical_path,
                    work_order_id,
                )
            except Exception as pdf_exc:
                # Deletion failure is non-fatal: the WorkOrder is already DONE
                # and the Excel is available. Log the error and continue — a
                # failed PDF deletion must not revert the processing result.
                # El fallo en el borrado no es fatal: el WorkOrder ya está DONE
                # y el Excel está disponible. Registrar el error y continuar —
                # un fallo al borrar el PDF no debe revertir el resultado del
                # procesamiento.
                logger.warning(
                    "# [Tarea] No se pudo eliminar el PDF físico %s "
                    "para WorkOrder #%d: %s. El parte sigue disponible.",
                    pdf_physical_path,
                    work_order_id,
                    pdf_exc,
                )
        else:
            logger.info(
                "# [Tarea] source_pdf ya estaba vacío para WorkOrder #%d — "
                "borrado omitido.",
                work_order_id,
            )

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
            # ----------------------------------------------------------
            # Guard: verify the WorkOrder still exists in DB before
            # attempting to persist the ERROR status. The record may have
            # been deleted by a concurrent overwrite confirmation
            # (WorkOrderUploadView.post() duplicate_wo.delete()) while
            # this Celery task was already in flight for the old pk.
            # In that scenario the task failure is expected and harmless
            # — the new WorkOrder has been created and enqueued separately.
            # We log a clear diagnostic and abort without retrying.
            #
            # Guardia: verificar que el WorkOrder todavía existe en BD
            # antes de intentar persistir el estado ERROR. El registro
            # puede haber sido eliminado por una confirmación de
            # sobrescritura concurrente (duplicate_wo.delete() en
            # WorkOrderUploadView.post()) mientras esta tarea Celery ya
            # estaba en vuelo sobre el pk antiguo. En ese escenario el
            # fallo de la tarea es esperado e inocuo — el nuevo WorkOrder
            # ha sido creado y encolado de forma independiente.
            # Registramos un diagnóstico claro y abortamos sin reintentar.
            # ----------------------------------------------------------
            still_exists = WorkOrder.objects.filter(pk=work_order.pk).exists()
            if not still_exists:
                logger.warning(
                    "# [Tarea] WorkOrder #%d ya no existe en BD — fue eliminado "
                    "por una sobrescritura de duplicado mientras la tarea estaba "
                    "en vuelo. Tarea abortada sin reintentar.",
                    work_order_id,
                )
                return

            work_order.status    = WorkOrder.Status.ERROR
            work_order.error_log = f"Error en procesamiento de PDF: {exc}"
            work_order.save(update_fields=["status", "error_log"])

        # Re-raise so Celery retry logic can engage.
        # Relanzar para que la lógica de reintentos de Celery actúe.
        raise self.retry(exc=exc)


# ---------------------------------------------------------------------------
# classify_fault_line — automatic fault classification for a single entry line
# classify_fault_line — clasificación automática de avería para una línea
# ---------------------------------------------------------------------------

@app.task(
    base=DjangoTask,
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    queue="work_orders",
)
def classify_fault_line(self, entry_line_pk: int) -> None:
    """
    Celery task: classifies the fault described in a WorkOrderEntryLine and
    persists the result into fault_category and fault_subcategory fields.

    Flow:
      1. Load WorkOrderEntryLine by pk. Abort silently if it no longer exists
         (the record may have been deleted between enqueue and execution).
      2. Skip if both fault_category and fault_subcategory are already set
         (idempotency guard — safe for backfill retries).
      3. Call classify_fault(fault_description, repair_notes) from services.py.
         This performs a single Gemini Flash inference and returns a
         (category, subcategory) tuple, or ("", "") on any error.
      4. If the returned category is non-empty, persist both fields via
         update_fields (minimal write, no full-model save).
      5. On Vertex AI 429 (ResourceExhausted): wait 60 s and retry up to
         max_retries times (Key Learning — server-side contention pattern).
      6. On any other unrecoverable exception: log and do not retry (fault
         classification is best-effort; a failed classification must never
         block or re-queue indefinitely).

    ---

    Tarea Celery: clasifica la avería descrita en una WorkOrderEntryLine y
    persiste el resultado en los campos fault_category y fault_subcategory.

    Flujo:
      1. Cargar WorkOrderEntryLine por pk. Abortar silenciosamente si ya no
         existe (el registro puede haber sido eliminado entre el encolado y
         la ejecución).
      2. Omitir si fault_category y fault_subcategory ya están rellenos
         (guardia de idempotencia — segura para reintentos de backfill).
      3. Llamar a classify_fault(fault_description, repair_notes) de
         services.py. Realiza una única inferencia de Gemini Flash y devuelve
         una tupla (categoría, subcategoría), o ("", "") ante cualquier error.
      4. Si la categoría devuelta no está vacía, persistir ambos campos vía
         update_fields (escritura mínima, sin save() completo del modelo).
      5. Ante 429 de Vertex AI (ResourceExhausted): esperar 60 s y reintentar
         hasta max_retries veces (Key Learning — patrón de contención en servidor).
      6. Ante cualquier otra excepción irrecuperable: registrar y no reintentar
         (la clasificación de averías es best-effort; un fallo no debe bloquear
         ni encolar indefinidamente).
    """
    logger.info(
        "# [classify_fault_line] Iniciada para WorkOrderEntryLine pk=%d.",
        entry_line_pk,
    )

    # Step 1 — Load the entry line.
    # Paso 1 — Cargar la línea de parte.
    try:
        line = WorkOrderEntryLine.objects.get(pk=entry_line_pk)
    except WorkOrderEntryLine.DoesNotExist:
        logger.warning(
            "# [classify_fault_line] WorkOrderEntryLine pk=%d no encontrada — "
            "puede haber sido eliminada antes de la ejecución de la tarea. "
            "Tarea abortada.",
            entry_line_pk,
        )
        return

    # Step 2 — Idempotency guard.
    # Paso 2 — Guardia de idempotencia.
    if line.fault_category and line.fault_subcategory:
        logger.info(
            "# [classify_fault_line] pk=%d ya clasificada "
            "(category=%s subcategory=%s). Nada que hacer.",
            entry_line_pk,
            line.fault_category,
            line.fault_subcategory,
        )
        return

    try:
        # Step 3 — Call classify_fault().
        # Paso 3 — Llamar a classify_fault().
        category, subcategory = classify_fault(
            fault_description=line.fault_description or "",
            repair_notes=line.repair_notes or "",
        )

        # Step 4 — Persist if classification succeeded.
        # Paso 4 — Persistir si la clasificación tuvo éxito.
        if category:
            line.fault_category    = category
            line.fault_subcategory = subcategory
            line.save(update_fields=["fault_category", "fault_subcategory"])
            logger.info(
                "# [classify_fault_line] pk=%d clasificada: "
                "category=%s subcategory=%s.",
                entry_line_pk,
                category,
                subcategory,
            )
        else:
            logger.warning(
                "# [classify_fault_line] pk=%d: classify_fault devolvió "
                "categoría vacía. Los campos quedan sin rellenar.",
                entry_line_pk,
            )

    except Exception as exc:
        exc_str = str(exc)

        # Step 5 — Retry on Vertex AI 429 (ResourceExhausted).
        # Paso 5 — Reintentar ante 429 de Vertex AI (ResourceExhausted).
        if "429" in exc_str or "RESOURCE_EXHAUSTED" in exc_str:
            logger.warning(
                "# [classify_fault_line] pk=%d: Vertex AI 429 detectado "
                "(intento %d/%d). Reintentando en 60 s.",
                entry_line_pk,
                self.request.retries + 1,
                self.max_retries,
            )
            raise self.retry(exc=exc, countdown=60)

        # Step 6 — Log and do not retry for any other error.
        # Paso 6 — Registrar sin reintentar ante cualquier otro error.
        logger.error(
            "# [classify_fault_line] pk=%d: error irrecuperable en "
            "clasificación: %s. Los campos quedan sin rellenar.",
            entry_line_pk,
            exc,
            exc_info=True,
        )
