# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/work_order_processor/management/commands/backfill_task_types.py

"""
Management command: backfill_task_types
Backfills tipo_tarea/task_category_free (and corrects fault_category/
fault_subcategory) for WorkOrderEntryLine records classified before the
tipo_tarea concept existed (H10 Paso 4-bis, added 2026-07-08).

Context: from 2026-05-13 (S023/S024, first fault-classification backfill)
until 2026-07-08, every WorkOrderEntryLine was classified via the legacy
classify_fault() prompt, which has no "this is not a fault" option and
forces every description into a real FaultCategory (often OTHER). This
mislabels genuine maintenance/improvement/fabrication tasks (washing,
refuelling, courses, workshop tidying...) as faults. This command
reclassifies every affected line via classify_task() (the prompt already
in production since 2026-07-08), and:
  - Sets tipo_tarea/task_category_free on the line always.
  - Sets fault_category/fault_subcategory only when tipo_tarea=AVERIA;
    clears them (empty string) otherwise -- correcting the old bias.
  - If the line has a breakdown_ticket whose ticket is already
    classified, mirrors the ticket's result instead of calling Gemini
    again (same idempotency contract as tasks.classify_fault_line).
  - If the line has an unclassified breakdown_ticket, mirrors the fresh
    result onto the ticket too.

Target queryset: WorkOrderEntryLine with non-empty fault_description and
empty tipo_tarea -- this naturally covers both the historical PDF
backlog and the post-2026-05-13 digital lines, regardless of whatever
fault_category value the old prompt already assigned.

---

Comando de gestión: backfill_task_types
Rellena retroactivamente tipo_tarea/task_category_free (y corrige
fault_category/fault_subcategory) en los registros WorkOrderEntryLine
clasificados antes de que existiera el concepto de tipo_tarea (H10 Paso
4-bis, añadido 2026-07-08).

Contexto: desde el 13/05/2026 (S023/S024, primer backfill de
clasificación de averías) hasta el 08/07/2026, toda WorkOrderEntryLine
se clasificó vía el prompt antiguo classify_fault(), que no tiene opción
de "esto no es una avería" y fuerza cualquier descripción a encajar en
una FaultCategory real (a menudo OTHER). Esto etiqueta mal tareas
genuinas de mantenimiento/mejora/fabricación (lavados, repostajes,
cursos, orden del taller...) como averías. Este comando reclasifica cada
línea afectada vía classify_task() (el prompt ya en producción desde el
08/07/2026), y:
  - Establece tipo_tarea/task_category_free en la línea siempre.
  - Establece fault_category/fault_subcategory solo cuando
    tipo_tarea=AVERIA; los vacía (cadena vacía) en caso contrario --
    corrigiendo el sesgo antiguo.
  - Si la línea tiene breakdown_ticket y ese ticket ya está clasificado,
    refleja el resultado del ticket en vez de volver a llamar a Gemini
    (mismo contrato de idempotencia que tasks.classify_fault_line).
  - Si la línea tiene un breakdown_ticket sin clasificar, refleja el
    resultado nuevo también en el ticket.

Queryset objetivo: WorkOrderEntryLine con fault_description no vacía y
tipo_tarea vacío -- esto cubre de forma natural tanto el histórico PDF
como las líneas digitales posteriores al 13/05/2026, con independencia
del valor de fault_category que ya le hubiera asignado el prompt
antiguo.
"""

import time

from django.core.management.base import BaseCommand

from work_order_processor.models import WorkOrderEntryLine
from work_order_processor.services import classify_task


class Command(BaseCommand):
    """
    Django management command that backfills tipo_tarea classification
    on WorkOrderEntryLine records that predate the tipo_tarea concept.

    Usage:
        python -m dotenv run python manage.py backfill_task_types
        python -m dotenv run python manage.py backfill_task_types --dry-run
        python -m dotenv run python manage.py backfill_task_types --limit 20
        python -m dotenv run python manage.py backfill_task_types \
            --batch-size 100

    ---

    Comando de gestión Django que rellena retroactivamente la
    clasificación tipo_tarea en registros WorkOrderEntryLine anteriores
    al concepto de tipo_tarea.

    Uso:
        python -m dotenv run python manage.py backfill_task_types
        python -m dotenv run python manage.py backfill_task_types --dry-run
        python -m dotenv run python manage.py backfill_task_types --limit 20
        python -m dotenv run python manage.py backfill_task_types \
            --batch-size 100
    """

    help = (
        "Reclasifica tipo_tarea/fault_category/fault_subcategory/"
        "task_category_free en WorkOrderEntryLine vía classify_task(), "
        "corrigiendo las líneas clasificadas con el prompt antiguo "
        "(sin concepto de tipo_tarea) entre el 13/05/2026 y el "
        "08/07/2026. Idempotente y seguro para múltiples ejecuciones."
    )

    def add_arguments(self, parser):
        """
        Registers optional CLI arguments for the command.
        ---
        Registra los argumentos CLI opcionales del comando.
        """
        parser.add_argument(
            "--batch-size",
            type=int,
            default=50,
            help="Número de líneas a iterar por chunk (por defecto: 50).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=False,
            help=(
                "Simula la reclasificación sin llamar a Gemini ni "
                "persistir cambios. Solo cuenta cuántas líneas se "
                "verían afectadas."
            ),
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help=(
                "Procesa como máximo N líneas (para probar en un "
                "subconjunto pequeño antes de lanzar todo el backlog)."
            ),
        )

    def handle(self, *args, **options):
        """
        Main entry point for the management command.

        Execution flow:
          1. Build base queryset: non-empty fault_description, empty
             tipo_tarea, ordered by pk.
          2. Apply --limit if given.
          3. Iterate in batches. For each line:
             a. If linked to an already-classified ticket: mirror onto
                the line without a new Gemini call.
             b. Otherwise call classify_task() (with 429 retry, up to 3
                attempts, 60 s wait -- same contract as
                tasks.classify_fault_line), persist on the line, and
                mirror onto the ticket if one is linked.
          4. Print progress every 20 lines and a final summary broken
             down by tipo_tarea.

        ---

        Punto de entrada principal del comando.

        Flujo de ejecución:
          1. Construir el queryset base: fault_description no vacía,
             tipo_tarea vacío, ordenado por pk.
          2. Aplicar --limit si se indica.
          3. Iterar en batches. Por cada línea:
             a. Si está vinculada a un ticket ya clasificado: reflejar
                en la línea sin nueva llamada a Gemini.
             b. Si no, llamar a classify_task() (con reintento ante 429,
                hasta 3 intentos, espera de 60 s -- mismo contrato que
                tasks.classify_fault_line), persistir en la línea, y
                reflejar en el ticket si hay uno vinculado.
          4. Imprimir progreso cada 20 líneas y un resumen final
             desglosado por tipo_tarea.
        """
        batch_size = options["batch_size"]
        dry_run    = options["dry_run"]
        limit      = options["limit"]

        if dry_run:
            self.stdout.write(
                "# [backfill_task_types] MODO DRY-RUN activo — no se "
                "llamará a Gemini ni se persistirá ningún cambio."
            )

        # ------------------------------------------------------------------
        # Step 1 — Build base queryset.
        # Paso 1 — Construir queryset base.
        # ------------------------------------------------------------------
        base_qs = (
            WorkOrderEntryLine.objects
            .exclude(fault_description="")
            .filter(tipo_tarea="")
            .select_related("breakdown_ticket")
            .order_by("pk")
        )

        if limit:
            base_qs = base_qs[:limit]

        total_pending = base_qs.count()
        self.stdout.write(
            f"# [backfill_task_types] Líneas pendientes de reclasificar: "
            f"{total_pending}."
        )

        if total_pending == 0:
            self.stdout.write(
                "# [backfill_task_types] Nada que procesar."
            )
            return

        # ------------------------------------------------------------------
        # Counters / Contadores
        # ------------------------------------------------------------------
        count_processed  = 0
        count_mirrored   = 0  # From already-classified ticket, no Gemini call.
        count_gemini     = 0  # Classified via a fresh Gemini call.
        count_empty      = 0  # classify_task() returned empty tipo_tarea.
        count_errors     = 0
        by_tipo = {
            "AVERIA": 0, "MEJORA": 0, "MANTENIMIENTO": 0, "FABRICACION": 0,
        }

        self.stdout.write(
            f"# [backfill_task_types] Iniciando iteración — "
            f"batch_size={batch_size} | dry_run={dry_run} | "
            f"limit={limit}."
        )

        # ------------------------------------------------------------------
        # Step 2/3 — Iterate and classify.
        # Paso 2/3 — Iterar y clasificar.
        # ------------------------------------------------------------------
        for line in base_qs.iterator(chunk_size=batch_size):
            count_processed += 1
            try:
                ticket = line.breakdown_ticket

                # --- Case A: ticket already classified -- mirror only. ---
                # --- Caso A: ticket ya clasificado -- solo reflejar. ---
                if ticket is not None and ticket.tipo_tarea:
                    tipo = ticket.tipo_tarea
                    fault_category = (
                        ticket.fault_category if tipo == "AVERIA" else ""
                    )
                    if dry_run:
                        self.stdout.write(
                            f"# [backfill_task_types] pk={line.pk} "
                            f"[DRY-RUN] reflejaría desde ticket "
                            f"pk={ticket.pk} tipo_tarea={tipo}. "
                            f"Sin persistir."
                        )
                    else:
                        WorkOrderEntryLine.objects.filter(
                            pk=line.pk
                        ).update(
                            tipo_tarea=tipo,
                            task_category_free=ticket.task_category_free,
                            fault_category=fault_category,
                        )
                        self.stdout.write(
                            f"# [backfill_task_types] pk={line.pk} "
                            f"reflejado desde ticket pk={ticket.pk} "
                            f"tipo_tarea={tipo}. Persistido."
                        )
                    count_mirrored += 1
                    if tipo in by_tipo:
                        by_tipo[tipo] += 1
                    _print_progress(self, count_processed, total_pending)
                    continue

                # --- Case B: fresh classification via Gemini. ---
                # --- Caso B: clasificación nueva vía Gemini. ---
                if dry_run:
                    self.stdout.write(
                        f"# [backfill_task_types] pk={line.pk} "
                        f"[DRY-RUN] requeriría llamada a "
                        f"classify_task(). Omitida."
                    )
                    _print_progress(self, count_processed, total_pending)
                    continue

                result = _classify_with_retry(
                    self,
                    line.pk,
                    line.fault_description or "",
                    line.repair_notes or "",
                )

                if result is None:
                    count_errors += 1
                    _print_progress(self, count_processed, total_pending)
                    continue

                if not result["tipo_tarea"]:
                    self.stdout.write(
                        f"# [backfill_task_types] pk={line.pk} "
                        f"classify_task() devolvió tipo_tarea vacío. "
                        f"Omitida."
                    )
                    count_empty += 1
                    _print_progress(self, count_processed, total_pending)
                    continue

                WorkOrderEntryLine.objects.filter(pk=line.pk).update(
                    tipo_tarea=result["tipo_tarea"],
                    task_category_free=result["task_category_free"],
                    fault_category=result["fault_category"],
                    fault_subcategory=result["fault_subcategory"],
                )

                if ticket is not None:
                    ticket.tipo_tarea = result["tipo_tarea"]
                    ticket.fault_category = result["fault_category"]
                    ticket.task_category_free = (
                        result["task_category_free"]
                    )
                    ticket.save(update_fields=[
                        "tipo_tarea", "fault_category",
                        "task_category_free",
                    ])

                self.stdout.write(
                    f"# [backfill_task_types] pk={line.pk} clasificada: "
                    f"tipo_tarea={result['tipo_tarea']}. Persistido."
                )
                count_gemini += 1
                if result["tipo_tarea"] in by_tipo:
                    by_tipo[result["tipo_tarea"]] += 1

                _print_progress(self, count_processed, total_pending)

            except Exception as exc:
                # Defensa en profundidad: una fila problemática (borrada
                # en producción durante el backfill, fallo de red al
                # guardar, etc.) no debe tumbar el resto del proceso.
                # ---
                # Defence in depth: one problematic row (deleted in
                # production during the backfill, network failure while
                # saving, etc.) must never bring down the rest of the
                # run.
                count_errors += 1
                self.stdout.write(
                    f"# [backfill_task_types] pk={line.pk}: error "
                    f"inesperado — {exc}. Línea omitida, continúa el "
                    f"resto."
                )
                _print_progress(self, count_processed, total_pending)
                continue

        # ------------------------------------------------------------------
        # Final summary / Resumen final
        # ------------------------------------------------------------------
        dry_run_label = (
            " [DRY-RUN — sin cambios persistidos]" if dry_run else ""
        )
        self.stdout.write(
            f"# [backfill_task_types] COMPLETADO{dry_run_label}.\n"
            f"#   Procesadas:           {count_processed}\n"
            f"#   Reflejadas (ticket):  {count_mirrored}\n"
            f"#   Clasificadas (Gemini):{count_gemini}\n"
            f"#   Sin resultado:        {count_empty}\n"
            f"#   Errores:              {count_errors}\n"
            f"#   --- Por tipo_tarea ---\n"
            f"#   AVERIA:               {by_tipo['AVERIA']}\n"
            f"#   MEJORA:               {by_tipo['MEJORA']}\n"
            f"#   MANTENIMIENTO:        {by_tipo['MANTENIMIENTO']}\n"
            f"#   FABRICACION:          {by_tipo['FABRICACION']}"
        )


# ---------------------------------------------------------------------------
# Module-level helpers / Funciones auxiliares de módulo
# ---------------------------------------------------------------------------

def _classify_with_retry(
    command_instance, line_pk, fault_description, repair_notes,
    max_retries=3,
):
    """
    Calls classify_task() with the given fault_description/repair_notes
    (already loaded by the caller from the outer queryset -- no re-fetch
    by pk here, precisely to avoid a DoesNotExist race if the row is
    edited/deleted concurrently in production during a long-running
    backfill). Retries up to max_retries times on Vertex AI 429
    (ResourceExhausted), waiting 60 s between attempts -- same contract
    as tasks.classify_fault_line. Returns the result dict, or None if an
    unrecoverable error occurred.
    ---
    Llama a classify_task() con el fault_description/repair_notes ya
    cargados por quien llama, desde el queryset externo -- sin volver a
    consultar por pk aquí, precisamente para evitar una condición de
    carrera DoesNotExist si la fila se edita/borra en producción durante
    un backfill largo. Reintenta hasta max_retries veces ante 429 de
    Vertex AI (ResourceExhausted), esperando 60 s entre intentos --
    mismo contrato que tasks.classify_fault_line. Devuelve el dict
    resultado, o None si hubo un error irrecuperable.
    """
    for attempt in range(1, max_retries + 1):
        try:
            return classify_task(
                fault_description=fault_description,
                repair_notes=repair_notes,
            )
        except Exception as exc:
            exc_str = str(exc)
            if "429" in exc_str or "RESOURCE_EXHAUSTED" in exc_str:
                command_instance.stdout.write(
                    f"# [backfill_task_types] pk={line_pk}: Vertex AI "
                    f"429 detectado (intento {attempt}/{max_retries}). "
                    f"Esperando 60 s."
                )
                if attempt < max_retries:
                    time.sleep(60)
                    continue
            command_instance.stdout.write(
                f"# [backfill_task_types] pk={line_pk}: error "
                f"irrecuperable — {exc}. Línea omitida."
            )
            return None

    return None


def _print_progress(command_instance, processed, total):
    """
    Prints a minimal progress line every 20 processed lines.
    ---
    Imprime una línea de progreso mínima cada 20 líneas procesadas.
    """
    if processed % 20 == 0:
        command_instance.stdout.write(
            f"# [backfill_task_types] Progreso: {processed}/{total}"
        )
