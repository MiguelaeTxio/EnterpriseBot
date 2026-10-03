# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/management/commands/fix_review_names_s127.py
"""
H30 (S127). Rename what was filed this session with an invented date.

---

H30 (S127). Corrige los nombres de lo archivado hoy en la revisión de
NO CONFORMES sin fecha legible: llevaban la fecha de subida a GCS
(`_20260724`), que se confundía con la del documento. Con el cambio de
`_resolve_date` (ae4afb15) se vuelven a archivar en su mismo sitio y
salen `_SINFECHA`. Y una fecha mal leída por Gemini: el justificante de
cita de Miguel Ángel es del 20/08/2026 (manuscrito "20/8/26"), no del
20/05/2020.

Sin --apply solo informa; idempotente (renombra al mismo destino).
"""
from django.core.management.base import BaseCommand

from document_explorer.classification_service import (
    _apply_company_classification, file_entry_manually,
)
from document_explorer.models import DocumentIndexEntry, PersonIdentity

# pk -> tipo (empresa, sin fecha legible).
COMPANY = {
    24642: "LISTADO_EXAMEN_OFICIAL", 24643: "LISTADO_EXAMEN_OFICIAL",
    24669: "LISTADO_EXAMEN_OFICIAL", 24800: "LISTADO_EXAMEN_OFICIAL",
    24825: "LISTADO_EXAMEN_OFICIAL", 24839: "LISTADO_EXAMEN_OFICIAL",
    24844: "LISTADO_EXAMEN_OFICIAL", 24845: "LISTADO_EXAMEN_OFICIAL",
    24864: "LISTADO_EXAMEN_OFICIAL", 24865: "LISTADO_EXAMEN_OFICIAL",
    35719: "MATERIAL_FORMACION",
}

# pk -> (persona, tipo, fecha).
PERSONAL = [
    (37953, 190, "CERTIFICADO_MATRIMONIO", ""),
    (35051, 3, "INFORME_MEDICO", ""),
    (40280, 191, "CERTIFICADO_BANCARIO", ""),
    (38572, 194, "FORMACION", ""),
    (36621, 250, "JUSTIFICANTE_LABORAL_AUSENCIA", "2026-08-20"),
]


def _live(pk):
    return DocumentIndexEntry.objects.filter(
        pk=pk, entry_kind=DocumentIndexEntry.KIND_FILE,
        deleted_at__isnull=True, purged_at__isnull=True,
    ).first()


class Command(BaseCommand):
    help = "S127: corrige nombres con fecha inventada. Sin --apply informa."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")

    def handle(self, *args, **options):
        apply = options["apply"]
        self.stdout.write("# [S127] Nombres -- %s" % (
            "APLICANDO" if apply else "MODO PRUEBA (sin --apply)"))
        for pk, code in COMPANY.items():
            entry = _live(pk)
            if entry is None:
                continue
            before = entry.name
            if apply:
                outcome = _apply_company_classification(
                    entry, {"document_type_code": code, "date_hint": ""},
                )
                after = outcome.get("new_name")
            else:
                after = "(%s_SINFECHA)" % code
            self.stdout.write("   - pk=%s %s -> %s" % (pk, before, after))
        people = {p.pk: p for p in PersonIdentity.objects.filter(
            pk__in={row[1] for row in PERSONAL})}
        for pk, person_pk, code, date_hint in PERSONAL:
            entry = _live(pk)
            if entry is None or person_pk not in people:
                continue
            before = entry.name
            outcome = file_entry_manually(
                entry, people[person_pk], code, date_hint,
                apply_changes=apply,
            )
            self.stdout.write("   - pk=%s %s -> %s" % (
                pk, before, outcome["new_name"] or outcome["reason"]))
        self.stdout.write("# [S127] Fin.")
