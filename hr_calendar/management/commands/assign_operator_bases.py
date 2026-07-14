# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/hr_calendar/management/commands/assign_operator_bases.py
"""
Management command: assign_operator_bases.

Ensures the "Maqueda" and "Huelva" Base records exist for a given
company, then assigns CompanyUser.base to every active WORKSHOP/
WORKSHOPBOSS/DRIVER user: HUELVA_MEMBERS (matched by exact "First Last"
full name, case-insensitive) get the Huelva base, everyone else gets
Maqueda -- per Miguel Ángel's explicit instruction in S018 ("el resto
son todos de Maqueda").

Matching is done on full name (User.first_name + " " + User.last_name),
not on free text -- SAFE_DEFAULT is --dry-run (no writes) so Miguel
Ángel can review the exact match list before applying anything for
real, same pattern as sync_base_calendars --dry-run.

⛔ HUELVA_MEMBERS below has "María" without a surname -- the S018
session only had a first name for the supervisor. Matching a bare
first name against User.first_name would silently over-match if there
is more than one "María" in the company. This command deliberately
raises CommandError and refuses to run (even in --dry-run) until her
surname is filled in, rather than guessing.

---

Comando de gestión: assign_operator_bases.

Asegura que existan los registros Base "Maqueda" y "Huelva" para una
empresa dada, y asigna CompanyUser.base a todos los usuarios activos
WORKSHOP/WORKSHOPBOSS/DRIVER: los de HUELVA_MEMBERS (por nombre
completo exacto "Nombre Apellido", insensible a mayúsculas) reciben la
base Huelva, el resto recibe Maqueda -- según instrucción explícita de
Miguel Ángel en S018 ("el resto son todos de Maqueda").

El emparejamiento se hace por nombre completo (User.first_name + " " +
User.last_name), no por texto libre -- el valor por defecto es
--dry-run (sin escritura) para que Miguel Ángel pueda revisar la lista
exacta de coincidencias antes de aplicar nada de verdad, mismo patrón
que sync_base_calendars --dry-run.

⛔ HUELVA_MEMBERS de abajo tiene a "María" sin apellido -- en la sesión
S018 solo se dio el nombre de pila de la supervisora. Emparejar solo
por nombre de pila contra User.first_name podría empatar de más en
silencio si hay más de una "María" en la empresa. Este comando
deliberadamente lanza CommandError y se niega a ejecutar (incluso en
--dry-run) hasta que se rellene su apellido, en vez de adivinar.
"""
from django.core.management.base import BaseCommand, CommandError

from ivr_config.models import Company, CompanyUser
from budgets.models import Base


# ---------------------------------------------------------------------------
# Huelva members — exact "First Last" full names, case-insensitive match.
# Everyone else with role WORKSHOP/WORKSHOPBOSS/DRIVER gets Maqueda.
# Miembros de Huelva — nombre completo exacto "Nombre Apellido", insensible
# a mayúsculas. El resto con rol WORKSHOP/WORKSHOPBOSS/DRIVER recibe Maqueda.
#
# TODO (S018): "María" needs a surname before this command can run for
# real -- see module docstring. Fill in and remove the CommandError guard
# in handle() once confirmed by Miguel Ángel.
# ---------------------------------------------------------------------------
HUELVA_MEMBERS = [
    "Maria APELLIDO_PENDIENTE_CONFIRMAR",  # Supervisora -- apellido sin confirmar (S018)
    "Carlos Bas",
    "David Marquez",
]

MAQUEDA_BASE_MUNICIPALITY = "Maqueda"
HUELVA_BASE_MUNICIPALITY = "Huelva"

# Roles that need a base assignment for the H24 calendar. ADMIN/SUPERVISOR
# (administrative, not tied to a physical workshop) are left untouched.
# Roles que necesitan asignación de base para el calendario H24.
# ADMIN/SUPERVISOR (administrativos, no ligados a un taller físico) se
# dejan sin tocar.
BASE_ASSIGNABLE_ROLES = [
    CompanyUser.ROLE_WORKSHOP,
    CompanyUser.ROLE_WORKSHOPBOSS,
    CompanyUser.ROLE_DRIVER,
]


def _strip_accents_lower(text: str) -> str:
    """
    Normalises a name for comparison: lowercase, strips common Spanish
    accents. Avoids false negatives from "María" vs "Maria" typed
    without the accent.
    ---
    Normaliza un nombre para comparar: minúsculas, elimina acentos
    españoles comunes. Evita falsos negativos entre "María" y "Maria"
    escrito sin tilde.
    """
    replacements = {
        "á": "a", "é": "e", "í": "i", "ó": "o", "ú": "u", "ñ": "n",
    }
    result = text.lower().strip()
    for accented, plain in replacements.items():
        result = result.replace(accented, plain)
    return result


class Command(BaseCommand):
    """
    Ensures Maqueda/Huelva Base records exist and assigns CompanyUser.base
    to every WORKSHOP/WORKSHOPBOSS/DRIVER user of a company.
    ---
    Asegura que existan los registros Base Maqueda/Huelva y asigna
    CompanyUser.base a cada usuario WORKSHOP/WORKSHOPBOSS/DRIVER de una
    empresa.
    """

    help = (
        "Asigna la base Maqueda/Huelva a cada operario/chófer de una "
        "empresa. Por defecto --dry-run: no escribe nada, solo informa."
    )

    def add_arguments(self, parser):
        """
        Registers --company-pk (required) and --apply (opt-in write mode).
        ---
        Registra --company-pk (obligatorio) y --apply (modo de escritura,
        opt-in).
        """
        parser.add_argument(
            "--company-pk",
            type=int,
            required=True,
            dest="company_pk",
            help="Clave primaria (pk) de la empresa a procesar.",
        )
        parser.add_argument(
            "--apply",
            action="store_true",
            default=False,
            help=(
                "Escribe los cambios en la base de datos. Sin este flag "
                "el comando solo informa de lo que haría (dry-run)."
            ),
        )

    def handle(self, *args, **options):
        """
        Main entry point. Refuses to run while María's surname is
        unconfirmed (see module docstring), otherwise ensures the two
        Base records exist and reports/applies the assignment.
        ---
        Punto de entrada principal. Se niega a ejecutar mientras el
        apellido de María no esté confirmado (ver docstring del módulo);
        en caso contrario asegura que existan las dos Base y
        informa/aplica la asignación.
        """
        if "APELLIDO_PENDIENTE_CONFIRMAR" in " ".join(HUELVA_MEMBERS):
            raise CommandError(
                "# Falta confirmar el apellido de 'Maria' en "
                "HUELVA_MEMBERS (hr_calendar/management/commands/"
                "assign_operator_bases.py) antes de poder ejecutar este "
                "comando, ni siquiera en --dry-run. Editar la constante "
                "con el apellido real y volver a intentar."
            )

        company_pk = options["company_pk"]
        apply_changes = options["apply"]

        try:
            company = Company.objects.get(pk=company_pk)
        except Company.DoesNotExist:
            raise CommandError(
                f"# No se encontró ninguna empresa con pk={company_pk}."
            )

        self.stdout.write(
            f"# Empresa resuelta: '{company.name}' (pk={company.pk})"
        )
        if not apply_changes:
            self.stdout.write(
                "# MODO DRY-RUN: no se escribirá nada. Usa --apply para "
                "aplicar los cambios de verdad."
            )

        # ------------------------------------------------------------------
        # Step 1 — ensure the two Base records exist.
        # Paso 1 — asegurar que existen las dos Base.
        # ------------------------------------------------------------------
        maqueda_base = None
        huelva_base = None
        for name, municipality in (
            ("Maqueda", MAQUEDA_BASE_MUNICIPALITY),
            ("Huelva", HUELVA_BASE_MUNICIPALITY),
        ):
            existing = Base.objects.filter(
                company=company, name=name,
            ).first()
            if existing:
                self.stdout.write(f"  [BASE EXISTENTE] {name} (pk={existing.pk})")
            elif apply_changes:
                existing = Base.objects.create(
                    company=company, name=name, municipality=municipality,
                )
                self.stdout.write(f"  [BASE CREADA]    {name} (pk={existing.pk})")
            else:
                self.stdout.write(
                    f"  [BASE A CREAR]   {name} (municipio={municipality}) "
                    f"-- no existe todavía, se crearía con --apply"
                )
            if name == "Maqueda":
                maqueda_base = existing
            else:
                huelva_base = existing

        # ------------------------------------------------------------------
        # Step 2 — match and assign.
        # Paso 2 — emparejar y asignar.
        # ------------------------------------------------------------------
        huelva_names_normalised = {
            _strip_accents_lower(n) for n in HUELVA_MEMBERS
        }

        operators = CompanyUser.objects.filter(
            company=company, role__in=BASE_ASSIGNABLE_ROLES, is_active=True,
        ).select_related("user")

        matched_huelva = 0
        assigned_maqueda = 0
        already_correct = 0

        for operator in operators:
            full_name = f"{operator.user.first_name} {operator.user.last_name}"
            is_huelva = _strip_accents_lower(full_name) in huelva_names_normalised
            target_base = huelva_base if is_huelva else maqueda_base
            target_label = "Huelva" if is_huelva else "Maqueda"

            if operator.base_id == getattr(target_base, "pk", None):
                already_correct += 1
                continue

            if apply_changes and target_base is not None:
                operator.base = target_base
                operator.save(update_fields=["base"])
                self.stdout.write(
                    f"  [ASIGNADO]  {full_name} ({operator.role}) -> {target_label}"
                )
            else:
                self.stdout.write(
                    f"  [A ASIGNAR] {full_name} ({operator.role}) -> {target_label}"
                )

            if is_huelva:
                matched_huelva += 1
            else:
                assigned_maqueda += 1

        self.stdout.write(
            f"\n# Completado: {matched_huelva} a Huelva, "
            f"{assigned_maqueda} a Maqueda, {already_correct} ya correctos "
            f"de {operators.count()} operarios/chóferes totales."
        )
        if matched_huelva != len(HUELVA_MEMBERS) - already_correct and matched_huelva < len(HUELVA_MEMBERS):
            self.stdout.write(
                self.style.WARNING(
                    f"# AVISO: se esperaban {len(HUELVA_MEMBERS)} miembros de "
                    f"Huelva mencionados en HUELVA_MEMBERS pero solo se "
                    f"encontraron coincidencias para {matched_huelva} (más "
                    f"{already_correct} ya correctos previamente) -- revisar "
                    f"nombres exactos si el total no cuadra."
                )
            )
