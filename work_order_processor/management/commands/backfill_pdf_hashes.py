# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/work_order_processor/management/commands/backfill_pdf_hashes.py
"""
Management command: backfill_pdf_hashes
Iterates all WorkOrder records with an empty source_pdf_hash, computes the
SHA-256 hash of the physical PDF file on disk and persists it. Records whose
PDF file no longer exists on disk are skipped with a warning.

Optional flag --purge-duplicates: after the backfill phase, identifies WorkOrder
records whose source_pdf_hash matches another WorkOrder of the same company
(exact duplicate on disk) and deletes the physical PDF file of the older
duplicate, leaving the WorkOrder record intact but with source_pdf cleared.
Produces a detailed report at the end of each phase.

---

Comando de gestión: backfill_pdf_hashes
Itera todos los registros WorkOrder con source_pdf_hash vacío, calcula el hash
SHA-256 del fichero PDF físico en disco y lo persiste. Los registros cuyo
fichero PDF ya no existe en disco se omiten con un aviso.

Flag opcional --purge-duplicates: tras la fase de backfill, identifica los
registros WorkOrder cuyo source_pdf_hash coincide con otro WorkOrder de la
misma empresa (duplicado exacto en disco) y elimina el fichero PDF físico del
duplicado más antiguo, dejando el registro WorkOrder intacto pero con
source_pdf vaciado. Produce un informe detallado al final de cada fase.
"""

import hashlib
import os

from django.core.management.base import BaseCommand
from django.db import transaction

from work_order_processor.models import WorkOrder


class Command(BaseCommand):
    """
    Backfills source_pdf_hash for existing WorkOrder records and optionally
    purges duplicate PDF files from disk.
    ---
    Rellena source_pdf_hash para los registros WorkOrder existentes y
    opcionalmente purga del disco los ficheros PDF duplicados.
    """

    help = (
        "Rellena el campo source_pdf_hash en los WorkOrders existentes calculando "
        "el SHA-256 del fichero PDF físico almacenado en disco. "
        "Con --purge-duplicates elimina del disco los PDFs cuyo hash ya existe en "
        "otro WorkOrder de la misma empresa, liberando espacio sin perder registros."
    )

    # ------------------------------------------------------------------
    # Command arguments / Argumentos del comando
    # ------------------------------------------------------------------

    def add_arguments(self, parser):
        """
        Registers the --purge-duplicates optional flag.
        ---
        Registra el flag opcional --purge-duplicates.
        """
        parser.add_argument(
            "--purge-duplicates",
            action="store_true",
            default=False,
            help=(
                "Tras el backfill, elimina del disco el fichero PDF físico de los "
                "WorkOrders cuyo hash ya existe en otro WorkOrder más reciente de la "
                "misma empresa. El registro WorkOrder se conserva con source_pdf "
                "vaciado. Esta operación es IRREVERSIBLE."
            ),
        )

    # ------------------------------------------------------------------
    # Command entry point / Punto de entrada del comando
    # ------------------------------------------------------------------

    def handle(self, *args, **options):
        """
        Executes the backfill phase and, when --purge-duplicates is set,
        the duplicate purge phase.
        ---
        Ejecuta la fase de backfill y, cuando se activa --purge-duplicates,
        la fase de purga de duplicados.
        """
        self._run_backfill_phase()

        if options["purge_duplicates"]:
            self._run_purge_phase()

    # ------------------------------------------------------------------
    # Phase 1 -- Backfill / Fase 1 -- Backfill
    # ------------------------------------------------------------------

    def _run_backfill_phase(self):
        """
        Iterates WorkOrder records with an empty source_pdf_hash, computes
        the SHA-256 of the physical file and persists it. Reports counters
        for processed, missing-file and skipped (no source_pdf field) records.
        ---
        Itera los WorkOrder con source_pdf_hash vacío, calcula el SHA-256 del
        fichero físico y lo persiste. Informa de contadores de procesados,
        sin-fichero y omitidos (sin campo source_pdf).
        """
        self.stdout.write(
            self.style.MIGRATE_HEADING(
                "\n# -- FASE 1: Backfill de hashes SHA-256 ----------------------------------------"
            )
        )

        qs = (
            WorkOrder.objects
            .filter(source_pdf_hash="")
            .order_by("pk")
        )

        total       = qs.count()
        procesados  = 0
        sin_fichero = 0
        omitidos    = 0

        self.stdout.write(f"# Registros con hash vacío encontrados: {total}")

        for wo in qs.iterator():
            if not wo.source_pdf:
                self.stdout.write(
                    self.style.WARNING(
                        f"# [OMITIDO] WorkOrder #{wo.pk} -- sin source_pdf. Se omite."
                    )
                )
                omitidos += 1
                continue

            try:
                pdf_path = wo.source_pdf.path
            except NotImplementedError:
                self.stdout.write(
                    self.style.WARNING(
                        f"# [OMITIDO] WorkOrder #{wo.pk} -- .path no disponible "
                        f"en este backend de almacenamiento. Se omite."
                    )
                )
                omitidos += 1
                continue

            try:
                sha256 = self._compute_sha256(pdf_path)
            except FileNotFoundError:
                self.stdout.write(
                    self.style.WARNING(
                        f"# [SIN FICHERO] WorkOrder #{wo.pk} -- "
                        f"fichero no encontrado en disco: {pdf_path}"
                    )
                )
                sin_fichero += 1
                continue

            with transaction.atomic():
                wo.source_pdf_hash = sha256
                wo.save(update_fields=["source_pdf_hash"])

            self.stdout.write(
                f"# [OK] WorkOrder #{wo.pk} -- hash: {sha256[:16]}..."
            )
            procesados += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"\n# Fase 1 completada.\n"
                f"#   Procesados (hash guardado) : {procesados}\n"
                f"#   Sin fichero en disco       : {sin_fichero}\n"
                f"#   Omitidos (sin source_pdf)  : {omitidos}\n"
                f"#   Total evaluados            : {total}"
            )
        )

    # ------------------------------------------------------------------
    # Phase 2 -- Purge duplicates / Fase 2 -- Purga de duplicados
    # ------------------------------------------------------------------

    def _run_purge_phase(self):
        """
        Identifies WorkOrder records whose source_pdf_hash matches another
        WorkOrder of the same company. For each group of duplicates, retains
        the record with the highest pk (most recent upload) and deletes the
        physical PDF file of all older duplicates, clearing their source_pdf
        field. The WorkOrder record itself is preserved intact.
        Reports counters for purged files, missing files and errors.
        ---
        Identifica registros WorkOrder cuyo source_pdf_hash coincide con otro
        WorkOrder de la misma empresa. Por cada grupo de duplicados, conserva
        el registro con el pk más alto (carga más reciente) y elimina el
        fichero PDF físico de los duplicados más antiguos, vaciando su campo
        source_pdf. El registro WorkOrder en sí se conserva intacto.
        Informa de contadores de ficheros purgados, sin fichero y errores.
        """
        self.stdout.write(
            self.style.MIGRATE_HEADING(
                "\n# -- FASE 2: Purga de PDFs duplicados en disco ----------------------------------"
            )
        )

        from django.db.models import Count

        duplicate_groups = (
            WorkOrder.objects
            .exclude(source_pdf_hash="")
            .values("company_id", "source_pdf_hash")
            .annotate(total=Count("pk"))
            .filter(total__gt=1)
            .order_by("company_id", "source_pdf_hash")
        )

        total_grupos = duplicate_groups.count()
        self.stdout.write(f"# Grupos de duplicados exactos encontrados: {total_grupos}")

        if total_grupos == 0:
            self.stdout.write(
                self.style.SUCCESS("# No hay PDFs duplicados en disco. Nada que purgar.")
            )
            return

        purgados    = 0
        sin_fichero = 0
        errores     = 0

        for group in duplicate_groups:
            company_id = group["company_id"]
            pdf_hash   = group["source_pdf_hash"]

            wos = list(
                WorkOrder.objects
                .filter(company_id=company_id, source_pdf_hash=pdf_hash)
                .order_by("-pk")
            )

            keeper     = wos[0]
            candidates = wos[1:]

            self.stdout.write(
                f"\n# Grupo hash {pdf_hash[:16]}... | empresa #{company_id} | "
                f"{len(wos)} registros | conservando WorkOrder #{keeper.pk}"
            )

            for wo in candidates:
                if not wo.source_pdf:
                    self.stdout.write(
                        self.style.WARNING(
                            f"#   [SIN FICHERO] WorkOrder #{wo.pk} -- "
                            f"source_pdf ya estaba vacío. Se omite."
                        )
                    )
                    sin_fichero += 1
                    continue

                try:
                    pdf_path = wo.source_pdf.path
                except NotImplementedError:
                    self.stdout.write(
                        self.style.WARNING(
                            f"#   [OMITIDO] WorkOrder #{wo.pk} -- "
                            f".path no disponible en este backend."
                        )
                    )
                    errores += 1
                    continue

                try:
                    if os.path.isfile(pdf_path):
                        os.remove(pdf_path)
                        self.stdout.write(
                            f"#   [PURGADO] WorkOrder #{wo.pk} -- "
                            f"fichero eliminado: {pdf_path}"
                        )
                    else:
                        self.stdout.write(
                            self.style.WARNING(
                                f"#   [SIN FICHERO] WorkOrder #{wo.pk} -- "
                                f"fichero no encontrado en disco: {pdf_path}"
                            )
                        )
                        sin_fichero += 1
                        continue

                    with transaction.atomic():
                        wo.source_pdf = None
                        wo.save(update_fields=["source_pdf"])

                    purgados += 1

                except OSError as exc:
                    self.stdout.write(
                        self.style.ERROR(
                            f"#   [ERROR] WorkOrder #{wo.pk} -- "
                            f"no se pudo eliminar {pdf_path}: {exc}"
                        )
                    )
                    errores += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"\n# Fase 2 completada.\n"
                f"#   Ficheros purgados del disco   : {purgados}\n"
                f"#   Sin fichero en disco          : {sin_fichero}\n"
                f"#   Errores / omitidos            : {errores}\n"
                f"#   Grupos de duplicados evaluados: {total_grupos}"
            )
        )

    # ------------------------------------------------------------------
    # Helper / Auxiliar
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_sha256(file_path: str) -> str:
        """
        Computes and returns the SHA-256 hex digest of the file at file_path.
        Reads the file in 64 KB chunks to avoid loading large PDFs into memory.
        Raises FileNotFoundError if the path does not exist.
        ---
        Calcula y devuelve el hex digest SHA-256 del fichero en file_path.
        Lee el fichero en bloques de 64 KB para evitar cargar PDFs grandes en
        memoria. Lanza FileNotFoundError si la ruta no existe.
        """
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as fh:
            for chunk in iter(lambda: fh.read(65536), b""):
                sha256.update(chunk)
        return sha256.hexdigest()
