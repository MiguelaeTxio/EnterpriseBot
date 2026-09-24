# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/fleet/management/commands/sync_active_from_excel_s117.py
"""
H30 (S117), punto 1 (máquinas activas) -- el Excel MANDA para las
familias A (grúas móviles), B (autocargantes) y Z (plataformas).

Hoja MAQUINARIA de document_explorer/data_imports/EXCEL_TRABAJADORES.xlsx,
actualizada en S117 a petición de Miguel Ángel:
- las 37 filas originales de Yolanda, intactas;
- A-67 a A-69 y B-37 a B-48: "el número es el orden de entrada en la
  empresa [...] si la última que aparece en el Excel es la 22 y luego
  tenemos documentos de la 23, la 24 y la 25, pues la 23, la 24 y la 25
  las ponemos en activo" (la A-69 es una Sany SAC700E comprada en 2026
  que el Excel aún no tenía);
- las 103 plataformas Z del listado del parque (29/06/2026).

Regla única: código A/B/Z en el Excel -> activa, salvo las marcadas
"BAJA" en su columna de notas (B-20) -> inactiva; código A/B/Z que NO
está en el Excel -> inactiva. Idempotente. Nunca borra.

DRY-RUN por defecto; --apply escribe is_active. Log propio
(com-standards 0bis/0ter).
"""
import re
from datetime import datetime
from pathlib import Path

import openpyxl
from django.conf import settings
from django.core.management.base import BaseCommand

from fleet.models import MachineAsset

EXCEL_PATH = Path(settings.BASE_DIR) / "document_explorer" / "data_imports" / "EXCEL_TRABAJADORES.xlsx"
FAMILY_RE = re.compile(r"^([ABZ])(\d+)$")


def _key(code):
    """
    "A-29 ", "a29", "Z03" -> ("A", 29): family + number without padding.
    ---
    "A-29 ", "a29", "Z03" -> ("A", 29): familia + número sin relleno.
    """
    compact = re.sub(r"[\s\-.]", "", str(code or "")).upper()
    match = FAMILY_RE.match(compact)
    return (match.group(1), int(match.group(2))) if match else None


class Command(BaseCommand):
    help = (
        "H30 (S117) -- familias A, B y Z: activas las del Excel (salvo BAJA), "
        "inactivas las demas. Dry-run por defecto."
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

    def _run(self, apply_changes):
        workbook = openpyxl.load_workbook(EXCEL_PATH, read_only=True, data_only=True)
        active_keys, baja_keys = set(), set()
        for row in list(workbook["MAQUINARIA"].iter_rows(values_only=True))[2:]:
            if not row or not row[0]:
                continue
            key = _key(row[0])
            if not key:
                continue
            notes = " ".join(str(cell) for cell in row[7:9] if cell)
            (baja_keys if "BAJA" in notes.upper() else active_keys).add(key)
        self._log(
            "MODO: %s -- Excel: %d activas, %d marcadas BAJA"
            % ("APLICAR (escribe is_active)" if apply_changes else "DRY-RUN (no escribe nada)",
               len(active_keys), len(baja_keys))
        )

        to_activate, to_deactivate = [], []
        for asset in MachineAsset.objects.all():
            key = _key(asset.code)
            if not key:
                continue
            should_be_active = key in active_keys
            if should_be_active and not asset.is_active:
                to_activate.append(asset)
            elif not should_be_active and asset.is_active:
                to_deactivate.append(asset)

        order = lambda a: _key(a.code)
        self._log("--- SE PONEN ACTIVAS (%d) ---" % len(to_activate))
        for asset in sorted(to_activate, key=order):
            self._log("    %-8s pk=%-5d %s" % (asset.code, asset.pk, asset.brand_model or ""))
        self._log("--- SE PONEN INACTIVAS (%d) ---" % len(to_deactivate))
        for asset in sorted(to_deactivate, key=order):
            self._log("    %-8s pk=%-5d %s" % (asset.code, asset.pk, asset.brand_model or ""))
        if apply_changes:
            MachineAsset.objects.filter(pk__in=[a.pk for a in to_activate]).update(is_active=True)
            MachineAsset.objects.filter(pk__in=[a.pk for a in to_deactivate]).update(is_active=False)
        self._log("=== RESUMEN (%s) ===" % ("APLICADO" if apply_changes else "DRY-RUN, nada escrito"))
        self._log("    activadas: %d -- desactivadas: %d" % (len(to_activate), len(to_deactivate)))
