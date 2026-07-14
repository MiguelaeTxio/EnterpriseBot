# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/machine_documents/management/commands/test_classify_batch.py
"""
Django management command: test_classify_batch.

Empirical validation tool for machine_documents.document_classification_service
(Hito 23, hoja de ruta paso 4): given a local folder containing a real
batch of PDF documents (typically the A-45 case -- one combined
"master" PDF plus its individual components, already known from
S016), runs classify_document() on every file, then
assess_master_coverage() on whichever file(s) come back with
is_possible_master=True, and finally extract_pages() for any
uncovered content -- printing a full report to stdout.

Read-only: never writes to the database or to Google Drive. This is
deliberately a throwaway validation command for this milestone step,
not the production ingestion pipeline (that is the upload view of
roadmap step 5, not yet built).

Usage:
    python -m dotenv run python manage.py test_classify_batch \\
        --folder /ruta/a/la/carpeta/A-45 \\
        [--extract-to /ruta/de/salida/para/paginas/extraidas]

---

Comando de gestión Django: test_classify_batch.

Herramienta de validación empírica de
machine_documents.document_classification_service (Hito 23, hoja de
ruta paso 4): dada una carpeta local con un lote real de documentos
PDF (típicamente el caso A-45 -- un PDF "maestro" combinado más sus
componentes individuales, ya conocido desde S016), ejecuta
classify_document() sobre cada archivo, después
assess_master_coverage() sobre el/los archivo(s) que vuelvan con
is_possible_master=True, y finalmente extract_pages() para cualquier
contenido no cubierto -- imprimiendo un informe completo por stdout.

Solo lectura: nunca escribe en base de datos ni en Google Drive. Es
deliberadamente un comando de validación desechable para este paso
del hito, no el pipeline de ingesta de producción (eso es la vista de
subida del paso 5 de la hoja de ruta, todavía sin construir).

Uso:
    python -m dotenv run python manage.py test_classify_batch \\
        --folder /ruta/a/la/carpeta/A-45 \\
        [--extract-to /ruta/de/salida/para/paginas/extraidas]
"""
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from machine_documents.document_classification_service import (
    assess_master_coverage,
    classify_by_filename_heuristic,
    classify_document,
    extract_pages,
)


class Command(BaseCommand):
    """
    Read-only validation command for the Gemini Vision classification
    service, run against a real local batch of PDF documents.
    ---
    Comando de validación de solo lectura para el servicio de
    clasificación Gemini Vision, ejecutado contra un lote local real
    de documentos PDF.
    """

    help = (
        "Valida machine_documents.document_classification_service "
        "contra un lote real de PDFs (Hito 23, paso 4 de la hoja de "
        "ruta). Solo lectura -- no escribe en BD ni en Drive."
    )

    def add_arguments(self, parser) -> None:
        """
        Defines the command-line arguments accepted by the command.
        ---
        Define los argumentos de línea de comandos aceptados por el
        comando.
        """
        parser.add_argument(
            "--folder",
            required=True,
            type=str,
            help=(
                "Ruta absoluta a la carpeta que contiene todos los "
                "PDFs del lote (maestro + individuales)."
            ),
        )
        parser.add_argument(
            "--extract-to",
            type=str,
            default="",
            help=(
                "Ruta absoluta a una carpeta donde escribir los PDFs "
                "extraídos de páginas no cubiertas, si las hay. Si se "
                "omite, no se escribe ningún archivo -- solo se "
                "informa en el reporte."
            ),
        )

    def handle(self, *args, **options) -> None:
        """
        Entry point. Orchestrates classification, master-coverage
        comparison and optional page extraction over every PDF found
        in the given folder, printing a full report.
        ---
        Punto de entrada. Orquesta la clasificación, la comparación
        de cobertura de maestro y la extracción opcional de páginas
        sobre cada PDF encontrado en la carpeta indicada, imprimiendo
        un informe completo.
        """
        folder = Path(options["folder"])
        if not folder.is_dir():
            raise CommandError(f"# La carpeta no existe: {folder}")

        extract_to = options["extract_to"]
        extract_dir = Path(extract_to) if extract_to else None
        if extract_dir is not None:
            extract_dir.mkdir(parents=True, exist_ok=True)

        pdf_paths = sorted(folder.glob("*.pdf"))
        if not pdf_paths:
            raise CommandError(f"# No se encontraron PDFs en: {folder}")

        self.stdout.write(
            f"# [test_classify_batch] {len(pdf_paths)} PDF(s) "
            f"encontrados en {folder}.\n"
        )

        # ------------------------------------------------------------
        # Step 1 -- classify every file individually.
        # Paso 1 -- clasificar cada archivo individualmente.
        # ------------------------------------------------------------
        classified = []
        for pdf_path in pdf_paths:
            pdf_bytes = pdf_path.read_bytes()
            heuristic_result = classify_by_filename_heuristic(
                pdf_path.name,
            )
            if heuristic_result is not None:
                result = heuristic_result
                via_heuristic = True
            else:
                result = classify_document(pdf_bytes, pdf_path.name)
                via_heuristic = False
            classified.append(
                (pdf_path, pdf_bytes, result, via_heuristic),
            )

            self.stdout.write(
                f"# {pdf_path.name}"
                f"{' [heurística, sin Gemini]' if via_heuristic else ''}\n"
                f"    document_type      = {result['document_type']!r}\n"
                f"    display_name       = {result['display_name']!r}\n"
                f"    is_possible_master = "
                f"{result['is_possible_master']}\n"
            )

        # ------------------------------------------------------------
        # Step 2 -- for every candidate master, compare against the
        # rest of the batch and report uncovered pages. Files
        # classified via heuristic (manuals) are excluded from the
        # comparison set -- never sent to Gemini.
        # Paso 2 -- para cada candidato a maestro, comparar contra el
        # resto del lote e informar de páginas no cubiertas. Los
        # archivos clasificados por heurística (manuales) se excluyen
        # del conjunto de comparación -- nunca se envían a Gemini.
        # ------------------------------------------------------------
        candidates = [
            (path, pdf_bytes)
            for path, pdf_bytes, result, via_heuristic in classified
            if result["is_possible_master"] and not via_heuristic
        ]

        if not candidates:
            self.stdout.write(
                "\n# [test_classify_batch] Ningún archivo se detectó "
                "como posible maestro -- fin del reporte.\n"
            )
            return

        for candidate_path, candidate_bytes in candidates:
            individuals = [
                (path.name, pdf_bytes)
                for path, pdf_bytes, _result, via_heuristic in classified
                if path != candidate_path and not via_heuristic
            ]

            coverage = assess_master_coverage(
                candidate_bytes, candidate_path.name, individuals,
            )

            self.stdout.write(
                f"\n# Comparación de cobertura -- candidato "
                f"{candidate_path.name}\n"
                f"    is_master        = {coverage['is_master']}\n"
                f"    fully_covered    = {coverage['fully_covered']}\n"
                f"    uncovered_pages  = {coverage['uncovered_pages']}\n"
                f"    reasoning        = {coverage['reasoning']!r}\n"
            )

            if coverage["uncovered_pages"] and extract_dir is not None:
                extracted_bytes = extract_pages(
                    candidate_bytes, coverage["uncovered_pages"],
                )
                out_path = (
                    extract_dir
                    / f"{candidate_path.stem}_extraido_no_cubierto.pdf"
                )
                out_path.write_bytes(extracted_bytes)
                self.stdout.write(
                    f"    -> páginas no cubiertas escritas en: "
                    f"{out_path}\n"
                )
            elif coverage["uncovered_pages"]:
                self.stdout.write(
                    "    -> hay páginas no cubiertas pero no se "
                    "indicó --extract-to, no se escribe archivo.\n"
                )

        self.stdout.write("\n# [test_classify_batch] Reporte completo.\n")
