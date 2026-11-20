# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/hr_calendar/migrations/0050_clockevent_worker_note_s149.py
# H24 (S149, sesión invasora): comentario del trabajador en la entrada y
# en la salida (Plataformas: "he fichado en mi casa...").
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("hr_calendar", "0049_meal_check_s149"),
    ]

    operations = [
        migrations.AddField(
            model_name="clockevent",
            name="worker_note",
            field=models.CharField(
                blank=True, default="", max_length=255,
                verbose_name="Comentario del trabajador",
            ),
        ),
    ]
