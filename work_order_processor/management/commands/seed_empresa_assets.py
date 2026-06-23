# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/work_order_processor/management/commands/seed_empresa_assets.py
"""
Management command: seed_empresa_assets
========================================
Creates (or verifies) the special MachineAsset records used as "EMPRESA_*"
cost centres for general workshop tasks that cannot be assigned to a single
machine (e.g. general taller maintenance, warehouse organisation, admin).

Each EMPRESA_* asset has a reserved code prefix that the digital work-order
form recognises to offer a sub-type dropdown (similar to how PERSONAL shows
the AbsenceCategory dropdown).

Family values map to the machine families that each cost centre's costs
should be considered against in analytics:

  EMPRESA_TALLER_MECANICO  → family MOVILES  (grúas móviles, camiones,
                              carretillas pesadas, remolques, turismos…)
  EMPRESA_TALLER_ELEVACION → family PLATAFOR (plataformas, tijeras, CARR,
                              ALQUILER elevación…)
  EMPRESA_TALLER_HUELVA    → family HUELVA   (delegación Huelva)
  EMPRESA_ALMACEN          → family ALMACEN  (general — todo el parque)
  EMPRESA_DEPENDENCIAS     → family DEPENDENCIAS (Administración, Larios…)

The command is idempotent: running it more than once has no effect if the
assets already exist for the company.

Usage:
  python3 -m dotenv run python3 manage.py seed_empresa_assets

---

Crea (o verifica) los registros MachineAsset especiales usados como centros
de gasto EMPRESA_* para tareas generales de taller que no pueden asignarse
a una máquina concreta.

El comando es idempotente.

Uso:
  python3 -m dotenv run python3 manage.py seed_empresa_assets
"""

from django.core.management.base import BaseCommand

from fleet.models import MachineAsset
from ivr_config.models import Company


EMPRESA_ASSETS = [
    {
        "code":         "EMPRESA_TALLER_MECANICO",
        "family":       "MOVILES",
        "type_code":    "EMPRESA",
        "type_name":    "Centro de gasto — Empresa / Taller Mecánico",
        "brand_model":  "Gastos generales — Taller Mecánico",
    },
    {
        "code":         "EMPRESA_TALLER_ELEVACION",
        "family":       "PLATAFOR",
        "type_code":    "EMPRESA",
        "type_name":    "Centro de gasto — Empresa / Taller Elevación",
        "brand_model":  "Gastos generales — Taller Elevación",
    },
    {
        "code":         "EMPRESA_TALLER_HUELVA",
        "family":       "HUELVA",
        "type_code":    "EMPRESA",
        "type_name":    "Centro de gasto — Empresa / Taller Huelva",
        "brand_model":  "Gastos generales — Taller Huelva",
    },
    {
        "code":         "EMPRESA_ALMACEN",
        "family":       "ALMACEN",
        "type_code":    "EMPRESA",
        "type_name":    "Centro de gasto — Empresa / Almacén",
        "brand_model":  "Gastos generales — Almacén",
    },
    {
        "code":         "EMPRESA_DEPENDENCIAS",
        "family":       "DEPENDENCIAS",
        "type_code":    "EMPRESA",
        "type_name":    "Centro de gasto — Empresa / Dependencias",
        "brand_model":  "Gastos generales — Dependencias (Administración, Larios…)",
    },
]


class Command(BaseCommand):
    """
    Seeds the EMPRESA_* MachineAssets for each active company.
    ---
    Crea los MachineAsset EMPRESA_* para cada empresa activa.
    """

    help = (
        "Crea los centros de gasto EMPRESA_* para cada empresa activa si no "
        "existen. Idempotente."
    )

    def handle(self, *args, **options):
        """
        Main entry point. Iterates over active companies and creates each
        EMPRESA_* asset if it does not already exist.

        ---

        Punto de entrada principal. Itera sobre las empresas activas y crea
        cada activo EMPRESA_* si no existe todavía.
        """
        companies = Company.objects.filter(is_active=True)
        created_total = 0
        existing_total = 0

        for company in companies:
            self.stdout.write(
                f"\n# [seed_empresa_assets] Empresa: {company.name} "
                f"(pk={company.pk})"
            )
            for spec in EMPRESA_ASSETS:
                asset, created = MachineAsset.objects.get_or_create(
                    code=spec["code"],
                    defaults={
                        "company":      company,
                        "company_code": (
                            company.slug.upper()[:20]
                            if company.slug else "GEN"
                        ),
                        "company_name":     company.name,
                        "family":           spec["family"],
                        "type_code":        spec["type_code"],
                        "type_name":        spec["type_name"],
                        "brand_model":      spec["brand_model"],
                        "is_active":        True,
                        "has_odometer":     False,
                        "has_engine_hours": False,
                        "has_crane_hours":  False,
                        "first_repair":     False,
                        "mileage":          0,
                        "hours":            0,
                    },
                )
                if created:
                    created_total += 1
                    self.stdout.write(
                        f"  CREADO   : {asset.code} "
                        f"[{asset.family}]"
                    )
                else:
                    existing_total += 1
                    self.stdout.write(
                        f"  YA EXISTE: {asset.code} "
                        f"[{asset.family}]"
                    )

        self.stdout.write(
            f"\n# [seed_empresa_assets] Completado. "
            f"Creados: {created_total} | Ya existían: {existing_total}"
        )

