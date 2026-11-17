# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/hr_calendar/migrations/0045_clockcorrection_source_system_s149.py
# H24 (S149, sesión invasora): origen «Restaurado por error del sistema»
# en las correcciones (días visados que la IA corrigió por error).
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("hr_calendar", "0044_albaransheet_vehicle_on_site_s149"),
    ]

    operations = [
        migrations.AlterField(
            model_name="clockcorrection",
            name="source",
            field=models.CharField(
                choices=[("MANUAL", "Manual"), ("AI", "IA"),
                         ("PARTE", "Parte de trabajo"),
                         ("SYSTEM", "Restaurado por error del sistema")],
                default="MANUAL",
                help_text="IA: la hizo el cotejo de albaranes, lanzado por "
                          "«Corregido por».",
                max_length=10,
                verbose_name="Origen",
            ),
        ),
    ]
