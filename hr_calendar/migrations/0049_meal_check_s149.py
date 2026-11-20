# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/hr_calendar/migrations/0049_meal_check_s149.py
# H24 (S149, sesión invasora): botón único con la casilla "No he parado
# para comer" (sección y tipo de fichaje propio del trabajador).
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("hr_calendar", "0048_workerclocksetting_schedule_note_s149"),
    ]

    operations = [
        migrations.AddField(
            model_name="sectionclocksetting",
            name="meal_check",
            field=models.BooleanField(
                default=False,
                verbose_name="Botón único con «No he parado para comer»",
            ),
        ),
        migrations.AlterField(
            model_name="workerclocksetting",
            name="clock_mode",
            field=models.CharField(
                blank=True,
                choices=[
                    ("", "Como su sección"),
                    ("normal", "Fichaje normal"),
                    ("meal", "Normal con «No he parado para comer»"),
                    ("types", "Por tipos"),
                ],
                default="",
                help_text="Vacío: como su sección.",
                max_length=10,
                verbose_name="Tipo de fichaje",
            ),
        ),
    ]
