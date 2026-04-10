# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/whatsapp/management/commands/seed_whatsapp_templates.py
"""
Django management command to seed WhatsApp templates for Grupo Álvarez.
Creates WhatsAppTemplate records using the ContentSid values obtained from
the Twilio Content Template Builder after Meta approval. Idempotent — safe
to run multiple times via get_or_create. ContentSid values must be updated
in the TEMPLATE_DEFINITIONS constant below once obtained from Twilio Console.
---
Comando de gestión de Django para sembrar las plantillas WhatsApp del Grupo Álvarez.
Crea registros WhatsAppTemplate usando los valores ContentSid obtenidos del
Content Template Builder de Twilio tras la aprobación de Meta. Idempotente —
seguro de ejecutar múltiples veces mediante get_or_create. Los valores ContentSid
deben actualizarse en la constante TEMPLATE_DEFINITIONS a continuación una vez
obtenidos del Console de Twilio.
"""

from django.core.management.base import BaseCommand, CommandError

from ivr_config.models import Company
from whatsapp.models import WhatsAppTemplate


# ---------------------------------------------------------------------------
# TEMPLATE DEFINITIONS — Update ContentSid values after Twilio Console approval.
# DEFINICIONES DE PLANTILLAS — Actualizar valores ContentSid tras aprobación en Twilio Console.
#
# HOW TO OBTAIN ContentSid:
#   1. Log in to Twilio Console → Messaging → Content Template Builder.
#   2. Locate the approved template.
#   3. Copy the Content SID (format: HXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx).
#   4. Replace the PENDING placeholder below with the real SID.
#   5. Re-run: python -m dotenv run python manage.py seed_whatsapp_templates
#
# CÓMO OBTENER ContentSid:
#   1. Acceder al Console de Twilio → Messaging → Content Template Builder.
#   2. Localizar la plantilla aprobada.
#   3. Copiar el Content SID (formato: HXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx).
#   4. Reemplazar el marcador PENDING a continuación con el SID real.
#   5. Volver a ejecutar: python -m dotenv run python manage.py seed_whatsapp_templates
# ---------------------------------------------------------------------------

TEMPLATE_DEFINITIONS = [
    {
        # Presence reminder sent by check_in_meeting_reminders Celery task.
        # Recordatorio de presencia enviado por la tarea Celery check_in_meeting_reminders.
        # Body: "¿Sigues reunido? Responde con una de estas opciones:
        #        1h — Seguiré ocupado 1 hora más
        #        2h — Seguiré ocupado 2 horas más
        #        disponible — Ya estoy disponible"
        "name":        "presence_reminder",
        "content_sid": "PENDING_HX_PRESENCE_REMINDER",
        "category":    WhatsAppTemplate.CATEGORY_UTILITY,
        "language":    "es",
    },
    {
        # Optional welcome message for business-initiated conversations.
        # Mensaje de bienvenida opcional para conversaciones iniciadas por la empresa.
        # Body: "Hola {{1}}, soy el asistente virtual de {{2}}. ¿En qué puedo ayudarte hoy?"
        "name":        "welcome_message",
        "content_sid": "PENDING_HX_WELCOME_MESSAGE",
        "category":    WhatsAppTemplate.CATEGORY_UTILITY,
        "language":    "es",
    },
]

# Slug of the pilot company. Must match the value seeded by seed_grupo_alvarez.
# Slug de la empresa piloto. Debe coincidir con el valor sembrado por seed_grupo_alvarez.
GRUPO_ALVAREZ_SLUG = "grupo-alvarez"


class Command(BaseCommand):
    """
    Management command: seed_whatsapp_templates.
    Idempotent — safe to run multiple times. Uses get_or_create to avoid
    duplicate records. Updates content_sid and category if the record already
    exists with a different value, supporting re-seeding after ContentSid changes.

    Usage:
        python -m dotenv run python manage.py seed_whatsapp_templates
    ---
    Comando de gestión: seed_whatsapp_templates.
    Idempotente — seguro de ejecutar múltiples veces. Usa get_or_create para
    evitar registros duplicados. Actualiza content_sid y category si el registro
    ya existe con un valor diferente, soportando re-sembrado tras cambios de ContentSid.

    Uso:
        python -m dotenv run python manage.py seed_whatsapp_templates
    """

    help = "Siembra las plantillas WhatsApp del Grupo Álvarez en la base de datos."

    def handle(self, *args, **options):
        """
        Main entry point. Resolves the Grupo Álvarez Company instance and
        iterates over TEMPLATE_DEFINITIONS to create or update each template.
        Warns if any ContentSid value is still set to a PENDING placeholder.
        ---
        Punto de entrada principal. Resuelve la instancia Company del Grupo Álvarez
        e itera sobre TEMPLATE_DEFINITIONS para crear o actualizar cada plantilla.
        Advierte si algún valor ContentSid sigue establecido como marcador PENDING.
        """
        # Resolve Grupo Álvarez company instance.
        # Resolver la instancia Company del Grupo Álvarez.
        try:
            company = Company.objects.get(slug=GRUPO_ALVAREZ_SLUG)
        except Company.DoesNotExist:
            raise CommandError(
                f"# [SEED] Company con slug '{GRUPO_ALVAREZ_SLUG}' no encontrada. "
                f"Ejecuta primero: python manage.py seed_grupo_alvarez --phone-numbers ..."
            )

        self.stdout.write(
            f"# [SEED] Iniciando seed de plantillas WhatsApp para: {company.name}..."
        )

        pending_count = 0
        seeded_count  = 0

        for definition in TEMPLATE_DEFINITIONS:
            name        = definition["name"]
            content_sid = definition["content_sid"]
            category    = definition["category"]
            language    = definition["language"]

            # Warn about pending ContentSid placeholders.
            # Advertir sobre marcadores ContentSid pendientes.
            if content_sid.startswith("PENDING_"):
                self.stdout.write(
                    self.style.WARNING(
                        f"# [SEED] ⚠️  Plantilla '{name}': ContentSid aún no configurado "
                        f"({content_sid}). Actualiza TEMPLATE_DEFINITIONS y re-ejecuta."
                    )
                )
                pending_count += 1

            template, created = WhatsAppTemplate.objects.get_or_create(
                company=company,
                name=name,
                defaults={
                    "content_sid": content_sid,
                    "category":    category,
                    "language":    language,
                    "is_active":   True,
                },
            )

            if not created:
                # Update mutable fields if the record already existed.
                # Actualizar campos mutables si el registro ya existía.
                updated_fields = []

                if template.content_sid != content_sid:
                    template.content_sid = content_sid
                    updated_fields.append("content_sid")

                if template.category != category:
                    template.category = category
                    updated_fields.append("category")

                if template.language != language:
                    template.language = language
                    updated_fields.append("language")

                if updated_fields:
                    template.save(update_fields=updated_fields)
                    self.stdout.write(
                        f"# [SEED] Plantilla '{name}' actualizada "
                        f"(campos: {', '.join(updated_fields)})."
                    )
                else:
                    self.stdout.write(
                        f"# [SEED] Plantilla '{name}' ya existente — sin cambios."
                    )
            else:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"# [SEED] Plantilla '{name}' creada "
                        f"[ContentSid: {content_sid}]."
                    )
                )
                seeded_count += 1

        # Final summary.
        # Resumen final.
        self.stdout.write(
            self.style.SUCCESS(
                f"# [SEED] Seed de plantillas completado. "
                f"{seeded_count} creada(s). "
                f"{pending_count} pendiente(s) de ContentSid real."
            )
        )

        if pending_count > 0:
            self.stdout.write(
                self.style.WARNING(
                    "# [SEED] Recuerda actualizar los ContentSid PENDING en "
                    "TEMPLATE_DEFINITIONS y volver a ejecutar este comando "
                    "una vez obtenidos del Content Template Builder de Twilio."
                )
            )
