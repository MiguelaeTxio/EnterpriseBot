# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/budgets/management/commands/seed_night_schedules.py
"""
Management command to seed the initial NightSchedule catalogue.
Creates two standard night-time windows for every active Company in
the database. Idempotent: uses get_or_create keyed on (company, name)
so repeated runs produce no duplicate records.
---
Comando de gestión para poblar el catálogo inicial de NightSchedule.
Crea dos franjas horarias nocturnas estándar para cada Company activa
en la base de datos. Idempotente: usa get_or_create con clave (company, name)
para que ejecuciones repetidas no generen registros duplicados.
"""

from datetime import time

from django.core.management.base import BaseCommand

from budgets.models import NightSchedule
from ivr_config.models import Company


# Default night-time windows to seed for every company.
# Franjas nocturnas por defecto a sembrar para cada empresa.
NIGHT_SCHEDULE_DEFAULTS = [
    {
        "name": "Nocturno estándar (18h–06h)",
        "night_start": time(18, 0),
        "night_end": time(6, 0),
        "is_default": True,
    },
    {
        "name": "Nocturno ampliado (20h–08h)",
        "night_start": time(20, 0),
        "night_end": time(8, 0),
        "is_default": False,
    },
]


class Command(BaseCommand):
    """
    Seeds the NightSchedule catalogue with the two standard night-time
    windows defined in NIGHT_SCHEDULE_DEFAULTS for every active Company.
    ---
    Puebla el catálogo NightSchedule con las dos franjas nocturnas estándar
    definidas en NIGHT_SCHEDULE_DEFAULTS para cada Company activa.
    """

    help = (
        "Poblar catálogo inicial NightSchedule con franjas nocturnas estándar."
    )

    def handle(self, *args, **options):
        """
        Iterates over all active companies and calls get_or_create for each
        entry in NIGHT_SCHEDULE_DEFAULTS. Reports created vs existing counts.
        ---
        Itera sobre todas las empresas activas y llama a get_or_create por cada
        entrada de NIGHT_SCHEDULE_DEFAULTS. Informa del conteo de creados vs existentes.
        """
        companies = Company.objects.filter(is_active=True)
        if not companies.exists():
            self.stdout.write(
                "# No hay empresas activas. Sin cambios."
            )
            return

        total_created = 0
        total_existing = 0

        for company in companies:
            self.stdout.write(
                f"# Empresa: {company.name}"
            )
            for defaults in NIGHT_SCHEDULE_DEFAULTS:
                obj, created = NightSchedule.objects.get_or_create(
                    company=company,
                    name=defaults["name"],
                    defaults={
                        "night_start": defaults["night_start"],
                        "night_end": defaults["night_end"],
                        "is_default": defaults["is_default"],
                        "is_active": True,
                    },
                )
                if created:
                    total_created += 1
                    self.stdout.write(
                        f"#   [CREADO] {obj.name} "
                        f"({obj.night_start.strftime('%H:%M')}–"
                        f"{obj.night_end.strftime('%H:%M')}) "
                        f"default={obj.is_default}"
                    )
                else:
                    total_existing += 1
                    self.stdout.write(
                        f"#   [EXISTE] {obj.name}"
                    )

        self.stdout.write(
            f"# Fin seed: {total_created} creados, "
            f"{total_existing} ya existían."
        )
