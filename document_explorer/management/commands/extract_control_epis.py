# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/management/commands/extract_control_epis.py
"""
H30 (S73). Extractor real de CONTROL EPIS -- punto 3 (antiguo) de la
hoja de ruta de S73. A diferencia de los extractores anteriores, esta
carpeta no es solo entregas: cada documento es una tabla de control
con marca de entrega Y columnas de estado (NUEVO/OPTIMO, DETERIORADO,
CADUCADO, REPUESTO) por ítem -- confirmado con 5 documentos reales
muestreados en esta misma sesión (2 .doc genéricos, 1 .doc de una
sola prenda, 1 imagen de PDF escaneado subida directamente por
Miguel Ángel).

Diseño confirmado por Miguel Ángel (S73):
- Marca de entrega (1ª columna, "X" o "SI") en CUALQUIER ítem -> crea
  `EpiDelivery` (delivery_date = fecha real de firma del documento).
- Columnas de estado (NUEVO/OPTIMO -- dos redacciones de época del
  mismo concepto -- DETERIORADO, CADUCADO) SOLO tienen sentido real
  para los 3 ítems con `requires_periodic_review=True` (arnés de
  seguridad, cinturón de dos elementos de amarre, elemento de
  amarre) -> crean `EpiReview` vinculada a la `EpiDelivery` de ese
  ítem/persona. Para el resto de ítems (ropa, casco, gafas...) estas
  columnas son ruido de plantilla y se ignoran (caso real:
  "GAFAS...DETERIORADO=X" solo documenta el motivo de la reposición,
  no una revisión formal de vida útil).
- `REPUESTO`: ignorado por completo, decisión explícita de Miguel
  Ángel ("no tiene sentido").
- Cuando toca crear una `EpiReview` y NO existe ninguna `EpiDelivery`
  previa de ese ítem/persona (el documento es la primera noticia que
  tenemos), se hace *backfill*: `delivery_date` estimada = fecha del
  documento menos `EpiItemCatalog.standard_expiry_years` (5 años,
  migración 0058) -- decisión explícita de Miguel Ángel tras
  confirmar que no hay caducidad legal fija (normativa EN 361/EN
  365), y que la fecha de caducidad real siempre podrá corregirse a
  mano por el supervisor en la futura interfaz (fuera de alcance de
  esta sesión).

Fuera de alcance de este comando, decisión explícita:
- El único PDF escaneado del lote (`CONTROL DE EPIS GALVEZ SIBAJAS,.
  JOSE MIGUEL.pdf`, id 22850) -- sin texto nativo, prohibido hacer
  OCR en consola (S62). Miguel Ángel ya lo subió como imagen y se
  procesó a mano en la misma sesión, fuera de este comando.
- Los 2 `.xlsx` de Huelva ("EPIS ENTREGADOS HUELVA...") -- estructura
  tabular multi-persona, necesitan su propio diseño, no encajan en
  este parser de un documento por persona.

Persona: SIEMPRE por DNI real (dígitos + letra de control CALCULADA).
Ítems: reutiliza ITEM_LABEL_MAP/_map_label/_convert_doc_to_docx ya
confirmados en extract_epis_deliveries.py -- nunca reinventados.

Documento original: SOLO se manda a papelera cuando persona + fecha
resolvieron Y ninguna fila marcada con entrega tuvo una etiqueta sin
mapear (mismo criterio "todo o nada" que el resto de extractores de
esta sesión). DRY-RUN POR DEFECTO. --apply escribe de verdad.
"""
import datetime
import io
import re

from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand

from document_explorer.classification_service import trash_dossier_entry
from document_explorer.management.commands.extract_epis_deliveries import (
    ITEM_LABEL_MAP, _convert_doc_to_docx, _map_label,
)
from document_explorer.models import (
    DocumentIndexEntry, EpiDelivery, EpiItemCatalog, EpiReview,
    PersonIdentity,
)
from spare_parts.gcs_service import download_bytes

assert ITEM_LABEL_MAP  # solo para dejar constancia del reuso real

_DNI_DIGITS_RE = re.compile(
    r"D\.?\s*N\.?\s*I\.?\s*[:.]?\s*([0-9]{1,2}[.\s]?[0-9]{3}[.\s]?[0-9]{3})"
)
_DNI_LETTER_TABLE = "TRWAGMYFPDXBNJZSQVHLCKE"
_FECHA_RE = re.compile(
    r"Fecha\s*[:.]?\s*([0-9]{1,2})/([0-9]{1,2})/([0-9]{2,4})",
    re.IGNORECASE,
)
_MARKED_VALUES = {"X", "SI"}

_REVIEW_ITEMS = {"ARNES_SEGURIDAD", "CINTURON_DOS_AMARRES", "ELEMENTO_AMARRE"}


def _compute_full_dni(digits):
    clean = re.sub(r"[.\s]", "", digits)
    if not clean.isdigit():
        return None
    return clean + _DNI_LETTER_TABLE[int(clean) % 23]


def _normalize_dni(dni):
    return re.sub(r"[.\s\-]", "", dni).upper()


def _extract_docx(data):
    import docx
    doc = docx.Document(io.BytesIO(data))
    tables = []
    for table in doc.tables:
        tables.append([[c.text.strip() for c in row.cells] for row in table.rows])
    return tables


def _parse_person(tables):
    for table in tables:
        for row in table:
            for cell in row:
                if "D.N.I" in cell.upper() or "DNI" in cell.upper():
                    m = _DNI_DIGITS_RE.search(cell)
                    if m:
                        return _compute_full_dni(m.group(1))
    return None


def _parse_fecha(tables):
    for table in tables:
        for row in table:
            for cell in row:
                m = _FECHA_RE.search(cell)
                if m:
                    day, month, year = m.groups()
                    year = int(year)
                    if year < 100:
                        year += 2000
                    try:
                        return datetime.date(year, int(month), int(day))
                    except ValueError:
                        continue
    return None


def _find_items_table(tables):
    for table in tables:
        if not table:
            continue
        header = [c.upper() for c in table[0]]
        if any("ARTICULO" in c for c in header):
            return table
    return None


def _is_marked(cell):
    return cell.strip().upper() in _MARKED_VALUES


def _subtract_years(d, years):
    try:
        return d.replace(year=d.year - years)
    except ValueError:
        # 29 de febrero sin año bisiesto de destino.
        return d.replace(year=d.year - years, day=28)


class Command(BaseCommand):
    help = (
        "H30 (S73) -- extractor real de CONTROL EPIS: EpiDelivery "
        "(marca de entrega, cualquier ítem) + EpiReview (estado, "
        "solo ítems con revisión periódica). Dry-run por defecto, "
        "--apply para escribir de verdad."
    )

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--limit", type=int, default=None)
        parser.add_argument(
            "--discard-unresolved-persona", action="store_true",
            dest="discard_unresolved",
            help=(
                "Manda directamente a papelera los documentos sin "
                "persona resoluble (sin DNI o DNI sin PersonIdentity), "
                "sin crear ningún EpiDelivery/EpiReview. Decisión "
                "explícita de Miguel Ángel (S73): se resolverá de "
                "verdad con la futura interfaz del supervisor."
            ),
        )

    def handle(self, *args, **options):
        apply_changes = options["apply"]
        limit = options["limit"]
        discard_unresolved = options["discard_unresolved"]

        qs = DocumentIndexEntry.objects.filter(
            bucket="cgs_grupo_alvarez",
            parent_path__icontains="CONTROL EPIS",
            entry_kind=DocumentIndexEntry.KIND_FILE,
            deleted_at__isnull=True,
            purged_at__isnull=True,
            name__iregex=r"\.docx?$",
        ).order_by("name")

        entries = list(qs.only("id", "bucket", "blob_name", "parent_path", "name"))
        if limit:
            entries = entries[:limit]

        self.stdout.write(self.style.MIGRATE_HEADING(
            "=== %d documento(s) .doc/.docx en alcance (%s) ==="
            % (len(entries), "APLICANDO" if apply_changes else "DRY-RUN")
        ))

        review_items = {
            c.code: c for c in EpiItemCatalog.objects.filter(code__in=_REVIEW_ITEMS)
        }

        totals = {
            "procesados": 0, "sin_persona": 0, "sin_fecha": 0,
            "sin_tabla_items": 0, "documentos_completos": 0,
            "documentos_parciales": 0, "deliveries_creadas": 0,
            "reviews_creadas": 0, "deliveries_backfilled": 0,
            "fallos_lectura": 0,
        }
        unmapped_labels = {}

        for entry in entries:
            data = download_bytes(entry.bucket, entry.blob_name)
            if entry.name.lower().endswith(".doc"):
                docx_bytes, err = _convert_doc_to_docx(data)
                if docx_bytes is None:
                    self.stdout.write(
                        "FALLO conversión: %s -- %s" % (entry.name, err)
                    )
                    totals["fallos_lectura"] += 1
                    continue
                data = docx_bytes

            try:
                tables = _extract_docx(data)
            except Exception as exc:
                self.stdout.write("FALLO lectura: %s -- %s" % (entry.name, exc))
                totals["fallos_lectura"] += 1
                continue

            totals["procesados"] += 1
            dni = _parse_person(tables)
            if not dni:
                self.stdout.write("SIN DNI: %s" % entry.name)
                totals["sin_persona"] += 1
                if apply_changes and discard_unresolved:
                    if trash_dossier_entry(entry):
                        self.stdout.write("  -> a papelera (sin persona resoluble)")
                continue

            person = PersonIdentity.objects.filter(
                dni__iexact=_normalize_dni(dni),
            ).first()
            if person is None:
                self.stdout.write(
                    "DNI SIN PersonIdentity: %s -- %s" % (dni, entry.name)
                )
                totals["sin_persona"] += 1
                if apply_changes and discard_unresolved:
                    if trash_dossier_entry(entry):
                        self.stdout.write("  -> a papelera (sin persona resoluble)")
                continue

            fecha = _parse_fecha(tables)
            if not fecha:
                self.stdout.write("SIN FECHA reconocible: %s" % entry.name)
                totals["sin_fecha"] += 1
                continue

            items_table = _find_items_table(tables)
            if not items_table:
                self.stdout.write("SIN TABLA DE ITEMS: %s" % entry.name)
                totals["sin_tabla_items"] += 1
                continue

            rows_to_create = []  # (code, event) event in {"DELIVERY", "REVIEW:<STATUS>"}
            fallo_mapeo = False
            for row in items_table[1:]:
                if len(row) < 5:
                    continue
                marca, articulo = row[0], row[1]
                col_estado1, deteriorado, caducado = row[2], row[3], row[4]

                code = _map_label(articulo)

                if _is_marked(marca):
                    if code is None:
                        fallo_mapeo = True
                        unmapped_labels[articulo] = (
                            unmapped_labels.get(articulo, 0) + 1
                        )
                        continue
                    rows_to_create.append((code, "DELIVERY"))

                if code in _REVIEW_ITEMS:
                    if _is_marked(deteriorado):
                        rows_to_create.append((code, "REVIEW:DETERIORATED"))
                    elif _is_marked(caducado):
                        rows_to_create.append((code, "REVIEW:EXPIRED"))
                    elif _is_marked(col_estado1):
                        rows_to_create.append((code, "REVIEW:OPTIMAL"))

            if fallo_mapeo:
                self.stdout.write(
                    "PARCIAL: %s -> persona=%s (pk=%d) fecha=%s -- "
                    "etiqueta(s) sin mapear, original SIN tocar"
                    % (entry.name, person, person.pk, fecha.isoformat())
                )
                totals["documentos_parciales"] += 1
                continue

            if not apply_changes:
                self.stdout.write(
                    "OK (dry-run): %s -> persona=%s (pk=%d) fecha=%s "
                    "eventos=%s"
                    % (
                        entry.name, person, person.pk, fecha.isoformat(),
                        rows_to_create,
                    )
                )
                totals["documentos_completos"] += 1
                totals["deliveries_creadas"] += sum(
                    1 for _, ev in rows_to_create if ev == "DELIVERY"
                )
                totals["reviews_creadas"] += sum(
                    1 for _, ev in rows_to_create if ev.startswith("REVIEW")
                )
                continue

            catalog_by_code = {
                c.code: c for c in EpiItemCatalog.objects.filter(
                    code__in={code for code, _ in rows_to_create},
                )
            }

            for code, event in rows_to_create:
                epi_item = catalog_by_code.get(code)
                if epi_item is None:
                    continue
                if event == "DELIVERY":
                    _, created = EpiDelivery.objects.get_or_create(
                        person=person, epi=epi_item, delivery_date=fecha,
                        defaults={
                            "source_entry": entry,
                            "extraction_method": EpiDelivery.METHOD_HEURISTIC,
                        },
                    )
                    if created:
                        totals["deliveries_creadas"] += 1
                    continue

                status = event.split(":")[1]
                status_map = {
                    "OPTIMAL": EpiReview.STATUS_OPTIMAL,
                    "DETERIORATED": EpiReview.STATUS_DETERIORATED,
                    "EXPIRED": EpiReview.STATUS_EXPIRED,
                }
                delivery = EpiDelivery.objects.filter(
                    person=person, epi=epi_item, delivery_date__lte=fecha,
                ).order_by("-delivery_date").first()
                if delivery is None:
                    years = review_items[code].standard_expiry_years
                    if not years:
                        continue
                    backfilled_date = _subtract_years(fecha, years)
                    delivery = EpiDelivery.objects.create(
                        person=person, epi=epi_item,
                        delivery_date=backfilled_date,
                        source_entry=entry,
                        extraction_method=EpiDelivery.METHOD_HEURISTIC,
                    )
                    totals["deliveries_backfilled"] += 1
                    totals["deliveries_creadas"] += 1

                _, created = EpiReview.objects.get_or_create(
                    delivery=delivery, review_date=fecha,
                    status=status_map[status],
                    defaults={"source_entry": entry},
                )
                if created:
                    totals["reviews_creadas"] += 1

            totals["documentos_completos"] += 1
            person_ct = ContentType.objects.get_for_model(PersonIdentity)
            entry.domain_content_type = person_ct
            entry.domain_object_id = person.pk
            entry.save(update_fields=["domain_content_type", "domain_object_id"])
            if trash_dossier_entry(entry):
                self.stdout.write(
                    "COMPLETO: %s -> %s (pk=%d), %d eventos, "
                    "original a papelera"
                    % (entry.name, person, person.pk, len(rows_to_create))
                )
            else:
                self.stdout.write(
                    "COMPLETO (aviso: no se pudo enviar a papelera): %s"
                    % entry.name
                )

        self.stdout.write(self.style.MIGRATE_HEADING("=== RESUMEN ==="))
        for key, value in totals.items():
            self.stdout.write("    %s: %d" % (key, value))
        if unmapped_labels:
            self.stdout.write("    Etiquetas sin mapear (frecuencia):")
            for label, n in sorted(unmapped_labels.items(), key=lambda x: -x[1]):
                self.stdout.write("      %4d  %r" % (n, label))
