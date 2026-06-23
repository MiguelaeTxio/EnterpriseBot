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

  EMPRESA_TALLER_MECANICO      → family MOVILES
  EMPRESA_TALLER_ELEVACION     → family PLATAFOR
  EMPRESA_TALLER_HUELVA        → family HUELVA
  EMPRESA_ALMACEN_MECANICO     → family MOVILES   (almacén taller mecánico)
  EMPRESA_ALMACEN_ELEVACION    → family PLATAFOR  (almacén taller elevación)
  EMPRESA_ALMACEN_HUELVA       → family HUELVA    (almacén taller Huelva)
  EMPRESA_ALMACEN_DEPENDENCIAS → family DEPENDENCIAS
  EMPRESA_DEPENDENCIAS         → family DEPENDENCIAS

NOTE: The legacy EMPRESA_ALMACEN (generic) is deactivated by this command
if found, to avoid entries being misclassified into a catch-all bucket.

---

Crea (o verifica) los registros MachineAsset especiales EMPRESA_*.
El activo genérico EMPRESA_ALMACEN se desactiva si existe.
Idempotente.

Uso:
  python3 -m dotenv run python3 manage.py seed_empresa_assets
"""

from django.core.management.base import BaseCommand

from fleet.models import MachineAsset
from ivr_config.models import Company


EMPRESA_ASSETS = [
    # -- Talleres / Workshops ------------------------------------------
    {
        "code":        "EMPRESA_TALLER_MECANICO",
        "family":      "MOVILES",
        "type_code":   "EMPRESA",
        "type_name":   "Centro de gasto — Empresa / Taller Mecánico",
        "brand_model": "Gastos generales — Taller Mecánico",
    },
    {
        "code":        "EMPRESA_TALLER_ELEVACION",
        "family":      "PLATAFOR",
        "type_code":   "EMPRESA",
        "type_name":   "Centro de gasto — Empresa / Taller Elevación",
        "brand_model": "Gastos generales — Taller Elevación",
    },
    {
        "code":        "EMPRESA_TALLER_HUELVA",
        "family":      "HUELVA",
        "type_code":   "EMPRESA",
        "type_name":   "Centro de gasto — Empresa / Taller Huelva",
        "brand_model": "Gastos generales — Taller Huelva",
    },
    # -- Almacenes / Warehouses ----------------------------------------
    {
        "code":        "EMPRESA_ALMACEN_MECANICO",
        "family":      "MOVILES",
        "type_code":   "EMPRESA",
        "type_name":   "Centro de gasto — Empresa / Almacén Taller Mecánico",
        "brand_model": "Gastos generales — Almacén Taller Mecánico",
    },
    {
        "code":        "EMPRESA_ALMACEN_ELEVACION",
        "family":      "PLATAFOR",
        "type_code":   "EMPRESA",
        "type_name":   "Centro de gasto — Empresa / Almacén Taller Elevación",
        "brand_model": "Gastos generales — Almacén Taller Elevación",
    },
    {
        "code":        "EMPRESA_ALMACEN_HUELVA",
        "family":      "HUELVA",
        "type_code":   "EMPRESA",
        "type_name":   "Centro de gasto — Empresa / Almacén Taller Huelva",
        "brand_model": "Gastos generales — Almacén Taller Huelva",
    },
    {
        "code":        "EMPRESA_ALMACEN_DEPENDENCIAS",
        "family":      "DEPENDENCIAS",
        "type_code":   "EMPRESA",
        "type_name":   "Centro de gasto — Empresa / Almacén Dependencias",
        "brand_model": "Gastos generales — Almacén Dependencias",
    },
    # -- Dependencias / Admin ------------------------------------------
    {
        "code":        "EMPRESA_DEPENDENCIAS",
        "family":      "DEPENDENCIAS",
        "type_code":   "EMPRESA",
        "type_name":   "Centro de gasto — Empresa / Dependencias",
        "brand_model": "Gastos generales — Dependencias (Administración, Larios…)",
    },
]

# Legacy generic asset to deactivate.
# Activo genérico legado a desactivar.
LEGACY_ALMACEN_CODE = "EMPRESA_ALMACEN"

# Subtype options injected into EB_CONFIG for the JS dropdown.
# Opciones de subtipo inyectadas en EB_CONFIG para el desplegable JS.
#
# Keys: prefix of EMPRESA_* code → list of {label, requires_note}.
# All subtypes require a note (repair_notes mandatory).
#
# Claves: prefijo del código EMPRESA_* → lista de {label, requires_note}.
# Todos los subtipos requieren nota (repair_notes obligatorio).
EMPRESA_SUBTYPES = {
    "taller": [
        {"label": "Orden y limpieza", "requires_note": True},
        {"label": "Reparación",       "requires_note": True},
        {"label": "Otros",            "requires_note": True},
    ],
    "almacen": [
        {"label": "Orden y limpieza", "requires_note": True},
        {"label": "Reparación",       "requires_note": True},
        {"label": "Inventario",       "requires_note": True},
        {"label": "Otros",            "requires_note": True},
    ],
    "dependencias": [
        {"label": "Orden y limpieza", "requires_note": True},
        {"label": "Reparación",       "requires_note": True},
        {"label": "Otros",            "requires_note": True},
    ],
}


def get_empresa_subtype_group(code):
    """
    Returns the EMPRESA_SUBTYPES key for the given asset code.
    Used by views to inject the correct subtype list into context.
    ---
    Devuelve la clave de EMPRESA_SUBTYPES para el código de activo dado.
    Usada por las vistas para inyectar la lista de subtipos correcta.
    """
    code_upper = code.upper()
    if "ALMACEN" in code_upper:
        return "almacen"
    if "DEPENDENCIAS" in code_upper:
        return "dependencias"
    return "taller"


class Command(BaseCommand):
    """
    Seeds the EMPRESA_* MachineAssets for each active company.
    Deactivates the legacy EMPRESA_ALMACEN generic asset.
    ---
    Crea los MachineAsset EMPRESA_* para cada empresa activa.
    Desactiva el activo genérico legado EMPRESA_ALMACEN.
    """

    help = (
        "Crea los centros de gasto EMPRESA_* para cada empresa activa si no "
        "existen. Desactiva EMPRESA_ALMACEN genérico. Idempotente."
    )

    def handle(self, *args, **options):
        """
        Main entry point. Deactivates the legacy generic asset, then
        iterates over active companies and creates each EMPRESA_* asset
        if it does not already exist.
        ---
        Punto de entrada principal. Desactiva el activo genérico legado,
        luego itera sobre las empresas activas y crea cada activo EMPRESA_*
        si no existe todavía.
        """
        # Step 0 — deactivate legacy generic EMPRESA_ALMACEN.
        # Paso 0 — desactivar EMPRESA_ALMACEN genérico legado.
        legacy_qs = MachineAsset.objects.filter(
            code=LEGACY_ALMACEN_CODE,
            is_active=True,
        )
        legacy_count = legacy_qs.update(is_active=False)
        if legacy_count:
            self.stdout.write(
                f"# [seed_empresa_assets] DESACTIVADO: "
                f"{LEGACY_ALMACEN_CODE} ({legacy_count} registro/s)"
            )
        else:
            self.stdout.write(
                f"# [seed_empresa_assets] {LEGACY_ALMACEN_CODE} "
                f"ya estaba inactivo o no existe — sin cambios."
            )

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
                        "company":          company,
                        "company_code":     (
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
                        f"  CREADO   : {asset.code} [{asset.family}]"
                    )
                else:
                    existing_total += 1
                    # Ensure existing asset is active.
                    # Asegurar que el activo existente está activo.
                    if not asset.is_active:
                        asset.is_active = True
                        asset.save(update_fields=["is_active"])
                        self.stdout.write(
                            f"  REACTIVADO: {asset.code} [{asset.family}]"
                        )
                    else:
                        self.stdout.write(
                            f"  YA EXISTE: {asset.code} [{asset.family}]"
                        )

        self.stdout.write(
            f"\n# [seed_empresa_assets] Completado. "
            f"Creados: {created_total} | Ya existían: {existing_total}"
        )
