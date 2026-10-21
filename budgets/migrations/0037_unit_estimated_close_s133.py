# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/budgets/migrations/0037_unit_estimated_close_s133.py
"""
H37 (S133). Base closing from the office: estimated km and fuel.

---

H37 (S133). Cierre en base desde la oficina: km y gasoil estimados del
servicio (de base a base) y quién cerró.
"""
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("budgets", "0036_assistancecrew_driverposition_s133"),
        ("ivr_config", "0049_companyuser_role_assist_supervisor_s132"),
    ]

    operations = [
        migrations.AddField(
            model_name="workorderassistanceunit",
            name="estimated_km",
            field=models.DecimalField(
                blank=True,
                decimal_places=1,
                help_text=(
                    "De base al servicio y vuelta, aunque la máquina "
                    "encadenara otro servicio."
                ),
                max_digits=8,
                null=True,
                verbose_name="Km estimados del servicio",
            ),
        ),
        migrations.AddField(
            model_name="workorderassistanceunit",
            name="estimated_fuel_liters",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Consumo estimado del servicio, de base a base.",
                max_digits=7,
                null=True,
                verbose_name="Gasoil estimado (l)",
            ),
        ),
        migrations.AddField(
            model_name="workorderassistanceunit",
            name="base_closed_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to="ivr_config.companyuser",
                verbose_name="Cerrado en base por",
            ),
        ),
    ]
