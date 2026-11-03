# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/ivr_config/migrations/0055_workdayschedule_works_holidays_s144.py
# H24 (S144): "Se trabaja en festivos" en el horario. Campo nuevo con
# default: no toca ningún horario.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("ivr_config", "0054_workdayschedule_is_open_s144"),
    ]

    operations = [
        migrations.AddField(
            model_name="workdayschedule",
            name="works_holidays",
            field=models.BooleanField(
                default=False,
                help_text="Los festivos del calendario laboral de la base "
                          "son días de trabajo: se comparan con el horario "
                          "y llevan recordatorios.",
                verbose_name="Se trabaja en festivos",
            ),
        ),
    ]
