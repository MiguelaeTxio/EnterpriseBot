# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/work_order_processor/management/commands/detect_duplicate_entries.py

"""
Management command: detect_duplicate_entries

Detects WorkOrders belonging to the same company that share WorkOrderEntry
records with identical (worker_name, work_date) tuples but originate from
different source PDFs (distinct source_pdf_hash values). This situation arises
when the same work data has been ingested more than once via different PDF files
— a scenario that Level-2 upload detection cannot always prevent (e.g. when the
duplicate PDF was uploaded before the Bloque-I hash system was in place).

Usage
-----
  python -m dotenv run python manage.py detect_duplicate_entries
  python -m dotenv run python manage.py detect_duplicate_entries --company 3
  python -m dotenv run python manage.py detect_duplicate_entries --company "Grupo Álvarez"
  python -m dotenv run python manage.py detect_duplicate_entries --fix
  python -m dotenv run python manage.py detect_duplicate_entries --company 3 --fix

Flags
-----
  --company   : (optional) Filter results to a single company identified by its
                primary key (integer) or exact name string.
  --fix       : (opt-in, IRREVERSIBLE) For each duplicate group, keep the
                WorkOrder with the highest pk (most recent) and delete the
                older ones in cascade after explicit per-group [s/N] confirmation.

---

Comando de gestión: detect_duplicate_entries

Detecta WorkOrders de la misma empresa que comparten registros WorkOrderEntry
con tuplas (worker_name, work_date) idénticas pero que provienen de ficheros PDF
distintos (valores source_pdf_hash diferentes). Esta situación surge cuando los
mismos datos de trabajo han sido ingeridos más de una vez a través de diferentes
ficheros PDF — un escenario que la detección de duplicados en el upload (Nivel 2)
no siempre puede prevenir (p. ej. cuando el PDF duplicado fue cargado antes de
que el sistema de hashes del Bloque I estuviera en vigor).

Uso
---
  python -m dotenv run python manage.py detect_duplicate_entries
  python -m dotenv run python manage.py detect_duplicate_entries --company 3
  python -m dotenv run python manage.py detect_duplicate_entries --company "Grupo Álvarez"
  python -m dotenv run python manage.py detect_duplicate_entries --fix
  python -m dotenv run python manage.py detect_duplicate_entries --company 3 --fix

Flags
-----
  --company   : (opcional) Filtra los resultados a una única empresa identificada
                por su clave primaria (entero) o nombre exacto (cadena).
  --fix       : (opt-in, IRREVERSIBLE) Para cada grupo duplicado detectado solicita
                confirmación [s/N] y, si se acepta, elimina en cascada todos
                los WorkOrders del grupo salvo el de pk más alto (más reciente).
"""

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Count

from ivr_config.models import Company
from work_order_processor.models import WorkOrder, WorkOrderEntry


class Command(BaseCommand):
    """
    Django management command that detects and optionally repairs duplicate
    WorkOrder records sharing identical (worker_name, work_date) entries.

    Exit codes:
      0 — completed normally (no duplicates found or report generated).
      1 — fatal error (company not found, invalid argument, etc.).

    ---

    Comando de gestión de Django que detecta y opcionalmente repara registros
    WorkOrder duplicados que comparten entradas (worker_name, work_date) idénticas.

    Códigos de salida:
      0 — completado normalmente (sin duplicados o informe generado).
      1 — error fatal (empresa no encontrada, argumento inválido, etc.).
    """

    help = (
        "Detecta WorkOrders distintos de la misma empresa que comparten entradas "
        "(worker_name, work_date). Usa --fix para eliminar los duplicados más antiguos "
        "de forma interactiva (IRREVERSIBLE)."
    )

    # ------------------------------------------------------------------
    # Argument declaration / Declaración de argumentos
    # ------------------------------------------------------------------

    def add_arguments(self, parser):
        """
        Registers --company and --fix CLI arguments on the argument parser.
        ---
        Registra los argumentos --company y --fix en el parser de argumentos CLI.
        """
        parser.add_argument(
            "--company",
            dest="company",
            default=None,
            metavar="PK_O_NOMBRE",
            help=(
                "Filtra la búsqueda a una única empresa. Acepta su pk numérico "
                "o su nombre exacto (sensible a mayúsculas)."
            ),
        )
        parser.add_argument(
            "--fix",
            dest="fix",
            action="store_true",
            default=False,
            help=(
                "IRREVERSIBLE. Para cada grupo duplicado detectado solicita "
                "confirmación [s/N] y, si se acepta, elimina en cascada todos "
                "los WorkOrders del grupo salvo el de pk más alto (más reciente)."
            ),
        )

    # ------------------------------------------------------------------
    # Main entry point / Punto de entrada principal
    # ------------------------------------------------------------------

    def handle(self, *args, **options):
        """
        Orchestrates the full detection (and optional repair) workflow:
          1. Resolve the optional company filter.
          2. Query duplicate (company, worker_name, work_date) groups.
          3. For each group, fetch the implicated WorkOrders with metadata.
          4. Print a detailed grouped report.
          5. If --fix: prompt per-group and delete confirmed duplicates in cascade.
          6. Print summary counters.

        ---

        Orquesta el flujo completo de detección (y reparación opcional):
          1. Resolver el filtro de empresa opcional.
          2. Consultar los grupos (company, worker_name, work_date) duplicados.
          3. Por cada grupo, obtener los WorkOrders implicados con metadatos.
          4. Imprimir un informe detallado agrupado.
          5. Si --fix: solicitar confirmación por grupo y eliminar duplicados
             confirmados en cascada.
          6. Imprimir contadores de resumen.
        """
        company_filter = options["company"]
        fix_mode       = options["fix"]

        # ------------------------------------------------------------------
        # Step 1 — Resolve optional company filter.
        # Paso 1 — Resolver el filtro de empresa opcional.
        # ------------------------------------------------------------------
        company_obj = self._resolve_company(company_filter)

        # ------------------------------------------------------------------
        # Step 2 — Query duplicate groups.
        # Paso 2 — Consultar los grupos duplicados.
        # ------------------------------------------------------------------
        duplicate_groups = self._query_duplicate_groups(company_obj)

        if not duplicate_groups:
            self.stdout.write(
                self.style.SUCCESS(
                    "# No se han detectado grupos duplicados. "
                    "La base de datos está limpia."
                )
            )
            return

        # ------------------------------------------------------------------
        # Step 3 & 4 — Enrich and print the report.
        # Paso 3 y 4 — Enriquecer e imprimir el informe.
        # ------------------------------------------------------------------
        enriched_groups = self._enrich_groups(duplicate_groups)
        self._print_report(enriched_groups, fix_mode)

        # ------------------------------------------------------------------
        # Step 5 — Optional interactive repair.
        # Paso 5 — Reparación interactiva opcional.
        # ------------------------------------------------------------------
        total_deleted = 0
        total_skipped = 0

        if fix_mode:
            self.stdout.write("")
            self.stdout.write(
                self.style.WARNING(
                    "# ============================================================"
                )
            )
            self.stdout.write(
                self.style.WARNING(
                    "# MODO --fix ACTIVO — Las eliminaciones son IRREVERSIBLES."
                )
            )
            self.stdout.write(
                self.style.WARNING(
                    "# ============================================================"
                )
            )
            self.stdout.write("")

            for group in enriched_groups:
                deleted, skipped = self._fix_group(group)
                total_deleted += deleted
                total_skipped += skipped

        # ------------------------------------------------------------------
        # Step 6 — Summary counters.
        # Paso 6 — Contadores de resumen.
        # ------------------------------------------------------------------
        self._print_summary(enriched_groups, fix_mode, total_deleted, total_skipped)

    # ------------------------------------------------------------------
    # Private helpers / Helpers privados
    # ------------------------------------------------------------------

    def _resolve_company(self, company_filter):
        """
        Resolves the --company argument to a Company instance or None.
        Accepts an integer (pk) or an exact name string.
        Raises CommandError if the argument is provided but no match is found.

        ---

        Resuelve el argumento --company a una instancia de Company o None.
        Acepta un entero (pk) o una cadena de nombre exacto.
        Lanza CommandError si el argumento se proporciona pero no hay coincidencia.
        """
        if company_filter is None:
            return None

        # Try numeric pk first, then fall back to exact name match.
        # Intentar pk numérico primero, luego nombre exacto.
        try:
            pk_val = int(company_filter)
            try:
                company_obj = Company.objects.get(pk=pk_val)
                self.stdout.write(
                    f"# Filtro de empresa activo: {company_obj.name} (pk={company_obj.pk})"
                )
                return company_obj
            except Company.DoesNotExist:
                raise CommandError(
                    f"No se encontró ninguna empresa con pk={pk_val}."
                )
        except ValueError:
            # Not an integer — treat as exact name.
            # No es un entero — tratar como nombre exacto.
            try:
                company_obj = Company.objects.get(name=company_filter)
                self.stdout.write(
                    f"# Filtro de empresa activo: {company_obj.name} (pk={company_obj.pk})"
                )
                return company_obj
            except Company.DoesNotExist:
                raise CommandError(
                    f"No se encontró ninguna empresa con nombre exacto: '{company_filter}'."
                )
            except Company.MultipleObjectsReturned:
                raise CommandError(
                    f"Más de una empresa coincide con el nombre '{company_filter}'. "
                    f"Usa el pk numérico para eliminar la ambigüedad."
                )

    def _query_duplicate_groups(self, company_obj):
        """
        Returns a queryset of (company_id, worker_name, work_date) value-dicts
        where more than one distinct WorkOrder contributes entries for that tuple.
        Optionally scoped to a single company when company_obj is not None.

        Only groups where all implicated WorkOrders have a non-empty
        source_pdf_hash are included, ensuring that the concept of "distinct PDF"
        is meaningful (hash-verified). Groups that contain at least one WorkOrder
        with an empty hash are still included but flagged in the report.

        ---

        Devuelve un queryset de value-dicts (company_id, worker_name, work_date)
        donde más de un WorkOrder distinto aporta entradas para esa tupla.
        Opcionalmente acotado a una única empresa cuando company_obj no es None.

        Solo se incluyen grupos donde todos los WorkOrders implicados tienen
        source_pdf_hash no vacío, garantizando que el concepto de "PDF distinto"
        es significativo (verificado por hash). Los grupos que contienen al menos
        un WorkOrder con hash vacío se incluyen igualmente pero se marcan en el
        informe.
        """
        qs = WorkOrderEntry.objects.all()

        if company_obj is not None:
            # Scope to the specified company via the WorkOrder FK chain.
            # Acotar a la empresa especificada via la cadena de FK WorkOrder.
            qs = qs.filter(work_order__company=company_obj)

        # Aggregate: count distinct work_order pks per (company, worker, date).
        # Agregar: contar work_order pks distintos por (company, operario, fecha).
        duplicate_groups = (
            qs
            .values("work_order__company_id", "worker_name", "work_date")
            .annotate(wo_count=Count("work_order_id", distinct=True))
            .filter(wo_count__gt=1)
            .order_by(
                "work_order__company_id",
                "worker_name",
                "work_date",
            )
        )

        return list(duplicate_groups)

    def _enrich_groups(self, duplicate_groups):
        """
        For each raw group dict, fetches the implicated WorkOrder records with
        all metadata required for the report and for --fix.

        Returns a list of enriched group dicts:
          {
            "company_id"  : int,
            "company_name": str,
            "worker_name" : str,
            "work_date"   : date | None,
            "work_orders" : list[WorkOrder],   # ordered by pk ascending
            "keeper"      : WorkOrder,         # highest pk — preserved by --fix
            "to_delete"   : list[WorkOrder],   # lower pks — deleted by --fix
          }

        ---

        Para cada dict de grupo crudo, obtiene los registros WorkOrder implicados
        con todos los metadatos necesarios para el informe y para --fix.

        Devuelve una lista de dicts de grupo enriquecidos:
          {
            "company_id"  : int,
            "company_name": str,
            "worker_name" : str,
            "work_date"   : date | None,
            "work_orders" : list[WorkOrder],   # ordenados por pk ascendente
            "keeper"      : WorkOrder,         # pk más alto — conservado por --fix
            "to_delete"   : list[WorkOrder],   # pks inferiores — eliminados por --fix
          }
        """
        # Build a cache of Company name lookups to avoid N+1 queries.
        # Construir caché de nombres de Company para evitar consultas N+1.
        company_name_cache: dict[int, str] = {}

        enriched: list[dict] = []

        for raw in duplicate_groups:
            company_id  = raw["work_order__company_id"]
            worker_name = raw["worker_name"] or ""
            work_date   = raw["work_date"]

            # Fetch company name from cache or DB.
            # Obtener nombre de empresa desde caché o BD.
            if company_id not in company_name_cache:
                try:
                    company_name_cache[company_id] = Company.objects.get(
                        pk=company_id
                    ).name
                except Company.DoesNotExist:
                    company_name_cache[company_id] = f"(Empresa pk={company_id})"

            company_name = company_name_cache[company_id]

            # Fetch all WorkOrders implicated in this (company, worker, date) group.
            # Obtener todos los WorkOrders implicados en este grupo (empresa, operario, fecha).
            implicated_wos = list(
                WorkOrder.objects
                .filter(
                    company_id=company_id,
                    entries__worker_name=worker_name,
                    entries__work_date=work_date,
                )
                .select_related("uploaded_by__user")
                .distinct()
                .order_by("pk")
            )

            if len(implicated_wos) < 2:
                # Edge case: race condition between query and fetch — skip.
                # Caso límite: condición de carrera entre consulta y fetch — omitir.
                continue

            keeper    = implicated_wos[-1]   # highest pk = most recent
            to_delete = implicated_wos[:-1]  # all lower pks

            enriched.append({
                "company_id":   company_id,
                "company_name": company_name,
                "worker_name":  worker_name,
                "work_date":    work_date,
                "work_orders":  implicated_wos,
                "keeper":       keeper,
                "to_delete":    to_delete,
            })

        return enriched

    def _format_work_order_row(self, wo, is_keeper=False):
        """
        Returns a formatted single-line string describing a WorkOrder record
        for use in the tabular report.

        Columns: pk | pdf_display_name | upload_date | hash_short | status | reviewed | role

        ---

        Devuelve una cadena de una línea formateada que describe un registro
        WorkOrder para uso en el informe tabular.

        Columnas: pk | pdf_display_name | fecha_carga | hash_corto | estado | revisado | rol
        """
        hash_short   = (wo.source_pdf_hash[:12] + "…") if wo.source_pdf_hash else "(sin hash)"
        upload_str   = wo.upload_date.strftime("%d/%m/%Y %H:%M") if wo.upload_date else "—"
        reviewed_str = "Revisado" if wo.reviewed else "Sin revisar"
        role_str     = "CONSERVAR" if is_keeper else "ELIMINAR"
        role_style   = self.style.SUCCESS if is_keeper else self.style.ERROR

        line = (
            f"  {'→' if is_keeper else ' '} "
            f"#{wo.pk:<5} "
            f"{wo.pdf_display_name:<45} "
            f"{upload_str:<18} "
            f"{hash_short:<14} "
            f"{wo.get_status_display():<12} "
            f"{reviewed_str:<12}"
        )
        return line, role_str, role_style

    def _print_report(self, enriched_groups, fix_mode):
        """
        Prints the full duplicate detection report to stdout, grouped by
        company then by (worker_name, work_date).

        ---

        Imprime el informe completo de detección de duplicados en stdout,
        agrupado por empresa y luego por (worker_name, work_date).
        """
        self.stdout.write("")
        self.stdout.write(
            self.style.WARNING(
                "# ============================================================"
            )
        )
        self.stdout.write(
            self.style.WARNING(
                f"# INFORME DE DUPLICADOS — {len(enriched_groups)} grupo(s) detectado(s)"
            )
        )
        if fix_mode:
            self.stdout.write(
                self.style.WARNING(
                    "# MODO --fix ACTIVO — se solicitará confirmación por grupo"
                )
            )
        self.stdout.write(
            self.style.WARNING(
                "# ============================================================"
            )
        )

        current_company_id = None

        for idx, group in enumerate(enriched_groups, start=1):
            # Print company separator when company changes.
            # Imprimir separador de empresa cuando cambia la empresa.
            if group["company_id"] != current_company_id:
                current_company_id = group["company_id"]
                self.stdout.write("")
                self.stdout.write(
                    self.style.HTTP_INFO(
                        f"  EMPRESA: {group['company_name']} "
                        f"(pk={group['company_id']})"
                    )
                )
                self.stdout.write(
                    self.style.HTTP_INFO(
                        "  " + "─" * 70
                    )
                )

            # Group header.
            # Cabecera del grupo.
            date_str = (
                group["work_date"].strftime("%d/%m/%Y")
                if group["work_date"] else "(sin fecha)"
            )
            self.stdout.write("")
            self.stdout.write(
                f"  Grupo {idx:>3} │ "
                f"Operario: {group['worker_name'] or '(desconocido)':<35} │ "
                f"Fecha: {date_str}"
            )
            self.stdout.write(
                f"           │ "
                f"{len(group['work_orders'])} WorkOrders implicados  │  "
                f"Conservar: #{group['keeper'].pk}  │  "
                f"Eliminar: {[wo.pk for wo in group['to_delete']]}"
            )
            self.stdout.write("")

            # WorkOrder rows.
            # Filas de WorkOrder.
            for wo in group["work_orders"]:
                is_keeper       = (wo.pk == group["keeper"].pk)
                line, role_str, role_style = self._format_work_order_row(wo, is_keeper)
                self.stdout.write(line + f"  [{role_style(role_str)}]")

        self.stdout.write("")

    def _fix_group(self, group):
        """
        Prompts the user for confirmation and, if accepted, deletes all
        WorkOrders in group["to_delete"] in cascade.

        Returns a tuple (deleted_count, skipped_count):
          deleted_count — number of WorkOrders deleted in this group.
          skipped_count — number of WorkOrders skipped (user declined or
                          already deleted by a previous run).

        ---

        Solicita confirmación al usuario y, si se acepta, elimina en cascada
        todos los WorkOrders de group["to_delete"].

        Devuelve una tupla (deleted_count, skipped_count):
          deleted_count — número de WorkOrders eliminados en este grupo.
          skipped_count — número de WorkOrders omitidos (usuario denegó o
                          ya eliminados por una ejecución anterior).
        """
        date_str = (
            group["work_date"].strftime("%d/%m/%Y")
            if group["work_date"] else "(sin fecha)"
        )
        to_delete_pks = [wo.pk for wo in group["to_delete"]]

        self.stdout.write(
            self.style.WARNING(
                f"  Grupo │ {group['worker_name']} │ {date_str} │ "
                f"Eliminar: {to_delete_pks}  →  Conservar: #{group['keeper'].pk}"
            )
        )

        # Interactive confirmation prompt — require explicit "s" to proceed.
        # Confirmación interactiva — requiere "s" explícita para proceder.
        try:
            answer = input("  ¿Confirmar eliminación? [s/N]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            self.stdout.write("")
            self.stdout.write(
                self.style.ERROR("# Interrupción detectada. Abortando --fix.")
            )
            raise CommandError("Proceso interrumpido por el usuario.")

        if answer != "s":
            self.stdout.write(
                self.style.HTTP_INFO(
                    f"  → Omitido. WorkOrders {to_delete_pks} conservados sin cambios."
                )
            )
            return 0, len(to_delete_pks)

        # Proceed with cascade deletion for each confirmed WorkOrder.
        # Proceder con la eliminación en cascada de cada WorkOrder confirmado.
        deleted_count = 0
        skipped_count = 0

        for wo in group["to_delete"]:
            # Re-fetch to guard against concurrent deletion between report and fix.
            # Re-obtener para proteger contra eliminación concurrente entre informe y fix.
            try:
                wo_live = WorkOrder.objects.get(pk=wo.pk)
            except WorkOrder.DoesNotExist:
                self.stdout.write(
                    self.style.HTTP_INFO(
                        f"  → Parte #{wo.pk} ya no existe en BD — omitido."
                    )
                )
                skipped_count += 1
                continue

            wo_live.delete()
            self.stdout.write(
                self.style.SUCCESS(
                    f"  ✓ Parte #{wo.pk} eliminado correctamente (cascada completa)."
                )
            )
            deleted_count += 1

        return deleted_count, skipped_count

    def _print_summary(self, enriched_groups, fix_mode, total_deleted, total_skipped):
        """
        Prints the final summary block with aggregate counters.

        ---

        Imprime el bloque de resumen final con contadores agregados.
        """
        total_groups     = len(enriched_groups)
        total_implicated = sum(len(g["work_orders"]) for g in enriched_groups)
        total_to_delete  = sum(len(g["to_delete"]) for g in enriched_groups)

        self.stdout.write(
            self.style.WARNING(
                "# ============================================================"
            )
        )
        self.stdout.write(
            self.style.WARNING("# RESUMEN")
        )
        self.stdout.write(
            self.style.WARNING(
                "# ============================================================"
            )
        )
        self.stdout.write(
            f"  Grupos duplicados detectados  : {total_groups}"
        )
        self.stdout.write(
            f"  WorkOrders implicados (total) : {total_implicated}"
        )
        self.stdout.write(
            f"  WorkOrders candidatos a borrar: {total_to_delete}"
        )

        if fix_mode:
            self.stdout.write(
                self.style.SUCCESS(
                    f"  WorkOrders eliminados         : {total_deleted}"
                )
            )
            self.stdout.write(
                self.style.HTTP_INFO(
                    f"  WorkOrders omitidos           : {total_skipped}"
                )
            )
        else:
            self.stdout.write(
                self.style.HTTP_INFO(
                    "  Ejecuta con --fix para eliminar los duplicados de forma interactiva."
                )
            )

        self.stdout.write(
            self.style.WARNING(
                "# ============================================================"
            )
        )
        self.stdout.write("")
