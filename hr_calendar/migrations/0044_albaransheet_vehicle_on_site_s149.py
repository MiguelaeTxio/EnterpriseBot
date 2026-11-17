# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/hr_calendar/migrations/0044_albaransheet_vehicle_on_site_s149.py
# H24 (S149, sesión invasora): casillas «Vehículo en obra» y
# «Continuación día ant.» del albarán (sin desplazamiento de vuelta ni,
# al día siguiente, de ida).

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("hr_calendar", "0043_parte_corrections_s153"),
    ]

    operations = [
        migrations.AddField(
            model_name="albaransheet",
            name="vehicle_on_site",
            field=models.BooleanField(default=False, verbose_name="Vehículo en obra"),
        ),
        migrations.AddField(
            model_name="albaransheet",
            name="continues_previous",
            field=models.BooleanField(default=False, verbose_name="Continuación del día anterior"),
        ),
    ]
