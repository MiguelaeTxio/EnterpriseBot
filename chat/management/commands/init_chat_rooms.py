# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/chat/management/commands/init_chat_rooms.py
"""
Management command: init_chat_rooms
Creates ChatRoom instances for a given company in an idempotent manner.
One SECTION room is created per active Section that does not yet have one.
One BREAKDOWNS room is created if it does not yet exist for the company.
Existing rooms are never modified or deleted.
---
Comando de gestión: init_chat_rooms
Crea instancias de ChatRoom para una empresa dada de forma idempotente.
Se crea una sala SECTION por cada Section activa que no tenga sala aún.
Se crea una sala BREAKDOWNS si no existe aún para la empresa.
Las salas existentes nunca se modifican ni eliminan.
"""

from django.core.management.base import BaseCommand, CommandError

from ivr_config.models import Company, Section
from chat.models import ChatRoom


class Command(BaseCommand):
    """
    Idempotent initializer for ChatRoom instances scoped to a company.
    Safe to run multiple times — skips already-existing rooms.
    Requires --company-pk to identify the target company.
    ---
    Inicializador idempotente de instancias ChatRoom para una empresa.
    Seguro para ejecutar múltiples veces — omite salas ya existentes.
    Requiere --company-pk para identificar la empresa objetivo.
    """

    help = "Inicializa las salas de chat IRC para una empresa. Idempotente."

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
            help="PK de la empresa para la que se inicializan las salas de chat.",
        )

    def handle(self, *args, **options):
        """
        Main execution logic.
        1. Resolves the Company from --company-pk.
        2. Creates one ChatRoom(SECTION) per active Section without an existing room.
        3. Creates one ChatRoom(BREAKDOWNS) if none exists for the company.
        Reports created and skipped counts per category.
        ---
        Lógica principal de ejecución.
        1. Resuelve la Company a partir de --company-pk.
        2. Crea una ChatRoom(SECTION) por cada Section activa sin sala existente.
        3. Crea una ChatRoom(BREAKDOWNS) si no existe ninguna para la empresa.
        Informa de los contadores de creadas y omitidas por categoría.
        """
        company_pk = options["company_pk"]

        # Resolve target company — resolución de la empresa objetivo.
        try:
            company = Company.objects.get(pk=company_pk)
        except Company.DoesNotExist:
            raise CommandError(
                f"No existe ninguna Company con pk={company_pk}. "
                "Verifica el identificador e inténtalo de nuevo."
            )

        self.stdout.write(
            f"# Inicializando salas de chat para: {company.name} (pk={company.pk})"
        )

        sections_created = 0
        sections_skipped = 0

        # --- SECTION rooms — salas de tipo SECTION ---
        active_sections = Section.objects.filter(company=company, is_active=True)

        for section in active_sections:
            # Check existence without raising — comprobación de existencia sin excepción.
            exists = ChatRoom.objects.filter(
                company=company,
                section=section,
                room_type=ChatRoom.ROOM_TYPE_SECTION,
            ).exists()

            if exists:
                self.stdout.write(
                    f"#   [OMITIDA] Sala SECTION ya existe para sección: {section.name}"
                )
                sections_skipped += 1
                continue

            ChatRoom.objects.create(
                company=company,
                section=section,
                room_type=ChatRoom.ROOM_TYPE_SECTION,
                name=section.name,
                is_active=True,
            )
            self.stdout.write(
                f"#   [CREADA]  Sala SECTION para sección: {section.name}"
            )
            sections_created += 1

        # --- BREAKDOWNS room — sala de tipo BREAKDOWNS ---
        breakdowns_exists = ChatRoom.objects.filter(
            company=company,
            room_type=ChatRoom.ROOM_TYPE_BREAKDOWNS,
        ).exists()

        if breakdowns_exists:
            self.stdout.write(
                "# [OMITIDA] Sala BREAKDOWNS ya existe para esta empresa."
            )
            breakdowns_created = 0
        else:
            ChatRoom.objects.create(
                company=company,
                section=None,
                room_type=ChatRoom.ROOM_TYPE_BREAKDOWNS,
                name="Averías",
                is_active=True,
            )
            self.stdout.write(
                "# [CREADA]  Sala BREAKDOWNS para esta empresa."
            )
            breakdowns_created = 1

        # --- Resumen final / Final summary ---
        self.stdout.write(
            f"\n# Resumen para {company.name}:\n"
            f"#   Salas SECTION  creadas : {sections_created}\n"
            f"#   Salas SECTION  omitidas: {sections_skipped}\n"
            f"#   Sala BREAKDOWNS creada : {breakdowns_created}\n"
            f"#   Total salas activas    : "
            f"{ChatRoom.objects.filter(company=company, is_active=True).count()}"
        )

