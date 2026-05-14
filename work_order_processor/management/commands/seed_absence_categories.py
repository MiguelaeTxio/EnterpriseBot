# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/work_order_processor/management/commands/seed_absence_categories.py
"""
Management command: seed_absence_categories
Preloads the standard AbsenceCategory catalogue for a given Company.
Idempotent: uses get_or_create keyed on (company, code) so repeated
runs are safe and do not produce duplicates.
---
Comando de gestión: seed_absence_categories
Precarga el catálogo estándar de AbsenceCategory para una Company dada.
Idempotente: usa get_or_create con clave (company, code) para que
ejecuciones repetidas sean seguras y no produzcan duplicados.
"""

from django.core.management.base import BaseCommand, CommandError


# ---------------------------------------------------------------------------
# Standard absence category definitions / Definiciones de categorías estándar
# ---------------------------------------------------------------------------
# Each dict maps to the AbsenceCategory model fields.
# Cada dict se corresponde con los campos del modelo AbsenceCategory.
# ---------------------------------------------------------------------------

_STANDARD_CATEGORIES = [
    {
        "code":          "MEDICAL",
        "label":         "Médico",
        "requires_note": False,
        "is_justified":  True,
        "order":         0,
    },
    {
        "code":          "PERSONAL_MATTERS",
        "label":         "Asuntos propios",
        "requires_note": False,
        "is_justified":  True,
        "order":         1,
    },
    {
        "code":          "VEHICLE_BREAKDOWN",
        "label":         "Avería del vehículo",
        "requires_note": True,
        "is_justified":  False,
        "order":         2,
    },
    {
        "code":          "SICK_LEAVE",
        "label":         "Baja médica",
        "requires_note": False,
        "is_justified":  True,
        "order":         3,
    },
    {
        "code":          "DAY_OFF",
        "label":         "Día libre",
        "requires_note": False,
        "is_justified":  True,
        "order":         4,
    },
    {
        "code":          "UNJUSTIFIED",
        "label":         "Falta sin justificante",
        "requires_note": True,
        "is_justified":  False,
        "order":         5,
    },
    {
        "code":          "OTHER",
        "label":         "Otro motivo",
        "requires_note": True,
        "is_justified":  False,
        "order":         6,
    },
]


class Command(BaseCommand):
    """
    Preloads the standard AbsenceCategory records for a given Company.
    Existing records (matched by company + code) are left untouched.
    New records are created with is_active=True.

    Usage:
        python manage.py seed_absence_categories --company-pk <pk>

    ---

    Precarga los registros AbsenceCategory estándar para una Company dada.
    Los registros existentes (identificados por company + code) no se modifican.
    Los registros nuevos se crean con is_active=True.

    Uso:
        python manage.py seed_absence_categories --company-pk <pk>
    """

    help = (
        "Precarga las categorías de ausencia estándar para una empresa. "
        "Idempotente: no duplica registros existentes."
    )

    def add_arguments(self, parser):
        """
        Registers the --company-pk required argument.
        ---
        Registra el argumento obligatorio --company-pk.
        """
        parser.add_argument(
            "--company-pk",
            type=int,
            required=True,
            help="Clave primaria (pk) de la empresa para la que se precargan las categorías.",
        )

    def handle(self, *args, **options):
        """
        Resolves the Company by pk and creates the standard AbsenceCategory
        records using get_or_create to guarantee idempotency.
        Reports each record as created or already existing.
        ---
        Resuelve la Company por pk y crea los registros AbsenceCategory
        estándar usando get_or_create para garantizar idempotencia.
        Informa de cada registro como creado o ya existente.
        """
        from ivr_config.models import Company, AbsenceCategory

        company_pk = options["company_pk"]

        # ------------------------------------------------------------------
        # Resolve Company by pk.
        # Resolver Company por pk.
        # ------------------------------------------------------------------
        try:
            company = Company.objects.get(pk=company_pk)
        except Company.DoesNotExist:
            raise CommandError(
                f"# No se encontró ninguna empresa con pk={company_pk}."
            )

        self.stdout.write(
            f"# Empresa resuelta: '{company.name}' (pk={company.pk})"
        )
        self.stdout.write(
            f"# Precargando {len(_STANDARD_CATEGORIES)} categorías estándar…"
        )

        created_count  = 0
        existing_count = 0

        for cat_data in _STANDARD_CATEGORIES:
            obj, created = AbsenceCategory.objects.get_or_create(
                company = company,
                code    = cat_data["code"],
                defaults = {
                    "label":         cat_data["label"],
                    "requires_note": cat_data["requires_note"],
                    "is_justified":  cat_data["is_justified"],
                    "order":         cat_data["order"],
                    "is_active":     True,
                },
            )
            if created:
                created_count += 1
                self.stdout.write(
                    f"  # [CREADA]   {obj.code:25s} — {obj.label}"
                )
            else:
                existing_count += 1
                self.stdout.write(
                    f"  # [EXISTENTE] {obj.code:25s} — {obj.label}"
                )

        # ------------------------------------------------------------------
        # Summary / Resumen
        # ------------------------------------------------------------------
        self.stdout.write(
            f"# Proceso completado: {created_count} creadas, "
            f"{existing_count} ya existentes."
        )
