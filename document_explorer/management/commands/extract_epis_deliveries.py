# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/management/commands/extract_epis_deliveries.py
"""
H30 (S72). Extractor real EPIs/Botiquines -- punto 5 de la hoja de
ruta de S71/S72. Crea filas reales de `EpiDelivery` a partir del
contenido real de los documentos ya tipados `EPIS` (.docx/.doc,
texto nativo -- nunca OCR, ver sample_epis_docx_extraction.py para el
detalle completo de por qué esto no cae bajo la prohibición de S62).

Ambito de esta primera pasada: las CUATRO subcarpetas ya validadas
con muestreo real (sample_epis_docx_extraction.py, S72) -- genérico
(años >= 2021, patrón [ARTICULO, X]), `EPIS POR ELEMENTOS`
("desglosados", patrón [X, ARTICULO, FECHA, FIRMA]),
`EPIS INDUSTRIA QUIMICA` (5 ítems del respirador), y `MECANICOS`
(patrón genérico con ítems extra de guantes/máscara de soldar).
NUNCA la raíz de `ENTREGA EPIS` (plantillas/guías, ya confirmado
S71) ni `EPIS VARIAS EMPRESAS` (entregas a nivel de empresa
subcontratada, no de persona) ni los años <2021 (ya vacíos, ver
find_empty_folders S72) ni el resto de subcarpetas especiales
(BOTIQUINES, CONTROL EPIS, ARNES MIRA 12-A, DETECTOR TENSION, ALTA
VISIBILIDAD, COVID) -- cada una necesita su propio diseño, no
encajan en este parser (0% esperado en el muestreo, confirmado).

Persona: SIEMPRE por DNI real extraído del contenido, NUNCA por
nombre/carpeta de origen -- lección real de esta sesión (archivo
"GOMEZ RIVERO, FCO.docx" cuyo contenido real es Daniel Serrano
Rojas, DNI distinto). Documentos cuyo DNI no resuelve contra
`PersonIdentity` se dejan intactos, reportados para revisión --
nunca se inventa ni se asume la persona por descarte.

Ítems: tabla de equivalencias fija (ver ITEM_LABEL_MAP), confirmada
por Miguel Ángel en S72:
- Etiquetas repetidas dentro del MISMO documento para el mismo ítem
  (p. ej. "ARNE DE SEGURIDAD" y "ARNES DE SEGURIDAD" en la misma
  tabla, o "CHALECO REFLECTANTE" marcado dos veces) -> UNA sola
  `EpiDelivery`, deduplicada por código de catálogo. Miguel Ángel,
  verbatim: "se ve que el que fuese se despistó y lo anotó dos
  veces."
- "PREFILTRO P3 /MASCARILLA 6200" y "FILTRO PARTICULAS" son el
  MISMO producto real (filtro 3M serie 2138/6200), confirmado con
  búsqueda de producto real -> mismo código `PREFILTRO_P3`.
- Etiquetas sin equivalencia reconocida se reportan (nunca se
  inventa una nueva fila de catálogo sobre la marcha) -- si aparecen
  con volumen real, se decide entonces si el catálogo necesita un
  ítem nuevo.

Fecha: parseada del nombre de archivo de origen (única fecha real
presente, mismo patrón ya usado en split_alta_idc_dossier.py).

Documento original: SOLO se manda a papelera cuando el archivo se
pudo procesar de punta a punta -- persona resuelta por DNI, al menos
un ítem reconocido, y todas las filas `EpiDelivery` creadas sin
fallo. Si algo falla a mitad, el documento original queda intacto y
se reporta, nunca se pierde contenido sin registrar.

DRY-RUN POR DEFECTO. Con --apply escribe de verdad: crea EpiDelivery,
vincula domain_content_type/domain_object_id en la fila original, y
la manda a papelera (trash_dossier_entry()). --limit acota el
número de documentos procesados en una pasada (muestreo previo
obligatorio antes de un --apply sin límite).
"""
import datetime
import io
import re
import subprocess
import tempfile
import unicodedata
from pathlib import Path

from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand

from document_explorer.classification_service import trash_dossier_entry
from document_explorer.models import (
    DocumentIndexEntry, EpiDelivery, EpiItemCatalog, PersonIdentity,
)
from spare_parts.gcs_service import download_bytes

_SOFFICE_TIMEOUT_SECONDS = 60

# Subcarpetas validadas por muestreo real (S72) -- ver docstring.
_SCOPED_SUBFOLDERS = {
    "EPIS POR ELEMENTOS", "EPIS INDUSTRIA QUIMICA", "MECANICOS",
}
# Los años sueltos (genérico) se aceptan por regex, ver _in_scope().
_YEAR_RE = re.compile(r"^\d{4}$")
_MIN_GENERIC_YEAR = 2021

_DNI_RE = re.compile(
    r"D\.?\s*N\.?\s*I\.?\s*[:.]?\s*([0-9]{1,2}[.\s]?[0-9]{3}[.\s]?"
    r"[0-9]{3}\s*-?\s*[A-Za-z]?)"
)
_NAME_ENTREGA_RE = re.compile(
    r"[Ee]ntrega\s+a\s+D\.?[ºa]?\.?\s+([A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑ\s.]+?)"
    r"\s+con\s+D\.?\s*N\.?\s*I"
)
_NAME_TABLE_RE = re.compile(
    r"D\.?\s+([A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑ\s]+?)\s+D\.?\s*N\.?\s*I\.?\s*[:.]?"
)
_DATE_LIKE_RE = re.compile(r"^[0-9./\-]+$")
_MARK_RE = re.compile(r"^[Xx✓]{1,2}$")
_FILENAME_DATE_RE = re.compile(r"(\d{1,2})-(\d{1,2})-(\d{2,4})")

# (frase clave normalizada -> codigo EpiItemCatalog). Se compara
# contra la etiqueta normalizada (mayusculas, sin acentos, espacios
# colapsados) con "in" -- primero las mas especificas.
ITEM_LABEL_MAP = [
    ("MASCARILLA FILTRO ANTIPARTICULAS", "MASCARILLA_FILTRO_ANTIPARTICULAS"),
    ("MASCARILLA CON FILTRO ANTI PARTICULAS", "MASCARILLA_FILTRO_ANTIPARTICULAS"),
    ("MASCARILLA BUCONASAL", "MASCARILLA_BUCONASAL"),
    ("MASCARA MEDIA", "MASCARA_MEDIA_RESPIRADOR"),
    ("MASCARA SOLDAR", "MASCARA_SOLDAR"),
    ("MASCARA DE SOLDAR", "MASCARA_SOLDAR"),
    ("CARETA DE PROTECCION", "CARETA_PROTECCION"),
    ("FILTROS VAPORES", "FILTRO_VAPORES_GASES_ACIDOS"),
    ("RETENEDOR DE FILTROS", "RETENEDOR_FILTROS"),
    ("BOLSA PORTARESPIRADOR", "BOLSA_PORTARRESPIRADOR"),
    ("BOLSA PORTARRESPIRADOR", "BOLSA_PORTARRESPIRADOR"),
    ("PREFILTRO P3", "PREFILTRO_P3"),
    ("FILTRO PARTICULAS", "PREFILTRO_P3"),
    ("GUANTES DE ACCION MECANICA Y QUIMICA", "GUANTES_MECANICA_QUIMICA"),
    ("GUANTES DE ACCION QUIMICA", "GUANTES_QUIMICA"),
    ("GUANTES ACCION QUIMICA", "GUANTES_QUIMICA"),
    ("GUANTES DE ACCION MECANICA", "GUANTES_MECANICA"),
    ("GUANTES ACCION MECANICA", "GUANTES_MECANICA"),
    ("GUANTES DE PROTECCION", "GUANTES_PROTECCION"),
    ("CINTURON DE SEG", "CINTURON_DOS_AMARRES"),
    ("ELEMENTO DE AMARRE", "ELEMENTO_AMARRE"),
    ("ARNE", "ARNES_SEGURIDAD"),  # cubre "ARNE" y "ARNES DE SEGURIDAD"
    ("ROPA IGNIFUGA", "ROPA_IGNIFUGA_ARCO"),
    ("ROPA INGNIFUGA", "ROPA_IGNIFUGA_ARCO"),  # typo real visto
    ("ROPA DE TRABAJO", "ROPA_TRABAJO"),
    ("CASCO", "CASCO_SEGURIDAD"),
    ("CHALECO REFLECTANTE", "CHALECO_REFLECTANTE"),
    ("ZAPATOS DE SEGURIDAD", "ZAPATOS_SEGURIDAD"),
    ("PROTECCION AUDITIVA", "PROTECCION_AUDITIVA"),
    ("GAFAS", "GAFAS_ANTIPARTICULAS"),
]


def _normalize(label):
    label = unicodedata.normalize("NFKD", label.upper())
    label = "".join(c for c in label if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", label).strip()


def _map_label(label):
    norm = _normalize(label)
    for phrase, code in ITEM_LABEL_MAP:
        if phrase in norm:
            return code
    return None


def _convert_doc_to_docx(content_bytes):
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
    import docx
    doc = docx.Document(io.BytesIO(data))
    para_text = "\n".join(p.text for p in doc.paragraphs)
    rows, table_texts = [], []
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


def _parse_marked_labels(table_rows):
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


def _normalize_dni(dni):
    return re.sub(r"[.\s\-]", "", dni).upper()


def _parse_date_from_filename(name):
    match = _FILENAME_DATE_RE.search(name)
    if not match:
        return None
    day, month, year = match.groups()
    year = int(year)
    if year < 100:
        year += 2000
    try:
        return datetime.date(year, int(month), int(day))
    except ValueError:
        return None


def _in_scope(entry, root_offset):
    resto = entry.parent_path[root_offset:].strip("/")
    primer_nivel = resto.split("/")[0] if resto else "(RAIZ)"
    if primer_nivel in _SCOPED_SUBFOLDERS:
        return True
    if _YEAR_RE.match(primer_nivel) and int(primer_nivel) >= _MIN_GENERIC_YEAR:
        return True
    return False


class Command(BaseCommand):
    help = (
        "H30 (S72) -- extractor real EPIs: crea EpiDelivery a partir "
        "del contenido real de los .docx/.doc ya validados (genérico "
        ">=2021, EPIS POR ELEMENTOS, EPIS INDUSTRIA QUIMICA, "
        "MECANICOS). Dry-run por defecto, --apply para escribir de "
        "verdad, --limit para acotar la pasada."
    )

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--limit", type=int, default=None)
        parser.add_argument(
            "--shard-count", type=int, default=1,
            help=(
                "Número total de consolas en paralelo. Cada documento "
                "se reparte de forma determinista (por pk) entre los "
                "shards -- ninguno se procesa dos veces."
            ),
        )
        parser.add_argument(
            "--shard-index", type=int, default=0,
            help="Índice de este shard (0 a shard-count - 1).",
        )

    def handle(self, *args, **options):
        apply_changes = options["apply"]
        limit = options["limit"]

        qs = DocumentIndexEntry.objects.filter(
            bucket="cgs_grupo_alvarez",
            parent_path__icontains="ENTREGA EPIS",
            document_type__code="EPIS",
            entry_kind=DocumentIndexEntry.KIND_FILE,
            deleted_at__isnull=True,
            purged_at__isnull=True,
            name__iregex=r"\.(docx?)$",
        )

        entries = []
        for e in qs.only("id", "bucket", "blob_name", "parent_path", "name"):
            idx = e.parent_path.upper().find("ENTREGA EPIS")
            root_offset = idx + len("ENTREGA EPIS")
            if _in_scope(e, root_offset):
                entries.append(e)

        shard_count = options["shard_count"]
        shard_index = options["shard_index"]
        if shard_count > 1:
            # Determinista por pk (nunca por posición en la lista, que
            # puede cambiar entre consolas si algo se procesa/borra
            # mientras las demás siguen corriendo) -- cada documento
            # cae en un único shard, sin solapes ni huecos.
            entries = [
                e for e in entries if e.id % shard_count == shard_index
            ]

        if limit:
            entries = entries[:limit]

        self.stdout.write(
            self.style.MIGRATE_HEADING(
                "=== %d documento(s) en alcance (%s) ==="
                % (
                    len(entries),
                    "APLICANDO" if apply_changes else "DRY-RUN",
                )
            )
        )

        totals = {
            "procesados": 0, "sin_persona": 0, "sin_items": 0,
            "items_sin_mapear": 0, "deliveries_creadas": 0,
            "documentos_completos": 0, "fallos_lectura": 0,
        }
        unmapped_labels = {}

        for entry in entries:
            data = download_bytes(entry.bucket, entry.blob_name)
            if entry.name.lower().endswith(".doc"):
                docx_bytes, err = _convert_doc_to_docx(data)
                if docx_bytes is None:
                    self.stdout.write(
                        "FALLO conversión: %s/%s -- %s"
                        % (entry.parent_path, entry.name, err)
                    )
                    totals["fallos_lectura"] += 1
                    continue
                data = docx_bytes

            try:
                text, rows = _extract_docx(data)
            except Exception as exc:
                self.stdout.write(
                    "FALLO lectura: %s/%s -- %s"
                    % (entry.parent_path, entry.name, exc)
                )
                totals["fallos_lectura"] += 1
                continue

            totals["procesados"] += 1
            _, dni = _parse_person(text)
            date = _parse_date_from_filename(entry.name)

            if not dni:
                self.stdout.write(
                    "SIN DNI: %s/%s" % (entry.parent_path, entry.name)
                )
                totals["sin_persona"] += 1
                continue

            person = PersonIdentity.objects.filter(
                dni__iexact=_normalize_dni(dni),
            ).first()
            if person is None:
                self.stdout.write(
                    "DNI SIN PersonIdentity: %s -- %s/%s"
                    % (dni, entry.parent_path, entry.name)
                )
                totals["sin_persona"] += 1
                continue

            if not date:
                self.stdout.write(
                    "SIN FECHA reconocible en el nombre: %s/%s"
                    % (entry.parent_path, entry.name)
                )
                totals["sin_items"] += 1
                continue

            labels = _parse_marked_labels(rows)
            codes = set()
            for label in labels:
                code = _map_label(label)
                if code:
                    codes.add(code)
                else:
                    totals["items_sin_mapear"] += 1
                    unmapped_labels[label] = unmapped_labels.get(label, 0) + 1

            if not codes:
                self.stdout.write(
                    "SIN ÍTEMS reconocidos: %s/%s"
                    % (entry.parent_path, entry.name)
                )
                totals["sin_items"] += 1
                continue

            if not apply_changes:
                self.stdout.write(
                    "OK (dry-run): %s -> persona=%s (pk=%d) fecha=%s "
                    "items=%s"
                    % (
                        entry.name, person, person.pk,
                        date.isoformat(), sorted(codes),
                    )
                )
                totals["documentos_completos"] += 1
                totals["deliveries_creadas"] += len(codes)
                continue

            catalog_by_code = {
                c.code: c for c in EpiItemCatalog.objects.filter(
                    code__in=codes,
                )
            }
            created_this_doc = 0
            for code in codes:
                epi_item = catalog_by_code.get(code)
                if epi_item is None:
                    self.stdout.write(
                        "AVISO: código %s no existe en EpiItemCatalog "
                        "-- omitido (%s/%s)"
                        % (code, entry.parent_path, entry.name)
                    )
                    continue
                EpiDelivery.objects.get_or_create(
                    person=person, epi=epi_item, delivery_date=date,
                    defaults={
                        "source_entry": entry,
                        "extraction_method": EpiDelivery.METHOD_HEURISTIC,
                    },
                )
                created_this_doc += 1

            totals["deliveries_creadas"] += created_this_doc
            if created_this_doc == len(codes):
                totals["documentos_completos"] += 1
                person_ct = ContentType.objects.get_for_model(PersonIdentity)
                entry.domain_content_type = person_ct
                entry.domain_object_id = person.pk
                entry.save(update_fields=[
                    "domain_content_type", "domain_object_id",
                ])
                if trash_dossier_entry(entry):
                    self.stdout.write(
                        "COMPLETO: %s -> %s (pk=%d), %d entregas, "
                        "original a papelera"
                        % (entry.name, person, person.pk, created_this_doc)
                    )
                else:
                    self.stdout.write(
                        "COMPLETO (aviso: no se pudo enviar a "
                        "papelera): %s" % entry.name
                    )
            else:
                self.stdout.write(
                    "PARCIAL: %s -- %d de %d ítems creados, original "
                    "SIN tocar" % (entry.name, created_this_doc, len(codes))
                )

        self.stdout.write(self.style.MIGRATE_HEADING("=== RESUMEN ==="))
        for key, value in totals.items():
            self.stdout.write("    %s: %d" % (key, value))
        if unmapped_labels:
            self.stdout.write("    Etiquetas sin mapear (frecuencia):")
            for label, n in sorted(
                unmapped_labels.items(), key=lambda x: -x[1],
            ):
                self.stdout.write("      %4d  %r" % (n, label))
