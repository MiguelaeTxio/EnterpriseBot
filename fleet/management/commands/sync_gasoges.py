# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/fleet/management/commands/sync_gasoges.py
"""
H30 (S135). Syncs GasoGes into the database (see fleet/gasoges_sync.py).

---

H30 (S135). Sincroniza GasoGes con la BD: usuarios, vehículos,
suministros, unidades y lecturas (ver `fleet/gasoges_sync.py`).
Sustituye a `link_gasoges_vehicles` (enlace con un solo campo por
máquina, retirado en la migración fleet/0021). Por defecto, los
últimos 3 días; `--since AAAA-MM-DD` para la carga inicial. Lo mismo
que hace la tarea periódica `fleet.tasks.sync_gasoges_task`.
"""
from datetime import date
from datetime import datetime
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.core.management.base import CommandError

from fleet.gasoges_client import GasoGesError
from fleet.gasoges_sync import run_sync

HEARTBEAT_EVERY_DAYS = 10


class Command(BaseCommand):
    """
    Sync GasoGes users, vehicles, supplies, units and readings.

    ---

    Sincroniza usuarios, vehículos, suministros, unidades y lecturas de
    GasoGes.
    """

    help = (
        "Sincroniza GasoGes con la BD (H30, S135): usuarios, vehículos, "
        "suministros, unidades y lecturas."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--since", help="Primer día a leer (AAAA-MM-DD).")
        parser.add_argument(
            "--days", type=int, default=3,
            help="Sin --since: días hacia atrás a leer (3 por defecto).")
        parser.add_argument(
            "--rebuild", action="store_true",
            help=(
                "Borra las lecturas del surtidor (nunca las puestas a "
                "mano) y las rehace con las reglas vigentes."
            ),
        )
        parser.add_argument(
            "--log-file", required=True,
            help="Ruta del log propio (pantalla y archivo a la vez).",
        )

    def _write(self, line):
        """
        Print and append one line to the log file, flushed.

        ---

        Escribe una línea en pantalla y en el log, con flush.
        """
        print(line, flush=True)
        self._handle.write(line + "\n")
        self._handle.flush()

    def _log(self, message):
        """
        Log line with the clock time in front.

        ---

        Línea de log con la hora delante.
        """
        self._write(
            "[%s] %s" % (datetime.now().strftime("%H:%M:%S"), message))

    def _heartbeat(self, done, total, counters):
        """
        Progress line with ETA every few days of supplies.

        ---

        Línea de progreso con ETA cada pocos días de suministros.
        """
        if done % HEARTBEAT_EVERY_DAYS and done != total:
            return
        elapsed = (datetime.now() - self._start).total_seconds()
        eta = (elapsed / done) * (total - done) if done else 0
        end = (datetime.now() + timedelta(seconds=eta)).strftime("%H:%M:%S")
        self._log(
            "Progreso: %d/%d días (%d%%) -- ETA %dm%02ds (fin aprox. %s) "
            "-- leídos=%d, nuevos=%d"
            % (done, total, done * 100 // total, eta // 60, eta % 60, end,
               counters["leidos"], counters["nuevos"])
        )

    def handle(self, *args, **options):
        end = date.today()
        if options["since"]:
            try:
                start = datetime.strptime(
                    options["since"], "%Y-%m-%d").date()
            except ValueError:
                raise CommandError("--since debe ser AAAA-MM-DD.")
        else:
            start = end - timedelta(days=max(options["days"], 1) - 1)
        with open(options["log_file"], "a", encoding="utf-8") as handle:
            self._handle = handle
            self._start = datetime.now()
            self._log("Inicio: sincronización de GasoGes, del %s al %s."
                      % (start, end))
            try:
                run_sync(start, end, self._log, self._heartbeat,
                         rebuild=options["rebuild"])
            except GasoGesError as exc:
                self._log("ERROR: %s" % exc)
                raise CommandError(str(exc))
            self._write("Fin.")
