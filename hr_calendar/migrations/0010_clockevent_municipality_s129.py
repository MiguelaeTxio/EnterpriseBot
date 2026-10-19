# H24 (S129): municipio de las coordenadas del fichaje.
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("hr_calendar", "0009_clockevent_rounded_s129"),
    ]

    operations = [
        migrations.AddField(
            model_name="clockevent",
            name="municipality",
            field=models.CharField(
                blank=True, max_length=150, null=True,
                verbose_name="Municipio",
                help_text=(
                    "Municipio de las coordenadas (Google Geocoding, "
                    "hr_calendar/clock_geocode.py). Vacío = sin resultado; "
                    "nulo = todavía sin consultar."
                ),
            ),
        ),
    ]
