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

"María" has no surname in the system (confirmed via panel screenshot,
S018) -- matching stays safe because the comparison uses the full
concatenated name, not the bare first name: another "María" with an
actual surname would not false-match.

---

Comando de gestión: assign_operator_bases.

Asegura que existan los registros Base "Maqueda" y "Huelva" para una
empresa dada, y asigna CompanyUser.base a todos los usuarios activos
WORKSHOP/WORKSHOPBOSS/SUPERVISOR/DRIVER: los de HUELVA_MEMBERS (por
nombre completo exacto "Nombre Apellido", insensible a mayúsculas)
reciben la base Huelva, el resto recibe Maqueda -- según instrucción
explícita de Miguel Ángel en S018 ("el resto son todos de Maqueda").

El emparejamiento se hace por nombre completo (User.first_name + " " +
User.last_name), no por texto libre -- el valor por defecto es
--dry-run (sin escritura) para que Miguel Ángel pueda revisar la lista
exacta de coincidencias antes de aplicar nada de verdad, mismo patrón
que sync_base_calendars --dry-run.

"María" está confirmada sin apellido en el sistema (captura de panel,
S018) -- el emparejamiento sigue siendo seguro porque se compara el
nombre completo concatenado, no el nombre de pila suelto: otra "María"
con apellido real no haría match falso.
"""
from django.core.management.base import BaseCommand, CommandError

from ivr_config.models import Company, CompanyUser
from budgets.models import Base


# ---------------------------------------------------------------------------
# Huelva members. Two matching keys supported per entry: "full_name"
# (First Last, case/accent-insensitive) and/or "username" (exact).
#
# Real full names confirmed from the S018 dry-run output (my first guess
# at "Carlos Bas" / "David Marquez" was wrong -- actual surnames are
# longer): "Carlos Bas Blanco", "David Contreras Marquez".
#
# "MARIA" has BOTH first_name and last_name blank in the system -- the
# dry-run showed TWO blank-named SUPERVISOR entries, indistinguishable
# by full name alone. Matched by username="MARIA" instead (confirmed
# from Miguel Ángel's panel screenshot, where blank-name rows display
# the username in bold).
#
# Miembros de Huelva. Dos claves de emparejamiento soportadas por
# entrada: "full_name" (Nombre Apellido, insensible a mayúsculas/tildes)
# y/o "username" (exacto).
#
# Nombres completos reales confirmados por la salida del dry-run de
# S018 (mi primera aproximación "Carlos Bas" / "David Marquez" era
# incorrecta -- los apellidos reales son más largos):
# "Carlos Bas Blanco", "David Contreras Marquez".
#
# "MARIA" tiene nombre Y apellido vacíos en el sistema -- el dry-run
# mostró DOS SUPERVISOR con nombre en blanco, indistinguibles por
# nombre completo. Emparejada por username="MARIA" en su lugar
# (confirmado por la captura de panel de Miguel Ángel, donde las filas
# sin nombre muestran el username en negrita).
# ---------------------------------------------------------------------------
HUELVA_MEMBERS = [
    {"username": "MARIA"},
    {"full_name": "Carlos Bas Blanco"},
    {"full_name": "David Contreras Marquez"},
]

MAQUEDA_BASE_MUNICIPALITY = "Maqueda"
HUELVA_BASE_MUNICIPALITY = "Huelva"

# Roles that need a base assignment for the H24 calendar. SUPERVISOR is
# included because María (one of the three Huelva members) has that
# exact role -- confirmed from Miguel Ángel's panel screenshot (S018).
# ADMIN is left untouched (purely administrative, not tied to a
# physical workshop).
# Roles que necesitan asignación de base para el calendario H24.
# SUPERVISOR se incluye porque María (uno de los tres miembros de
# Huelva) tiene exactamente ese rol -- confirmado por la captura de
# panel de Miguel Ángel (S018). ADMIN se deja sin tocar (puramente
# administrativo, no ligado a un taller físico).
BASE_ASSIGNABLE_ROLES = [
    CompanyUser.ROLE_WORKSHOP,
    CompanyUser.ROLE_WORKSHOPBOSS,
    CompanyUser.ROLE_DRIVER,
    CompanyUser.ROLE_SUPERVISOR,
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
        Main entry point. Ensures the two Base records exist and
        reports/applies the assignment.
        ---
        Punto de entrada principal. Asegura que existan las dos Base y
        informa/aplica la asignación.
        """
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
        huelva_full_names = {
            _strip_accents_lower(m["full_name"])
            for m in HUELVA_MEMBERS if "full_name" in m
        }
        huelva_usernames = {
            m["username"].strip().lower()
            for m in HUELVA_MEMBERS if "username" in m
        }

        operators = CompanyUser.objects.filter(
            company=company, role__in=BASE_ASSIGNABLE_ROLES, is_active=True,
        ).select_related("user")

        matched_huelva = 0
        assigned_maqueda = 0
        already_correct = 0

        for operator in operators:
            full_name = f"{operator.user.first_name} {operator.user.last_name}"
            username = operator.user.username
            is_huelva = (
                _strip_accents_lower(full_name) in huelva_full_names
                or username.strip().lower() in huelva_usernames
            )
            target_base = huelva_base if is_huelva else maqueda_base
            target_label = "Huelva" if is_huelva else "Maqueda"
            display_name = full_name.strip() or f"({username})"

            if operator.base_id == getattr(target_base, "pk", None):
                already_correct += 1
                continue

            if apply_changes and target_base is not None:
                operator.base = target_base
                operator.save(update_fields=["base"])
                self.stdout.write(
                    f"  [ASIGNADO]  {display_name} ({operator.role}) -> {target_label}"
                )
            else:
                self.stdout.write(
                    f"  [A ASIGNAR] {display_name} ({operator.role}) -> {target_label}"
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
