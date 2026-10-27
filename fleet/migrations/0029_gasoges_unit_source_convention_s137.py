# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/fleet/migrations/0029_gasoges_unit_source_convention_s137.py
# H30 (S137): origen de la unidad "Regla del taller" (P, turismos y
# furgonetas por km; A y B por horas). Solo cambian las opciones.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("fleet", "0028_gasogesuser_ask_driver_s137"),
    ]

    operations = [
        migrations.AlterField(
            model_name="gasogesvehicle",
            name="unit_source",
            field=models.CharField(
                blank=True,
                choices=[
                    ("DEDUCED", "Deducida"),
                    ("DRIVER", "Confirmada por el chófer"),
                    ("MANUAL", "Puesta a mano"),
                    ("CONVENTION", "Regla del taller"),
                ],
                max_length=10,
                verbose_name="Origen de la unidad",
            ),
        ),
    ]
