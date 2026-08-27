# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/management/commands/extract_botiquines_deliveries.py
"""
H30 (S73). Extractor real de Botiquines -- punto 2 de la hoja de ruta
de S73. Crea filas reales de `EpiDelivery` (epi=BOTIQUIN) a partir
del contenido real de los 14 .docx de `DOC. PERSONAL/ENTREGA
EPIS/BOTIQUINES` (texto nativo, nunca OCR -- mismo criterio que
extract_epis_deliveries.py).

Plantilla real (muestreo S73, 3/14 leídos, mismo patrón en los tres):
tabla 0 con 3 filas -- "DATOS DEL TRABAJADOR:", "D. <NOMBRE>  DNI.
<digitos>-<letra>" en una sola celda, "MÁQUINA:\n<codigo(s)>" en otra
celda; tabla 1 con la firma y "A fecha (DD/MM/AAAA)".

Persona: SIEMPRE por DNI real (dígitos + letra de control CALCULADA,
nunca la transcrita -- mismo criterio de toda la plataforma). Fecha:
del pie de firma real del documento (este formato no trae fecha en
el nombre de archivo, a diferencia de EPIS genérico).

Máquina -- decisión real de Miguel Ángel (S73): "MÁQUINA:" puede
traer VARIOS códigos separados por coma/"y" en un mismo documento
(hasta 12 en un caso real) -- se crea UNA `EpiDelivery` por máquina
(misma persona/botiquín/fecha, `destination_machine` distinto en cada
fila). Dos casos especiales confirmados con datos reales de BD:
"FURGONETA <matrícula>" (vehículo real, resuelto por matrícula sin
guion) y "TALLER" a secas (sin más contexto -> siempre
`EMPRESA_TALLER_MECANICO`, decisión explícita de Miguel Ángel, nunca
Huelva ni Elevación salvo que el documento lo diga explícitamente).

Resolución de código de máquina: NUNCA reinventar el normalizador --
se reutiliza `_resolve_machine_asset` real de
`work_order_processor.services` (regla D4, zero-padding G-8/G-08,
variantes con/sin guion, ya probado en producción), en vez de
duplicar lógica de padding ad-hoc.

Documento original: SOLO se manda a papelera cuando TODAS las
máquinas del documento resolvieron sin fallo (mismo criterio "todo o
nada" que extract_epis_deliveries.py) -- si una sola máquina no
resuelve, el documento completo queda PARCIAL, original intacto,
reportado para revisión manual, ninguna EpiDelivery a medias.

DRY-RUN POR DEFECTO. --apply escribe de verdad.
"""
import io
import re
import unicodedata

from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand

from document_explorer.classification_service import trash_dossier_entry
from document_explorer.models import (
    DocumentIndexEntry, EpiDelivery, EpiItemCatalog, PersonIdentity,
)
from spare_parts.gcs_service import download_bytes
from work_order_processor.services import _resolve_machine_asset

_DNI_DIGITS_RE = re.compile(
    r"DNI\.?\s*[:.]?\s*([0-9]{1,2}[.\s]?[0-9]{3}[.\s]?[0-9]{3})"
)
_DNI_LETTER_TABLE = "TRWAGMYFPDXBNJZSQVHLCKE"
_NAME_RE = re.compile(
    r"D\.?\s*([A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑ\s.]+?)\s+DNI\.?\s*[:.]?\s*[0-9]"
)
_FECHA_RE = re.compile(
    r"fecha\s*\(([0-9]{1,2})/([0-9]{1,2})/([0-9]{2,4})\)",
    re.IGNORECASE,
)
_TALLER_MECANICO_CODE = "EMPRESA_TALLER_MECANICO"
_FURGONETA_PLATE_RE = re.compile(r"([0-9]{4})[\s\-]?([A-Za-zÑñ]{3})")
_MACHINE_TOKEN_SPLIT_RE = re.compile(r",|\s+[yY]\s+")


def _strip_accents(text):
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(c for c in normalized if not unicodedata.combining(c))


def _compute_full_dni(digits):
    """Dígitos reales + letra de control CALCULADA (nunca la
    transcrita a mano en el formulario)."""
    clean = re.sub(r"[.\s]", "", digits)
    if not clean.isdigit():
        return None
    return clean + _DNI_LETTER_TABLE[int(clean) % 23]


def _normalize_dni(dni):
    return re.sub(r"[.\s\-]", "", dni).upper()


def _extract_docx(data):
    import docx
    doc = docx.Document(io.BytesIO(data))
    rows = []
    for table in doc.tables:
        for row in table.rows:
            rows.append([c.text.strip() for c in row.cells])
    return rows


def _find_cell(rows, prefix):
    prefix_norm = _strip_accents(prefix).upper()
    for row in rows:
        for cell in row:
            if _strip_accents(cell).upper().startswith(prefix_norm):
                return cell
    return None


def _parse_person(rows):
    # Se busca explícitamente la celda que contenga DNI, no basta con
    # localizar la que empieza por "D." (falso positivo con la fila
    # de cabecera "DATOS DEL TRABAJADOR:").
    trabajador_cell = None
    for row in rows:
        for cell in row:
            if "DNI" in cell.upper() and cell.upper().strip().startswith("D."):
                trabajador_cell = cell
                break
        if trabajador_cell:
            break
    if not trabajador_cell:
        return None, None
    dni_match = _DNI_DIGITS_RE.search(trabajador_cell)
    dni = _compute_full_dni(dni_match.group(1)) if dni_match else None
    name_match = _NAME_RE.search(trabajador_cell)
    name = name_match.group(1).strip() if name_match else None
    return name, dni


def _parse_fecha(rows):
    for row in rows:
        for cell in row:
            m = _FECHA_RE.search(cell)
            if m:
                day, month, year = m.groups()
                year = int(year)
                if year < 100:
                    year += 2000
                import datetime
                try:
                    return datetime.date(year, int(month), int(day))
                except ValueError:
                    return None
    return None


def _parse_machine_tokens(rows):
    maquina_cell = _find_cell(rows, "MÁQUINA") or _find_cell(rows, "MAQUINA")
    if not maquina_cell:
        return None
    _, _, resto = maquina_cell.partition(":")
    resto = resto.strip() if resto else maquina_cell.strip()
    tokens = [
        t.strip() for t in _MACHINE_TOKEN_SPLIT_RE.split(resto) if t.strip()
    ]
    return tokens


def _resolve_token(token):
    """Devuelve (MachineAsset|None, motivo_si_falla)."""
    token_norm = _strip_accents(token).upper().strip()

    if token_norm == "TALLER":
        asset = MachineAssetLookup.get(_TALLER_MECANICO_CODE)
        return asset, None if asset else "EMPRESA_TALLER_MECANICO no existe"

    if token_norm.startswith("FURGONETA"):
        m = _FURGONETA_PLATE_RE.search(token_norm)
        if not m:
            return None, "FURGONETA sin matrícula reconocible: %r" % token
        plate = (m.group(1) + m.group(2)).upper()
        asset = _resolve_machine_asset(plate)
        return asset, None if asset else "matrícula %r sin resolver" % plate

    asset = _resolve_machine_asset(token_norm)
    return asset, None if asset else "código %r sin resolver" % token


class MachineAssetLookup:
    """Cache mínima para EMPRESA_TALLER_MECANICO (una sola fila fija,
    no tiene sentido consultarla por cada token)."""
    _cache = {}

    @classmethod
    def get(cls, code):
        if code not in cls._cache:
            from fleet.models import MachineAsset
            cls._cache[code] = MachineAsset.objects.filter(
                code=code,
            ).first()
        return cls._cache[code]


class Command(BaseCommand):
    help = (
        "H30 (S73) -- extractor real de Botiquines: crea EpiDelivery "
        "(epi=BOTIQUIN, una fila por máquina) a partir del contenido "
        "real de los .docx de BOTIQUINES. Dry-run por defecto, "
        "--apply para escribir de verdad."
    )

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--limit", type=int, default=None)

    def handle(self, *args, **options):
        apply_changes = options["apply"]
        limit = options["limit"]

        qs = DocumentIndexEntry.objects.filter(
            bucket="cgs_grupo_alvarez",
            parent_path__icontains="BOTIQUINES",
            entry_kind=DocumentIndexEntry.KIND_FILE,
            deleted_at__isnull=True,
            purged_at__isnull=True,
            name__iregex=r"\.(docx?)$",
        ).order_by("name")

        entries = list(qs.only("id", "bucket", "blob_name", "parent_path", "name"))
        if limit:
            entries = entries[:limit]

        self.stdout.write(self.style.MIGRATE_HEADING(
            "=== %d documento(s) en alcance (%s) ==="
            % (len(entries), "APLICANDO" if apply_changes else "DRY-RUN")
        ))

        try:
            botiquin_item = EpiItemCatalog.objects.get(code="BOTIQUIN")
        except EpiItemCatalog.DoesNotExist:
            self.stdout.write(self.style.ERROR(
                "FALLO: no existe EpiItemCatalog(code='BOTIQUIN')."
            ))
            return

        totals = {
            "procesados": 0, "sin_persona": 0, "sin_fecha": 0,
            "sin_maquinas": 0, "documentos_completos": 0,
            "documentos_parciales": 0, "deliveries_creadas": 0,
            "fallos_lectura": 0,
        }

        for entry in entries:
            data = download_bytes(entry.bucket, entry.blob_name)
            try:
                rows = _extract_docx(data)
            except Exception as exc:
                self.stdout.write(
                    "FALLO lectura: %s/%s -- %s"
                    % (entry.parent_path, entry.name, exc)
                )
                totals["fallos_lectura"] += 1
                continue

            totals["procesados"] += 1
            name, dni = _parse_person(rows)

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

            date = _parse_fecha(rows)
            if not date:
                self.stdout.write(
                    "SIN FECHA reconocible: %s/%s"
                    % (entry.parent_path, entry.name)
                )
                totals["sin_fecha"] += 1
                continue

            tokens = _parse_machine_tokens(rows)
            if not tokens:
                self.stdout.write(
                    "SIN CELDA MÁQUINA: %s/%s"
                    % (entry.parent_path, entry.name)
                )
                totals["sin_maquinas"] += 1
                continue

            resolved = []
            fallos = []
            for token in tokens:
                asset, motivo = _resolve_token(token)
                if asset is not None:
                    resolved.append((token, asset))
                else:
                    fallos.append((token, motivo))

            if fallos:
                self.stdout.write(
                    "PARCIAL: %s -> persona=%s (pk=%d) fecha=%s -- "
                    "%d/%d máquinas resueltas, sin tocar original. "
                    "Fallos: %s"
                    % (
                        entry.name, person, person.pk, date.isoformat(),
                        len(resolved), len(tokens),
                        "; ".join(
                            "%r (%s)" % (t, m) for t, m in fallos
                        ),
                    )
                )
                totals["documentos_parciales"] += 1
                continue

            if not apply_changes:
                self.stdout.write(
                    "OK (dry-run): %s -> persona=%s (pk=%d) fecha=%s "
                    "maquinas=%s"
                    % (
                        entry.name, person, person.pk, date.isoformat(),
                        [a.code for _, a in resolved],
                    )
                )
                totals["documentos_completos"] += 1
                totals["deliveries_creadas"] += len(resolved)
                continue

            new_rows_this_doc = 0
            for token, asset in resolved:
                _, was_created = EpiDelivery.objects.get_or_create(
                    person=person, epi=botiquin_item,
                    delivery_date=date, destination_machine=asset,
                    defaults={
                        "source_entry": entry,
                        "extraction_method": EpiDelivery.METHOD_HEURISTIC,
                    },
                )
                if was_created:
                    new_rows_this_doc += 1

            totals["deliveries_creadas"] += new_rows_this_doc
            totals["documentos_completos"] += 1
            person_ct = ContentType.objects.get_for_model(PersonIdentity)
            entry.domain_content_type = person_ct
            entry.domain_object_id = person.pk
            entry.save(update_fields=[
                "domain_content_type", "domain_object_id",
            ])
            if trash_dossier_entry(entry):
                self.stdout.write(
                    "COMPLETO: %s -> %s (pk=%d), %d entregas "
                    "(%d nuevas), original a papelera"
                    % (
                        entry.name, person, person.pk,
                        len(resolved), new_rows_this_doc,
                    )
                )
            else:
                self.stdout.write(
                    "COMPLETO (aviso: no se pudo enviar a "
                    "papelera): %s" % entry.name
                )

        self.stdout.write(self.style.MIGRATE_HEADING("=== RESUMEN ==="))
        for key, value in totals.items():
            self.stdout.write("    %s: %d" % (key, value))
