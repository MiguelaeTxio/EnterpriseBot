# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/hr_calendar/migrations/0046_clock_day_hold_s149.py
"""
H24 (S149 invasora). Clock-in days set aside to review later.

---

Días de fichajes marcados para revisarlos después (Miguel Ángel, S149,
18/11): sin el albarán a mano, la jornada se marca y sale en otro color.
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("hr_calendar", "0045_clockcorrection_source_system_s149"),
        ("ivr_config", "0050_role_crane_operator_s137"),
    ]

    operations = [
        migrations.CreateModel(
            name="ClockDayHold",
            fields=[
                ("id", models.BigAutoField(auto_created=True,
                                           primary_key=True,
                                           serialize=False,
                                           verbose_name="ID")),
                ("day", models.DateField(verbose_name="Día")),
                ("note", models.CharField(blank=True, default="",
                                          max_length=255,
                                          verbose_name="Motivo")),
                ("held_at", models.DateTimeField(
                    auto_now_add=True, verbose_name="Marcado")),
                ("company_user", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="clock_day_holds",
                    to="ivr_config.companyuser",
                    verbose_name="Trabajador")),
                ("held_by", models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="+", to="ivr_config.companyuser",
                    verbose_name="Marcado por")),
            ],
            options={
                "verbose_name": "Día de fichajes pendiente de revisar",
                "verbose_name_plural": "Días de fichajes pendientes de "
                                       "revisar",
                "constraints": [models.UniqueConstraint(
                    fields=("company_user", "day"),
                    name="clockdayhold_unique_user_day")],
            },
        ),
    ]
