# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/fleet/migrations/0032_gasogessupply_hours_issue_s141.py
# H30 (S141): marca de los repostajes de vehículos que van por horas en
# los que no se anotaron horas (km en vez de horas, o vacío/0). La
# rellena fleet/gasoges_hours.py en la siguiente sincronización.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("fleet", "0031_refuelquestion_reason_s137"),
    ]

    operations = [
        migrations.AddField(
            model_name="gasogessupply",
            name="hours_issue",
            field=models.CharField(
                blank=True,
                choices=[
                    ("", "Sin problema"),
                    ("KM", "Km en vez de horas"),
                    ("EMPTY", "Sin anotar (vacío o 0)"),
                ],
                db_index=True,
                default="",
                max_length=6,
                verbose_name="Horas sin anotar",
            ),
        ),
    ]
