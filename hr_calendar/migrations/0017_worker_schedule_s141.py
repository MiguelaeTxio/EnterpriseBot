# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/hr_calendar/migrations/0017_worker_schedule_s141.py
# H24 (S141): el horario de jornada va en el trabajador (no hace falta
# usuario del panel).

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("hr_calendar", "0016_clocktype_s141"),
        ("ivr_config", "0052_workday_schedule_days_s141"),
    ]

    operations = [
        migrations.AddField(
            model_name="workerclocksetting",
            name="workday_schedule",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="worker_settings",
                to="ivr_config.workdayschedule",
                verbose_name="Horario de jornada",
            ),
        ),
    ]
