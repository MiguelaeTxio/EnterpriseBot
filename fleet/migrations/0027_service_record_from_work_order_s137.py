# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/fleet/migrations/0027_service_record_from_work_order_s137.py
# H30 (S137): revisión anotada desde la casilla "Revisión" de una tarea
# del parte (filtros, aceite y próxima revisión). Campos nuevos nulos o
# en blanco; sin datos que mover.

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("fleet", "0026_gasoges_meter_broken_s137"),
        ("work_order_processor", "0035_tipo_tarea_revision_s137"),
    ]

    operations = [
        migrations.AddField(
            model_name="machineservicerecord",
            name="work_order_line",
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="service_record",
                to="work_order_processor.workorderentryline",
                verbose_name="Tarea del parte",
            ),
        ),
        migrations.AddField(
            model_name="machineservicerecord",
            name="filters_changed",
            field=models.CharField(
                blank=True, max_length=255, verbose_name="Filtros cambiados",
            ),
        ),
        migrations.AddField(
            model_name="machineservicerecord",
            name="oil_type",
            field=models.CharField(
                blank=True,
                choices=[
                    ("SYNTHETIC", "Sintético (cada 1200 h)"),
                    ("SEMI_SYNTHETIC", "Semisintético (cada 800 h)"),
                ],
                max_length=20,
                verbose_name="Tipo de aceite",
            ),
        ),
        migrations.AddField(
            model_name="machineservicerecord",
            name="oil_litres",
            field=models.DecimalField(
                blank=True,
                decimal_places=1,
                max_digits=6,
                null=True,
                verbose_name="Litros de aceite",
            ),
        ),
        migrations.AddField(
            model_name="machineservicerecord",
            name="next_service_hours",
            field=models.PositiveIntegerField(
                blank=True, null=True,
                verbose_name="Próxima revisión (horas)",
            ),
        ),
        migrations.AddField(
            model_name="machineservicerecord",
            name="next_service_km",
            field=models.PositiveIntegerField(
                blank=True, null=True, verbose_name="Próxima revisión (km)",
            ),
        ),
    ]
