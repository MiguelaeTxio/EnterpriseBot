# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/management/commands/fix_contract_periods_s127.py
"""
H30 (S127). Retype and redate the contracts/altas behind the remaining
"contract missing" notices, after reading them page by page.

---

H30 (S127). Corrige tipo y fecha de los contratos y altas que dejaban
avisos de contrato del periodo actual sin resolver. Cada uno abierto y
leído entero en la sesión (relevo gcs_image):

- Díaz Quintero: el "contrato" es la carta de SUBROGACIÓN de Grualdi a
  Grúas Adolfo Álvarez con efectos 01/11/2008, fechada 31/10/2008 (la BD
  tenía 2007-05-01).
- Zafra, Núñez, Correa, Graña: el "contrato" es la CONVERSIÓN a
  indefinido; su fecha útil es la de celebración del temporal original
  (01/06/2007, 02/12/2019, 07/09/2021 y 08/01/2021), que casa con su alta.
- Ramos Zambrana: el "contrato" 37085 es la resolución de ALTA TA2/R del
  01/01/2007, y el "alta" 37277 (BD 2010-02-12) es otra copia de ella.
- Hidalgo: sus "altas" de 2021/2022 son informes del INSS de PRESTACIÓN
  por nacimiento (transmitidos el 30/12/2020 y el 04/01/2021).

Mismo camino que el H28 (`file_entry_manually`: tipo, nombre canónico en
su carpeta) y después `issue_date`, que es lo que miran los periodos.
Sin --apply solo informa; idempotente.
"""
from datetime import date

from django.core.management.base import BaseCommand

from document_explorer.classification_service import file_entry_manually
from document_explorer.models import DocumentIndexEntry, PersonIdentity

FIXES = [
    # (pk, persona, tipo, fecha)
    (35077, 3, "SUBROGACION_CONTRATO", "2008-10-31"),
    (38036, 192, "CONVERSION_CONTRATO", "2007-06-01"),
    (28580, 30, "CONVERSION_CONTRATO", "2019-12-02"),
    (39305, 198, "CONVERSION_CONTRATO", "2021-09-07"),
    (28261, 15, "CONVERSION_CONTRATO", "2021-01-08"),
    (37085, 175, "ALTA", "2007-01-01"),
    (37277, 175, "ALTA", "2007-01-01"),
    (35961, 165, "PRESTACION_NACIMIENTO", "2020-12-30"),
    (35960, 165, "PRESTACION_NACIMIENTO", "2021-01-04"),
    (38512, 165, "PRESTACION_NACIMIENTO", "2021-01-04"),
]


class Command(BaseCommand):
    help = "S127: tipo y fecha de contratos y altas revisados. Sin --apply informa."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")

    def handle(self, *args, **options):
        apply = options["apply"]
        self.stdout.write("# [S127] Contratos y altas -- %s" % (
            "APLICANDO" if apply else "MODO PRUEBA (sin --apply)"))
        people = {p.pk: p for p in PersonIdentity.objects.filter(
            pk__in={row[1] for row in FIXES})}
        for pk, person_pk, code, date_text in FIXES:
            entry = DocumentIndexEntry.objects.filter(
                pk=pk, deleted_at__isnull=True, purged_at__isnull=True,
            ).select_related("document_type").first()
            if entry is None or person_pk not in people:
                self.stdout.write("   - pk=%s [SALTADO]" % pk)
                continue
            before = "%s %s %s" % (
                entry.document_type.code if entry.document_type else "-",
                entry.issue_date, entry.name,
            )
            outcome = file_entry_manually(
                entry, people[person_pk], code, date_text,
                apply_changes=apply,
            )
            if outcome["reason"]:
                self.stdout.write("   - pk=%s [SALTADO] %s" % (
                    pk, outcome["reason"]))
                continue
            if apply:
                entry.issue_date = date.fromisoformat(date_text)
                entry.save(update_fields=["issue_date"])
            self.stdout.write("   - pk=%s %s -> %s %s %s" % (
                pk, before, code, date_text, outcome["new_name"]))
        self.stdout.write("# [S127] Fin.")
