# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/management/commands/run_fase_b0_filename_dates.py
"""
H30 (S48) -- Fase B0: extracción de fecha por heurística de NOMBRE de
archivo, para los tipos `tracks_expiry=True` que ya tienen
`document_type`/`domain_object` resueltos por la Fase A pero todavía
sin `expiry_date`/`issue_date`. Precede siempre al OCR (Fase B1) --
gratis, sin abrir el documento, mismo principio de coste que el resto
del hito.

Criterios confirmados por Miguel Ángel con datos reales (S48), nunca
generalizados sin evidencia -- ver anexo H30, sección "COMPLETADAS EN
S48":

- `ITV`, `OCA`, `CARNET_CONDUCIR`: fecha unica en el nombre = fecha de
  CADUCIDAD (`expiry_date`). Confirmado con muestras reales donde la
  misma maquina/persona tiene varias fechas futuras a lo largo de los
  años (renovacion periodica).
- `PERMISO_CIRCULACION`, `FORMACION`: fecha unica en el nombre = fecha
  de EMISION (`issue_date`). Confirmado con muestras reales sin
  repeticion de fecha para el mismo sujeto (no hay patron de
  renovacion visible).
- `EXCEDENCIA`: sin patron de fecha en el nombre verificado (0/2
  muestras) -- va integramente por OCR (Fase B1), este comando no lo
  toca.
- Cualquier otro tipo `tracks_expiry=True` no listado aqui (`SEGURO`,
  `TACOGRAFO`, `CONTRATO`, `AUTORIZACION_USO_MAQUINARIA`) tampoco se
  toca -- sin verificar con datos reales todavia, queda para Fase B1
  o una calibracion futura.

DRY-RUN POR DEFECTO. Sin `--apply`, solo informa. Con `--apply`,
escribe `expiry_date`/`issue_date` de verdad.
"""
import re
from datetime import date

from django.core.management.base import BaseCommand

from document_explorer.models import DocumentIndexEntry

BUCKET = "cgs_grupo_alvarez"

# code -> campo destino ("expiry" o "issue"), confirmado con datos
# reales en S48. EXCEDENCIA deliberadamente ausente -- va por OCR.
FIELD_BY_CODE = {
    "ITV": "expiry",
    "OCA": "expiry",
    "CARNET_CONDUCIR": "expiry",
    "PERMISO_CIRCULACION": "issue",
    "FORMACION": "issue",
}

_DATE_RE = re.compile(r"(\d{1,2})[-./](\d{1,2})[-./](\d{2,4})")


def _parse_date(day_s, month_s, year_s):
    try:
        day, month = int(day_s), int(month_s)
        year = int(year_s)
    except ValueError:
        return None
    if year < 100:
        year += 2000
    if not (1 <= day <= 31 and 1 <= month <= 12 and 1900 <= year <= 2100):
        return None
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _extract_date(name):
    """
    Devuelve la ÚLTIMA fecha valida encontrada en el nombre -- por
    convencion real observada en el corpus, la fecha va al final del
    nombre, justo antes de la extension; cuando hay mas de un numero
    con forma de fecha, el ultimo es el fiable (el primero suele ser
    parte de un codigo de maquina/matricula).
    """
    matches = list(_DATE_RE.finditer(name))
    for match in reversed(matches):
        parsed = _parse_date(*match.groups())
        if parsed:
            return parsed
    return None


class Command(BaseCommand):
    help = (
        "H30 (S48) -- Fase B0: fecha por heuristica de nombre para "
        "ITV/OCA/CARNET_CONDUCIR/PERMISO_CIRCULACION/FORMACION. "
        "Dry-run por defecto, usar --apply para escribir de verdad."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply", action="store_true",
            help="Escribe de verdad. Sin esta flag, solo informa.",
        )

    def handle(self, *args, **options):
        apply_changes = options["apply"]
        stats = {"con_fecha": 0, "sin_fecha_en_nombre": 0}

        qs = DocumentIndexEntry.objects.filter(
            bucket=BUCKET, entry_kind=DocumentIndexEntry.KIND_FILE,
            deleted_at__isnull=True, purged_at__isnull=True,
            document_type__code__in=list(FIELD_BY_CODE),
            expiry_date__isnull=True, issue_date__isnull=True,
            domain_object_id__isnull=False,
        ).select_related("document_type")

        for entry in qs:
            code = entry.document_type.code
            field = FIELD_BY_CODE[code]
            found = _extract_date(entry.name)

            if not found:
                stats["sin_fecha_en_nombre"] += 1
                continue

            stats["con_fecha"] += 1
            self.stdout.write(
                "%s -> %s=%s  [%s] %s"
                % (code, field, found.isoformat(),
                   entry.parent_path, entry.name)
            )
            if apply_changes:
                if field == "expiry":
                    entry.expiry_date = found
                    entry.save(update_fields=["expiry_date"])
                else:
                    entry.issue_date = found
                    entry.save(update_fields=["issue_date"])

        self.stdout.write("=== RESUMEN (%s) ===" % (
            "APLICADO" if apply_changes else "DRY-RUN, nada escrito"
        ))
        for key, value in stats.items():
            self.stdout.write("    %s: %d" % (key, value))
