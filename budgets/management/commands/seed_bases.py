# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/budgets/management/commands/seed_bases.py
"""
Management command: seed_bases.
Parses the notes field of every active Insurer and creates Base records
for each locality found. Bases are extracted from the pattern:
  "Base: X." or "Bases: X, Y, Z."
Idempotent: safe to run multiple times. Uses get_or_create so existing
bases are not duplicated.
Supports --dry-run flag to preview changes without writing to the database.
---
Comando de gestion: seed_bases.
Parsea el campo notes de cada Insurer activo y crea registros Base
para cada localidad encontrada. Las bases se extraen del patron:
  "Base: X." o "Bases: X, Y, Z."
Idempotente: seguro para ejecutar multiples veces. Usa get_or_create
para no duplicar bases existentes.
Soporta el flag --dry-run para previsualizar sin escribir en la BD.
"""

import re

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from budgets.models import Base, Insurer


# ---------------------------------------------------------------------------
# Municipality map — maps locality name (from notes) to municipality
# for the sync_base_calendars command and future geocoding.
# Mapa de municipios — relaciona nombre de localidad (de notes) con municipio
# para el comando sync_base_calendars y geocodificacion futura.
# ---------------------------------------------------------------------------

MUNICIPALITY_MAP: dict[str, str] = {
    "Antequera":             "Antequera",
    "Carratraca":            "Carratraca",
    "Coin":                  "Coin",
    "Fuengirola":            "Fuengirola",
    "La Roda de Andalucia":  "La Roda de Andalucia",
    "Loja":                  "Loja",
    "Malaga":                "Malaga",
    "Marbella":              "Marbella",
    "Moraleda":              "Moraleda de Zafayona",
    "Saula Rosalia":         "Malaga",
    "Velez Malaga":          "Velez-Malaga",
    "Villanueva del Cauche": "Villanueva del Cauche",
}


def _parse_bases(notes: str) -> list[str]:
    """
    Extract locality names from the notes field of an Insurer.
    Supports both singular ('Base: X.') and plural ('Bases: X, Y, Z.') forms.
    Returns a list of stripped locality name strings.
    ---
    Extrae nombres de localidades del campo notes de un Insurer.
    Soporta las formas singular ('Base: X.') y plural ('Bases: X, Y, Z.').
    Devuelve una lista de cadenas de nombre de localidad limpias.
    """
    if not notes:
        return []
    match = re.search(r"Bases?:\s*([^.]+)", notes, re.IGNORECASE)
    if not match:
        return []
    raw = match.group(1)
    return [b.strip() for b in raw.split(",") if b.strip()]


class Command(BaseCommand):
    """
    Seed Base records from Insurer.notes field.
    ---
    Sembrar registros Base desde el campo Insurer.notes.
    """

    help = (
        "Crea registros Base parseando el campo notes de cada Insurer activo. "
        "Idempotente. Usa --dry-run para previsualizar sin escribir."
    )

    def add_arguments(self, parser):
        """
        Register --dry-run flag.
        ---
        Registra el flag --dry-run.
        """
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=False,
            dest="dry_run",
            help="Previsualiza los cambios sin escribir en la base de datos.",
        )

    def handle(self, *args, **options):
        """
        Main handler. Iterates active insurers, parses bases from notes
        and creates Base records via get_or_create.
        ---
        Manejador principal. Itera aseguradoras activas, parsea bases de notes
        y crea registros Base via get_or_create.
        """
        dry_run = options["dry_run"]

        if dry_run:
            self.stdout.write("# MODO DRY-RUN — no se escribira en la base de datos.")

        insurers = Insurer.objects.filter(is_active=True).order_by("code")
        total = insurers.count()
        self.stdout.write(f"# Procesando {total} aseguradoras activas...")

        created_count = 0
        skipped_count = 0
        unknown_count = 0
        error_count = 0

        try:
            with transaction.atomic():
                for insurer in insurers:
                    localities = _parse_bases(insurer.notes)
                    if not localities:
                        self.stdout.write(
                            f"  [SIN BASES] {insurer.code} — notes sin patron Base/Bases."
                        )
                        continue

                    for locality in localities:
                        municipality = MUNICIPALITY_MAP.get(locality)
                        if municipality is None:
                            self.stderr.write(
                                f"  [DESCONOCIDO] {insurer.code} — localidad "
                                f"'{locality}' no en MUNICIPALITY_MAP. Anadir manualmente."
                            )
                            unknown_count += 1
                            municipality = locality

                        if not dry_run:
                            _, base_created = Base.objects.get_or_create(
                                insurer=insurer,
                                name=locality,
                                defaults={
                                    "municipality": municipality,
                                    "is_active": True,
                                },
                            )
                            if base_created:
                                created_count += 1
                                self.stdout.write(
                                    f"  [CREADA] {insurer.code} — {locality} ({municipality})"
                                )
                            else:
                                skipped_count += 1
                                self.stdout.write(
                                    f"  [EXISTE]  {insurer.code} — {locality}"
                                )
                        else:
                            self.stdout.write(
                                f"  [DRY-RUN] {insurer.code} — {locality} ({municipality})"
                            )
                            created_count += 1

                if dry_run:
                    raise _DryRunRollback()

        except _DryRunRollback:
            self.stdout.write("# Dry-run completado — transaccion revertida.")

        except Exception as exc:
            raise CommandError(f"Error durante el sembrado: {exc}") from exc

        self.stdout.write("")
        self.stdout.write("# --- RESUMEN ---")
        self.stdout.write(f"# Bases creadas:      {created_count}")
        self.stdout.write(f"# Bases ya existentes: {skipped_count}")
        self.stdout.write(f"# Localidades desconocidas: {unknown_count}")
        if not dry_run:
            self.stdout.write("# Sembrado completado correctamente.")


class _DryRunRollback(Exception):
    """
    Internal sentinel to roll back dry-run transaction.
    ---
    Centinela interno para revertir la transaccion dry-run.
    """
