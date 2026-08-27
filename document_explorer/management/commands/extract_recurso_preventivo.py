# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/management/commands/extract_recurso_preventivo.py
"""
H30 (S73). Extractor real de las dos subcarpetas de
`DOC. PERSONAL/NOMBRAMIENTO RECURSO PREVENTIVO` (la raíz, 14
archivos, ya se procesó a mano en la misma sesión -- 10 documentos
reales + 4 plantillas en blanco dejadas intactas).

Dos plantillas reales distintas, confirmadas por muestreo (S73):

- `ENTREGA FUNCIONES RECURSO PREVENTIVO` (67 archivos, tipo
  `ENTREGA_INFORMACION`): texto plano sin tabla, "TRABAJADOR: <nombre>"
  / "DNI: <dni>" / "A fecha(DD/MM/AAAA)".
- `FIRMADOS` (77 archivos, tipo `RECURSO_PREVENTIVO`): mismo texto de
  designación que la raíz, "Sr. D. <nombre> con DNI nº <dni>" / "En
  <CIUDAD> a <DIA> de <MES EN LETRA> de <AÑO>".

Persona: SIEMPRE por DNI real (dígitos + letra de control CALCULADA).
Destino: `DocumentAcknowledgment` (persona + tipo documental + fecha),
NUNCA `EpiDelivery` -- decisión ya registrada en el propio modelo
(H30 S69): nombramientos y EPIs son catálogos distintos.

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
    DocumentAcknowledgment, DocumentIndexEntry, PersonIdentity,
)
from spare_parts.gcs_service import download_bytes

_DNI_DIGITS_RE = re.compile(
    r"DNI\.?\s*(?:n[ºo°]\.?)?\s*[:.]?\s*([0-9]{1,2}[.\s]?[0-9]{3}[.\s]?[0-9]{3})"
)
_DNI_LETTER_TABLE = "TRWAGMYFPDXBNJZSQVHLCKE"

# "ENTREGA FUNCIONES": "A fecha(DD/MM/AAAA)"
_FECHA_NUMERICA_RE = re.compile(
    r"[Aa]\s*fecha\s*\(\s*([0-9]{1,2})/([0-9]{1,2})/([0-9]{2,4})\s*\)"
)

# "FIRMADOS": "En MALAGA a 23 de septiembre de 2022"
_MESES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5,
    "junio": 6, "julio": 7, "agosto": 8, "septiembre": 9,
    "octubre": 10, "noviembre": 11, "diciembre": 12,
}
_FECHA_LITERAL_RE = re.compile(
    r"a\s+(\d{1,2})\s+de\s+([A-Za-zÁÉÍÓÚáéíóú]+)\s+de\s+(\d{4})",
    re.IGNORECASE,
)


def _compute_full_dni(digits):
    clean = re.sub(r"[.\s]", "", digits)
    if not clean.isdigit():
        return None
    return clean + _DNI_LETTER_TABLE[int(clean) % 23]


def _normalize_dni(dni):
    return re.sub(r"[.\s\-]", "", dni).upper()


def _extract_text(data):
    import docx
    doc = docx.Document(io.BytesIO(data))
    parts = [p.text for p in doc.paragraphs]
    for table in doc.tables:
        for row in table.rows:
            parts.append(" | ".join(c.text.strip() for c in row.cells))
    return "\n".join(parts)


def _parse_person(text):
    m = _DNI_DIGITS_RE.search(text)
    if not m:
        return None
    return _compute_full_dni(m.group(1))


def _parse_fecha(text):
    m = _FECHA_NUMERICA_RE.search(text)
    if m:
        day, month, year = m.groups()
        year = int(year)
        if year < 100:
            year += 2000
        try:
            return datetime.date(year, int(month), int(day))
        except ValueError:
            pass

    m = _FECHA_LITERAL_RE.search(text)
    if m:
        day, mes_texto, year = m.groups()
        month = _MESES.get(mes_texto.lower())
        if month:
            try:
                return datetime.date(int(year), month, int(day))
            except ValueError:
                return None
    return None


class Command(BaseCommand):
    help = (
        "H30 (S73) -- extractor real de las subcarpetas ENTREGA "
        "FUNCIONES RECURSO PREVENTIVO y FIRMADOS: crea "
        "DocumentAcknowledgment (persona + tipo documental + fecha). "
        "Dry-run por defecto, --apply para escribir de verdad."
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
            parent_path__icontains="RECURSO PREVENTIVO",
            entry_kind=DocumentIndexEntry.KIND_FILE,
            deleted_at__isnull=True,
            purged_at__isnull=True,
            name__iregex=r"\.docx?$",
        ).exclude(
            parent_path="DOC. PERSONAL/NOMBRAMIENTO RECURSO PREVENTIVO",
        ).order_by("parent_path", "name")

        entries = list(qs.only(
            "id", "bucket", "blob_name", "parent_path", "name", "document_type_id",
        ))
        if limit:
            entries = entries[:limit]

        self.stdout.write(self.style.MIGRATE_HEADING(
            "=== %d documento(s) en alcance (%s) ==="
            % (len(entries), "APLICANDO" if apply_changes else "DRY-RUN")
        ))

        totals = {
            "procesados": 0, "sin_persona": 0, "sin_fecha": 0,
            "documentos_completos": 0, "acknowledgments_creados": 0,
            "fallos_lectura": 0,
        }

        for entry in entries:
            data = download_bytes(entry.bucket, entry.blob_name)
            try:
                text = _extract_text(data)
            except Exception as exc:
                self.stdout.write("FALLO lectura: %s -- %s" % (entry.name, exc))
                totals["fallos_lectura"] += 1
                continue

            totals["procesados"] += 1
            dni = _parse_person(text)
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

            fecha = _parse_fecha(text)
            if not fecha:
                self.stdout.write("SIN FECHA reconocible: %s" % entry.name)
                totals["sin_fecha"] += 1
                continue

            if not apply_changes:
                self.stdout.write(
                    "OK (dry-run): %s -> persona=%s (pk=%d) tipo=%s fecha=%s"
                    % (entry.name, person, person.pk, entry.document_type.code, fecha.isoformat())
                )
                totals["documentos_completos"] += 1
                totals["acknowledgments_creados"] += 1
                continue

            _, created = DocumentAcknowledgment.objects.get_or_create(
                person=person, document_type=entry.document_type,
                delivery_date=fecha,
                defaults={"extraction_method": DocumentAcknowledgment.METHOD_HEURISTIC},
            )
            if created:
                totals["acknowledgments_creados"] += 1

            person_ct = ContentType.objects.get_for_model(PersonIdentity)
            entry.domain_content_type = person_ct
            entry.domain_object_id = person.pk
            entry.save(update_fields=["domain_content_type", "domain_object_id"])
            totals["documentos_completos"] += 1
            if trash_dossier_entry(entry):
                self.stdout.write(
                    "COMPLETO: %s -> %s (pk=%d) tipo=%s fecha=%s creada=%s, "
                    "original a papelera"
                    % (entry.name, person, person.pk, entry.document_type.code, fecha.isoformat(), created)
                )
            else:
                self.stdout.write(
                    "COMPLETO (aviso: no se pudo enviar a papelera): %s"
                    % entry.name
                )

        self.stdout.write(self.style.MIGRATE_HEADING("=== RESUMEN ==="))
        for key, value in totals.items():
            self.stdout.write("    %s: %d" % (key, value))
