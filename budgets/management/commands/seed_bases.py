# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/budgets/management/commands/seed_bases.py
"""
Management command: seed_bases.
Parses the notes field of every active Insurer and creates Base records
for each locality found, then links them via InsurerBase.
Bases are extracted from the pattern:
  "Base: X." or "Bases: X, Y, Z."
Idempotent: safe to run multiple times. Uses get_or_create so existing
bases and relations are not duplicated.
Supports --dry-run flag to preview changes without writing to the database.
---
Comando de gestion: seed_bases.
Parsea el campo notes de cada Insurer activo y crea registros Base
para cada localidad encontrada, luego los vincula via InsurerBase.
Las bases se extraen del patron:
  "Base: X." o "Bases: X, Y, Z."
Idempotente: seguro para ejecutar multiples veces. Usa get_or_create
para no duplicar bases ni relaciones existentes.
Soporta el flag --dry-run para previsualizar sin escribir en la BD.
"""

import re

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from budgets.models import Base, Insurer, InsurerBase


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
    Seed Base records from Insurer.notes field and link them via InsurerBase.
    ---
    Sembrar registros Base desde el campo Insurer.notes y vincularlos via InsurerBase.
    """

    help = (
        "Crea registros Base parseando el campo notes de cada Insurer activo "
        "y los vincula a cada aseguradora via InsurerBase. "
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
        Main handler. Iterates active insurers, parses bases from notes,
        creates Base records scoped to company and creates InsurerBase relations.
        ---
        Manejador principal. Itera aseguradoras activas, parsea bases de notes,
        crea registros Base con ambito de empresa y crea relaciones InsurerBase.
        """
        dry_run = options["dry_run"]

        if dry_run:
            self.stdout.write("# MODO DRY-RUN — no se escribira en la base de datos.")

        insurers = Insurer.objects.filter(
            is_active=True,
        ).select_related("company").order_by("code")
        total = insurers.count()
        self.stdout.write(f"# Procesando {total} aseguradoras activas...")

        bases_created      = 0
        bases_skipped      = 0
        relations_created  = 0
        relations_skipped  = 0
        unknown_count      = 0

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

                        if dry_run:
                            self.stdout.write(
                                f"  [DRY-RUN] {insurer.code} — Base '{locality}' "
                                f"({municipality}) + InsurerBase"
                            )
                            bases_created += 1
                            relations_created += 1
                            continue

                        # Step 1 — Get or create the Base entity scoped to company.
                        # Paso 1 — Obtener o crear la entidad Base con ambito de empresa.
                        base, base_created = Base.objects.get_or_create(
                            company=insurer.company,
                            name=locality,
                            defaults={
                                "municipality": municipality,
                                "is_active": True,
                            },
                        )
                        if base_created:
                            bases_created += 1
                            self.stdout.write(
                                f"  [BASE CREADA]    {insurer.code} — '{locality}' ({municipality})"
                            )
                        else:
                            bases_skipped += 1
                            self.stdout.write(
                                f"  [BASE EXISTE]    {insurer.code} — '{locality}'"
                            )

                        # Step 2 — Get or create the InsurerBase relation.
                        # Paso 2 — Obtener o crear la relacion InsurerBase.
                        _, ib_created = InsurerBase.objects.get_or_create(
                            insurer=insurer,
                            base=base,
                            defaults={"is_active": True},
                        )
                        if ib_created:
                            relations_created += 1
                            self.stdout.write(
                                f"  [RELACION CREADA] {insurer.code} <-> '{locality}'"
                            )
                        else:
                            relations_skipped += 1
                            self.stdout.write(
                                f"  [RELACION EXISTE] {insurer.code} <-> '{locality}'"
                            )

                if dry_run:
                    raise _DryRunRollback()

        except _DryRunRollback:
            self.stdout.write("# Dry-run completado — transaccion revertida.")

        except Exception as exc:
            raise CommandError(f"Error durante el sembrado: {exc}") from exc

        self.stdout.write("")
        self.stdout.write("# --- RESUMEN ---")
        self.stdout.write(f"# Bases creadas:            {bases_created}")
        self.stdout.write(f"# Bases ya existentes:      {bases_skipped}")
        self.stdout.write(f"# Relaciones creadas:       {relations_created}")
        self.stdout.write(f"# Relaciones ya existentes: {relations_skipped}")
        self.stdout.write(f"# Localidades desconocidas: {unknown_count}")
        if not dry_run:
            self.stdout.write("# Sembrado completado correctamente.")


class _DryRunRollback(Exception):
    """
    Internal sentinel to roll back dry-run transaction.
    ---
    Centinela interno para revertir la transaccion dry-run.
    """
