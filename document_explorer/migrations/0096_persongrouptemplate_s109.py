# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0096_persongrouptemplate_s109.py
"""
H31 (S109). Crea `PersonGroupTemplate` -- "grupo de reparto" guardado
por un supervisor: conjunto de personas (M2M a PersonIdentity),
deliberadamente SIN FK a Company para permitir mezclar personas de
varias empresas reales en un mismo grupo (caso real: entrega de
chalecos de alta visibilidad a choferes de varias empresas a la vez).
Ver el docstring completo de la clase en models.py para el
razonamiento completo.

Solo esquema, ninguna fila sembrada -- vacío hasta que un supervisor
guarde su primer grupo desde el panel.
"""
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0095_seed_factura_informe_empresa_s108"),
    ]

    operations = [
        migrations.CreateModel(
            name="PersonGroupTemplate",
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
                        verbose_name="Nombre del grupo",
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
                        related_name="created_person_groups",
                        to="ivr_config.companyuser",
                        verbose_name="Creado por",
                    ),
                ),
                (
                    "members",
                    models.ManyToManyField(
                        related_name="group_templates",
                        to="document_explorer.personidentity",
                        verbose_name="Personas incluidas",
                    ),
                ),
            ],
            options={
                "verbose_name": "Grupo de reparto",
                "verbose_name_plural": "Grupos de reparto",
                "ordering": ["name"],
            },
        ),
    ]
