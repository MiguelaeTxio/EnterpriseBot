# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/management/commands/sample_epis_docx_extraction.py
"""
H30 (S72). Muestreo obligatorio previo (mismo criterio ya aplicado en
toda la plataforma: nunca lanzar un barrido grande sin antes validar
con --limit contra una muestra real) para el extractor real
EPIs/Botiquines.

Objetivo de este comando: SOLO informar. Extrae de una muestra de
archivos .docx/.doc reales de document_type=EPIS (repartida entre las
distintas subcarpetas/plantillas conocidas: genérico, EPIS POR
ELEMENTOS/desglosados, MECANICOS, ALTA VISIBILIDAD, INDUSTRIA
QUIMICA, resto) el nombre/DNI real de la persona (nunca del nombre de
archivo -- lección real de esta sesión, ver caso GOMEZ RIVERO /
Daniel Serrano Rojas) y la lista de items marcados con X en la tabla
de EPIs entregados. Imprime todo para revisión humana -- NO escribe
nada en la base de datos, NO crea EpiDelivery, NO decide todavía el
mapeo final de etiquetas de tabla a codigos de EpiItemCatalog.

.doc legacy se convierte a .docx en memoria con LibreOffice headless
(mismo `soffice` ya confirmado instalado y usado en
classification_service._convert_to_pdf() -- aqui con
--convert-to docx en vez de pdf, para conservar la tabla real, no solo
el texto). Ni la conversión ni la lectura de texto nativo de un
.docx/.doc son OCR (pytesseract/PyMuPDF sobre imagen) -- no caen bajo
la prohibición de S62 (com-standards, "COSTE DE CPU DE OCR"), que
habla estrictamente de reconocimiento óptico sobre escaneos.

DNI: regex tolerante a los formatos reales vistos (con o sin puntos,
con o sin guion, letra de control opcional).

Tabla de EPIs: cada tabla del docx se recorre celda a celda; una
celda es "marca" (X/x) si su texto, sin espacios, es exactamente "X"
o una variante de 1-2 caracteres -- la etiqueta real es la celda
INMEDIATAMENTE ANTERIOR en la misma fila. Mismo patrón visto en
GOMEZ_RIVERO/GALLARDO: pares (etiqueta, marca) repetidos en la fila.
"""
import io
import re
import subprocess
import tempfile
from pathlib import Path

from django.core.management.base import BaseCommand

from document_explorer.models import DocumentIndexEntry
from spare_parts.gcs_service import download_bytes

_DNI_RE = re.compile(
    r"D\.?\s*N\.?\s*I\.?\s*[:.]?\s*([0-9]{1,2}[.\s]?[0-9]{3}[.\s]?"
    r"[0-9]{3}\s*-?\s*[A-Za-z]?)"
)
# Dos formas reales confirmadas (S72): "Se hace entrega a D. X con
# D.N.I. Y" (plantilla genérica, en párrafo suelto) y "D. X ... D.N.I.
# Y" sin "entrega a" (plantilla "desglosados", dentro de celda de
# tabla -- ver EPIS_01-10-18_desglosados_MORENO_GARCIA.doc real).
_NAME_ENTREGA_RE = re.compile(
    r"[Ee]ntrega\s+a\s+D\.?[ºa]?\.?\s+([A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑ\s.]+?)"
    r"\s+con\s+D\.?\s*N\.?\s*I"
)
_NAME_TABLE_RE = re.compile(
    r"D\.?\s+([A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑ\s]+?)\s+D\.?\s*N\.?\s*I\.?\s*[:.]?"
)
_DATE_LIKE_RE = re.compile(r"^[0-9./\-]+$")
_MARK_RE = re.compile(r"^[Xx✓]{1,2}$")

_SOFFICE_TIMEOUT_SECONDS = 60


def _convert_doc_to_docx(content_bytes):
    """.doc -> .docx en memoria via LibreOffice headless. None si falla."""
    with tempfile.TemporaryDirectory() as workdir:
        input_path = Path(workdir) / "input.doc"
        profile_dir = Path(workdir) / "profile"
        input_path.write_bytes(content_bytes)
        try:
            subprocess.run(
                [
                    "soffice", "--headless", "--norestore",
                    "-env:UserInstallation=file://%s" % profile_dir,
                    "--convert-to", "docx", "--outdir", workdir,
                    str(input_path),
                ],
                check=True, timeout=_SOFFICE_TIMEOUT_SECONDS,
                capture_output=True,
            )
        except Exception as exc:
            return None, str(exc)
        output_path = Path(workdir) / "input.docx"
        if not output_path.exists():
            return None, "soffice no generó input.docx"
        return output_path.read_bytes(), None


def _extract_docx(data):
    """Devuelve (texto_completo, filas_tabla) de un .docx real.

    texto_completo combina parrafos de cuerpo Y texto de celdas de
    tabla -- python-docx los separa (doc.paragraphs NUNCA incluye
    contenido de doc.tables), y la plantilla "desglosados" pone el
    bloque DATOS DEL TRABAJADOR entero dentro de una celda, no en un
    parrafo suelto (hallazgo real S72, ver
    EPIS_01-10-18_desglosados_MORENO_GARCIA.doc).
    """
    import docx
    doc = docx.Document(io.BytesIO(data))
    para_text = "\n".join(p.text for p in doc.paragraphs)

    rows = []
    table_texts = []
    for table in doc.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells]
            rows.append(cells)
            table_texts.append(" ".join(cells))

    full_text = para_text + "\n" + "\n".join(table_texts)
    return full_text, rows


def _parse_person(text):
    dni_match = _DNI_RE.search(text)
    dni = dni_match.group(1).strip() if dni_match else None

    name_match = _NAME_ENTREGA_RE.search(text) or _NAME_TABLE_RE.search(text)
    name = name_match.group(1).strip() if name_match else None
    return name, dni


def _parse_marked_items(table_rows):
    """Una celda es "marca" si es X/x/✓. La etiqueta real puede estar
    en la celda SIGUIENTE (plantilla "desglosados": [X, ARTICULO,
    FECHA, FIRMA]) o en la ANTERIOR (plantilla generica:
    [ARTICULO, X]) -- se prueba la siguiente primero, y solo si no
    parece una etiqueta real (vacia o con pinta de fecha) se prueba la
    anterior."""
    marked = []
    for row in table_rows:
        for i, cell in enumerate(row):
            if not _MARK_RE.match(cell):
                continue
            label = None
            if (
                i - 1 >= 0 and row[i - 1]
                and not _MARK_RE.match(row[i - 1])
                and not _DATE_LIKE_RE.match(row[i - 1])
            ):
                label = row[i - 1]
            elif (
                i + 1 < len(row) and row[i + 1]
                and not _DATE_LIKE_RE.match(row[i + 1])
            ):
                label = row[i + 1]
            if label:
                marked.append(label)
    return marked


class Command(BaseCommand):
    help = (
        "H30 (S72) -- SOLO INFORMA. Muestra el resultado real de "
        "extraer persona/DNI/items marcados de una muestra de "
        "archivos EPIS .docx/.doc, repartida por subcarpeta. Nunca "
        "escribe nada -- es el muestreo previo obligatorio antes de "
        "construir el extractor real."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--per-folder", type=int, default=3,
            help="Cuántos archivos muestrear por subcarpeta (por defecto 3).",
        )

    def handle(self, *args, **options):
        per_folder = options["per_folder"]

        qs = DocumentIndexEntry.objects.filter(
            bucket="cgs_grupo_alvarez",
            parent_path__icontains="ENTREGA EPIS",
            document_type__code="EPIS",
            entry_kind=DocumentIndexEntry.KIND_FILE,
            deleted_at__isnull=True,
            purged_at__isnull=True,
            name__iregex=r"\.(docx?)$",
        )

        # Agrupar por primer nivel bajo ENTREGA EPIS, para repartir la
        # muestra entre plantillas distintas, no solo las primeras N
        # filas de la BD.
        buckets = {}
        for e in qs.only("id", "parent_path", "name"):
            idx = e.parent_path.upper().find("ENTREGA EPIS")
            resto = e.parent_path[idx + len("ENTREGA EPIS"):].strip("/")
            primer_nivel = resto.split("/")[0] if resto else "(RAIZ)"
            buckets.setdefault(primer_nivel, []).append(e)

        total_ok, total_fail = 0, 0

        for carpeta, entries in sorted(buckets.items()):
            muestra = entries[:per_folder]
            self.stdout.write(
                self.style.MIGRATE_HEADING(
                    "=== %s (%d vivos, muestreando %d) ==="
                    % (carpeta, len(entries), len(muestra))
                )
            )
            for entry in muestra:
                self.stdout.write("  %s" % entry.name)
                data = download_bytes(entry.bucket, entry.blob_name)

                if entry.name.lower().endswith(".doc"):
                    docx_bytes, err = _convert_doc_to_docx(data)
                    if docx_bytes is None:
                        self.stdout.write(
                            "    FALLO conversión .doc->.docx: %s" % err
                        )
                        total_fail += 1
                        continue
                    data = docx_bytes

                try:
                    text, rows = _extract_docx(data)
                except Exception as exc:
                    self.stdout.write("    FALLO lectura .docx: %s" % exc)
                    total_fail += 1
                    continue

                name, dni = _parse_person(text)
                marked = _parse_marked_items(rows)

                if not name or not dni:
                    self.stdout.write(
                        "    SIN PATRÓN reconocido -- nombre=%r dni=%r"
                        % (name, dni)
                    )
                    total_fail += 1
                else:
                    self.stdout.write(
                        "    persona=%r  dni=%r" % (name, dni)
                    )
                    total_ok += 1

                self.stdout.write(
                    "    items marcados (%d): %s"
                    % (len(marked), marked)
                )

        self.stdout.write(self.style.MIGRATE_HEADING("=== RESUMEN ==="))
        self.stdout.write(
            "Con persona+DNI reconocidos: %d | Sin patrón/fallo: %d"
            % (total_ok, total_fail)
        )
