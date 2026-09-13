# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0082_personaldossiertemplate_s103.py
"""
H31 (S103). Crea `PersonalDossierTemplate` -- "plantilla" de dossier
guardada por un supervisor sobre una persona: qué TIPOS documentales
incluir (M2M a DocumentTypeCatalog, resuelto al vigente de cada uno
en el momento de aplicar la plantilla, nunca IDs fijos de
DocumentIndexEntry) y en qué formato (PDF único / ZIP). Ver el
docstring completo de la clase en models.py para el razonamiento
completo de esta decisión de diseño.

Solo esquema, ninguna fila sembrada -- vacío hasta que un supervisor
guarde su primera plantilla desde el panel.
"""
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0081_documenttypecatalog_family_media_label_s103"),
    ]

    operations = [
        migrations.CreateModel(
            name="PersonalDossierTemplate",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "name",
                    models.CharField(
                        max_length=150,
                        verbose_name="Nombre de la plantilla",
                        help_text=(
                            "Nunca vacío -- \"Dossier N\" autonumerado si el "
                            "supervisor no escribe uno propio al guardar."
                        ),
                    ),
                ),
                (
                    "output_format",
                    models.CharField(
                        max_length=3,
                        choices=[("PDF", "PDF único"), ("ZIP", "ZIP")],
                        verbose_name="Formato de salida",
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(
                        auto_now_add=True, verbose_name="Fecha de creación",
                    ),
                ),
                (
                    "updated_at",
                    models.DateTimeField(
                        auto_now=True, verbose_name="Última edición",
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="created_dossier_templates",
                        to="ivr_config.companyuser",
                        verbose_name="Creada por",
                    ),
                ),
                (
                    "person",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="dossier_templates",
                        to="document_explorer.personidentity",
                        verbose_name="Persona",
                    ),
                ),
                (
                    "document_types",
                    models.ManyToManyField(
                        related_name="dossier_templates",
                        to="document_explorer.documenttypecatalog",
                        verbose_name="Tipos documentales incluidos",
                        help_text=(
                            "El \"vigente\" de cada tipo se resuelve de "
                            "nuevo cada vez que se aplica la plantilla -- "
                            "nunca fila fija de DocumentIndexEntry."
                        ),
                    ),
                ),
            ],
            options={
                "verbose_name": "Plantilla de dossier",
                "verbose_name_plural": "Plantillas de dossier",
                "ordering": ["person_id", "created_at"],
            },
        ),
    ]
