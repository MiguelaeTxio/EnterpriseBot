# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/fleet/management/commands/sync_work_order_readings.py
"""
H30 (S137). Creates the meter readings of the work orders already saved.

---

H30 (S137). Crea las lecturas de km y horas de los partes digitales ya
guardados (los nuevos las crean solos, ver `fleet/signals.py`). Se puede
repetir: cada bloque tiene una sola lectura y solo se toca si cambia; si
ya no vale (p. ej. era el valor del catálogo que trae el formulario), se
borra.
"""
from datetime import datetime
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db.models import Q

from fleet.work_order_readings import sync_line_reading
from work_order_processor.models import WorkOrderEntryLine

HEARTBEAT_EVERY = 500


class Command(BaseCommand):
    """
    Create the readings of the saved work order blocks.

    ---

    Crea las lecturas de los bloques de parte ya guardados.
    """

    help = (
        "Crea las lecturas de km y horas de los partes digitales ya "
        "guardados (H30, S137)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--log-file", required=True,
            help="Ruta del log propio (pantalla y archivo a la vez).",
        )

    def _write(self, line):
        print(line, flush=True)
        self._handle.write(line + "\n")
        self._handle.flush()

    def _log(self, message):
        self._write(
            "[%s] %s" % (datetime.now().strftime("%H:%M:%S"), message))

    def _heartbeat(self, done, total, counters):
        """
        Progress line with ETA every few hundred blocks.

        ---

        Línea de progreso con ETA cada pocos cientos de bloques.
        """
        if done % HEARTBEAT_EVERY and done != total:
            return
        elapsed = (datetime.now() - self._start).total_seconds()
        eta = (elapsed / done) * (total - done) if done else 0
        end = (datetime.now() + timedelta(seconds=eta)).strftime("%H:%M:%S")
        self._log(
            "Progreso: %d/%d bloques (%d%%) -- ETA %dm%02ds (fin aprox. "
            "%s) -- creadas=%d, cambiadas=%d, borradas=%d"
            % (done, total, done * 100 // total, eta // 60, eta % 60, end,
               counters["created"], counters["updated"],
               counters["deleted"]))

    def handle(self, *args, **options):
        lines = WorkOrderEntryLine.objects.filter(
            Q(odometer_reading__isnull=False)
            | Q(engine_hours_reading__isnull=False)
            | Q(crane_hours_reading__isnull=False)
            | Q(meter_reading__isnull=False),
        ).select_related("entry", "machine_asset").order_by("id")
        with open(options["log_file"], "a", encoding="utf-8") as handle:
            self._handle = handle
            self._start = datetime.now()
            total = lines.count()
            self._log("Inicio: %d bloques de parte con alguna lectura."
                      % total)
            counters = {"created": 0, "updated": 0, "deleted": 0}
            for done, line in enumerate(lines.iterator(), start=1):
                action = sync_line_reading(line)
                if action:
                    counters[action] += 1
                self._heartbeat(done, total, counters)
            self._write(
                "Resumen: %(created)d lecturas creadas, %(updated)d "
                "cambiadas y %(deleted)d borradas." % counters)
            self._write("Fin.")
