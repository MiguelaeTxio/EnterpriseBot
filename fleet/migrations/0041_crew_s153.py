# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/fleet/migrations/0041_crew_s153.py
"""
S153: equipos (un vehículo y una persona, desde una fecha).
"""
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("fleet", "0040_logbook_reconstruction_signature_s154"),
        ("document_explorer", "0225_signedform_waiting_s156"),
        ("ivr_config", "0061_companyuser_insurance_access_s152"),
    ]

    operations = [
        migrations.CreateModel(
            name="Crew",
            fields=[
                ("id", models.BigAutoField(auto_created=True,
                                           primary_key=True,
                                           serialize=False,
                                           verbose_name="ID")),
                ("date_start", models.DateField(verbose_name="Desde")),
                ("date_end", models.DateField(
                    blank=True, null=True,
                    help_text="Vacío mientras siga siendo el equipo "
                              "actual.",
                    verbose_name="Hasta")),
                ("notes", models.CharField(blank=True, max_length=255,
                                           verbose_name="Nota")),
                ("created_at", models.DateTimeField(auto_now_add=True,
                                                    verbose_name="Alta")),
                ("company", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="crews", to="ivr_config.company",
                    verbose_name="Empresa")),
                ("created_by", models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="+", to="ivr_config.companyuser",
                    verbose_name="Dado de alta por")),
                ("machine", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="crews", to="fleet.machineasset",
                    verbose_name="Centro de gasto")),
                ("person", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="crews",
                    to="document_explorer.personidentity",
                    verbose_name="Persona")),
            ],
            options={
                "verbose_name": "Equipo",
                "verbose_name_plural": "Equipos",
                "ordering": ["machine__code", "-date_start", "pk"],
                "indexes": [models.Index(
                    fields=["company", "date_end"],
                    name="fleet_crew_company_end_idx")],
            },
        ),
    ]
