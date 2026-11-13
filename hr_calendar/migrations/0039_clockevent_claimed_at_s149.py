# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/hr_calendar/migrations/0039_clockevent_claimed_at_s149.py
# H24 (S149, sesión invasora): hora real de salida que indica el
# trabajador al fichar tarde la salida, con su mensaje.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("hr_calendar", "0038_albaranes_ia_s149"),
    ]

    operations = [
        migrations.AddField(
            model_name="clockevent",
            name="claimed_at",
            field=models.DateTimeField(
                blank=True,
                help_text="Hora real de salida que indica el trabajador al fichar tarde la salida.",
                null=True,
                verbose_name="Hora real indicada",
            ),
        ),
        migrations.AddField(
            model_name="clockevent",
            name="claim_note",
            field=models.CharField(
                blank=True,
                default="",
                max_length=255,
                verbose_name="Mensaje del trabajador",
            ),
        ),
    ]
