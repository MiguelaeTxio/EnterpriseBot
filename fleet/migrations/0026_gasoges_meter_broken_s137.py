# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/fleet/migrations/0026_gasoges_meter_broken_s137.py
# H30 (S137): contador averiado en los vehículos de GasoGes, estado
# "Contador averiado" en suministros y en preguntas al chófer. Campos
# nuevos con valor por defecto o nulos; sin datos que mover.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("fleet", "0025_meterreading_work_order_line_s137"),
    ]

    operations = [
        migrations.AddField(
            model_name="gasogesvehicle",
            name="meter_broken",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "Cuentakilómetros u horómetro averiado: no se pregunta "
                    "al chófer y sus repostajes no dan lectura hasta que "
                    "se repare."
                ),
                verbose_name="Contador averiado",
            ),
        ),
        migrations.AddField(
            model_name="gasogesvehicle",
            name="meter_broken_since",
            field=models.DateTimeField(
                blank=True, null=True, verbose_name="Averiado desde"
            ),
        ),
        migrations.AlterField(
            model_name="gasogessupply",
            name="status",
            field=models.CharField(
                choices=[
                    ("PENDING", "Pendiente"),
                    ("READING", "Lectura creada"),
                    ("ANOMALY", "Lectura dudosa"),
                    ("NO_MACHINE", "Sin centro de gasto"),
                    ("NO_UNIT", "Sin saber si son km u horas"),
                    ("BROKEN", "Contador averiado"),
                ],
                db_index=True,
                default="PENDING",
                max_length=12,
                verbose_name="Estado",
            ),
        ),
        migrations.AlterField(
            model_name="refuelquestion",
            name="status",
            field=models.CharField(
                choices=[
                    ("SENT", "Enviada, sin respuesta"),
                    ("AWAITING_VALUE", "Esperando el valor correcto"),
                    ("CONFIRMED", "El chófer dice que es correcto"),
                    ("CORRECTED", "Corregido por el chófer"),
                    ("UNIT_SET", "Unidad confirmada por el chófer"),
                    (
                        "METER_BROKEN",
                        "El chófer dice que el contador está averiado",
                    ),
                    ("EXPIRED", "Sin respuesta a tiempo"),
                ],
                db_index=True,
                default="SENT",
                max_length=16,
                verbose_name="Estado",
            ),
        ),
    ]
