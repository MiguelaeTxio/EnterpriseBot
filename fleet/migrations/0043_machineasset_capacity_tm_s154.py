# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/fleet/migrations/0043_machineasset_capacity_tm_s154.py
"""
H23 (S154, invasora) -- momento de carga (t·m) de la grúa de los
autocargantes, para filtrarlos aparte de la capacidad en toneladas.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("fleet", "0042_vehicle_specs_s154"),
    ]

    operations = [
        migrations.AddField(
            model_name="machineasset",
            name="capacity_tm",
            field=models.DecimalField(
                blank=True, decimal_places=2, max_digits=7, null=True,
                verbose_name="Momento de carga (t·m)",
            ),
        ),
    ]
