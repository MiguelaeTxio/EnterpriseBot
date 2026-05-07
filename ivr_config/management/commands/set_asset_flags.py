# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/ivr_config/management/commands/set_asset_flags.py
"""
Management command: set_asset_flags
Activates has_odometer, has_engine_hours and has_crane_hours to True on
every MachineAsset record, regardless of current mileage/hours values.
This establishes the baseline flag state for the counter-validation workflow
introduced in Hito 7: all assets are assumed to have all three counters until
an operator explicitly confirms otherwise during a work-order entry.
---
Comando de gestión: set_asset_flags
Activa has_odometer, has_engine_hours y has_crane_hours a True en todos los
registros MachineAsset, independientemente de los valores actuales de mileage/hours.
Establece el estado base de flags para el flujo de validación de contadores
introducido en el Hito 7: se asume que todos los activos tienen los tres contadores
hasta que un operario confirme lo contrario durante la entrada de un parte.
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from fleet.models import MachineAsset


class Command(BaseCommand):
    """
    Bulk-activates the three meter flags on all MachineAsset records.
    Safe to run multiple times (idempotent): only records with at least one
    flag currently set to False are updated, leaving already-correct records
    untouched.
    ---
    Activa masivamente los tres flags de contador en todos los registros
    MachineAsset. Seguro para ejecutar múltiples veces (idempotente): solo
    se actualizan los registros con al menos un flag actualmente a False,
    dejando intactos los que ya son correctos.
    """

    help = (
        "Activa los flags de contador en MachineAsset segun los valores de mileage y hours: "
        "has_odometer=True si mileage>0; has_engine_hours y has_crane_hours=True si hours>0. "
        "Primero resetea todos los flags a False y luego aplica la logica. "
        "Seguro para ejecutar multiples veces (idempotente)."
    )

    def add_arguments(self, parser):
        """
        Adds the --dry-run flag to preview changes without writing to DB.
        ---
        Aniade el flag --dry-run para previsualizar cambios sin escribir en BD.
        """
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=False,
            help="Muestra los cambios que se aplicarian sin modificar la BD.",
        )

    def handle(self, *args, **options):
        """
        Resets all meter flags to False, then activates based on mileage/hours:
          - has_odometer=True     if mileage > 0
          - has_engine_hours=True if hours   > 0
          - has_crane_hours=True  if hours   > 0
        Assets with both values at zero keep all flags False.
        ---
        Resetea todos los flags a False y los activa segun mileage/hours:
          - has_odometer=True     si mileage > 0
          - has_engine_hours=True si hours   > 0
          - has_crane_hours=True  si hours   > 0
        Los activos con ambos valores a cero mantienen todos los flags a False.
        """
        dry_run = options["dry_run"]
        verbose = options["verbosity"] >= 2

        total     = MachineAsset.objects.count()
        odo_qs    = MachineAsset.objects.filter(mileage__gt=0)
        hrs_qs    = MachineAsset.objects.filter(hours__gt=0)
        odo_count = odo_qs.count()
        hrs_count = hrs_qs.count()

        self.stdout.write(f"# Total activos:                    {total}")
        self.stdout.write(f"# has_odometer=True (mileage>0):    {odo_count}")
        self.stdout.write(f"# has_engine/crane=True (hours>0):  {hrs_count}")

        if verbose or dry_run:
            self.stdout.write("# Activos con has_odometer=True:")
            for a in odo_qs.order_by("code"):
                self.stdout.write(f"#   {a.code:<20} mileage={a.mileage}")
            self.stdout.write("# Activos con has_engine/crane_hours=True:")
            for a in hrs_qs.order_by("code"):
                self.stdout.write(f"#   {a.code:<20} hours={a.hours}")

        if dry_run:
            self.stdout.write("# [DRY-RUN] No se ha escrito nada en BD.")
            return

        with transaction.atomic():
            # Step 1 — Reset all flags to False.
            # Paso 1 — Resetear todos los flags a False.
            MachineAsset.objects.all().update(
                has_odometer     = False,
                has_engine_hours = False,
                has_crane_hours  = False,
            )
            # Step 2 — Activate has_odometer where mileage > 0.
            # Paso 2 — Activar has_odometer donde mileage > 0.
            updated_odo = MachineAsset.objects.filter(mileage__gt=0).update(
                has_odometer=True,
            )
            # Step 3 — Activate has_engine_hours and has_crane_hours where hours > 0.
            # Paso 3 — Activar has_engine_hours y has_crane_hours donde hours > 0.
            updated_hrs = MachineAsset.objects.filter(hours__gt=0).update(
                has_engine_hours=True,
                has_crane_hours=True,
            )

        self.stdout.write(
            f"# [OK] has_odometer activado en {updated_odo} activos (mileage>0)."
        )
        self.stdout.write(
            f"# [OK] has_engine_hours + has_crane_hours activado en "
            f"{updated_hrs} activos (hours>0)."
        )
        self.stdout.write(
            f"# [OK] Sin contadores: {total - updated_odo} sin odometro, "
            f"{total - updated_hrs} sin horometros."
        )
