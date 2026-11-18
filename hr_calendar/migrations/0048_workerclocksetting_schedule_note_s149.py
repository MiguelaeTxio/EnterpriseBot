# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/hr_calendar/migrations/0048_workerclocksetting_schedule_note_s149.py
# H24 (S149, sesión invasora): nota del cambio de horario de un
# trabajador (motivo, quién y cuándo).
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("hr_calendar", "0047_workerclocksetting_out_round_up_s149"),
    ]

    operations = [
        migrations.AddField(
            model_name="workerclocksetting",
            name="schedule_note",
            field=models.CharField(
                blank=True, default="", max_length=255,
                verbose_name="Nota del cambio de horario",
            ),
        ),
    ]
