# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/fleet/migrations/0034_machinegrouptemplate_s148.py
"""
H31 (S148). Crea `MachineGroupTemplate`: grupos de selección de
máquinas en árbol, iguales que los de Personal (Miguel Ángel: "Vamos a
hacer lo mismo que en personal, creando los grupos de selección").
Solo esquema, ningún grupo sembrado.
"""
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("fleet", "0033_refuelexporttemplate_s144"),
        ("ivr_config", "0056_workdayscheduleday_holiday_s144"),
    ]

    operations = [
        migrations.CreateModel(
            name="MachineGroupTemplate",
            fields=[
                (
                    "id",
                    models.BigAutoField(
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
                        related_name="created_machine_groups",
                        to="ivr_config.companyuser",
                        verbose_name="Creado por",
                    ),
                ),
                (
                    "parent",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="children",
                        to="fleet.machinegrouptemplate",
                        verbose_name="Dentro de",
                    ),
                ),
                (
                    "members",
                    models.ManyToManyField(
                        related_name="group_templates",
                        to="fleet.machineasset",
                        verbose_name="Máquinas incluidas",
                    ),
                ),
            ],
            options={
                "verbose_name": "Grupo de selección de máquinas",
                "verbose_name_plural": "Grupos de selección de máquinas",
                "ordering": ["name"],
            },
        ),
    ]
