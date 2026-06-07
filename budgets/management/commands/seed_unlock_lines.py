# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/budgets/management/commands/seed_unlock_lines.py
"""
Management command: seed_unlock_lines
Ensures every registered InsurerTariff has a generic UNLOCK TariffLine.
Idempotent: skips tariffs that already have an UNLOCK line.
Tariffs without a registered price (RACE pk=86, Petit Forestier pk=101)
are skipped and must be configured manually from the panel.

---

Comando de gestión: seed_unlock_lines
Garantiza que cada InsurerTariff registrada tenga una TariffLine genérica UNLOCK.
Idempotente: omite las tarifas que ya tienen línea UNLOCK.
Las tarifas sin precio registrado (RACE pk=86, Petit Forestier pk=101)
se omiten y deben configurarse manualmente desde el panel.
"""

from decimal import Decimal

from django.core.management.base import BaseCommand

from budgets.models import InsurerTariff, TariffLine


# ---------------------------------------------------------------------------
# Price registry — tariff_pk: unlock price in EUR
# Registro de precios — tariff_pk: precio de desbloqueo en EUR
# ---------------------------------------------------------------------------

UNLOCK_PRICES = {
    # Tariffs that already have an UNLOCK line in DB — included for audit.
    # Tarifas que ya tienen línea UNLOCK en BD — incluidas para auditoría.
    79:  Decimal("53.75"),   # Mondial / Transgrual
    83:  Decimal("52.20"),   # Asitur / Transgrual
    84:  Decimal("62.80"),   # TAI / Asistencia y Gruas Granada
    85:  Decimal("62.80"),   # TAI / Gruas Alvarez / Grualdi
    87:  Decimal("54.03"),   # Mapfre / Gruas Alvarez
    88:  Decimal("54.03"),   # Mapfre / Asistencia y Gruas Granada
    89:  Decimal("55.00"),   # Mondial / Gruas Alvarez
    95:  Decimal("59.80"),   # Inter Partner / Transgrual
    96:  Decimal("61.52"),   # Zurich - RACC / Transgrual
    97:  Decimal("50.56"),   # RACC - Zurich / Transgrual
    98:  Decimal("50.56"),   # RACC - Zurich / Asistencia y Gruas Granada
    99:  Decimal("61.52"),   # Zurich - RACC / Asistencia y Gruas Granada
    102: Decimal("65.00"),   # COVEI / Gruas Alvarez
    103: Decimal("60.00"),   # Prosegur / Transgrual
    104: Decimal("65.00"),   # F.C.C. / Gruas Alvarez
    110: Decimal("65.00"),   # UTE Envases Ligeros / Gruas Alvarez
    # Tariffs missing UNLOCK line — added by this seed.
    # Tarifas sin línea UNLOCK — añadidas por este seed.
    80:  Decimal("45.00"),   # Europ Assistance / Asistencia y Gruas Granada
    81:  Decimal("45.00"),   # Europ Assistance / Transgrual
    82:  Decimal("49.58"),   # ARAG / Transgrual (Quitar Transmisión)
    90:  Decimal("80.00"),   # Avinatan / Transgrual (Quitar Transmisión)
    91:  Decimal("80.00"),   # Asistencia Tecnica Europea / Transgrual (Quitar Transmisión)
    92:  Decimal("80.00"),   # Treasca / Transgrual (Quitar Transmisión)
    93:  Decimal("80.00"),   # IMA Iberica / Prestima / Gruas Alvarez (Quitar Transmisión)
    94:  Decimal("57.00"),   # Servireac SVR / Transgrual (equivalente a 1h trabajo)
    100: Decimal("78.00"),   # MAN Truck / Gruas Alvarez
    105: Decimal("68.00"),   # TVA ALSA / Gruas Alvarez (equivalente a hora espera)
    106: Decimal("68.00"),   # Selltruck Ford / Transgrual (equivalente a hora espera)
    107: Decimal("68.00"),   # Scora / Transgrual (equivalente a hora espera)
    108: Decimal("68.00"),   # Veinluc / Transgrual (equivalente a hora espera)
    109: Decimal("65.00"),   # Angal Truck / Gruas Alvarez
    # SKIPPED — no price available in tariff documents:
    # OMITIDOS — sin precio en los documentos de tarifa:
    #   86  RACE / Transgrual
    #   101 Petit Forestier / Gruas Alvarez
}

# Tariffs without registered price — must be configured manually.
# Tarifas sin precio registrado — deben configurarse manualmente.
NO_PRICE_PKS = [86, 101]


class Command(BaseCommand):
    """
    Seed generic UNLOCK TariffLine records for all registered InsurerTariff.
    Run with --dry-run to preview without writing to the database.
    ---
    Siembra registros TariffLine UNLOCK genéricos para todas las InsurerTariff
    registradas. Ejecutar con --dry-run para previsualizar sin escribir en BD.
    """

    help = (
        "Seed generic UNLOCK TariffLine for all registered InsurerTariff records. "
        "Idempotent. Use --dry-run to preview."
    )

    def add_arguments(self, parser):
        """
        Register the optional --dry-run flag.
        ---
        Registra el flag opcional --dry-run.
        """
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Preview changes without writing to the database.",
        )

    def handle(self, *args, **options):
        """
        Iterate over UNLOCK_PRICES, skip tariffs already having an UNLOCK line,
        skip tariffs not found in DB, and create missing TariffLine records.
        Report NO_PRICE_PKS separately regardless of their current state.
        ---
        Itera sobre UNLOCK_PRICES, omite tarifas que ya tienen línea UNLOCK,
        omite tarifas no encontradas en BD, y crea los registros TariffLine
        faltantes. Informa de NO_PRICE_PKS por separado.
        """
        dry_run = options["dry_run"]
        created = 0
        already_present = 0
        skipped_no_tariff = 0

        for tariff_pk, price in sorted(UNLOCK_PRICES.items()):
            # Resolve tariff record — may not exist if pk drifted.
            # Resolver registro de tarifa — puede no existir si el pk cambió.
            try:
                tariff = InsurerTariff.objects.select_related("insurer").get(
                    pk=tariff_pk
                )
            except InsurerTariff.DoesNotExist:
                self.stdout.write(
                    self.style.WARNING(
                        f"# [SKIP] tariff pk={tariff_pk} no encontrada en BD."
                    )
                )
                skipped_no_tariff += 1
                continue

            insurer_label = tariff.insurer.name

            # Check if a generic UNLOCK line already exists for this tariff.
            # Comprobar si ya existe una línea UNLOCK genérica para esta tarifa.
            already = TariffLine.objects.filter(
                tariff=tariff,
                concept=TariffLine.CONCEPT_UNLOCK,
                vehicle_type__isnull=True,
            ).exists()

            if already:
                self.stdout.write(
                    f"# [OK]   tariff={tariff_pk} '{insurer_label}' "
                    f"— UNLOCK ya presente ({price} EUR)."
                )
                already_present += 1
                continue

            if dry_run:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"# [DRY]  tariff={tariff_pk} '{insurer_label}' "
                        f"— se crearía UNLOCK FIXED {price} EUR."
                    )
                )
                created += 1
                continue

            # Create the missing UNLOCK TariffLine.
            # Crear la TariffLine UNLOCK faltante.
            TariffLine.objects.create(
                tariff=tariff,
                vehicle_type=None,
                concept=TariffLine.CONCEPT_UNLOCK,
                unit=TariffLine.UNIT_FIXED,
                price=price,
                min_units=None,
                km_threshold=None,
            )
            self.stdout.write(
                self.style.SUCCESS(
                    f"# [NEW]  tariff={tariff_pk} '{insurer_label}' "
                    f"— UNLOCK FIXED {price} EUR creada."
                )
            )
            created += 1

        # Report tariffs without registered price.
        # Informar de tarifas sin precio registrado.
        for pk in NO_PRICE_PKS:
            try:
                tariff = InsurerTariff.objects.select_related("insurer").get(pk=pk)
                has_unlock = TariffLine.objects.filter(
                    tariff=tariff,
                    concept=TariffLine.CONCEPT_UNLOCK,
                ).exists()
                status = (
                    "ya tiene UNLOCK"
                    if has_unlock
                    else "SIN UNLOCK — configurar manualmente desde el panel"
                )
                self.stdout.write(
                    self.style.WARNING(
                        f"# [SKIP] tariff={pk} '{tariff.insurer.name}' — {status}."
                    )
                )
            except InsurerTariff.DoesNotExist:
                self.stdout.write(
                    self.style.WARNING(
                        f"# [SKIP] tariff={pk} no encontrada en BD."
                    )
                )

        # Summary / Resumen.
        self.stdout.write("")
        self.stdout.write(
            f"# Resumen: creadas={created} ya_presentes={already_present} "
            f"sin_tarifa={skipped_no_tariff} sin_precio={len(NO_PRICE_PKS)}"
        )
        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    "# Modo --dry-run activo. No se escribió nada en BD."
                )
            )
