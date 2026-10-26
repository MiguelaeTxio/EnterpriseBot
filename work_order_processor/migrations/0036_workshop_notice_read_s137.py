# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/work_order_processor/migrations/0036_workshop_notice_read_s137.py
# H30 (S137): el aviso de Nuevo parte sale una sola vez por operario.
# Versión del aviso (empieza en 1 en el que ya existe) y tabla nueva de
# la versión aceptada por cada operario; sin datos que mover.

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("ivr_config", "0049_companyuser_role_assist_supervisor_s132"),
        ("work_order_processor", "0035_tipo_tarea_revision_s137"),
    ]

    operations = [
        migrations.AddField(
            model_name="workshopnotice",
            name="version",
            field=models.PositiveIntegerField(
                default=1,
                help_text="Sube cada vez que cambia el texto del aviso.",
                verbose_name="Versión",
            ),
        ),
        migrations.CreateModel(
            name="WorkshopNoticeRead",
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
                    "version",
                    models.PositiveIntegerField(
                        verbose_name="Versión aceptada",
                    ),
                ),
                (
                    "read_at",
                    models.DateTimeField(
                        auto_now=True, verbose_name="Aceptado el",
                    ),
                ),
                (
                    "company_user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="+",
                        to="ivr_config.companyuser",
                        verbose_name="Operario",
                    ),
                ),
                (
                    "notice",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="reads",
                        to="work_order_processor.workshopnotice",
                        verbose_name="Aviso",
                    ),
                ),
            ],
            options={
                "verbose_name": "Aviso aceptado",
                "verbose_name_plural": "Avisos aceptados",
                "constraints": [
                    models.UniqueConstraint(
                        fields=("notice", "company_user"),
                        name="unique_notice_read_per_user",
                    ),
                ],
            },
        ),
    ]
