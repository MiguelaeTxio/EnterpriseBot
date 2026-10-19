# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/hr_calendar/migrations/0011_clockevent_sent_by_manual_s130.py
# H24 (S130): MANUAL pasa a ser el fichaje manual por olvido; el botón
# «Enviar pendientes» envía como PAGE. Solo cambian las etiquetas.
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("hr_calendar", "0010_clockevent_municipality_s129"),
    ]

    operations = [
        migrations.AlterField(
            model_name="clockevent",
            name="sent_by",
            field=models.CharField(
                choices=[
                    ("ONLINE", "Al momento"),
                    ("BACKGROUND", "Al volver la cobertura (segundo plano)"),
                    ("PAGE", "Desde la página (al abrirla o con su botón)"),
                    ("MANUAL", "Fichaje manual (olvido)"),
                ],
                default="ONLINE",
                max_length=12,
                verbose_name="Cómo se envió",
            ),
        ),
    ]
