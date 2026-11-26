# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/management/commands/fix_logbook_swapped.py
"""
Fix logbook repair rows with "type" and "concept" swapped.

---

S163 (26/11): reparaciones del libro historial leídas con «Tipo» y
«Concepto» cambiados de sitio (fleet.logbook_service.fix_swapped_repair).
Sin --apply solo las cuenta y enseña. Pantalla y --log-file a la vez.
"""
from datetime import datetime

from django.core.management.base import BaseCommand
from django.db import transaction

from fleet.logbook_service import _fault_labels, fix_swapped_repair
from fleet.models import MachineLogbookEntry


class Command(BaseCommand):
    """Fix swapped logbook rows. --- Corrige filas cambiadas."""

    help = "Corrige Tipo/Concepto cambiados en reparaciones del libro."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--log-file", default="")

    def _log(self, text):
        line = "[%s] %s" % (datetime.now().strftime("%H:%M:%S"), text)
        print(line, flush=True)
        if self.log:
            self.log.write(line + "\n")
            self.log.flush()

    def handle(self, *args, **options):
        self.log = (open(options["log_file"], "a", encoding="utf-8")
                    if options["log_file"] else None)
        labels = _fault_labels()
        rows = MachineLogbookEntry.objects.filter(
            section=MachineLogbookEntry.SECTION_REPAIR,
            signed_at__isnull=True,
        ).select_related("machine")
        fixed = []
        for row in rows.iterator():
            values = {"entry_type": row.entry_type, "concept": row.concept}
            if fix_swapped_repair(row.section, values, labels):
                fixed.append((row, values))
        self._log("Modo: %s · filas a corregir: %d" % (
            "APLICAR" if options["apply"] else "solo mirar", len(fixed)))
        by_machine = {}
        for row, _values in fixed:
            by_machine[row.machine.code] = by_machine.get(
                row.machine.code, 0) + 1
        for code, count in sorted(by_machine.items()):
            self._log("  %s: %d" % (code, count))
        for row, values in fixed[:5]:
            self._log("  ej. #%d: tipo «%s» / concepto «%s»" % (
                row.pk, values["entry_type"], values["concept"][:60]))
        if options["apply"]:
            with transaction.atomic():
                for row, values in fixed:
                    row.entry_type = values["entry_type"]
                    row.concept = values["concept"]
                    row.save(update_fields=["entry_type", "concept"])
            self._log("Corregidas: %d" % len(fixed))
        self._log("Fin.")
