# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/fleet/migrations/0025_meterreading_work_order_line_s137.py
# H30 (S137): lecturas de km y horas sacadas de los partes digitales
# (origen "Parte de trabajo" y enlace con el bloque del parte).

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("fleet", "0024_machineasset_service_crane_hours_interval_s137"),
        ("work_order_processor", "0034_workshop_notice_s133"),
    ]

    operations = [
        migrations.AddField(
            model_name="machinemeterreading",
            name="work_order_line",
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="meter_reading",
                to="work_order_processor.workorderentryline",
                verbose_name="Bloque del parte",
            ),
        ),
        migrations.AlterField(
            model_name="machinemeterreading",
            name="source",
            field=models.CharField(
                choices=[
                    ("MANUAL", "A mano"),
                    ("GASOGES", "Surtidor (GasoGes)"),
                    ("PARTE", "Parte de trabajo"),
                ],
                default="MANUAL",
                max_length=10,
                verbose_name="Origen",
            ),
        ),
    ]
