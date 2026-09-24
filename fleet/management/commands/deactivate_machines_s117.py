# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/fleet/management/commands/deactivate_machines_s117.py
"""
H30 (S117), punto 1 de la hoja de ruta (máquinas activas) -- pone
INACTIVAS las máquinas que ya no son de la empresa, con dos reglas
dictadas por Miguel Ángel:

1. Familias A (grúas móviles) y B (camiones brazo): "vamos a coger las
   que no estén en el Excel de eso, de esas dos familias las ponemos
   como inactivas directamente" -- código A<n>/B<n> que NO está en la
   hoja MAQUINARIA de document_explorer/data_imports/
   EXCEL_TRABAJADORES.xlsx (37 códigos reales, "A-29 ", "B-12"...,
   normalizados sin guion ni espacios).
2. Cualquier máquina con documentos en una carpeta "BAJA DEFINITIVA":
   "un comando de gestión que ponga ahora mismo en inactivas todas las
   máquinas que tengan documentos en baja definitiva".

3. Máquinas del Excel marcadas "BAJA" en su columna de notas (B-20) --
   decisión de Miguel Ángel tras el dry-run EnterpriseBot_024: "inactiva".
4. Máquinas con documentos en carpetas "(VENTA)", "(VENDIDA)" o "BAJA
   TEMPORAL" -- misma decisión: "inactivas".

Nunca reactiva nada. DRY-RUN por defecto; --apply escribe is_active.
Log propio (com-standards 0bis/0ter).
"""
import re
from datetime import datetime
from pathlib import Path

import openpyxl
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand
from django.db.models import Q

from document_explorer.models import DocumentIndexEntry
from fleet.models import MachineAsset

EXCEL_PATH = Path(settings.BASE_DIR) / "document_explorer" / "data_imports" / "EXCEL_TRABAJADORES.xlsx"
FAMILY_RE = re.compile(r"^[AB]\d+$")


def _norm(code):
    return re.sub(r"[\s\-.]", "", str(code or "")).upper()


class Command(BaseCommand):
    help = (
        "H30 (S117) -- pone inactivas las maquinas A/B fuera del Excel y "
        "las que tienen documentos en BAJA DEFINITIVA. Dry-run por defecto."
    )

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--log-file", required=True)

    def _log(self, message):
        line = "[%s] %s" % (datetime.now().strftime("%H:%M:%S"), message)
        print(line, flush=True)
        self._log_handle.write(line + "\n")
        self._log_handle.flush()

    def handle(self, *args, **options):
        self._log_handle = open(options["log_file"], "a", encoding="utf-8")
        try:
            self._run(options["apply"])
        finally:
            self._log_handle.close()

    def _machines_with_docs_in(self, machine_ct, needle):
        ids = (
            DocumentIndexEntry.objects.filter(
                entry_kind=DocumentIndexEntry.KIND_FILE,
                domain_content_type=machine_ct,
                parent_path__icontains=needle,
                deleted_at__isnull=True, purged_at__isnull=True,
            ).values_list("domain_object_id", flat=True).distinct()
        )
        return set(ids)

    def _run(self, apply_changes):
        workbook = openpyxl.load_workbook(EXCEL_PATH, read_only=True, data_only=True)
        rows = list(workbook["MAQUINARIA"].iter_rows(values_only=True))
        excel_codes, excel_baja = set(), set()
        for row in rows[2:]:
            if not row or not row[0]:
                continue
            code = _norm(row[0])
            excel_codes.add(code)
            notes = " ".join(str(cell) for cell in row[7:9] if cell)
            if "BAJA" in notes.upper():
                excel_baja.add(code)
        self._log(
            "MODO: %s -- Excel MAQUINARIA: %d codigos"
            % ("APLICAR (escribe is_active)" if apply_changes else "DRY-RUN (no escribe nada)",
               len(excel_codes))
        )

        machine_ct = ContentType.objects.get_for_model(MachineAsset)
        reasons = {}
        for asset in MachineAsset.objects.all():
            code = _norm(asset.code)
            if FAMILY_RE.match(code) and code not in excel_codes:
                reasons.setdefault(asset.pk, []).append("familia A/B fuera del Excel")
        for pk in self._machines_with_docs_in(machine_ct, "BAJA DEFINITIVA"):
            reasons.setdefault(pk, []).append("documentos en BAJA DEFINITIVA")
        for asset in MachineAsset.objects.all():
            if _norm(asset.code) in excel_baja:
                reasons.setdefault(asset.pk, []).append("marcada BAJA en el Excel")
        for needle in ("(VENTA)", "(VENDIDA)", "BAJA TEMPORAL"):
            for pk in self._machines_with_docs_in(machine_ct, needle):
                reasons.setdefault(pk, []).append("documentos en %s" % needle)

        assets = {a.pk: a for a in MachineAsset.objects.filter(pk__in=reasons)}
        to_change = sorted(
            (a for a in assets.values() if a.is_active), key=lambda a: a.code,
        )
        already = sum(1 for a in assets.values() if not a.is_active)
        self._log("--- SE PONEN INACTIVAS (%d; %d ya lo estaban) ---" % (len(to_change), already))
        for asset in to_change:
            self._log("    %-12s %-40s %s" % (
                asset.code, (asset.brand_model or "")[:40], " + ".join(reasons[asset.pk]),
            ))
        if apply_changes and to_change:
            MachineAsset.objects.filter(pk__in=[a.pk for a in to_change]).update(is_active=False)

        self._log("=== RESUMEN (%s) ===" % ("APLICADO" if apply_changes else "DRY-RUN, nada escrito"))
        self._log("    maquinas puestas inactivas: %d" % len(to_change))
