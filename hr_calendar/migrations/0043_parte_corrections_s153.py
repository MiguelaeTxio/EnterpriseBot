# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/hr_calendar/migrations/0043_parte_corrections_s153.py
# S153: fichajes corregidos con el parte de trabajo (origen PARTE en las
# correcciones y en los días comparados).
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("hr_calendar", "0042_albaranbatch_heartbeat_s149"),
    ]

    operations = [
        migrations.AlterField(
            model_name="clockcorrection",
            name="source",
            field=models.CharField(
                choices=[("MANUAL", "Manual"), ("AI", "IA"),
                         ("PARTE", "Parte de trabajo")],
                default="MANUAL",
                help_text="IA: la hizo el cotejo de albaranes, lanzado por "
                          "«Corregido por».",
                max_length=10,
                verbose_name="Origen",
            ),
        ),
        migrations.AddField(
            model_name="clockdayaicheck",
            name="origin",
            field=models.CharField(
                choices=[("AI", "IA (albaranes)"),
                         ("PARTE", "Parte de trabajo")],
                default="AI", max_length=10, verbose_name="Origen",
            ),
        ),
    ]
