"""
Management command: seed_dni_pin
=================================
Sets the password of every active WORKSHOP and DRIVER CompanyUser to
the last 4 digits of their DNI field, enabling PIN-based login.

Behaviour
---------
- Targets roles WORKSHOP and DRIVER only.
- Skips users whose DNI field is blank or shorter than 4 characters.
- Extracts the last 4 *digit* characters from the DNI string (ignores
  trailing letter, e.g. "12345678Z" → "5678"; "12345678" → "5678").
- Calls user.set_password(pin) and saves the auth.User.
- Sets must_change_password=False so the operator is not redirected to
  the password-change screen on first login.
- Idempotent: can be run multiple times safely. Each run overwrites the
  password with the current DNI-derived PIN — useful after a DNI is
  corrected in the database.
- Dry-run mode (--dry-run): prints what would happen without writing.

Usage
-----
  python manage.py seed_dni_pin [--dry-run] [--company <slug_or_pk>]

Options
-------
  --dry-run         Print actions without applying changes.
  --company         Restrict to a specific company (slug or pk).
                    If omitted, processes all companies.

---

Comando de gestión: seed_dni_pin
=================================
Establece la contraseña de cada CompanyUser activo con rol WORKSHOP o
DRIVER a los 4 últimos dígitos de su campo DNI, habilitando el acceso
mediante PIN.

Comportamiento
--------------
- Solo afecta a los roles WORKSHOP y DRIVER.
- Omite usuarios con DNI vacío o con menos de 4 caracteres.
- Extrae los 4 últimos *dígitos* del DNI (ignora la letra final,
  p.ej. "12345678Z" → "5678"; "12345678" → "5678").
- Llama a user.set_password(pin) y guarda el auth.User.
- Establece must_change_password=False para que el operario no sea
  redirigido al cambio de contraseña en el primer acceso.
- Idempotente: se puede ejecutar varias veces sin riesgo. Cada
  ejecución sobreescribe con el PIN derivado del DNI actual.
- Modo simulación (--dry-run): muestra lo que haría sin escribir.

Uso
---
  python manage.py seed_dni_pin [--dry-run] [--company <slug_o_pk>]

Opciones
--------
  --dry-run         Mostrar acciones sin aplicar cambios.
  --company         Restringir a una empresa concreta (slug o pk).
                    Si se omite, procesa todas las empresas.
"""

from django.core.management.base import BaseCommand, CommandError
from ivr_config.models import CompanyUser


_TARGET_ROLES = {CompanyUser.ROLE_WORKSHOP, CompanyUser.ROLE_DRIVER}


def _extract_pin(dni: str) -> str | None:
    """
    Returns the last 4 digit characters from the DNI string, or None
    if fewer than 4 digits are present.

    Examples:
      "12345678Z" → "5678"
      "12345678"  → "5678"
      "A123"      → "1234"  (4 digits exactly)
      "12Z"       → None    (only 2 digits)
      ""          → None
    ---
    Devuelve los 4 últimos caracteres dígito del DNI, o None si hay
    menos de 4 dígitos en la cadena.
    """
    digits = [ch for ch in dni if ch.isdigit()]
    if len(digits) < 4:
        return None
    return "".join(digits[-4:])


class Command(BaseCommand):
    help = (
        "Sets the password of WORKSHOP and DRIVER users to the last "
        "4 digits of their DNI. Enables PIN-based login."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=False,
            help="Print what would be done without applying changes.",
        )
        parser.add_argument(
            "--company",
            type=str,
            default="",
            help=(
                "Restrict to a specific company identified by slug or pk. "
                "If omitted, all companies are processed."
            ),
        )

    def handle(self, *args, **options):
        dry_run  = options["dry_run"]
        company_filter = options["company"].strip()

        if dry_run:
            self.stdout.write(
                self.style.WARNING("# [DRY-RUN] No changes will be written.\n")
            )

        # Build base queryset.
        # Construir queryset base.
        qs = CompanyUser.objects.filter(
            role__in=_TARGET_ROLES,
            is_active=True,
        ).select_related("user", "company")

        # Optional company filter.
        # Filtro de empresa opcional.
        if company_filter:
            from ivr_config.models import Company
            try:
                # Try pk first, then slug.
                # Intentar pk primero, luego slug.
                try:
                    pk = int(company_filter)
                    company_obj = Company.objects.get(pk=pk)
                except (ValueError, Company.DoesNotExist):
                    company_obj = Company.objects.get(slug=company_filter)
                qs = qs.filter(company=company_obj)
                self.stdout.write(
                    f"# Filtering by company: {company_obj.name} (pk={company_obj.pk})\n"
                )
            except Company.DoesNotExist:
                raise CommandError(
                    f"Company not found: '{company_filter}'. "
                    "Provide a valid slug or pk."
                )

        total    = qs.count()
        updated  = 0
        skipped  = 0
        errors   = 0

        self.stdout.write(
            f"# Processing {total} active WORKSHOP/DRIVER users...\n"
        )

        for cu in qs:
            dni = (cu.dni or "").strip()
            username = cu.user.username
            company_name = cu.company.name
            role = cu.get_role_display()

            pin = _extract_pin(dni)

            if pin is None:
                self.stdout.write(
                    self.style.WARNING(
                        f"  SKIP  {username} ({company_name}, {role}) "
                        f"— DNI '{dni}' has fewer than 4 digits."
                    )
                )
                skipped += 1
                continue

            if dry_run:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"  [DRY] {username} ({company_name}, {role}) "
                        f"— would set PIN '{pin}' from DNI '{dni}'."
                    )
                )
                updated += 1
                continue

            try:
                cu.user.set_password(pin)
                cu.user.save(update_fields=["password"])
                cu.must_change_password = False
                cu.save(update_fields=["must_change_password"])
                self.stdout.write(
                    self.style.SUCCESS(
                        f"  OK    {username} ({company_name}, {role}) "
                        f"— PIN set from DNI '{dni}'."
                    )
                )
                updated += 1
            except Exception as exc:
                self.stdout.write(
                    self.style.ERROR(
                        f"  ERROR {username} ({company_name}, {role}) "
                        f"— {exc}"
                    )
                )
                errors += 1

        # Summary / Resumen.
        self.stdout.write("\n# ── Summary ─────────────────────────────")
        self.stdout.write(f"#   Total processed : {total}")
        self.stdout.write(f"#   Updated (or dry) : {updated}")
        self.stdout.write(f"#   Skipped (no DNI) : {skipped}")
        self.stdout.write(f"#   Errors            : {errors}")
        if dry_run:
            self.stdout.write(self.style.WARNING(
                "#   [DRY-RUN] No changes were written."
            ))
        self.stdout.write("# ─────────────────────────────────────────\n")
