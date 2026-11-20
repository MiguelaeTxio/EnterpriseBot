# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/fleet/migrations/0042_vehicle_specs_s154.py
"""
H23 (S154, invasora) -- especificaciones técnicas para filtrar los
centros de gasto: capacidad de elevación (t), masa máxima autorizada,
de dónde salió cada dato y cuándo se leyó.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("fleet", "0041_crew_s153"),
    ]

    operations = [
        migrations.AddField(
            model_name="machineasset",
            name="capacity_tonnes",
            field=models.DecimalField(
                blank=True, decimal_places=2, max_digits=7, null=True,
                verbose_name="Capacidad de elevación (t)",
            ),
        ),
        migrations.AddField(
            model_name="machineasset",
            name="max_authorized_mass_kg",
            field=models.PositiveIntegerField(
                blank=True, null=True,
                verbose_name="Masa máxima autorizada (kg)",
            ),
        ),
        migrations.AddField(
            model_name="machineasset",
            name="specs_source",
            field=models.TextField(
                blank=True, default="",
                verbose_name="Origen de las especificaciones",
            ),
        ),
        migrations.AddField(
            model_name="machineasset",
            name="specs_read_at",
            field=models.DateTimeField(
                blank=True, null=True,
                verbose_name="Especificaciones leídas el",
            ),
        ),
    ]
