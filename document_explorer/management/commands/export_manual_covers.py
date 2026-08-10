# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/management/commands/export_manual_covers.py
"""
Django management command: export_manual_covers.

H30, S044 -- alternativa de coste cero a audit_manual_models: en vez de
llamar a Gemini para identificar el modelo real de cada manual (219/291
candidatos, con varios por encima del límite real de 50 MB de Gemini
para documentos -- 16 detectados en esta sesión, hasta 420,6 MB),
Miguel Ángel revisa él mismo las dos primeras páginas de cada manual,
reunidas en un único PDF descargable. Decisión explícita de Miguel
Ángel (S044): "podemos generar un PDF con las dos primeras páginas de
cada uno de los archivos [...] y de esa forma hacemos cero llamadas a
la API de Gemini."

Solo lectura sobre DocumentIndexEntry y GCS -- no escribe nada en la
base de datos, no mueve ni renombra ningún archivo real ni virtual.
El único efecto es un fichero PDF nuevo en disco del servidor (SWAP),
fuera de GCS y fuera del índice.

Antes de cada extracto de dos páginas se inserta una página de rótulo
con el número de secuencia, la carpeta y nombre reales, y el tamaño en
MB -- así Miguel Ángel puede identificar cada manual sin ambigüedad al
revisar el PDF combinado. Los archivos que no son PDF real (p. ej. un
.rar mezclado en la misma carpeta) o que no se pueden abrir se marcan
en su propia página de rótulo, sin intentar extraer nada de ellos.

Reutiliza exactamente el mismo filtro de consulta que
audit_manual_models (mismo bug real corregido en S041: "MANUAL" sin
más también casaba con DOC. PERSONAL/ENTREGA MANUAL COMBUSTIBLE).

Uso:
    python -m dotenv run python manage.py export_manual_covers \
        --bucket cgs_grupo_alvarez \
        --output /home/MiguelAeTxio/SWAP/EnterpriseBot_manual_covers.pdf

---

Django management command: export_manual_covers.

H30, S044 -- zero-cost alternative to audit_manual_models: instead of
calling Gemini to identify each manual's real machine model, Miguel
Ángel reviews the first two pages of every candidate manual himself,
gathered into a single downloadable PDF. Read-only over
DocumentIndexEntry and GCS; the only side effect is a new PDF file on
the server's disk (SWAP), outside of GCS and outside the index.
"""
import io

import fitz

from django.core.management.base import BaseCommand, CommandError
from django.db import close_old_connections

from document_explorer.models import DocumentIndexEntry
from spare_parts.gcs_service import download_bytes

_COVER_PAGES = 2

# Tamaño de página A4 en puntos, para las páginas de rótulo -- mismo
# criterio visual que el resto de páginas insertadas (A4 es el formato
# real de casi todos los manuales de este corpus).
_PAGE_WIDTH = 595
_PAGE_HEIGHT = 842


class Command(BaseCommand):
    help = (
        "Extrae las dos primeras páginas de cada manual candidato "
        "(mismo filtro que audit_manual_models) y las combina en un "
        "único PDF de revisión manual, con una página de rótulo por "
        "archivo. Solo lectura -- cero llamadas a Gemini, cero "
        "escrituras en BD o GCS."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--bucket",
            required=True,
            help="Cubo indexado a recorrer (obligatorio).",
        )
        parser.add_argument(
            "--output",
            required=True,
            help=(
                "Ruta absoluta de salida en el servidor para el PDF "
                "combinado (p. ej. /home/MiguelAeTxio/SWAP/"
                "EnterpriseBot_manual_covers.pdf)."
            ),
        )

    def handle(self, *args, **options):
        bucket = options["bucket"]
        output_path = options["output"]

        manuals = list(
            DocumentIndexEntry.objects.filter(
                bucket=bucket,
                entry_kind=DocumentIndexEntry.KIND_FILE,
                deleted_at__isnull=True,
                purged_at__isnull=True,
                parent_path__icontains="MANUAL",
            )
            # Mismo bug real de S041 evitado aquí también: "MANUAL"
            # sin más casa con DOC. PERSONAL/ENTREGA MANUAL
            # COMBUSTIBLE -- exclusión de principio, no un parche.
            .exclude(parent_path__istartswith="DOC. PERSONAL")
            .order_by("parent_path", "name")
        )
        if not manuals:
            raise CommandError(
                "Sin archivos vivos con 'MANUAL' en parent_path en %s "
                "(fuera de DOC. PERSONAL)." % bucket
            )

        self.stdout.write(self.style.MIGRATE_HEADING(
            "=== %d manual(es) a exportar (bucket=%s) ===" % (
                len(manuals), bucket,
            )
        ))

        combined = fitz.open()
        ok_count = 0
        skipped_count = 0
        try:
            for index, entry in enumerate(manuals, start=1):
                self.stdout.write(
                    "[%d/%d] %s / %s (%.1f MB)" % (
                        index, len(manuals), entry.parent_path,
                        entry.name, (entry.size_bytes or 0) / (1024 * 1024),
                    )
                )
                # Mismo fix real de S044 que audit_manual_models: sin
                # esto, una sesión larga con muchas descargas seguidas
                # puede dejar la conexión MySQL inactiva más tiempo del
                # wait_timeout del servidor y reventar a mitad de la
                # exportación.
                close_old_connections()

                note = self._append_entry(combined, entry, index)
                if note is None:
                    ok_count += 1
                else:
                    skipped_count += 1
                    self.stdout.write(
                        self.style.WARNING("  omitido: %s" % note)
                    )

            output = io.BytesIO()
            combined.save(output)
        finally:
            combined.close()

        with open(output_path, "wb") as fh:
            fh.write(output.getvalue())

        self.stdout.write(self.style.MIGRATE_HEADING("\n=== RESUMEN ==="))
        self.stdout.write("Con extracto de 2 páginas: %d" % ok_count)
        self.stdout.write("Omitidos (marcados en su propio rótulo): %d" % (
            skipped_count
        ))
        self.stdout.write("PDF combinado escrito en: %s" % output_path)

    def _append_entry(self, combined, entry, index) -> str | None:
        """
        Añade a `combined` la página de rótulo de `entry` seguida de
        sus 2 primeras páginas reales. Devuelve None si se extrajeron
        páginas reales, o un texto explicando por qué se omitió la
        extracción (el rótulo se añade siempre, incluso al omitir).
        """
        label_lines = [
            "#%d" % index,
            entry.parent_path or "(raíz)",
            entry.name,
            "%.1f MB" % ((entry.size_bytes or 0) / (1024 * 1024)),
        ]

        if not entry.name.lower().endswith(".pdf"):
            note = "no es un PDF (extensión distinta) -- revisar manualmente"
            self._insert_label_page(combined, label_lines, note)
            return note

        try:
            content_bytes = download_bytes(entry.bucket, entry.blob_name)
        except Exception as exc:
            note = "fallo al descargar de GCS: %s" % exc
            self._insert_label_page(combined, label_lines, note)
            return note

        try:
            with fitz.open(stream=content_bytes, filetype="pdf") as source:
                pages_to_take = min(_COVER_PAGES, source.page_count)
                if pages_to_take < 1:
                    note = "PDF sin páginas"
                    self._insert_label_page(combined, label_lines, note)
                    return note
                self._insert_label_page(combined, label_lines, None)
                combined.insert_pdf(
                    source, from_page=0, to_page=pages_to_take - 1,
                )
        except Exception as exc:
            note = "PDF corrupto o no soportado: %s" % exc
            self._insert_label_page(combined, label_lines, note)
            return note

        return None

    def _insert_label_page(self, combined, label_lines, note):
        page = combined.new_page(width=_PAGE_WIDTH, height=_PAGE_HEIGHT)
        y = 60
        for line in label_lines:
            page.insert_text((40, y), line, fontsize=14)
            y += 24
        if note:
            page.insert_text(
                (40, y + 20), "OMITIDO: %s" % note, fontsize=12,
                color=(0.7, 0, 0),
            )
