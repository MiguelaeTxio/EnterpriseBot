# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/fleet/management/commands/normalize_machine_families.py
"""
S119 -- normalize abbreviated MachineAsset.family values to their full
name, confirmed by Miguel Ángel.
---
S119 -- normaliza las familias abreviadas de `MachineAsset.family` a su
nombre completo, confirmado por Miguel Ángel tras revisar los
representantes reales de cada una (incluidas las inactivas E.M./S/TM,
identificadas por su propia máquina "EMPRESA MANTENEDORA"/"NAVE
MAQUEDA"). `family` es texto libre (sin catálogo fijo, campo de 100
caracteres) usado también para construir la carpeta virtual de la
máquina (`naming_service.build_machine_folder_path`); las carpetas de
las máquinas activas se renombran solas la próxima vez que se ejecute
`reorganize_machine_documents`, sin ninguna acción aparte.

VENTOSA se fusiona con ELEM -> "ELEMENTOS AUXILIARES" (decisión de
Miguel Ángel: es un accesorio de elevación, no una familia propia).

DRY-RUN por defecto.
"""
from django.core.management.base import BaseCommand

from fleet.models import MachineAsset

# family actual (tal cual en BD) -> nombre completo confirmado
RENAMES = {
    "PLATAFOR": "PLATAFORMAS",
    "MOVILES": "MÓVILES",
    "REMOLQUE": "REMOLQUES",
    "ASISTENC": "ASISTENCIA",
    "AUTOCARG": "AUTOCARGANTES",
    "CARR": "CARRETILLAS",
    "TTE.": "TRANSPORTES",
    "S/F": "SIN FAMILIA",
    "ADM": "ADMINISTRACIÓN",
    "ELEM": "ELEMENTOS AUXILIARES",
    "VENTOSA": "ELEMENTOS AUXILIARES",
    "BEN": "BENAJARAFE",
    "E.M.": "EMPRESA MANTENEDORA",
    "S/TM": "NAVE MAQUEDA",
}


class Command(BaseCommand):
    help = (
        "S119 -- normaliza las familias abreviadas de MachineAsset a "
        "su nombre completo confirmado. Dry-run por defecto."
    )

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")
        parser.add_argument(
            "--log-file", required=True,
            help="Log propio (pantalla y archivo a la vez, 0bis).",
        )

    def _log(self, message):
        print(message, flush=True)
        self._handle.write(message + "\n")
        self._handle.flush()

    def handle(self, *args, **options):
        self._handle = open(options["log_file"], "a", encoding="utf-8")
        try:
            self._run(options["apply"])
        finally:
            self._handle.close()

    def _run(self, apply_changes):
        self._log(
            "MODO: %s" % (
                "APLICAR (escribe)" if apply_changes
                else "DRY-RUN (no escribe nada)"
            )
        )
        total = 0
        for old_family, new_family in RENAMES.items():
            queryset = MachineAsset.objects.filter(family=old_family)
            count = queryset.count()
            if count == 0:
                continue
            active_count = queryset.filter(is_active=True).count()
            self._log(
                "  %s -> %s: %d maquinas (%d activas)" % (
                    old_family, new_family, count, active_count,
                )
            )
            if apply_changes:
                queryset.update(family=new_family)
            total += count
        self._log("=== RESUMEN (%s) ===" % (
            "APLICADO" if apply_changes else "DRY-RUN, nada escrito"
        ))
        self._log("    maquinas actualizadas: %d" % total)
