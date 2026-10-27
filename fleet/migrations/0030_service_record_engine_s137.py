# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/fleet/migrations/0030_service_record_engine_s137.py
# H30 (S137): una tarea del parte puede anotar dos revisiones, la del
# motor del camión y la del motor de la grúa. Campo nuevo con valor por
# defecto (las que ya hay son del motor del camión) y la tarea pasa de
# uno-a-uno a muchos-a-uno, con una revisión por tarea y motor. Sin
# datos que mover.

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("fleet", "0029_gasoges_unit_source_convention_s137"),
        ("work_order_processor", "0036_workshop_notice_read_s137"),
    ]

    operations = [
        migrations.AddField(
            model_name="machineservicerecord",
            name="engine",
            field=models.CharField(
                choices=[
                    ("TRUCK", "Motor del camión"),
                    ("CRANE", "Motor de la grúa"),
                ],
                default="TRUCK",
                max_length=10,
                verbose_name="Motor",
            ),
        ),
        migrations.AlterField(
            model_name="machineservicerecord",
            name="work_order_line",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="service_records",
                to="work_order_processor.workorderentryline",
                verbose_name="Tarea del parte",
            ),
        ),
        migrations.AddConstraint(
            model_name="machineservicerecord",
            constraint=models.UniqueConstraint(
                fields=("work_order_line", "engine"),
                name="unique_service_per_line_engine",
            ),
        ),
    ]
