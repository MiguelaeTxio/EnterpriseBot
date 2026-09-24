# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/fleet/management/commands/deactivate_platforms_s117.py
"""
H30 (S117), punto 1 (máquinas activas) -- PLATAFORMAS ELEVADORAS (Z).

Lista maestra real: listado impreso del parque de plataformas a fecha
29/06/2026 (3 páginas, fotografiadas por Miguel Ángel), transcrita por
su columna "Nº Parque" -- 103 plataformas. Instrucción de Miguel Ángel:
"Toda plataforma elevadora que no esté en este listado, automáticamente
la damos de baja."

Corrección de Miguel Ángel sobre el dry-run: "Todas las máquinas que
vienen en las tres páginas [...] todas se ponen en activo. Las que no
estén en estas tres páginas se ponen inactivas. No hay que mirar
ninguna cosa más." El listado es la verdad para las plataformas:
1. Plataforma Z<n> que ESTÁ en el listado -> activa (incluidas las que
   estaban inactivas, p. ej. Z67, inactivada esa mañana por una carpeta
   "(VENTA)").
2. Plataforma Z<n> que NO está en el listado -> inactiva.
Solo informativo (no cambia nada): plataformas del listado que no
existen en Centros de gasto.

Nunca borra nada. DRY-RUN por defecto; --apply escribe is_active. Log propio (com-standards 0bis/0ter).
"""
import re
from collections import defaultdict
from datetime import datetime

from django.core.management.base import BaseCommand

from fleet.models import MachineAsset

PARK_LIST = [
    # Página 1
    "Z03", "Z04", "Z06", "Z08", "Z09", "Z100", "Z101", "Z102", "Z103",
    "Z104", "Z105", "Z106", "Z107", "Z108", "Z109", "Z110", "Z111", "Z112",
    "Z113", "Z114", "Z115", "Z116", "Z117", "Z118", "Z119", "Z120", "Z121",
    "Z122", "Z123", "Z124", "Z125", "Z126", "Z127", "Z128", "Z129", "Z130",
    "Z131", "Z132", "Z133", "Z134",
    # Página 2
    "Z135", "Z136", "Z137", "Z138", "Z14", "Z17", "Z19", "Z20", "Z22",
    "Z24", "Z25", "Z26", "Z28", "Z29", "Z31", "Z32", "Z37", "Z39", "Z40",
    "Z42", "Z43", "Z44", "Z45", "Z46", "Z47", "Z48", "Z49", "Z50", "Z51",
    "Z52", "Z53", "Z54", "Z55", "Z56", "Z57", "Z58", "Z59", "Z60", "Z61",
    "Z62", "Z63", "Z64", "Z67", "Z69", "Z71", "Z72", "Z73", "Z77", "Z78",
    # Página 3
    "Z79", "Z82", "Z83", "Z84", "Z88", "Z89", "Z91", "Z92", "Z93", "Z94",
    "Z95", "Z96", "Z97", "Z98",
]
Z_RE = re.compile(r"^Z(\d+)$")


def _norm(code):
    """
    "Z-03", "z3", "Z03 " -> "Z3" (number without leading zeros), so the
    list and the fleet compare the same whatever the padding.
    ---
    "Z-03", "z3", "Z03 " -> "Z3" (número sin ceros a la izquierda), para
    comparar lista y flota igual sea cual sea el relleno.
    """
    compact = re.sub(r"[\s\-.]", "", str(code or "")).upper()
    match = Z_RE.match(compact)
    return "Z%d" % int(match.group(1)) if match else None


class Command(BaseCommand):
    help = (
        "H30 (S117) -- plataformas Z: las del listado del parque "
        "(29/06/2026) activas, el resto inactivas. Dry-run por defecto."
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
        park = {_norm(code) for code in PARK_LIST}
        self._log(
            "MODO: %s -- listado del parque 29/06/2026: %d plataformas"
            % ("APLICAR (escribe is_active)" if apply_changes else "DRY-RUN (no escribe nada)",
               len(park))
        )
        by_code = defaultdict(list)
        for asset in MachineAsset.objects.all().order_by("code"):
            key = _norm(asset.code)
            if key:
                by_code[key].append(asset)

        to_activate, to_deactivate = [], []
        for key, assets in sorted(by_code.items(), key=lambda kv: int(kv[0][1:])):
            for asset in assets:
                if key in park and not asset.is_active:
                    to_activate.append(asset)
                elif key not in park and asset.is_active:
                    to_deactivate.append(asset)

        self._log("--- SE PONEN ACTIVAS: en el listado y estaban inactivas (%d) ---" % len(to_activate))
        for asset in to_activate:
            self._log("    %-8s pk=%-5d %s" % (asset.code, asset.pk, asset.brand_model or ""))
        self._log("--- SE PONEN INACTIVAS: plataformas Z fuera del listado (%d) ---" % len(to_deactivate))
        for asset in to_deactivate:
            self._log("    %-8s pk=%-5d %s" % (asset.code, asset.pk, asset.brand_model or ""))
        if apply_changes:
            if to_activate:
                MachineAsset.objects.filter(pk__in=[a.pk for a in to_activate]).update(is_active=True)
            if to_deactivate:
                MachineAsset.objects.filter(pk__in=[a.pk for a in to_deactivate]).update(is_active=False)

        self._log("--- SOLO INFORMATIVO: en el listado pero NO existen en Centros de gasto ---")
        for key in sorted(park, key=lambda k: int(k[1:])):
            if key not in by_code:
                self._log("    %s" % key)

        self._log("=== RESUMEN (%s) ===" % ("APLICADO" if apply_changes else "DRY-RUN, nada escrito"))
        self._log("    plataformas puestas activas: %d" % len(to_activate))
        self._log("    plataformas puestas inactivas: %d" % len(to_deactivate))
