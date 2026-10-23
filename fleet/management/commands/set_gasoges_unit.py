# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/fleet/management/commands/set_gasoges_unit.py
"""
H30 (S135). Sets by hand whether some GasoGes vehicles type
kilometres or hours, and redoes their readings.

---

H30 (S135). Fija a mano si unos vehículos de GasoGes apuntan km u
horas (queda "a mano": la deducción ya no la cambia) y rehace sus
lecturas del surtidor. Por códigos de centro de gasto (`--codes`) y/o
por principio de código (`--code-prefix`, p. ej. Z: Miguel Ángel,
S135, "Todas las Z son plataforma elevadora. Todas van con horas").
Lo mismo que la acción "Apunta kilómetros / horas" de la pestaña
Repostajes, para muchos a la vez.
"""
from datetime import datetime

from django.core.management.base import BaseCommand, CommandError

from fleet.gasoges_sync import redo_vehicle
from fleet.models import GasoGesVehicle


class Command(BaseCommand):
    """
    Set the unit of GasoGes vehicles and redo their readings.

    ---

    Fija la unidad de vehículos de GasoGes y rehace sus lecturas.
    """

    help = (
        "Fija a mano km u horas de vehículos de GasoGes por código de "
        "centro de gasto y rehace sus lecturas (H30, S135)."
    )

    def add_arguments(self, parser):
        parser.add_argument("--unit", required=True,
                            choices=["KM", "HOURS"])
        parser.add_argument("--codes", default="",
                            help="Códigos separados por comas.")
        parser.add_argument("--code-prefix", default="",
                            help="Todos los códigos que empiezan así.")
        parser.add_argument(
            "--log-file", required=True,
            help="Ruta del log propio (pantalla y archivo a la vez).")

    def _log(self, message):
        """
        Print and append one line to the log file, flushed.

        ---

        Escribe una línea en pantalla y en el log, con flush.
        """
        line = "[%s] %s" % (datetime.now().strftime("%H:%M:%S"), message)
        print(line, flush=True)
        self._handle.write(line + "\n")
        self._handle.flush()

    def handle(self, *args, **options):
        codes = [c.strip().upper() for c in options["codes"].split(",")
                 if c.strip()]
        prefix = options["code_prefix"].strip().upper()
        if not codes and not prefix:
            raise CommandError("Indica --codes o --code-prefix.")
        with open(options["log_file"], "a", encoding="utf-8") as handle:
            self._handle = handle
            vehicles = GasoGesVehicle.objects.filter(
                machine__isnull=False).select_related("machine")
            chosen = [v for v in vehicles
                      if v.machine.code.upper() in codes
                      or (prefix and v.machine.code.upper().startswith(
                          prefix))]
            self._log("Inicio: %d vehículos de GasoGes a %s." % (
                len(chosen), options["unit"]))
            found = {v.machine.code.upper() for v in chosen}
            for code in codes:
                if code not in found:
                    self._log("AVISO: %s no tiene vehículo de GasoGes "
                              "enlazado." % code)
            for vehicle in chosen:
                vehicle.unit = options["unit"]
                vehicle.unit_source = GasoGesVehicle.UNIT_SOURCE_MANUAL
                vehicle.save(update_fields=[
                    "unit", "unit_source", "updated_at"])
                redo_vehicle(vehicle, self._log)
            self._handle.write("Fin.\n")
            print("Fin.", flush=True)
