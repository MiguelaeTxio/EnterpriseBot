# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/ivr_config/migrations/0008_sectioncontact_transferattempt_pendingnotification.py
"""
Migration 0008 — SectionContact through model + TransferAttempt + PendingNotification.

SectionContact replaces the implicit Django M2M join table ivr_config_section_contacts
with an explicit through model (ivr_config_sectioncontact) that adds a priority field
for ordered multi-contact transfer attempts (Paso 39).

The conversion uses SeparateDatabaseAndState to avoid dropping and recreating the
existing join table, which would destroy all existing Section ↔ Contact relations.
The database_operations block renames the table and adds the new columns.
The state_operations block informs the Django migration autodetector of the new
model and the altered ManyToManyField.

TransferAttempt and PendingNotification are created as conventional new models.
---
Migración 0008 — Modelo through SectionContact + TransferAttempt + PendingNotification.

SectionContact reemplaza la tabla de unión M2M implícita de Django ivr_config_section_contacts
por un modelo through explícito (ivr_config_sectioncontact) que añade un campo priority
para intentos de transferencia multi-contacto ordenados (Paso 39).

La conversión usa SeparateDatabaseAndState para evitar eliminar y recrear la tabla de
unión existente, lo que destruiría todas las relaciones Section ↔ Contact existentes.
El bloque database_operations renombra la tabla y añade las nuevas columnas.
El bloque state_operations informa al autodetector de migraciones de Django del nuevo
modelo y el ManyToManyField alterado.

TransferAttempt y PendingNotification se crean como nuevos modelos convencionales.
"""

import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("ivr_config", "0007_section_call_flow_callflow_fallback_section"),
    ]

    operations = [

        # -------------------------------------------------------------------
        # PART 1 — Convert implicit M2M table to explicit SectionContact through model.
        # PARTE 1 — Convertir tabla M2M implícita en modelo through SectionContact explícito.
        #
        # Django already created ivr_config_section_contacts when Section.contacts
        # was defined as a plain ManyToManyField. That table has two columns:
        #   - id          (auto PK)
        #   - section_id  (FK → ivr_config_section)
        #   - contact_id  (FK → ivr_config_contact)
        #
        # We need ivr_config_sectioncontact with:
        #   - id          (auto PK)
        #   - section_id  (FK → ivr_config_section)
        #   - contact_id  (FK → ivr_config_contact)
        #   - priority    (IntegerField, default 0)
        #   - created_at  (DateTimeField, auto_now_add)
        #
        # Strategy: rename the table, then add the two new columns.
        # The FK column names (section_id, contact_id) match what Django used
        # in the implicit table, so no column renames are needed.
        #
        # Django ya creó ivr_config_section_contacts cuando Section.contacts se
        # definió como ManyToManyField simple. Esa tabla tiene las columnas:
        #   - id          (PK auto)
        #   - section_id  (FK → ivr_config_section)
        #   - contact_id  (FK → ivr_config_contact)
        #
        # Necesitamos ivr_config_sectioncontact con:
        #   - id          (PK auto)
        #   - section_id  (FK → ivr_config_section)
        #   - contact_id  (FK → ivr_config_contact)
        #   - priority    (IntegerField, default 0)
        #   - created_at  (DateTimeField, auto_now_add)
        #
        # Estrategia: renombrar la tabla y luego añadir las dos columnas nuevas.
        # Los nombres de columna FK (section_id, contact_id) coinciden con los que
        # Django usó en la tabla implícita, por lo que no se necesitan renombres de columna.
        # -------------------------------------------------------------------
        migrations.SeparateDatabaseAndState(

            database_operations=[
                # Step 1: Rename the implicit join table to the through model table name.
                # Paso 1: Renombrar la tabla de unión implícita al nombre de la tabla through.
                migrations.RunSQL(
                    sql="RENAME TABLE ivr_config_section_contacts TO ivr_config_sectioncontact;",
                    reverse_sql="RENAME TABLE ivr_config_sectioncontact TO ivr_config_section_contacts;",
                ),
                # Step 2: Add the priority column with default 0 (existing rows get 0).
                # Paso 2: Añadir la columna priority con default 0 (filas existentes obtienen 0).
                migrations.RunSQL(
                    sql="ALTER TABLE ivr_config_sectioncontact ADD COLUMN priority INT NOT NULL DEFAULT 0;",
                    reverse_sql="ALTER TABLE ivr_config_sectioncontact DROP COLUMN priority;",
                ),
                # Step 3: Add the created_at column with current timestamp as default.
                # Paso 3: Añadir la columna created_at con el timestamp actual como default.
                migrations.RunSQL(
                    sql="ALTER TABLE ivr_config_sectioncontact ADD COLUMN created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6);",
                    reverse_sql="ALTER TABLE ivr_config_sectioncontact DROP COLUMN created_at;",
                ),
            ],

            state_operations=[
                # Declare the SectionContact model so the Django ORM knows about it.
                # Declarar el modelo SectionContact para que el ORM de Django lo conozca.
                migrations.CreateModel(
                    name="SectionContact",
                    fields=[
                        ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                        ("section", models.ForeignKey(
                            help_text="Sección a la que pertenece esta asignación de contacto.",
                            on_delete=django.db.models.deletion.CASCADE,
                            related_name="section_contacts",
                            to="ivr_config.section",
                            verbose_name="Sección",
                        )),
                        ("contact", models.ForeignKey(
                            help_text="Contacto asignado a esta sección para transferencias de llamada.",
                            on_delete=django.db.models.deletion.CASCADE,
                            related_name="section_assignments",
                            to="ivr_config.contact",
                            verbose_name="Contacto",
                        )),
                        ("priority", models.IntegerField(
                            default=0,
                            help_text="Orden de intento de transferencia. Menor número = mayor prioridad.",
                            verbose_name="Prioridad",
                        )),
                        ("created_at", models.DateTimeField(
                            auto_now_add=True,
                            verbose_name="Fecha de creación",
                        )),
                    ],
                    options={
                        "verbose_name": "Contacto de sección",
                        "verbose_name_plural": "Contactos de sección",
                        "ordering": ["section", "priority", "contact__name"],
                    },
                ),
                # Update unique_together on the new model.
                # Actualizar unique_together en el nuevo modelo.
                migrations.AlterUniqueTogether(
                    name="sectioncontact",
                    unique_together={("section", "contact")},
                ),
                # Alter Section.contacts to reference SectionContact as through model.
                # Alterar Section.contacts para referenciar SectionContact como modelo through.
                migrations.AlterField(
                    model_name="section",
                    name="contacts",
                    field=models.ManyToManyField(
                        blank=True,
                        help_text=(
                            "Personas asociadas a esta sección ordenadas por prioridad de transferencia. "
                            "La relación se gestiona a través del modelo intermedio SectionContact, que "
                            "añade el campo 'priority' para controlar el orden de intento de transferencia "
                            "desde el panel. Menor número de prioridad = mayor preferencia."
                        ),
                        related_name="sections",
                        through="ivr_config.SectionContact",
                        through_fields=("section", "contact"),
                        to="ivr_config.contact",
                        verbose_name="Contactos",
                    ),
                ),
            ],
        ),

        # -------------------------------------------------------------------
        # PART 2 — Create TransferAttempt model (conventional CreateModel).
        # PARTE 2 — Crear modelo TransferAttempt (CreateModel convencional).
        # -------------------------------------------------------------------
        migrations.CreateModel(
            name="TransferAttempt",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("call_sid", models.CharField(
                    db_index=True,
                    help_text="Identificador único de la llamada Twilio (CA...). Clave primaria de negocio.",
                    max_length=40,
                    unique=True,
                    verbose_name="Call SID",
                )),
                ("section", models.ForeignKey(
                    blank=True,
                    help_text="Sección destino de la transferencia.",
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="transfer_attempts",
                    to="ivr_config.section",
                    verbose_name="Sección",
                )),
                ("twilio_number", models.CharField(
                    help_text="Número Twilio receptor de la llamada original (formato E.164).",
                    max_length=20,
                    verbose_name="Número Twilio",
                )),
                ("caller_number", models.CharField(
                    help_text="Número del llamante original (formato E.164).",
                    max_length=20,
                    verbose_name="Número llamante",
                )),
                ("contact_index", models.IntegerField(
                    default=0,
                    help_text=(
                        "Índice (base 0) del contacto de sección que se está intentando en este momento, "
                        "ordenado por SectionContact.priority ASC."
                    ),
                    verbose_name="Índice de contacto",
                )),
                ("status", models.CharField(
                    choices=[("PENDING", "Pendiente"), ("FAILED", "Fallida"), ("COMPLETED", "Completada")],
                    default="PENDING",
                    help_text="Estado actual de la transferencia.",
                    max_length=20,
                    verbose_name="Estado",
                )),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Fecha de creación")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Fecha de modificación")),
            ],
            options={
                "verbose_name": "Intento de transferencia",
                "verbose_name_plural": "Intentos de transferencia",
                "ordering": ["-created_at"],
            },
        ),

        # -------------------------------------------------------------------
        # PART 3 — Create PendingNotification model (conventional CreateModel).
        # PARTE 3 — Crear modelo PendingNotification (CreateModel convencional).
        # -------------------------------------------------------------------
        migrations.CreateModel(
            name="PendingNotification",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("company", models.ForeignKey(
                    help_text="Empresa a la que pertenece esta notificación pendiente.",
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="pending_notifications",
                    to="ivr_config.company",
                    verbose_name="Empresa",
                )),
                ("section", models.ForeignKey(
                    blank=True,
                    help_text="Sección destino que no pudo gestionar la llamada.",
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="pending_notifications",
                    to="ivr_config.section",
                    verbose_name="Sección",
                )),
                ("caller_number", models.CharField(
                    help_text="Número de teléfono del llamante en formato E.164.",
                    max_length=20,
                    verbose_name="Número llamante",
                )),
                ("call_sid", models.CharField(
                    help_text="Identificador único de la llamada Twilio para trazabilidad.",
                    max_length=40,
                    verbose_name="Call SID",
                )),
                ("voice_recording_url", models.URLField(
                    blank=True,
                    help_text="URL de Twilio de la grabación de voz del mensaje dejado por el llamante.",
                    verbose_name="URL de grabación de voz",
                )),
                ("channel", models.CharField(
                    choices=[
                        ("WHATSAPP", "WhatsApp"),
                        ("SMS", "SMS"),
                        ("EMAIL", "Correo electrónico"),
                        ("PENDING", "Pendiente"),
                    ],
                    default="PENDING",
                    help_text=(
                        "Canal por el que se enviará la notificación al responsable. "
                        "PENDING: aún no procesado por Celery."
                    ),
                    max_length=20,
                    verbose_name="Canal de notificación",
                )),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Fecha de creación")),
                ("notified_at", models.DateTimeField(
                    blank=True,
                    help_text="Fecha y hora en que se envió la notificación real al responsable.",
                    null=True,
                    verbose_name="Fecha de notificación",
                )),
                ("notes", models.TextField(
                    blank=True,
                    help_text="Observaciones adicionales sobre la llamada o el seguimiento.",
                    verbose_name="Notas",
                )),
            ],
            options={
                "verbose_name": "Notificación pendiente",
                "verbose_name_plural": "Notificaciones pendientes",
                "ordering": ["-created_at"],
            },
        ),
    ]
