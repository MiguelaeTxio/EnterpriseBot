# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/fleet/management/commands/recover_service_records_s137.py
"""
H30 (S137). Loads the latest service of each cost centre from the
work order tasks marked REVISION, with hours from the work order when
they are real and, if not, from the nearest GasoGes reading.

---

H30 (S137). Carga la última revisión de cada centro de gasto a partir
de las tareas de parte marcadas como REVISION (las 52 confirmadas a
mano). Miguel Ángel eligió la opción 1: los grupos 1 y 2 con sus
horas, el grupo 3 solo con fecha, y cada revisión con anotado de dónde
sale el dato, para cruzarla después con la hoja de José Antonio Mora.

- Grupo 1 (horas fiables): horas reales del parte (A34, A44, A45) o
  lectura de GasoGes a 7 días o menos de la revisión.
- Grupo 2 (aproximadas): lectura de GasoGes a más de una semana; si la
  lectura es posterior, son "como mucho" esas horas.
- Grupo 3: solo fecha (sin lectura útil, lectura que no cuadra o
  demasiado lejos).

Lista cerrada, sacada de la consulta de solo lectura de S137 (run
40493434159). Cada revisión queda enlazada a su tarea del parte (motor
del camión). Si la máquina ya tiene una revisión de esa fecha (las de
S131), no se duplica: se enlaza a la tarea, se rellenan solo las horas
y km que falten y se añade el origen a las observaciones. Comprueba que
la tarea es de esa máquina y de esa fecha; si no, la salta. Sin
`--apply` solo informa. Idempotente.
"""
from datetime import date, datetime

from django.core.management.base import BaseCommand
from django.db import transaction

from fleet.models import MachineAsset, MachineServiceRecord
from work_order_processor.models import WorkOrderEntryLine

NOTE_PREFIX = "Recuperada del parte (S137): "

# (grupo, código, tarea, fecha, horas, km, origen)
SERVICES = [
    (1, "A34", 3446, date(2026, 7, 27), 21236, None,
     "horas del parte; GasoGes cuadra"),
    (1, "A44", 3841, date(2026, 10, 6), 22287, 150392,
     "horas y km del parte; GasoGes cuadra"),
    (1, "A45", 3243, date(2026, 7, 6), 23281, 150804,
     "horas y km del parte; GasoGes cuadra"),
    (1, "2655KSF", 405, date(2026, 4, 15), None, 131521,
     "km de GasoGes del mismo día"),
    (1, "Z132", 2765, date(2026, 1, 2), 4206, None,
     "horas de GasoGes del mismo día"),
    (1, "Z14", 2650, date(2025, 12, 29), 2934, None,
     "horas de GasoGes del 02/01/2026 (4 días después)"),
    (1, "Z29", 413, date(2026, 4, 17), 1975, None,
     "horas de GasoGes entre el 15/04 (1.972) y el 06/05 (1.999)"),
    (1, "Z96", 2260, date(2026, 1, 26), 2882, None,
     "horas de GasoGes entre el 23/01 (2.880) y el 28/01 (2.883)"),
    (1, "T22", 2794, date(2026, 1, 14), 1013, None,
     "horas de GasoGes entre el 07/01 (1.009) y el 19/03 (1.048)"),
    (2, "Z79", 414, date(2026, 4, 17), 3185, None,
     "aproximadas: GasoGes entre el 24/03 (3.172) y el 30/04 (3.192)"),
    (2, "Z77", 399, date(2026, 4, 13), 1451, None,
     "aproximadas: GasoGes entre el 24/02 (1.427) y el 02/06 (1.477)"),
    (2, "Z91", 2710, date(2026, 1, 5), 5089, None,
     "como mucho: GasoGes del 19/01/2026 (14 días después)"),
    (2, "Z116", 2660, date(2026, 1, 2), 2254, None,
     "como mucho: GasoGes del 22/01/2026 (20 días después)"),
    (2, "Z115", 2654, date(2025, 12, 30), 4089, None,
     "como mucho: GasoGes del 29/01/2026 (30 días después)"),
    (2, "Z15", 2646, date(2025, 12, 26), 4020, None,
     "como mucho: GasoGes del 29/01/2026 (34 días después)"),
    (2, "Z78", 2708, date(2026, 1, 2), 3952, None,
     "como mucho: GasoGes del 06/02/2026 (35 días después)"),
    (3, "5462FJP", 3785, date(2026, 9, 25), None, None,
     "solo fecha: sin horas en el parte ni en GasoGes"),
    (3, "A29", 3779, date(2026, 9, 22), None, None,
     "solo fecha: sin horas en el parte ni en GasoGes"),
    (3, "A52", 3876, date(2026, 10, 7), None, None,
     "solo fecha: sin horas en el parte ni en GasoGes"),
    (3, "A53", 2098, date(2026, 1, 30), None, None,
     "solo fecha: sin horas en el parte ni en GasoGes"),
    (3, "A68", 3856, date(2026, 10, 8), None, None,
     "solo fecha: el parte trae ceros"),
    (3, "Z97", 2271, date(2026, 1, 29), None, None,
     "solo fecha: sin horas en el parte ni en GasoGes"),
    (3, "A66", 2422, date(2026, 2, 23), None, None,
     "solo fecha: GasoGes no cuadra (174.511)"),
    (3, "B27", 3917, date(2026, 10, 20), None, None,
     "solo fecha: GasoGes no cuadra (247.689)"),
    (3, "B28", 2495, date(2026, 5, 18), None, None,
     "solo fecha: GasoGes no cuadra (225.989)"),
    (3, "B41", 2869, date(2026, 1, 1), None, None,
     "solo fecha: GasoGes no cuadra (730.480)"),
    (3, "B42", 3840, date(2026, 10, 5), None, None,
     "solo fecha: GasoGes no cuadra (121.738)"),
    (3, "Z17", 2651, date(2025, 12, 29), None, None,
     "solo fecha: GasoGes no cuadra (60.747)"),
    (3, "Z08", 2706, date(2025, 12, 30), None, None,
     "solo fecha: lectura de GasoGes demasiado lejos"),
    (3, "Z114", 2753, date(2025, 12, 31), None, None,
     "solo fecha: lectura de GasoGes demasiado lejos"),
    (3, "Z25", 2747, date(2025, 12, 23), None, None,
     "solo fecha: lectura de GasoGes demasiado lejos"),
    (3, "Z83", 2642, date(2025, 12, 24), None, None,
     "solo fecha: lectura de GasoGes demasiado lejos"),
    (3, "B32", 351, date(2026, 3, 10), None, None,
     "solo fecha: lectura de GasoGes demasiado lejos"),
    (3, "Z117", 417, date(2010, 4, 26), None, None,
     "solo fecha, y mal puesta en el parte (26/04/2010)"),
]


def _fmt(value):
    """
    Number with Spanish thousands separator, or "-".

    ---

    Número con punto de miles, o "-".
    """
    return "-" if value is None else "{:,}".format(value).replace(",", ".")


class Command(BaseCommand):
    """
    Load the latest service of each machine from the work orders.

    ---

    Carga la última revisión de cada máquina desde los partes.
    """

    help = (
        "Carga la última revisión de cada centro de gasto desde las "
        "tareas REVISION de los partes (H30, S137). Sin --apply solo "
        "informa."
    )

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")
        parser.add_argument(
            "--log-file", required=True,
            help="Ruta del log propio (pantalla y archivo a la vez).",
        )

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
        with open(options["log_file"], "a", encoding="utf-8") as handle:
            self._handle = handle
            self._run(options["apply"])

    def _run(self, apply):
        mode = "APLICAR" if apply else "SOLO INFORME (sin --apply)"
        self._log("Inicio: revisiones recuperadas de los partes -- %s."
                  % mode)
        counts = {"created": 0, "updated": 0, "same": 0, "skipped": 0}
        total = len(SERVICES)
        with transaction.atomic():
            for position, row in enumerate(SERVICES, start=1):
                self._one(position, total, row, apply, counts)
        self._log(
            "Resumen: %d revisiones %s, %d %s (ya existían de S131), %d "
            "ya estaban cargadas, %d saltadas."
            % (counts["created"], "nuevas" if apply else "por crear",
               counts["updated"],
               "completadas" if apply else "por completar",
               counts["same"], counts["skipped"]))
        self._log("Fin.")

    def _one(self, position, total, row, apply, counts):
        """
        Create or complete the service record of one machine.

        ---

        Crea o completa la revisión de una máquina.
        """
        group, code, line_id, day, hours, km, origin = row
        prefix = "%d/%d grupo %d %s" % (position, total, group, code)
        machine = MachineAsset.objects.filter(code=code).first()
        line = WorkOrderEntryLine.objects.filter(pk=line_id).select_related(
            "entry").first()
        if machine is None or line is None:
            counts["skipped"] += 1
            self._log("%s: SALTADA, no existe %s." % (
                prefix, "la máquina" if machine is None else
                "la tarea %d" % line_id))
            return
        if line.machine_asset_id != machine.pk or line.entry.work_date != day:
            counts["skipped"] += 1
            self._log("%s: SALTADA, la tarea %d no es de esta máquina o de "
                      "esta fecha." % (prefix, line_id))
            return
        note = (NOTE_PREFIX + origin)[:255]
        detail = "%s -- horas %s, km %s -- %s" % (
            day.strftime("%d/%m/%Y"), _fmt(hours), _fmt(km), origin)
        linked = MachineServiceRecord.objects.filter(
            work_order_line=line,
            engine=MachineServiceRecord.ENGINE_TRUCK).first()
        if linked is not None:
            counts["same"] += 1
            self._log("%s: ya cargada (revisión %d), no se toca."
                      % (prefix, linked.pk))
            return
        existing = MachineServiceRecord.objects.filter(
            machine=machine, service_date=day,
            work_order_line__isnull=True).first()
        if existing is not None:
            counts["updated"] += 1
            self._log("%s: completa la revisión %d de S131 -- %s"
                      % (prefix, existing.pk, detail))
            if apply:
                existing.work_order_line = line
                existing.engine = MachineServiceRecord.ENGINE_TRUCK
                if existing.hours is None:
                    existing.hours = hours
                if existing.km is None:
                    existing.km = km
                existing.notes = ("%s %s" % (existing.notes, note)).strip()[
                    :255]
                existing.save(update_fields=[
                    "work_order_line", "engine", "hours", "km", "notes"])
            return
        counts["created"] += 1
        self._log("%s: nueva -- %s" % (prefix, detail))
        if apply:
            MachineServiceRecord.objects.create(
                machine=machine, service_date=day, hours=hours, km=km,
                work_order_line=line,
                engine=MachineServiceRecord.ENGINE_TRUCK, notes=note)
