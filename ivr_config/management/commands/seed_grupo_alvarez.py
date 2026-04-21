# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/ivr_config/management/commands/seed_grupo_alvarez.py
"""
Django management command to seed the Grupo Álvarez pilot data into the database.
Creates the initial Company, CompanyUser, CorporateVoiceProfile, CallFlow, PhoneNumbers
and Sections for the EnterpriseBot IVR platform pilot, migrating the hardcoded
configuration from vox_bridge/services.py into the multicompany data model.

Phone numbers are accepted as a dynamic argument (--phone-numbers) to reflect the
reality that a company may operate multiple Twilio numbers simultaneously, each
independently assignable to a CallFlow. This design is valid for any future company
seeded via this command pattern.
---
Comando de gestión de Django para sembrar los datos piloto del Grupo Álvarez en la BD.
Crea la Company, CompanyUser, CorporateVoiceProfile, CallFlow, PhoneNumbers y Sections
iniciales para el piloto de la plataforma IVR EnterpriseBot, migrando la configuración
hardcodeada de vox_bridge/services.py al modelo de datos multiempresa.

Los números de teléfono se aceptan como argumento dinámico (--phone-numbers) para
reflejar la realidad de que una empresa puede operar múltiples números Twilio
simultáneamente, cada uno asignable independientemente a un CallFlow. Este diseño
es válido para cualquier empresa futura sembrada mediante este patrón de comando.
"""

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from ivr_config.models import (
    CallFlow,
    Company,
    CompanyUser,
    Contact,
    CorporateVoiceProfile,
    PhoneNumber,
    Section,
    SectionSchedule,
)


# ---------------------------------------------------------------------------
# SEED DATA CONSTANTS — Migrated verbatim from vox_bridge/services.py.
# CONSTANTES DE SEED — Migradas literalmente desde vox_bridge/services.py.
# ---------------------------------------------------------------------------

GRUPO_ALVAREZ_SYSTEM_INSTRUCTION = (
    "Eres María, la asistente virtual del Grupo Álvarez. "
    "Atiendes llamadas de voz en tiempo real. "
    "Tu tono es profesional, cálido y conciso. "
    "Habla siempre en castellano, salvo que el llamante se dirija a ti en otro idioma. "
    "\n\n"
    "ORGANIGRAMA DE ATENCIÓN:\n"
    "\n"
    "1. ELEVACIÓN (alquiler de plataformas elevadoras):\n"
    "   Si el llamante pregunta por el departamento de Elevación o por el alquiler "
    "de plataformas elevadoras, infórmale de que el horario de atención es de lunes "
    "a viernes de 8:00 a 18:00 horas, y despídete amablemente.\n"
    "\n"
    "2. ASISTENCIA (rescate de vehículos pesados):\n"
    "   Si el llamante pregunta por el departamento de Asistencia o por el rescate "
    "de vehículos pesados, infórmale de que el servicio está disponible las 24 horas "
    "del día, los 7 días de la semana, y despídete amablemente.\n"
    "\n"
    "3. PREGUNTA POR ALGUIEN CON APELLIDO ÁLVAREZ:\n"
    "   Si el llamante pregunta por cualquier persona cuyo apellido sea Álvarez, "
    "indícale que en estos momentos está reunida. "
    "Ofrécete a tomar nota del recado. "
    "Pídele su nombre y, una vez que te lo facilite, confirma que transmitirás el "
    "mensaje y despídete amablemente.\n"
    "\n"
    "4. PREGUNTA POR ALGUIEN SIN APELLIDO ÁLVAREZ:\n"
    "   Si el llamante pregunta por una persona cuyo apellido NO es Álvarez, "
    "pregúntale el motivo de su llamada y redirígele según su respuesta conforme "
    "a las categorías anteriores (Elevación o Asistencia). "
    "Si el motivo no encaja en ninguna categoría, pasa a la regla 5.\n"
    "\n"
    "5. MOTIVO AMBIGUO O SIN CATEGORÍA:\n"
    "   Si el motivo de la llamada no encaja en ninguna de las categorías anteriores, "
    "indícale al llamante que un comercial se pondrá en contacto con él a la mayor "
    "brevedad posible. "
    "Solicítale sus datos de contacto (nombre y número de teléfono) y, "
    "una vez recogidos, despídete amablemente.\n"
    "\n"
    "REGLAS GENERALES:\n"
    "- Nunca inventes información que no figure en este organigrama.\n"
    "- Nunca menciones que eres una inteligencia artificial salvo que el llamante "
    "te lo pregunte directamente.\n"
    "- Mantén siempre un tono sereno y profesional, independientemente del tono "
    "del llamante.\n"
    "- Sé concisa: no des explicaciones innecesarias.\n"
)

GRUPO_ALVAREZ_INITIAL_GREETING = (
    "El llamante acaba de contestar la llamada. "
    "Salúdale presentándote como María, asistente virtual del Grupo Álvarez, "
    "con el siguiente mensaje exacto, sin añadir ni modificar nada: "
    "'Hola, me llamo María, soy la asistente virtual del Grupo Álvarez. "
    "¿En qué puedo ayudarle?'"
)

GRUPO_ALVAREZ_TONE_GUIDELINES = (
    "Tono profesional, cálido y conciso. "
    "El agente representa a una empresa de servicios industriales de alto nivel. "
    "Nunca utiliza jerga informal ni expresiones coloquiales. "
    "Siempre se dirige al llamante de usted. "
    "Las respuestas son breves y directas al punto, sin rodeos innecesarios."
)

GRUPO_ALVAREZ_SAMPLE_RESPONSES = [
    "Grupo Álvarez, buenos días, ¿en qué puedo ayudarle?",
    "El departamento de Elevación atiende de lunes a viernes de 8:00 a 18:00 horas.",
    "El servicio de Asistencia está disponible las 24 horas del día, los 7 días de la semana.",
    "En estos momentos está reunido/a. ¿Desea dejarle algún recado?",
    "Por supuesto, tomaré nota y le trasladaré el mensaje. ¿Me indica su nombre?",
    "Un comercial se pondrá en contacto con usted a la mayor brevedad posible.",
]

GRUPO_ALVAREZ_FORBIDDEN_PHRASES = [
    "no sé",
    "no tengo ni idea",
    "un momento",
    "espera",
    "¿cómo?",
    "¿eh?",
    "o sea",
    "bueno",
    "soy una inteligencia artificial",
    "soy un bot",
    "soy una IA",
]

GRUPO_ALVAREZ_SECTIONS = [
    {
        "name": "Elevación",
        "description": (
            "Departamento de alquiler de plataformas elevadoras. "
            "Horario de atención: lunes a viernes de 8:00 a 18:00 horas."
        ),
    },
    {
        "name": "Asistencia",
        "description": (
            "Departamento de rescate de vehículos pesados. "
            "Servicio disponible 24 horas al día, 7 días a la semana."
        ),
        "is_24h": True,
    },
]


class Command(BaseCommand):
    """
    Management command: seed_grupo_alvarez.
    Idempotent — safe to run multiple times. Uses get_or_create throughout
    to avoid duplicate records on repeated executions.

    Usage:
        python manage.py seed_grupo_alvarez --phone-numbers +12603466780 +34XXXXXXXXX
    ---
    Comando de gestión: seed_grupo_alvarez.
    Idempotente — seguro de ejecutar múltiples veces. Utiliza get_or_create
    en todo momento para evitar registros duplicados en ejecuciones repetidas.

    Uso:
        python manage.py seed_grupo_alvarez --phone-numbers +12603466780 +34XXXXXXXXX
    """

    help = "Siembra los datos piloto iniciales del Grupo Álvarez en la base de datos."

    def add_arguments(self, parser):
        """
        Registers the --phone-numbers argument.
        Accepts one or more E.164 phone numbers to be registered as PhoneNumber
        records linked to the Grupo Álvarez CallFlow.
        A company may operate any number of Twilio lines simultaneously.
        ---
        Registra el argumento --phone-numbers.
        Acepta uno o más números de teléfono E.164 a registrar como registros
        PhoneNumber vinculados al CallFlow del Grupo Álvarez.
        Una empresa puede operar cualquier número de líneas Twilio simultáneamente.
        """
        parser.add_argument(
            "--phone-numbers",
            nargs="+",
            type=str,
            required=True,
            metavar="E164_NUMBER",
            help=(
                "Uno o más números Twilio en formato E.164 (p. ej. +34951799117 +34951796832). "
                "Cada número se registrará como PhoneNumber activo vinculado al CallFlow principal."
            ),
        )

        parser.add_argument(
            "--capabilities",
            nargs="+",
            type=str,
            required=False,
            metavar="CAPABILITY",
            default=None,
            help=(
                "Capacidades de canal para cada número en --phone-numbers, en el mismo orden. "
                "Valores válidos: VOICE, WHATSAPP, BOTH. "
                "Si se omite, todos los números reciben BOTH por defecto. "
                "Ejemplo: --capabilities BOTH VOICE"
            ),
        )

    def handle(self, *args, **options):
        """
        Main entry point for the seed command.
        Validates the supplied phone numbers and their capabilities, then wraps
        the entire seeding operation in an atomic transaction to guarantee
        database consistency. The --capabilities argument must match the length
        of --phone-numbers when supplied; if omitted, all numbers default to BOTH.
        ---
        Punto de entrada principal del comando de seed.
        Valida los números de teléfono suministrados y sus capacidades de canal,
        y envuelve toda la operación de seed en una transacción atómica para
        garantizar la consistencia de la BD. El argumento --capabilities debe
        coincidir en longitud con --phone-numbers cuando se suministra; si se
        omite, todos los números reciben BOTH por defecto.
        """
        phone_numbers  = options["phone_numbers"]
        raw_caps       = options["capabilities"]

        # Validate E.164 format for every supplied number.
        # Validar formato E.164 para cada número suministrado.
        invalid = [n for n in phone_numbers if not n.startswith("+")]
        if invalid:
            raise CommandError(
                f"# [SEED] Números inválidos (deben estar en formato E.164): {invalid}"
            )

        # Validate or default capabilities list.
        # Validar o establecer por defecto la lista de capacidades.
        valid_caps = {"VOICE", "WHATSAPP", "BOTH"}
        if raw_caps is None:
            capabilities = ["BOTH"] * len(phone_numbers)
        else:
            if len(raw_caps) != len(phone_numbers):
                raise CommandError(
                    f"# [SEED] --capabilities debe tener el mismo número de valores "
                    f"que --phone-numbers ({len(phone_numbers)} esperado, "
                    f"{len(raw_caps)} recibido)."
                )
            invalid_caps = [c for c in raw_caps if c not in valid_caps]
            if invalid_caps:
                raise CommandError(
                    f"# [SEED] Capacidades inválidas: {invalid_caps}. "
                    f"Valores permitidos: {sorted(valid_caps)}."
                )
            capabilities = raw_caps

        self.stdout.write(
            f"# [SEED] Iniciando seed de datos piloto: Grupo Álvarez "
            f"con {len(phone_numbers)} número(s): {', '.join(phone_numbers)}..."
        )

        try:
            with transaction.atomic():
                company = self._seed_company()
                self._seed_admin_user(company)
                self._seed_voice_profile(company)
                call_flow = self._seed_call_flow(company)
                self._seed_phone_numbers(company, call_flow, phone_numbers, capabilities)
                sections_by_name = self._seed_sections(company)
                self._seed_section_schedules(sections_by_name)

            self.stdout.write(
                self.style.SUCCESS(
                    "# [SEED] Seed completado correctamente. "
                    "Grupo Álvarez está listo en la base de datos."
                )
            )

        except Exception as exc:
            self.stdout.write(
                self.style.ERROR(
                    f"# [SEED] ERROR durante el seed. Transacción revertida. Detalle: {exc}"
                )
            )
            raise

    # -----------------------------------------------------------------------
    # PRIVATE SEED METHODS / MÉTODOS PRIVADOS DE SEED
    # -----------------------------------------------------------------------

    def _seed_company(self) -> Company:
        """
        Creates or retrieves the Grupo Álvarez Company instance.
        ---
        Crea o recupera la instancia Company del Grupo Álvarez.
        """
        company, created = Company.objects.get_or_create(
            slug="grupo-alvarez",
            defaults={
                "name": "Grupo Álvarez",
                "is_active": True,
            },
        )
        status = "creada" if created else "ya existente"
        self.stdout.write(f"# [SEED] Company 'Grupo Álvarez' {status}.")
        return company

    def _seed_admin_user(self, company: Company) -> CompanyUser:
        """
        Creates or retrieves the Django auth.User and linked CompanyUser
        for the Grupo Álvarez platform administrator.
        The Django User is created with is_staff=False and is_active=True
        to comply with the CompanyUser access constraint.
        ---
        Crea o recupera el auth.User de Django y el CompanyUser vinculado
        para el administrador de plataforma del Grupo Álvarez.
        El User de Django se crea con is_staff=False e is_active=True
        para cumplir con la restricción de acceso de CompanyUser.
        """
        # Create or retrieve the underlying Django auth.User.
        # Crear o recuperar el auth.User subyacente de Django.
        django_user, user_created = User.objects.get_or_create(
            username="alvarez_admin",
            defaults={
                "email": "admin@grupoalvarez.es",
                "is_staff": False,
                "is_active": True,
                "is_superuser": False,
            },
        )
        if user_created:
            # Assign an unusable password — authentication will be via the
            # custom /panel/ interface, not Django's /admin/.
            # Asignar una contraseña inutilizable — la autenticación será a través
            # de la interfaz /panel/ personalizada, no del /admin/ de Django.
            django_user.set_unusable_password()
            django_user.save()
            self.stdout.write("# [SEED] Django User 'alvarez_admin' creado.")
        else:
            self.stdout.write("# [SEED] Django User 'alvarez_admin' ya existente.")

        company_user, cu_created = CompanyUser.objects.get_or_create(
            user=django_user,
            defaults={
                "company": company,
                "role": CompanyUser.ROLE_ADMIN,
                "is_active": True,
            },
        )
        status = "creado" if cu_created else "ya existente"
        self.stdout.write(f"# [SEED] CompanyUser 'alvarez_admin' {status}.")
        return company_user

    def _seed_voice_profile(self, company: Company) -> CorporateVoiceProfile:
        """
        Creates or retrieves the CorporateVoiceProfile for Grupo Álvarez,
        extracting tone identity from the legacy SYSTEM_INSTRUCTION constant.
        ---
        Crea o recupera el CorporateVoiceProfile del Grupo Álvarez,
        extrayendo la identidad de tono de la constante SYSTEM_INSTRUCTION heredada.
        """
        profile, created = CorporateVoiceProfile.objects.get_or_create(
            company=company,
            defaults={
                "voice_name": CorporateVoiceProfile.VOICE_AOEDE,
                "tone_guidelines": GRUPO_ALVAREZ_TONE_GUIDELINES,
                "sample_responses": GRUPO_ALVAREZ_SAMPLE_RESPONSES,
                "forbidden_phrases": GRUPO_ALVAREZ_FORBIDDEN_PHRASES,
                "is_active": True,
            },
        )
        status = "creado" if created else "ya existente"
        self.stdout.write(f"# [SEED] CorporateVoiceProfile de Grupo Álvarez {status}.")
        return profile

    def _seed_call_flow(self, company: Company) -> CallFlow:
        """
        Creates or retrieves the main CallFlow for Grupo Álvarez, migrating
        the SYSTEM_INSTRUCTION and INITIAL_GREETING_TEXT constants verbatim
        from vox_bridge/services.py into the database record.
        ---
        Crea o recupera el CallFlow principal del Grupo Álvarez, migrando
        literalmente las constantes SYSTEM_INSTRUCTION e INITIAL_GREETING_TEXT
        de vox_bridge/services.py al registro de base de datos.
        """
        call_flow, created = CallFlow.objects.get_or_create(
            company=company,
            name="Recepción principal — María",
            defaults={
                "system_instruction": GRUPO_ALVAREZ_SYSTEM_INSTRUCTION,
                "initial_greeting": GRUPO_ALVAREZ_INITIAL_GREETING,
                "is_active": True,
            },
        )
        status = "creado" if created else "ya existente"
        self.stdout.write(f"# [SEED] CallFlow 'Recepción principal — María' {status}.")
        return call_flow

    def _seed_phone_numbers(
        self,
        company: Company,
        call_flow: CallFlow,
        phone_numbers: list,
        capabilities: list,
    ) -> None:
        """
        Creates or retrieves a PhoneNumber record for each number supplied
        via the --phone-numbers argument. Each number is paired with its
        corresponding capability from the --capabilities argument (VOICE,
        WHATSAPP or BOTH). All numbers are linked to the company's main
        CallFlow and marked as active.
        A company may register any number of Twilio lines simultaneously —
        this method enforces no upper limit.
        ---
        Crea o recupera un registro PhoneNumber para cada número suministrado
        a través del argumento --phone-numbers. Cada número se empareja con su
        capacidad de canal correspondiente del argumento --capabilities (VOICE,
        WHATSAPP o BOTH). Todos los números se vinculan al CallFlow principal
        de la empresa y se marcan como activos.
        Una empresa puede registrar cualquier número de líneas Twilio
        simultáneamente — este método no impone ningún límite superior.
        """
        for number, capability in zip(phone_numbers, capabilities):
            phone_number, created = PhoneNumber.objects.get_or_create(
                number=number,
                defaults={
                    "company": company,
                    "friendly_name": f"Línea Twilio — {company.name} — {number}",
                    "call_flow": call_flow,
                    "is_active": True,
                    "capabilities": capability,
                },
            )
            if not created and phone_number.capabilities != capability:
                # Update capabilities if the record already existed with a
                # different value — supports re-seeding after capability changes.
                # Actualizar capabilities si el registro ya existía con un valor
                # diferente — soporta re-sembrado tras cambios de capacidad.
                phone_number.capabilities = capability
                phone_number.save(update_fields=["capabilities"])
                self.stdout.write(
                    f"# [SEED] PhoneNumber '{number}' ya existente — "
                    f"capabilities actualizado a '{capability}'."
                )
            else:
                status = "creado" if created else "ya existente"
                self.stdout.write(
                    f"# [SEED] PhoneNumber '{number}' {status} "
                    f"[capabilities={capability}]."
                )

    def _seed_sections(self, company: Company) -> None:
        """
        Creates or retrieves the two initial Sections for Grupo Álvarez:
        Elevación and Asistencia — the two departments currently hardcoded
        in the SYSTEM_INSTRUCTION routing logic.
        ---
        Crea o recupera las dos Sections iniciales del Grupo Álvarez:
        Elevación y Asistencia — los dos departamentos actualmente hardcodeados
        en la lógica de enrutamiento del SYSTEM_INSTRUCTION.
        """
        for section_data in GRUPO_ALVAREZ_SECTIONS:
            section, created = Section.objects.get_or_create(
                company=company,
                name=section_data["name"],
                defaults={
                    "description": section_data["description"],
                    "is_24h": section_data.get("is_24h", False),
                    "is_active": True,
                },
            )
            if not created and section.is_24h != section_data.get("is_24h", False):
                section.is_24h = section_data.get("is_24h", False)
                section.save(update_fields=["is_24h"])
                self.stdout.write(
                    f"# [SEED] Section '{section_data['name']}' is_24h actualizado."
                )
            status = "creada" if created else "ya existente"
            self.stdout.write(
                f"# [SEED] Section '{section_data['name']}' {status}."
            )
        return {
            s.name: s for s in Section.objects.filter(company=company)
        }

    def _seed_section_schedules(self, sections_by_name: dict) -> None:
        """
        Creates or retrieves SectionSchedule records for Elevacion:
        Monday to Friday 08:00-18:00. Asistencia is is_24h=True so no
        schedule records are needed for it.
        ---
        Crea o recupera los registros SectionSchedule para Elevacion:
        lunes a viernes de 08:00 a 18:00. Asistencia tiene is_24h=True
        por lo que no necesita registros de horario.
        """
        import datetime
        elevacion = sections_by_name.get("Elevación")
        if not elevacion:
            self.stdout.write(
                "# [SEED] WARN: Sección 'Elevación' no encontrada. "
                "No se crearan horarios."
            )
            return

        # Monday=0 to Friday=4, 08:00-18:00
        # Lunes=0 a Viernes=4, 08:00-18:00
        time_open  = datetime.time(8, 0)
        time_close = datetime.time(18, 0)
        created_count = 0
        for weekday in range(5):  # 0=Lunes ... 4=Viernes
            _, created = SectionSchedule.objects.get_or_create(
                section=elevacion,
                weekday=weekday,
                time_open=time_open,
                time_close=time_close,
            )
            if created:
                created_count += 1
        self.stdout.write(
            f"# [SEED] SectionSchedule Elevación: "
            f"{created_count} franja(s) creada(s), "
            f"{5 - created_count} ya existente(s)."
        )
