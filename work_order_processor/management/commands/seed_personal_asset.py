# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/work_order_processor/management/commands/seed_personal_asset.py
"""
Management command: seed_personal_asset
========================================
Creates (or verifies) the special MachineAsset record used as the
"Personal" cost centre for absence work-order blocks.

This asset has a reserved code (PERSONAL) that the digital form
recognises to switch the block UI from repair mode to absence mode,
showing an AbsenceCategory dropdown instead of fault/repair fields.

The command is idempotent: running it more than once has no effect
if the asset already exists for the company.

Usage:
  python3 -m dotenv run python3 manage.py seed_personal_asset

---

Crea (o verifica) el registro MachineAsset especial usado como centro
de gasto "Personal" para los bloques de ausencia en partes digitales.

Este activo tiene un codigo reservado (PERSONAL) que el formulario digital
reconoce para cambiar la interfaz del bloque de modo reparacion a modo
ausencia, mostrando un desplegable de AbsenceCategory en lugar de los
campos de averia/reparacion.

El comando es idempotente: ejecutarlo mas de una vez no tiene efecto si
el activo ya existe para la empresa.

Uso:
  python3 -m dotenv run python3 manage.py seed_personal_asset
"""

from django.core.management.base import BaseCommand

from fleet.models import MachineAsset
from ivr_config.models import Company

PERSONAL_ASSET_CODE = "PERSONAL"


class Command(BaseCommand):
    """
    Seeds the PERSONAL MachineAsset for each active company.
    ---
    Crea el MachineAsset PERSONAL para cada empresa activa.
    """

    help = (
        "Crea el centro de gasto PERSONAL para cada empresa activa si no existe. "
        "Idempotente."
    )

    def handle(self, *args, **options):
        """
        Main entry point. Iterates over active companies and creates the
        PERSONAL asset if it does not already exist.
        ---
        Punto de entrada principal. Itera sobre las empresas activas y crea
        el activo PERSONAL si no existe todavia.
        """
        companies = Company.objects.filter(is_active=True)
        created_count = 0
        existing_count = 0

        for company in companies:
            asset, created = MachineAsset.objects.get_or_create(
                code=PERSONAL_ASSET_CODE,
                defaults={
                    "company":      company,
                    "company_code": company.slug.upper()[:20] if company.slug else "GEN",
                    "company_name": company.name,
                    "family":       "PERSONAL",
                    "type_code":    "PERSONAL",
                    "type_name":    "Centro de gasto — Ausencias de personal",
                    "brand_model":  "Ausencia / Incidencia de personal",
                    "is_active":    True,
                    "has_odometer":     False,
                    "has_engine_hours": False,
                    "has_crane_hours":  False,
                    "first_repair":     False,
                    "mileage":          0,
                    "hours":            0,
                },
            )
            if created:
                created_count += 1
                self.stdout.write(
                    f"# [seed_personal_asset] CREADO: {asset.code} "
                    f"para empresa '{company.name}' (pk={company.pk})"
                )
            else:
                existing_count += 1
                self.stdout.write(
                    f"# [seed_personal_asset] YA EXISTE: {asset.code} "
                    f"para empresa '{company.name}' (pk={company.pk})"
                )

        self.stdout.write(
            f"# [seed_personal_asset] Completado. "
            f"Creados: {created_count} | Ya existian: {existing_count}"
        )
