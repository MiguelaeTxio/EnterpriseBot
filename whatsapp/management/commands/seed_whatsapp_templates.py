# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/whatsapp/management/commands/seed_whatsapp_templates.py
"""
Django management command to seed WhatsApp templates for Grupo Alvarez.
Creates WhatsAppTemplate records using the ContentSid values obtained from
the Twilio Content Template Builder after Meta approval. Idempotent — safe
to run multiple times via get_or_create. ContentSid values must be updated
in the TEMPLATE_DEFINITIONS constant below once obtained from Twilio Console.

Template inventory (11 total):
  APPROVED (6):
    - presence_reminder          UTILITY   HXe0ea154a5fa8756be305f6f0c24023c4
    - welcome_message            MARKETING HX6619d4bded96b01c62fada40e6259dd8
    - chat_onboarding            UTILITY   HX9c92dd8981366dda0764900958b7abbc
    - chat_session_renewal       UTILITY   HX7e0f3f4d9b8553acc58240e7767f2133
    - ivr_capture_notification   UTILITY   HX1a301d32db3acaedf6b13d83fd7579ac
    - document_expiry_alert      UTILITY   HX55da66276bb2025f691c378abff0123e (confirmado S025, 2026-07-20)

  PENDING APPROVAL (5 — creadas en H17 S055, awaiting Meta review):
    - breakdown_ticket_created   UTILITY   HX32d590d2a40360c789060a7f88fa50ef
    - breakdown_location_request UTILITY   HXb9139eb63adb500855a679957d3de232
    - breakdown_info_request     UTILITY   HXe3baa955000b20e312d6d000f775533b
    - breakdown_assigned         UTILITY   HX41a742714147cc5ec92fa83dbf5c3db6
    - breakdown_broadcast        UTILITY   HXa1b32520e94663a32d3c7c1453429fe3

  NOT SUBMITTED (1 — created previously, pending Meta submission decision):
    - employee_help_menu         UTILITY   HXe8c20c02d4cf4ab340924ed5e2b0ac6f
---
Comando de gestion de Django para sembrar las plantillas WhatsApp del Grupo Alvarez.
Crea registros WhatsAppTemplate usando los valores ContentSid obtenidos del
Content Template Builder de Twilio tras la aprobacion de Meta. Idempotente —
seguro de ejecutar multiples veces mediante get_or_create. Los valores ContentSid
deben actualizarse en la constante TEMPLATE_DEFINITIONS a continuacion una vez
obtenidos del Console de Twilio.
"""

from django.core.management.base import BaseCommand, CommandError

from ivr_config.models import Company
from whatsapp.models import WhatsAppTemplate


# ---------------------------------------------------------------------------
# TEMPLATE DEFINITIONS — Full inventory for Grupo Alvarez.
# Update ContentSid values here if templates are recreated in Twilio Console.
#
# HOW TO OBTAIN ContentSid:
#   1. Log in to Twilio Console -> Messaging -> Content Template Builder.
#   2. Locate the template.
#   3. Copy the Content SID (format: HXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx).
#   4. Replace the value below with the real SID.
#   5. Re-run: python -m dotenv run python manage.py seed_whatsapp_templates
# ---------------------------------------------------------------------------

TEMPLATE_DEFINITIONS = [
    # ------------------------------------------------------------------
    # APPROVED TEMPLATES — Active and available for sending.
    # ------------------------------------------------------------------
    {
        # Presence reminder sent by check_in_meeting_reminders Celery task.
        # Recordatorio de presencia enviado por la tarea Celery.
        # Body: "Esta reunido? Responde con una de estas opciones: ..."
        "name":        "presence_reminder",
        "content_sid": "HXe0ea154a5fa8756be305f6f0c24023c4",
        "category":    WhatsAppTemplate.CATEGORY_UTILITY,
        "language":    "es",
    },
    {
        # Welcome message for business-initiated conversations (generic).
        # Approved as MARKETING by Meta (not transactional — generic greeting).
        # Mensaje de bienvenida para conversaciones iniciadas por la empresa.
        # Aprobada como MARKETING por Meta (no transaccional).
        # Body: "Hola {{1}}, soy el asistente virtual de {{2}}. En que puedo ayudarte hoy?"
        "name":        "welcome_message",
        "content_sid": "HX6619d4bded96b01c62fada40e6259dd8",
        "category":    WhatsAppTemplate.CATEGORY_MARKETING,
        "language":    "es",
    },
    {
        # Onboarding message sent when a new employee registers via WhatsApp.
        # Mensaje de onboarding enviado al registrar un nuevo empleado por WhatsApp.
        "name":        "chat_onboarding",
        "content_sid": "HX9c92dd8981366dda0764900958b7abbc",
        "category":    WhatsAppTemplate.CATEGORY_UTILITY,
        "language":    "es",
    },
    {
        # Session renewal template sent when a WhatsApp session expires (24h window).
        # Plantilla de renovacion de sesion enviada al expirar la sesion de 24h.
        # Content type: twilio/quick-reply
        "name":        "chat_session_renewal",
        "content_sid": "HX7e0f3f4d9b8553acc58240e7767f2133",
        "category":    WhatsAppTemplate.CATEGORY_UTILITY,
        "language":    "es",
    },
    {
        # Notification sent after an IVR call captures breakdown data.
        # Notificacion enviada tras una llamada IVR que captura datos de averia.
        "name":        "ivr_capture_notification",
        "content_sid": "HX1a301d32db3acaedf6b13d83fd7579ac",
        "category":    WhatsAppTemplate.CATEGORY_UTILITY,
        "language":    "es",
    },
    # ------------------------------------------------------------------
    # H17 BREAKDOWN FLOW TEMPLATES — Created S055, pending Meta approval.
    # All use the "trabajador de Grupo Alvarez" anchor pattern for UTILITY.
    # ------------------------------------------------------------------
    {
        # Sent business-initiated when a breakdown ticket is registered.
        # Body: "Usted recibe este mensaje porque consta como trabajador de
        #        Grupo Alvarez. Su averia ha sido registrada con el codigo {{2}}.
        #        El equipo de taller ha sido notificado. Puede ampliar
        #        informacion respondiendo a este mensaje, {{1}}."
        # Enviado de forma business-initiated al registrar un ticket de averia.
        "name":        "breakdown_ticket_created",
        "content_sid": "HX32d590d2a40360c789060a7f88fa50ef",
        "category":    WhatsAppTemplate.CATEGORY_UTILITY,
        "language":    "es",
    },
    {
        # Sent business-initiated to request GPS location from the mechanic
        # after a breakdown is registered (H17 Step 5 — geolocation).
        # Body: "Usted recibe este mensaje porque consta como trabajador de
        #        Grupo Alvarez. Para completar la averia {{2}}, necesitamos
        #        su ubicacion actual. Por favor, comparta su ubicacion
        #        pulsando el icono de adjunto en WhatsApp, {{1}}."
        # Enviado de forma business-initiated para solicitar ubicacion GPS.
        "name":        "breakdown_location_request",
        "content_sid": "HXb9139eb63adb500855a679957d3de232",
        "category":    WhatsAppTemplate.CATEGORY_UTILITY,
        "language":    "es",
    },
    {
        # Sent business-initiated when the workshop needs additional info
        # about an open ticket. Variable {{3}} carries the specific question.
        # Body: "Usted recibe este mensaje porque consta como trabajador de
        #        Grupo Alvarez. El taller necesita informacion adicional sobre
        #        la averia {{2}}: {{3}} Responda a este mensaje para continuar, {{1}}."
        # Enviado cuando el taller necesita informacion adicional sobre un ticket.
        "name":        "breakdown_info_request",
        "content_sid": "HXe3baa955000b20e312d6d000f775533b",
        "category":    WhatsAppTemplate.CATEGORY_UTILITY,
        "language":    "es",
    },
    {
        # Quick-reply sent when a mechanic is assigned to a breakdown ticket.
        # Buttons: "Si, la atiendo" / "No disponible"
        # Body: "Usted recibe este mensaje porque consta como trabajador de
        #        Grupo Alvarez. Se le ha asignado la averia {{2}} en {{3}}.
        #        Acceda al panel para ver los detalles o confirme su
        #        disponibilidad, {{1}}."
        # Quick-reply enviado al asignar un mecanico a un ticket de averia.
        "name":        "breakdown_assigned",
        "content_sid": "HX41a742714147cc5ec92fa83dbf5c3db6",
        "category":    WhatsAppTemplate.CATEGORY_UTILITY,
        "language":    "es",
    },
    {
        # Quick-reply broadcast to workshop mechanics when a new ticket is created.
        # Buttons: "Si, la atiendo" / "No disponible"
        # Body: "Usted recibe este mensaje porque consta como trabajador de
        #        Grupo Alvarez. Nueva averia registrada: {{2}} en {{3}},
        #        ubicacion: {{4}}. Puede atenderla, {{1}}?"
        # Quick-reply de difusion al taller al crear un nuevo ticket de averia.
        "name":        "breakdown_broadcast",
        "content_sid": "HXa1b32520e94663a32d3c7c1453429fe3",
        "category":    WhatsAppTemplate.CATEGORY_UTILITY,
        "language":    "es",
    },
    # ------------------------------------------------------------------
    # H23 DOCUMENT EXPIRY ALERT -- Created S021, APPROVED (confirmado
    # via API de Twilio en S025, 2026-07-20: {"status": "approved"}).
    # Comentario "pending Meta approval" de mas abajo desactualizado
    # hasta este mismo commit -- corregido tras el hallazgo real de
    # que este seed nunca se habia ejecutado desde que se anadio esta
    # entrada, dejando la tabla WhatsAppTemplate sin fila para esta
    # plantilla pese a que Twilio ya la tenia aprobada.
    # ------------------------------------------------------------------
    {
        # Sent business-initiated when a MachineDocument.expiry_date is
        # approaching, to alert about a cost-center document nearing expiry
        # (ITV, OCA certificate, insurance, etc.). Not yet wired to any
        # sender task -- created ahead of the alerting feature itself.
        # REJECTED once (HXc85c75b0d8ba412025ff09db4960cd35) and again on a
        # duplicate attempt (HX1b943a259babe8fe3e9f329bf7f7b25b) by Meta:
        # "Variables can't be at the start or end of the template" -- the
        # body ended in "..., {{1}}.". Both deleted from Twilio, replaced by
        # this corrected body with the greeting variable moved to the start
        # and the message ending in plain text.
        # Body: "Hola {{1}}. Usted recibe este mensaje porque consta como
        #        trabajador de Grupo Alvarez. El documento {{2}} de la
        #        maquina {{3}} caduca el {{4}}. Consulte el panel para mas
        #        detalles."
        # Enviado de forma business-initiated cuando un documento de centro
        # de gasto esta proximo a caducar. Aun sin tarea de envio conectada
        # -- creada antes de construir la propia funcionalidad de alarmas.
        # RECHAZADA una vez (HXc85c75b0d8ba412025ff09db4960cd35) y de nuevo
        # en un intento duplicado (HX1b943a259babe8fe3e9f329bf7f7b25b) por
        # Meta: "Variables can't be at the start or end of the template" --
        # el cuerpo terminaba en "..., {{1}}.". Ambas borradas de Twilio,
        # sustituidas por este cuerpo corregido con la variable de saludo
        # movida al principio y el mensaje terminando en texto plano.
        "name":        "document_expiry_alert",
        "content_sid": "HX55da66276bb2025f691c378abff0123e",
        "category":    WhatsAppTemplate.CATEGORY_UTILITY,
        "language":    "es",
    },
    # ------------------------------------------------------------------
    # ONBOARDING HELPER TEMPLATE — Existing, not yet submitted to Meta.
    # Pending decision on whether to submit or redesign for H17 flow.
    # ------------------------------------------------------------------
    {
        # Quick-reply help menu sent to employees needing panel access or
        # password assistance. Created prior to H17; not yet submitted to Meta.
        # Buttons: "Acceder al panel" / "Recordar contrasena"
        # Body: "Hola! Que necesitas?"
        # Quick-reply de ayuda para empleados con acceso al panel o contrasena.
        "name":        "employee_help_menu",
        "content_sid": "HXe8c20c02d4cf4ab340924ed5e2b0ac6f",
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
    Comando de gestion: seed_whatsapp_templates.
    Idempotente — seguro de ejecutar multiples veces. Usa get_or_create para
    evitar registros duplicados. Actualiza content_sid y category si el registro
    ya existe con un valor diferente, soportando re-sembrado tras cambios de ContentSid.

    Uso:
        python -m dotenv run python manage.py seed_whatsapp_templates
    """

    help = "Siembra las plantillas WhatsApp del Grupo Alvarez en la base de datos."

    def handle(self, *args, **options):
        """
        Main entry point. Resolves the Grupo Alvarez Company instance and
        iterates over TEMPLATE_DEFINITIONS to create or update each template.
        Warns if any ContentSid value is still set to a PENDING placeholder.
        ---
        Punto de entrada principal. Resuelve la instancia Company del Grupo Alvarez
        e itera sobre TEMPLATE_DEFINITIONS para crear o actualizar cada plantilla.
        Advierte si algun valor ContentSid sigue establecido como marcador PENDING.
        """
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
        updated_count = 0

        for definition in TEMPLATE_DEFINITIONS:
            name        = definition["name"]
            content_sid = definition["content_sid"]
            category    = definition["category"]
            language    = definition["language"]

            if content_sid.startswith("PENDING_"):
                self.stdout.write(
                    self.style.WARNING(
                        f"# [SEED] Plantilla '{name}': ContentSid aun no configurado "
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
                    updated_count += 1
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

        self.stdout.write(
            self.style.SUCCESS(
                f"# [SEED] Seed completado. "
                f"{seeded_count} creada(s), "
                f"{updated_count} actualizada(s). "
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

        # Desactivar plantillas legacy eliminadas de Twilio.
        # alias_confirmation fue eliminada de Twilio en H17 S055 (legacy H13).
        # Se marca is_active=False para conservar el registro historico en BD.
        LEGACY_INACTIVE = ["alias_confirmation"]
        for legacy_name in LEGACY_INACTIVE:
            updated = WhatsAppTemplate.objects.filter(
                company=company,
                name=legacy_name,
                is_active=True,
            ).update(is_active=False)
            if updated:
                self.stdout.write(
                    self.style.WARNING(
                        f"# [SEED] Plantilla legacy '{legacy_name}' marcada "
                        f"como inactiva (eliminada de Twilio en H17)."
                    )
                )
