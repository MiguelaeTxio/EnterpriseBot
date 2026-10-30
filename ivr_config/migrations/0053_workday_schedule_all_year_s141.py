# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/ivr_config/migrations/0053_workday_schedule_all_year_s141.py
# H24 (S141): temporada "Todo el año". Miguel Ángel: solo Taller tiene
# horario de invierno y de verano; los demás horarios (creados como
# invierno) valen todo el año.

from django.db import migrations, models

SEASON_CHOICES = [
    ("WINTER", "Invierno"),
    ("SUMMER", "Verano"),
    ("ALL_YEAR", "Todo el año"),
]


def mark_all_year(apps, schema_editor):
    schedule = apps.get_model("ivr_config", "WorkdaySchedule")
    schedule.objects.exclude(label__iexact="Taller").filter(
        season="WINTER",
    ).update(season="ALL_YEAR")


class Migration(migrations.Migration):

    dependencies = [
        ("ivr_config", "0052_workday_schedule_days_s141"),
    ]

    operations = [
        migrations.AlterField(
            model_name="workdayschedule",
            name="season",
            field=models.CharField(
                choices=SEASON_CHOICES,
                default="WINTER",
                help_text="Temporada a la que aplica este horario. "
                          "INVIERNO: turno partido con tramo de mañana y "
                          "tarde. VERANO: jornada intensiva (solo mañana si "
                          "is_intensive=True). TODO EL AÑO: el mismo "
                          "horario en cualquier temporada.",
                max_length=10,
                verbose_name="Temporada",
            ),
        ),
        migrations.RunPython(mark_all_year, migrations.RunPython.noop),
    ]
