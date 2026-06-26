# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/ivr_config/management/commands/split_contact_names.py
"""
Management command: split_contact_names

Splits Contact.name into first_name + last_name for workshop members
and the ASISTENCIA user José Antonio Zafra.

Targets:
  - All internal Contacts belonging to a Section with
    ivr_breakdown_enabled=True.
  - Any internal Contact whose name contains 'Zafra' (case-insensitive),
    as requested for the ASISTENCIA section user.

Split logic:
  Given a full name string like 'Miguel Ángel Muñoz Cara':
    - first_name: all tokens up to (but not including) the first
      token that looks like a surname (i.e. starts with uppercase
      and is preceded by at least one token). For compound given names
      (Miguel Ángel, José Antonio, etc.) ALL leading tokens before
      the first plausible surname are kept as first_name.
    - last_name: remaining tokens after first_name.

  Heuristic: surnames in Spanish typically appear after the first 1–2
  given-name tokens. We use a configurable split_at=2 — the first 2
  tokens form the first_name, the rest form the last_name. Edge cases
  (single-word names) are handled: first_name = the single token,
  last_name = ''.

  The dry-run (-n / --dry-run) flag prints the proposed changes without
  writing anything to the database.

Usage:
  # Dry run — show proposed splits:
  python manage.py split_contact_names --dry-run

  # Apply changes:
  python manage.py split_contact_names
---
Comando de gestión: split_contact_names

Divide Contact.name en first_name + last_name para los miembros del
taller y el usuario de ASISTENCIA José Antonio Zafra.
"""

from django.core.management.base import BaseCommand

from ivr_config.models import Contact, SectionContact


def _split_name(full_name: str, split_at: int = 2):
    """
    Splits a full name string into (first_name, last_name).

    Args:
        full_name: The complete name string.
        split_at:  Number of tokens to assign to first_name (default 2).
                   Handles compound given names like 'Miguel Ángel' or
                   'José Antonio'.

    Returns:
        Tuple (first_name, last_name) — both stripped strings.
    ---
    Divide una cadena de nombre completo en (first_name, last_name).
    """
    tokens = full_name.strip().split()
    if not tokens:
        return "", ""
    if len(tokens) == 1:
        return tokens[0], ""
    # Clamp split_at to avoid IndexError.
    split_at = min(split_at, len(tokens) - 1)
    first_name = " ".join(tokens[:split_at])
    last_name  = " ".join(tokens[split_at:])
    return first_name, last_name


class Command(BaseCommand):
    """
    Splits Contact.name into first_name + last_name for workshop
    and ASISTENCIA contacts. Supports --dry-run.
    ---
    Divide Contact.name en first_name + last_name para los contactos
    del taller y de ASISTENCIA. Soporta --dry-run.
    """

    help = (
        "Divide Contact.name en first_name + last_name "
        "para miembros del taller y usuario Zafra (ASISTENCIA)."
    )

    def add_arguments(self, parser):
        """Registers the --dry-run flag."""
        parser.add_argument(
            "--dry-run",
            "-n",
            action="store_true",
            default=False,
            help="Muestra los cambios propuestos sin escribir en la BD.",
        )

    def handle(self, *args, **options):
        """
        Main entry point. Resolves target contacts, computes splits
        and either prints a dry-run report or applies the changes.
        ---
        Punto de entrada principal. Resuelve los contactos objetivo,
        calcula los splits y muestra el informe o aplica los cambios.
        """
        dry_run = options["dry_run"]

        if dry_run:
            self.stdout.write(
                self.style.WARNING("--- DRY RUN — sin cambios en BD ---\n")
            )

        # ---------------------------------------------------------------
        # Collect target contacts.
        # Recopilar contactos objetivo.
        # ---------------------------------------------------------------

        # 1. Workshop: internal Contacts in sections with
        #    ivr_breakdown_enabled=True.
        # 1. Taller: Contacts internos en secciones con
        #    ivr_breakdown_enabled=True.
        breakdown_contact_pks = set(
            SectionContact.objects.filter(
                section__ivr_breakdown_enabled=True,
            ).values_list("contact_id", flat=True)
        )
        workshop_contacts = Contact.objects.filter(
            pk__in=breakdown_contact_pks,
            is_internal=True,
        ).select_related("company")

        # 2. Zafra (ASISTENCIA): any internal Contact with 'Zafra'
        #    in their name (case-insensitive).
        # 2. Zafra (ASISTENCIA): cualquier Contact interno cuyo nombre
        #    contenga 'Zafra' (sin distinción de mayúsculas).
        zafra_contacts = Contact.objects.filter(
            is_internal=True,
            name__icontains="zafra",
        ).select_related("company")

        # Merge into a single de-duplicated queryset via union of PKs.
        # Unir en un único conjunto sin duplicados mediante unión de PKs.
        all_pks = set(
            list(workshop_contacts.values_list("pk", flat=True))
            + list(zafra_contacts.values_list("pk", flat=True))
        )
        target_contacts = Contact.objects.filter(
            pk__in=all_pks,
        ).select_related("company").order_by("company__name", "name")

        if not target_contacts.exists():
            self.stdout.write(
                self.style.WARNING("No se encontraron contactos objetivo.")
            )
            return

        # ---------------------------------------------------------------
        # Process each contact.
        # Procesar cada contacto.
        # ---------------------------------------------------------------
        updated   = 0
        skipped   = 0
        no_change = 0

        for contact in target_contacts:
            first_name, last_name = _split_name(contact.name)

            # Skip if already populated with the same values.
            # Omitir si ya están rellenos con los mismos valores.
            already_set = (
                contact.first_name == first_name
                and contact.last_name == last_name
            )
            if already_set:
                no_change += 1
                self.stdout.write(
                    f"  [SIN CAMBIO]  {contact.name!r:40s} "
                    f"— first='{contact.first_name}' "
                    f"last='{contact.last_name}'"
                )
                continue

            self.stdout.write(
                f"  {'[DRY-RUN]' if dry_run else '[ACTUALIZAR]'} "
                f"{contact.name!r:40s} → "
                f"first='{first_name}' last='{last_name}'"
            )

            if not dry_run:
                contact.first_name = first_name
                contact.last_name  = last_name
                contact.save(update_fields=["first_name", "last_name"])
                updated += 1
            else:
                skipped += 1

        # ---------------------------------------------------------------
        # Summary.
        # Resumen.
        # ---------------------------------------------------------------
        self.stdout.write("")
        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f"--- DRY RUN completado — "
                    f"{skipped} para actualizar, "
                    f"{no_change} sin cambio ---"
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f"--- Completado — "
                    f"{updated} actualizado/s, "
                    f"{no_change} sin cambio ---"
                )
            )
