# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0100_jobposition_personidentity_job_position_s109.py
"""
H31 (S109). Crea `JobPosition` (catalogo de puestos de trabajo, cada
uno con sus tipos documentales obligatorios -- "plantilla de puesto",
misma mecanica que PersonalDossierTemplate) y anade
`PersonIdentity.job_position` (FK nullable). Ver docstring completo
de ambos en models.py para el razonamiento completo -- origen: el
triangulo de "documento faltante" marcaba cualquiera de los 70-80
tipos del catalogo sin distinguir si el puesto de la persona lo
necesita de verdad.

Solo esquema, ninguna fila sembrada -- vacio hasta que Miguel Angel
cree el primer puesto desde el panel.
"""
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0099_personaldossiertemplate_epi_items_s109"),
    ]

    operations = [
        migrations.CreateModel(
            name="JobPosition",
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
                        unique=True,
                        verbose_name="Puesto",
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
                        related_name="created_job_positions",
                        to="ivr_config.companyuser",
                        verbose_name="Creado por",
                    ),
                ),
                (
                    "required_document_types",
                    models.ManyToManyField(
                        blank=True,
                        related_name="job_positions",
                        to="document_explorer.documenttypecatalog",
                        verbose_name="Documentos obligatorios para este puesto",
                    ),
                ),
            ],
            options={
                "verbose_name": "Puesto de trabajo",
                "verbose_name_plural": "Puestos de trabajo",
                "ordering": ["name"],
            },
        ),
        migrations.AddField(
            model_name="personidentity",
            name="job_position",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="people",
                to="document_explorer.jobposition",
                verbose_name="Puesto de trabajo",
            ),
        ),
    ]
