# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/fleet/migrations/0047_meterreading_source_real_s154.py
"""
S154 (invasora, 27/11) -- origen nuevo de las lecturas: «Contadores
actualizados (lectura real)», desde el editor de fichas QR.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("fleet", "0046_qreditorsettings_password_encrypted_s163"),
    ]

    operations = [
        migrations.AlterField(
            model_name="machinemeterreading",
            name="source",
            field=models.CharField(
                choices=[
                    ("MANUAL", "A mano"),
                    ("GASOGES", "Surtidor (GasoGes)"),
                    ("PARTE", "Parte de trabajo"),
                    ("REAL", "Contadores actualizados (lectura real)"),
                ],
                default="MANUAL",
                max_length=10,
                verbose_name="Origen",
            ),
        ),
    ]
