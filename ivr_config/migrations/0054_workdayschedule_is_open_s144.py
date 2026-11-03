# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/ivr_config/migrations/0054_workdayschedule_is_open_s144.py
# H24 (S144): "Horario abierto" (sin comparación con el fichaje ni
# recordatorios). Campo nuevo con default: no toca ningún horario.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("ivr_config", "0053_workday_schedule_all_year_s141"),
    ]

    operations = [
        migrations.AddField(
            model_name="workdayschedule",
            name="is_open",
            field=models.BooleanField(
                default=False,
                help_text="Cada trabajador entra y sale a horas distintas: "
                          "el fichaje no se compara con este horario y no "
                          "hay recordatorios.",
                verbose_name="Horario abierto",
            ),
        ),
    ]
