# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/hr_calendar/migrations/0042_albaranbatch_heartbeat_s149.py
# H24 (S149, sesión invasora): señal de vida de la lectura de una carga
# de albaranes y número de reanudaciones (una lectura cortada por un
# reinicio de Celery se reanuda sola donde se quedó).

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("hr_calendar", "0041_albaranes_varios_s149"),
    ]

    operations = [
        migrations.AddField(
            model_name="albaranbatch",
            name="heartbeat_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="Última señal"),
        ),
        migrations.AddField(
            model_name="albaranbatch",
            name="resumes",
            field=models.PositiveSmallIntegerField(default=0, verbose_name="Reanudaciones"),
        ),
    ]
