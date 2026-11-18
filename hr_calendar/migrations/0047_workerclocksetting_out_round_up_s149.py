# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/hr_calendar/migrations/0047_workerclocksetting_out_round_up_s149.py
# H24 (S149, sesión invasora): por trabajador, la salida sube a la media
# hora siguiente desde unos minutos pasados (Rocío Macías, 15).
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("hr_calendar", "0046_clock_day_hold_s149"),
    ]

    operations = [
        migrations.AddField(
            model_name="workerclocksetting",
            name="out_round_up_minutes",
            field=models.PositiveSmallIntegerField(
                blank=True, null=True,
                help_text="Vacío: la regla general (la salida va a la media "
                          "hora anterior salvo a 5 minutos de la "
                          "siguiente).",
                verbose_name="Salida: sube a la media hora desde (min)",
            ),
        ),
    ]
