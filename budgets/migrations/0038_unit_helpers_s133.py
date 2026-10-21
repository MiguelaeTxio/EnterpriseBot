# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/budgets/migrations/0038_unit_helpers_s133.py
"""
H37 (S133). Helpers of an albarán.

---

H37 (S133). Ayudantes del albarán: operarios que acompañan al
conductor en el mismo vehículo.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("budgets", "0037_unit_estimated_close_s133"),
        ("ivr_config", "0049_companyuser_role_assist_supervisor_s132"),
    ]

    operations = [
        migrations.AddField(
            model_name="workorderassistanceunit",
            name="helpers",
            field=models.ManyToManyField(
                blank=True,
                help_text=(
                    "Operarios que acompañan al conductor en este "
                    "vehículo."
                ),
                related_name="assistance_units_helper",
                to="ivr_config.companyuser",
                verbose_name="Ayudantes",
            ),
        ),
    ]
