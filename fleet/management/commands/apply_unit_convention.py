# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/fleet/management/commands/apply_unit_convention.py
"""
H30 (S137). Apply the workshop unit rule to the GasoGes vehicles.

---

H30 (S137). Pone a los vehículos de GasoGes la unidad que fija la regla
del taller (turismos, furgonetas X y P por km; A, B, T, Z y grúas
móviles por horas), solo en centros de gasto activos, y rehace las
lecturas de los que cambian. Solo se aplica con este comando.
"""
from datetime import datetime

from django.core.management.base import BaseCommand

from fleet.gasoges_sync import apply_convention


class Command(BaseCommand):
    """
    Apply the workshop unit rule now.

    ---

    Aplica ya la regla del taller a los vehículos de GasoGes.
    """

    help = ("Pone la unidad de la regla del taller a los vehículos de "
            "centros de gasto activos y rehace sus lecturas.")

    def add_arguments(self, parser):
        parser.add_argument(
            "--log-file", required=True,
            help="Ruta del log propio (pantalla y archivo a la vez).",
        )
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Solo lista lo que cambiaría, sin guardar.",
        )

    def handle(self, *args, **options):
        with open(options["log_file"], "a", encoding="utf-8") as handle:
            def log(line):
                line = "[%s] %s" % (datetime.now().strftime("%H:%M:%S"),
                                    line)
                print(line, flush=True)
                handle.write(line + "\n")
                handle.flush()

            log("Inicio%s." % (" (DRY-RUN)" if options["dry_run"] else ""))
            apply_convention(log, dry_run=options["dry_run"])
            log("Fin.")
