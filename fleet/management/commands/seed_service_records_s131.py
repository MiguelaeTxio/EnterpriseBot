# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/fleet/management/commands/seed_service_records_s131.py
"""
H30 (S131). Loads, as the latest service of each cost centre, the
service dates found in the work orders.

---

H30 (S131). Carga como última revisión de cada centro de gasto las
fechas de revisión encontradas en los partes de trabajo (Miguel Ángel:
"sí, carga esas fechas"). Lista cerrada, revisada a mano contra el
texto real de cada parte (consultas de solo lectura de S131): líneas
"Revisión", "revisión anual", "cambio de aceite y filtros",
"mantenimiento preventivo motor", "aceite y filtros revisión
cumplida". No entran las "revisión general" de las plataformas que son
"Comprobar y subir".

Horas y km solo donde el mecánico los apuntó de verdad en el parte
(A44, A45, A68): en el resto, la lectura del parte es la del catálogo
precargada por el formulario y no vale. Esas revisiones se cargan solo
con fecha, para completar después en la pestaña Revisiones.

A44 y A68 quedan además con revisión cada 800 horas si no tenían
ninguna (A44: "aceite semisintético son máximo 800 horas"; A68:
próxima a 15.141 + 800 y 1.315 + 800). Idempotente: no anota una
revisión que ya exista con esa fecha en esa máquina, ni cambia un
intervalo ya puesto. Sin `--apply` solo informa.
"""
from datetime import date, datetime

from django.core.management.base import BaseCommand
from django.db import transaction

from fleet.models import MachineAsset, MachineServiceRecord

SOURCE_NOTE = "Cargada desde el parte de trabajo del %s (S131)."

# (código, fecha, horas, horas de grúa, km)
SERVICES = [
    ("A44", date(2026, 10, 6), 22287, None, 150392),
    ("A68", date(2026, 10, 8), 1315, 15141, None),
    ("A45", date(2026, 7, 6), 23281, None, 150804),
    ("A29", date(2026, 9, 22), None, None, None),
    ("A52", date(2026, 10, 7), None, None, None),
    ("B42", date(2026, 10, 5), None, None, None),
    ("B24", date(2026, 9, 3), None, None, None),
    ("P21", date(2026, 6, 8), None, None, None),
    ("B28", date(2026, 5, 18), None, None, None),
    ("B32", date(2026, 3, 10), None, None, None),
    ("A53", date(2026, 1, 30), None, None, None),
    ("T22", date(2026, 1, 14), None, None, None),
    ("5462FJP", date(2026, 9, 25), None, None, None),
    ("2655KSF", date(2026, 4, 15), None, None, None),
    ("Z29", date(2026, 4, 17), None, None, None),
    ("Z79", date(2026, 4, 17), None, None, None),
    ("Z96", date(2026, 1, 26), None, None, None),
    ("Z115", date(2025, 12, 30), None, None, None),
    ("A66", date(2026, 2, 23), None, None, None),
]
HOURS_800_CODES = ("A44", "A68")


class Command(BaseCommand):
    """
    Load the service dates found in the work orders.

    ---

    Carga las fechas de revisión encontradas en los partes.
    """

    help = (
        "Carga como última revisión las fechas encontradas en los "
        "partes de trabajo (H30, S131). Sin --apply solo informa."
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
        self._log("Inicio: revisiones desde partes de trabajo -- %s." % mode)
        created = skipped = missing = intervals = 0
        total = len(SERVICES)
        with transaction.atomic():
            for position, (code, day, hours, crane, km) in enumerate(
                SERVICES, start=1,
            ):
                prefix = "%d/%d %s" % (position, total, code)
                machine = MachineAsset.objects.filter(code=code).first()
                if machine is None:
                    missing += 1
                    self._log("%s: NO EXISTE el centro de gasto." % prefix)
                    continue
                if code in HOURS_800_CODES and not (
                    machine.service_hours_interval
                ):
                    intervals += 1
                    self._log("%s: revisión cada 800 horas." % prefix)
                    if apply:
                        machine.service_hours_interval = 800
                        machine.save(update_fields=[
                            "service_hours_interval", "updated_at",
                        ])
                if MachineServiceRecord.objects.filter(
                    machine=machine, service_date=day,
                ).exists():
                    skipped += 1
                    self._log(
                        "%s: ya tiene revisión del %s -- no se toca."
                        % (prefix, day.strftime("%d/%m/%Y"))
                    )
                    continue
                created += 1
                self._log(
                    "%s: revisión del %s -- horas %s, horas grúa %s, km %s."
                    % (
                        prefix, day.strftime("%d/%m/%Y"),
                        hours if hours is not None else "-",
                        crane if crane is not None else "-",
                        km if km is not None else "-",
                    )
                )
                if apply:
                    MachineServiceRecord.objects.create(
                        machine=machine, service_date=day, hours=hours,
                        crane_hours=crane, km=km,
                        notes=SOURCE_NOTE % day.strftime("%d/%m/%Y"),
                    )
        self._log(
            "Resumen: %d revisiones %s, %d ya existían, %d códigos no "
            "existen, %d intervalos de 800 h %s."
            % (
                created, "anotadas" if apply else "por anotar", skipped,
                missing, intervals, "puestos" if apply else "por poner",
            )
        )
        self._log("Fin.")
