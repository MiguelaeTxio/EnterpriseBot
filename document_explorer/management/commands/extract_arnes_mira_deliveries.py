# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/management/commands/extract_arnes_mira_deliveries.py
"""
H30 (S73). Extractor real de ARNES MIRA 12-A -- 50 .docx reales bajo
`DOC. PERSONAL/ENTREGA EPIS/EPIS ARNES MIRA 12-A` (el 51º archivo de
la carpeta, "Folleto informativo arne y absorbedor.pdf", ya se
clasificó como `FICHA_TECNICA_EPI` en el punto 1 de esta sesión y
queda fuera de este comando).

Muestreo real (3/50) confirmó plantilla ÚNICA y consistente: cada
documento es la entrega conjunta de DOS EPIs al mismo tiempo -- un
ARNES DE SEGURIDAD (fabricante Miguel Miranda S.L., modelo MIRA-12A)
y un equipo de amarre (modelo E15C) -- sin tabla de marcas ni
columnas de estado, a diferencia de CONTROL EPIS. Misma fecha de
entrega para ambos ítems.

Persona: SIEMPRE por DNI real (dígitos + letra de control CALCULADA).
Fecha: pie de firma "A fecha (DD/MM/AAAA)" (mismo formato que
Botiquines, S73).

Documento original: SOLO se manda a papelera cuando persona + fecha
resolvieron. DRY-RUN POR DEFECTO. --apply escribe de verdad.
"""
import datetime
import io
import re

from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand

from document_explorer.classification_service import trash_dossier_entry
from document_explorer.models import (
    DocumentIndexEntry, EpiDelivery, EpiItemCatalog, PersonIdentity,
)
from spare_parts.gcs_service import download_bytes

_DNI_DIGITS_RE = re.compile(
    r"DNI\.?\s*[:.]?\s*([0-9]{1,2}[.\s]?[0-9]{3}[.\s]?[0-9]{3})"
)
_DNI_LETTER_TABLE = "TRWAGMYFPDXBNJZSQVHLCKE"
_FECHA_RE = re.compile(
    r"fecha\s*\(([0-9]{1,2})/([0-9]{1,2})/([0-9]{2,4})\)",
    re.IGNORECASE,
)
_ITEMS_ENTREGADOS = ["ARNES_SEGURIDAD", "ELEMENTO_AMARRE"]


def _compute_full_dni(digits):
    clean = re.sub(r"[.\s]", "", digits)
    if not clean.isdigit():
        return None
    return clean + _DNI_LETTER_TABLE[int(clean) % 23]


def _normalize_dni(dni):
    return re.sub(r"[.\s\-]", "", dni).upper()


def _extract_rows(data):
    import docx
    doc = docx.Document(io.BytesIO(data))
    rows = []
    for table in doc.tables:
        for row in table.rows:
            rows.append([c.text.strip() for c in row.cells])
    return rows


def _parse_person(rows):
    for row in rows:
        for cell in row:
            if "DNI" in cell.upper() and cell.upper().strip().startswith("D."):
                m = _DNI_DIGITS_RE.search(cell)
                if m:
                    return _compute_full_dni(m.group(1))
    return None


def _parse_fecha(rows):
    for row in rows:
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
                    return None
    return None


class Command(BaseCommand):
    help = (
        "H30 (S73) -- extractor real de ARNES MIRA 12-A: crea 2 "
        "EpiDelivery (ARNES_SEGURIDAD + ELEMENTO_AMARRE) por "
        "documento. Dry-run por defecto, --apply para escribir de "
        "verdad."
    )

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--limit", type=int, default=None)
        parser.add_argument(
            "--discard-unresolved-persona", action="store_true",
            dest="discard_unresolved",
        )

    def handle(self, *args, **options):
        apply_changes = options["apply"]
        limit = options["limit"]
        discard_unresolved = options["discard_unresolved"]

        qs = DocumentIndexEntry.objects.filter(
            bucket="cgs_grupo_alvarez",
            parent_path__icontains="ARNES MIRA",
            entry_kind=DocumentIndexEntry.KIND_FILE,
            deleted_at__isnull=True,
            purged_at__isnull=True,
            name__iregex=r"\.docx?$",
        ).order_by("name")

        entries = list(qs.only("id", "bucket", "blob_name", "parent_path", "name"))
        if limit:
            entries = entries[:limit]

        self.stdout.write(self.style.MIGRATE_HEADING(
            "=== %d documento(s) en alcance (%s) ==="
            % (len(entries), "APLICANDO" if apply_changes else "DRY-RUN")
        ))

        items = {
            c.code: c for c in EpiItemCatalog.objects.filter(
                code__in=_ITEMS_ENTREGADOS,
            )
        }

        totals = {
            "procesados": 0, "sin_persona": 0, "sin_fecha": 0,
            "documentos_completos": 0, "deliveries_creadas": 0,
            "fallos_lectura": 0,
        }

        for entry in entries:
            data = download_bytes(entry.bucket, entry.blob_name)
            try:
                rows = _extract_rows(data)
            except Exception as exc:
                self.stdout.write("FALLO lectura: %s -- %s" % (entry.name, exc))
                totals["fallos_lectura"] += 1
                continue

            totals["procesados"] += 1
            dni = _parse_person(rows)
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

            fecha = _parse_fecha(rows)
            if not fecha:
                self.stdout.write("SIN FECHA reconocible: %s" % entry.name)
                totals["sin_fecha"] += 1
                continue

            if not apply_changes:
                self.stdout.write(
                    "OK (dry-run): %s -> persona=%s (pk=%d) fecha=%s "
                    "items=%s"
                    % (entry.name, person, person.pk, fecha.isoformat(), _ITEMS_ENTREGADOS)
                )
                totals["documentos_completos"] += 1
                totals["deliveries_creadas"] += len(_ITEMS_ENTREGADOS)
                continue

            new_rows_this_doc = 0
            for code in _ITEMS_ENTREGADOS:
                epi_item = items.get(code)
                if epi_item is None:
                    continue
                _, created = EpiDelivery.objects.get_or_create(
                    person=person, epi=epi_item, delivery_date=fecha,
                    defaults={
                        "source_entry": entry,
                        "extraction_method": EpiDelivery.METHOD_HEURISTIC,
                    },
                )
                if created:
                    new_rows_this_doc += 1

            totals["deliveries_creadas"] += new_rows_this_doc
            totals["documentos_completos"] += 1
            person_ct = ContentType.objects.get_for_model(PersonIdentity)
            entry.domain_content_type = person_ct
            entry.domain_object_id = person.pk
            entry.save(update_fields=["domain_content_type", "domain_object_id"])
            if trash_dossier_entry(entry):
                self.stdout.write(
                    "COMPLETO: %s -> %s (pk=%d), %d entregas (%d nuevas), "
                    "original a papelera"
                    % (entry.name, person, person.pk, len(_ITEMS_ENTREGADOS), new_rows_this_doc)
                )
            else:
                self.stdout.write(
                    "COMPLETO (aviso: no se pudo enviar a papelera): %s"
                    % entry.name
                )

        self.stdout.write(self.style.MIGRATE_HEADING("=== RESUMEN ==="))
        for key, value in totals.items():
            self.stdout.write("    %s: %d" % (key, value))
