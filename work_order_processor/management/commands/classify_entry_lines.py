# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/work_order_processor/management/commands/classify_entry_lines.py

"""
Management command: classify_entry_lines
Backfills fault_category and fault_subcategory for WorkOrderEntryLine records
that were created before the automatic Celery classification was in place (Hito 7 / S023).

Iterates all WorkOrderEntryLine records with an empty fault_category in batches,
consulting find_cached_classification() first to avoid unnecessary Gemini calls,
then calling classify_fault() directly for lines with no cached match.

Results are persisted via targeted QuerySet.update() calls (no full-model save).
The command is fully idempotent: lines already classified are excluded from the
base queryset and are never re-processed.

---

Comando de gestión: classify_entry_lines
Rellena retroactivamente fault_category y fault_subcategory para los registros
WorkOrderEntryLine creados antes de que la clasificación automática Celery estuviera
activa (Hito 7 / S023).

Itera en batches todos los registros WorkOrderEntryLine con fault_category vacío,
consultando primero find_cached_classification() para evitar llamadas innecesarias a
Gemini, y llamando a classify_fault() directamente para las líneas sin coincidencia
en caché.

Los resultados se persisten mediante llamadas QuerySet.update() acotadas (sin save()
completo del modelo). El comando es totalmente idempotente: las líneas ya clasificadas
se excluyen del queryset base y nunca se reprocesarán.
"""


from django.core.management.base import BaseCommand

from work_order_processor.models import WorkOrderEntryLine
from work_order_processor.services import classify_fault, find_cached_classification


class Command(BaseCommand):
    """
    Django management command that backfills fault classification fields on
    WorkOrderEntryLine records whose fault_category is still empty.

    Usage:
        python -m dotenv run python manage.py classify_entry_lines
        python -m dotenv run python manage.py classify_entry_lines --batch-size 100
        python -m dotenv run python manage.py classify_entry_lines --dry-run

    ---

    Comando de gestión Django que rellena retroactivamente los campos de clasificación
    de averías en los registros WorkOrderEntryLine cuyo fault_category sigue vacío.

    Uso:
        python -m dotenv run python manage.py classify_entry_lines
        python -m dotenv run python manage.py classify_entry_lines --batch-size 100
        python -m dotenv run python manage.py classify_entry_lines --dry-run
    """

    help = (
        "Rellena retroactivamente fault_category y fault_subcategory en todos los "
        "WorkOrderEntryLine con fault_category vacío. Consulta primero la caché "
        "interna (find_cached_classification) y llama a Gemini Flash (classify_fault) "
        "solo cuando no hay coincidencia. Idempotente y seguro para múltiples ejecuciones."
    )

    def add_arguments(self, parser):
        """
        Registers optional CLI arguments for the command.

        --batch-size: number of lines processed per iterator chunk (default 50).
        --dry-run: simulate execution without persisting any changes.

        ---

        Registra los argumentos CLI opcionales del comando.

        --batch-size: número de líneas procesadas por chunk del iterador (por defecto 50).
        --dry-run: simula la ejecución sin persistir ningún cambio.
        """
        parser.add_argument(
            "--batch-size",
            type=int,
            default=50,
            help="Número de líneas a procesar por batch (por defecto: 50).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=False,
            help=(
                "Simula la clasificación sin persistir cambios. "
                "Útil para estimar el volumen de líneas pendientes."
            ),
        )

    def handle(self, *args, **options):
        """
        Main entry point for the management command.

        Execution flow:
          1. Build base queryset: WorkOrderEntryLine records with empty
             fault_category, ordered by pk (stable iteration order).
          2. Iterate in batches using iterator(chunk_size=batch_size) to
             avoid loading the full dataset into memory.
          3. For each line:
             a. Call find_cached_classification() with the line's company.
                If a match is found, persist directly (no Gemini call).
             b. If no cached match, call classify_fault(). If the result is
                non-empty, persist both fields.
             c. If classify_fault() returns empty strings, increment the
                skipped counter (result was inconclusive).
          4. Print progress every 10 lines and a final summary.

        ---

        Punto de entrada principal del comando de gestión.

        Flujo de ejecución:
          1. Construir el queryset base: registros WorkOrderEntryLine con
             fault_category vacío, ordenados por pk (orden de iteración estable).
          2. Iterar en batches con iterator(chunk_size=batch_size) para no
             cargar el dataset completo en memoria.
          3. Por cada línea:
             a. Llamar a find_cached_classification() con la empresa de la línea.
                Si hay coincidencia, persistir directamente (sin llamada a Gemini).
             b. Si no hay coincidencia en caché, llamar a classify_fault(). Si el
                resultado no está vacío, persistir ambos campos.
             c. Si classify_fault() devuelve cadenas vacías, incrementar el
                contador de omitidas (resultado no concluyente).
          4. Imprimir progreso cada 10 líneas y un resumen final.
        """
        batch_size = options["batch_size"]
        dry_run    = options["dry_run"]

        if dry_run:
            self.stdout.write(
                "# [classify_entry_lines] MODO DRY-RUN activo — "
                "no se persistirá ningún cambio."
            )

        # ------------------------------------------------------------------
        # Step 1 — Build base queryset.
        # Paso 1 — Construir queryset base.
        # Lines already classified (fault_category != "") are excluded.
        # Las líneas ya clasificadas (fault_category != "") se excluyen.
        # ------------------------------------------------------------------
        base_qs = (
            WorkOrderEntryLine.objects
            .filter(fault_category="")
            .select_related("entry__work_order__company")
            .order_by("pk")
        )

        total_pending = base_qs.count()
        self.stdout.write(
            f"# [classify_entry_lines] Líneas pendientes de clasificar: {total_pending}."
        )

        if total_pending == 0:
            self.stdout.write(
                "# [classify_entry_lines] Nada que procesar. Todas las líneas "
                "ya están clasificadas."
            )
            return

        # ------------------------------------------------------------------
        # Counters / Contadores
        # ------------------------------------------------------------------
        count_processed        = 0   # Total lines visited / Total líneas visitadas
        count_classified_cache = 0   # Classified via cache hit / Clasificadas por caché
        count_classified_gemini = 0  # Classified via Gemini call / Clasificadas por Gemini
        count_skipped          = 0   # Gemini returned empty / Gemini devolvió vacío
        count_errors           = 0   # Unexpected exceptions / Excepciones inesperadas

        # ------------------------------------------------------------------
        # Step 2 — Iterate in batches.
        # Paso 2 — Iterar en batches.
        # ------------------------------------------------------------------
        self.stdout.write(
            f"# [classify_entry_lines] Iniciando iteración — "
            f"batch_size={batch_size} | dry_run={dry_run}."
        )

        for line in base_qs.iterator(chunk_size=batch_size):
            count_processed += 1

            # Resolve company from the related WorkOrder.
            # Resolver la empresa desde el WorkOrder relacionado.
            try:
                company = line.entry.work_order.company
            except Exception as exc:
                self.stdout.write(
                    f"# [classify_entry_lines] pk={line.pk}: no se pudo resolver "
                    f"la empresa — {exc}. Línea omitida."
                )
                count_errors += 1
                _print_progress(self, count_processed, total_pending)
                continue

            try:
                # ----------------------------------------------------------
                # Step 3a — Try cache first.
                # Paso 3a — Intentar caché primero.
                # ----------------------------------------------------------
                cached = find_cached_classification(
                    fault_description=line.fault_description or "",
                    repair_notes=line.repair_notes or "",
                    company=company,
                )

                if cached is not None:
                    # Cache hit: persist without calling Gemini.
                    # Coincidencia en caché: persistir sin llamar a Gemini.
                    category, subcategory = cached
                    if dry_run:
                        self.stdout.write(
                            f"# [classify_entry_lines] pk={line.pk} "
                            f"[DRY-RUN] caché → category={category} "
                            f"subcategory={subcategory}. Sin persistir."
                        )
                    else:
                        WorkOrderEntryLine.objects.filter(pk=line.pk).update(
                            fault_category=category,
                            fault_subcategory=subcategory,
                        )
                        self.stdout.write(
                            f"# [classify_entry_lines] pk={line.pk} "
                            f"caché → category={category} subcategory={subcategory}. "
                            f"Persistido."
                        )
                    count_classified_cache += 1

                else:
                    # ----------------------------------------------------------
                    # Step 3b — No cache match.
                    # In dry-run mode: skip Gemini call entirely, count as pending.
                    # In real run: call classify_fault() and persist if successful.
                    #
                    # Paso 3b — Sin coincidencia en caché.
                    # En dry-run: omitir llamada a Gemini, contar como pendiente.
                    # En ejecución real: llamar a classify_fault() y persistir si OK.
                    # ----------------------------------------------------------
                    if dry_run:
                        # Simulate: count this line as a pending Gemini call.
                        # Simular: contar esta línea como llamada Gemini pendiente.
                        self.stdout.write(
                            f"# [classify_entry_lines] pk={line.pk} "
                            f"[DRY-RUN] sin caché — requeriría llamada Gemini. "
                            f"Omitida."
                        )
                        count_skipped += 1
                    else:
                        self.stdout.write(
                            f"# [classify_entry_lines] pk={line.pk} "
                            f"sin caché — llamando a Gemini Flash..."
                        )
                        category, subcategory = classify_fault(
                            fault_description=line.fault_description or "",
                            repair_notes=line.repair_notes or "",
                        )

                        if category:
                            # Classification succeeded: persist both fields.
                            # Clasificación exitosa: persistir ambos campos.
                            WorkOrderEntryLine.objects.filter(pk=line.pk).update(
                                fault_category=category,
                                fault_subcategory=subcategory,
                            )
                            self.stdout.write(
                                f"# [classify_entry_lines] pk={line.pk} "
                                f"Gemini → category={category} "
                                f"subcategory={subcategory}. Persistido."
                            )
                            count_classified_gemini += 1
                        else:
                            # Step 3c — Gemini returned empty (inconclusive result).
                            # Paso 3c — Gemini devolvió vacío (resultado no concluyente).
                            self.stdout.write(
                                f"# [classify_entry_lines] pk={line.pk} "
                                f"Gemini → resultado vacío. Línea omitida."
                            )
                            count_skipped += 1

            except Exception as exc:
                self.stdout.write(
                    f"# [classify_entry_lines] pk={line.pk}: error inesperado — "
                    f"{exc}. Línea omitida."
                )
                count_errors += 1

            # ------------------------------------------------------------------
            # Step 4 — Progress report every 10 lines.
            # Paso 4 — Informe de progreso cada 10 líneas.
            # ------------------------------------------------------------------
            if count_processed % 10 == 0:
                self.stdout.write(
                    f"# [classify_entry_lines] Progreso: {count_processed}/{total_pending} "
                    f"| caché={count_classified_cache} "
                    f"| gemini={count_classified_gemini} "
                    f"| omitidas/pendientes={count_skipped} "
                    f"| errores={count_errors}"
                )

        # ------------------------------------------------------------------
        # Final summary / Resumen final
        # ------------------------------------------------------------------
        dry_run_label = " [DRY-RUN — sin cambios persistidos]" if dry_run else ""
        self.stdout.write(
            f"# [classify_entry_lines] COMPLETADO{dry_run_label}.\n"
            f"#   Procesadas:           {count_processed}\n"
            f"#   Clasificadas (caché): {count_classified_cache}\n"
            f"#   Clasificadas (Gemini):{count_classified_gemini}\n"
            f"#   Omitidas (vacío):     {count_skipped}\n"
            f"#   Errores:              {count_errors}"
        )


# ---------------------------------------------------------------------------
# Module-level helper / Función auxiliar de módulo
# ---------------------------------------------------------------------------

def _print_progress(command_instance, processed: int, total: int) -> None:
    """
    Prints a minimal progress line when the processed count is a multiple of 10.
    Extracted as a module-level function to keep handle() readable.

    ---

    Imprime una línea de progreso mínima cuando el contador es múltiplo de 10.
    Extraída como función de módulo para mantener handle() legible.
    """
    if processed % 10 == 0:
        command_instance.stdout.write(
            f"# [classify_entry_lines] Procesadas: {processed}/{total}"
        )
