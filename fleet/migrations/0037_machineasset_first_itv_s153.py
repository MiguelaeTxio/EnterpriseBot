# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/fleet/migrations/0037_machineasset_first_itv_s153.py
"""
S153 -- primera matriculación y tipo de vehículo para la ITV.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("fleet", "0036_machineasset_document_requirements_s153"),
    ]

    operations = [
        migrations.AddField(
            model_name="machineasset",
            name="first_registration_date",
            field=models.DateField(
                blank=True, null=True,
                help_text="Campo B del permiso de circulación.",
                verbose_name="Fecha de primera matriculación",
            ),
        ),
        migrations.AddField(
            model_name="machineasset",
            name="itv_category",
            field=models.CharField(
                blank=True, default="", max_length=10,
                choices=[
                    ("", "Sin indicar"),
                    ("TURISMO", "Turismo o furgoneta particular (1.ª ITV a "
                                "los 4 años)"),
                    ("LIGERO", "Ligero hasta 3.500 kg, mixto o furgoneta de "
                               "mercancías (1.ª ITV a los 2 años)"),
                    ("PESADO", "Pesado de más de 3.500 kg (1.ª ITV al año)"),
                    ("ESPECIAL", "Vehículo especial de obras (1.ª ITV a los "
                                 "4 años)"),
                    ("SIN_ITV", "No pasa ITV (sin matrícula)"),
                ],
                verbose_name="Tipo de vehículo para la ITV",
            ),
        ),
    ]
