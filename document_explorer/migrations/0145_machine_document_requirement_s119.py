# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0145_machine_document_requirement_s119.py
"""
H30 (S119). Crea `MachineDocumentRequirement` (misma mecánica que
`JobPosition`, para MachineAsset). Ver docstring completo en
document_explorer/models.py -- origen: Miguel Ángel, verbatim, "lo
mismo que tenemos requisitos documentales para personas, también lo
tenemos que tener para los tipos de máquina [...] exactamente la misma
filosofía que con los empleados".

El campo `MachineAsset.document_requirement` va en su propia migración
de `fleet` (0013), que depende de esta -- `AddField` sobre un modelo
de otra app no puede ir aquí (el estado de migraciones lo aplicaría al
app equivocado).

Solo esquema, ninguna fila sembrada -- vacío hasta que Miguel Ángel
cree el primer requisito desde el panel.
"""
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0144_tipo_condiciones_generales_seguro_s119"),
    ]

    operations = [
        migrations.CreateModel(
            name="MachineDocumentRequirement",
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
                        verbose_name="Nombre",
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
                        related_name="created_machine_document_requirements",
                        to="ivr_config.companyuser",
                        verbose_name="Creado por",
                    ),
                ),
                (
                    "required_document_types",
                    models.ManyToManyField(
                        blank=True,
                        related_name="machine_document_requirements",
                        to="document_explorer.documenttypecatalog",
                        verbose_name=(
                            "Documentos obligatorios para este requisito"
                        ),
                    ),
                ),
            ],
            options={
                "verbose_name": "Requisito de documentación (máquina)",
                "verbose_name_plural": (
                    "Requisitos de documentación (máquina)"
                ),
                "ordering": ["name"],
            },
        ),
    ]
