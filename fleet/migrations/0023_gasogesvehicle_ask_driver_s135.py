# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/fleet/migrations/0023_gasogesvehicle_ask_driver_s135.py
# H30 (S135): "Preguntar al chófer" por vehículo de GasoGes (sí por
# defecto; no para los que lleva siempre la misma persona).

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('fleet', '0022_refuelquestion_s135'),
    ]

    operations = [
        migrations.AddField(
            model_name='gasogesvehicle',
            name='ask_driver',
            field=models.BooleanField(
                default=True,
                help_text=(
                    'Si no, sus repostajes dan lecturas igual, pero el '
                    'robot no pregunta nunca por ellos.'
                ),
                verbose_name='Preguntar al chófer',
            ),
        ),
    ]
