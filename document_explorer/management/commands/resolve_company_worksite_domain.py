# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/management/commands/resolve_company_worksite_domain.py
"""
H30 (S58) -- puebla `CompanyWorksite` real y vincula el dominio de
tipos documentales COMPANY (empieza por PAGO_CORRIENTE) a esa tabla,
en vez de a `PersonIdentity`.

Decision explicita de Miguel Angel (S58): el vinculo de este tipo
documental es SIEMPRE por empresa/obra, nunca por persona, ni siquiera
en el caso real minoritario donde el documento sí llevaba el nombre de
un unico trabajador (alta suelta sobre una relacion ya enviada). Por
eso este comando reemplaza CUALQUIER `domain_content_type`/
`domain_object_id` previo de las entradas que toca -- incluidos los
274 `PAGO_CORRIENTE` que el bloque anterior de esta misma sesion
(`resolve_domain_pending_types`) habia vinculado a `PersonIdentity`.

Deteccion de empresa/obra, dos niveles de prioridad, verificados
contra datos reales de S58 (EnterpriseBot_004/005_GET.txt):

1. Bajo `DOC. PERSONAL/DECLARACION AL CORRIENTE/DECLARACION POR
   OBRAS/{empresa}/{obra}/...` -- segmento real de carpeta tal cual
   (1.660 de 1.762 archivos reales de PAGO_CORRIENTE en S58).
2. Sin carpeta de obra (102 archivos reales en S58, confirmados por
   Miguel Angel para dejar en su sitio, solo asignarles empresa): la
   empresa va marcada en el propio nombre de archivo -- "(GR)" o
   "GRUAS ALVAREZ" para Grúas Álvarez, "(TR)" o "TRANSGRUAL" para
   Transgrual, mismo marcador que ya usan decenas de archivos reales
   del propio árbol. Si aparecen los dos marcadores a la vez, o
   ninguno, la entrada se deja `SIN RESOLVER` -- nunca se adivina,
   mismo criterio de unicidad estricta que el resto de resolutores de
   H30 (`_resolve_person_by_name`, `_resolve_person_by_sliding_
   window`).

DRY-RUN POR DEFECTO. Con `--apply` escribe de verdad
(`CompanyWorksite.objects.get_or_create()` +
`domain_content_type`/`domain_object_id`). Nunca toca `document_type`
ni GCS (4.12).
"""
import re

from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand

from document_explorer.management.commands.calibrate_fase_a_keywords import (
    BUCKET, _strip_accents,
)
from document_explorer.models import (
    CompanyWorksite, DocumentIndexEntry,
)

OBRAS_PREFIX = "DOC. PERSONAL/DECLARACION AL CORRIENTE/DECLARACION POR OBRAS/"

_GR_MARKER_RE = re.compile(r"\(GR\)|GRUAS ALVAREZ")
_TR_MARKER_RE = re.compile(r"\(TR\)|TRANSGRUAL")

DEFAULT_TYPES = ["PAGO_CORRIENTE"]


def _detect_company_worksite(entry):
    """Ver docstring del módulo para el criterio completo. Devuelve
    (company, worksite) o (None, None) si no se puede resolver sin
    adivinar."""
    if entry.parent_path.startswith(OBRAS_PREFIX):
        rest = entry.parent_path[len(OBRAS_PREFIX):]
        parts = [p for p in rest.split("/") if p]
        if not parts:
            return None, None
        company = parts[0]
        worksite = parts[1] if len(parts) > 1 else ""
        return company, worksite

    name_upper = _strip_accents(entry.name).upper()
    is_gr = bool(_GR_MARKER_RE.search(name_upper))
    is_tr = bool(_TR_MARKER_RE.search(name_upper))
    if is_gr and not is_tr:
        return "GRUAS", ""
    if is_tr and not is_gr:
        return "TRANSGRUAL", ""
    return None, None


class Command(BaseCommand):
    help = (
        "H30 (S58) -- puebla CompanyWorksite real y vincula el "
        "dominio COMPANY de PAGO_CORRIENTE (reemplaza cualquier "
        "vinculo previo, incluido el de PersonIdentity). Dry-run por "
        "defecto, usar --apply."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply", action="store_true",
            help="Escribe de verdad. Sin esta flag, solo informa.",
        )
        parser.add_argument(
            "--types", nargs="+", default=DEFAULT_TYPES,
            help=(
                "Codigos de DocumentTypeCatalog de dominio COMPANY a "
                "procesar (por defecto, PAGO_CORRIENTE)."
            ),
        )

    def handle(self, *args, **options):
        apply_changes = options["apply"]
        types = options["types"]
        company_ct = ContentType.objects.get_for_model(CompanyWorksite)
        cache = {}

        totals = {
            "total": 0, "resueltos": 0, "sin_resolver": 0,
            "filas_nuevas": 0,
        }

        for code in types:
            entries = list(
                DocumentIndexEntry.objects.filter(
                    bucket=BUCKET,
                    entry_kind=DocumentIndexEntry.KIND_FILE,
                    document_type__code=code,
                    deleted_at__isnull=True, purged_at__isnull=True,
                ).only(
                    "id", "name", "parent_path",
                    "domain_content_type", "domain_object_id",
                )
            )
            self.stdout.write(
                "--- %s: %d archivos ---" % (code, len(entries))
            )

            for entry in entries:
                totals["total"] += 1
                company, worksite = _detect_company_worksite(entry)

                if company is None:
                    totals["sin_resolver"] += 1
                    self.stdout.write(
                        "SIN RESOLVER [%s] %s"
                        % (entry.parent_path, entry.name)
                    )
                    continue

                key = (company, worksite)
                if key not in cache:
                    if apply_changes:
                        obj, created = CompanyWorksite.objects.get_or_create(
                            company=company, worksite=worksite,
                        )
                        if created:
                            totals["filas_nuevas"] += 1
                        cache[key] = obj
                    else:
                        if not CompanyWorksite.objects.filter(
                            company=company, worksite=worksite,
                        ).exists():
                            totals["filas_nuevas"] += 1
                        cache[key] = None

                totals["resueltos"] += 1
                self.stdout.write(
                    "RESUELTO [%s] %s -> %s / %s"
                    % (
                        entry.parent_path, entry.name, company,
                        worksite or "(sin obra)",
                    )
                )
                if apply_changes:
                    obj = cache[key]
                    entry.domain_content_type = company_ct
                    entry.domain_object_id = obj.pk
                    entry.save(update_fields=[
                        "domain_content_type", "domain_object_id",
                    ])

        self.stdout.write("=== RESUMEN (%s) ===" % (
            "APLICADO" if apply_changes else "DRY-RUN, nada escrito"
        ))
        for key, value in totals.items():
            self.stdout.write("    %s: %d" % (key, value))
