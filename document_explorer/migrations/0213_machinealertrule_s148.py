# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0213_machinealertrule_s148.py
# S148: `MachineAlertRule`, avisos de documentación de UN centro de
# gasto (mismos campos que RequirementAlertRule; sustituyen a los del
# requisito para ese tipo y esa máquina). Solo esquema, ninguna fila.

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0212_personidentity_notes_s148"),
        ("fleet", "0035_machineasset_notes_s148"),
        ("ivr_config", "0056_workdayscheduleday_holiday_s144"),
    ]

    operations = [
        migrations.CreateModel(
            name="MachineAlertRule",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("notify_missing", models.BooleanField(default=False, verbose_name="Avisar si falta")),
                ("notify_30_days", models.BooleanField(default=False, verbose_name="Avisar 30 días antes")),
                ("notify_15_days", models.BooleanField(default=False, verbose_name="Avisar 15 días antes")),
                ("notify_7_days", models.BooleanField(default=False, verbose_name="Avisar 7 días antes")),
                ("notify_day_before", models.BooleanField(default=False, verbose_name="Avisar el día anterior")),
                ("custom_1_value", models.PositiveSmallIntegerField(blank=True, null=True, verbose_name="Aviso personalizado 1 -- antelación")),
                ("custom_1_unit", models.CharField(blank=True, choices=[("DAYS", "días"), ("MONTHS", "meses")], max_length=6, verbose_name="Aviso personalizado 1 -- unidad")),
                ("custom_2_value", models.PositiveSmallIntegerField(blank=True, null=True, verbose_name="Aviso personalizado 2 -- antelación")),
                ("custom_2_unit", models.CharField(blank=True, choices=[("DAYS", "días"), ("MONTHS", "meses")], max_length=6, verbose_name="Aviso personalizado 2 -- unidad")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Última edición")),
                ("document_type", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="machine_alert_rules", to="document_explorer.documenttypecatalog", verbose_name="Tipo documental")),
                ("machine", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="alert_rules", to="fleet.machineasset", verbose_name="Centro de gasto")),
                ("updated_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to="ivr_config.companyuser", verbose_name="Última edición por")),
            ],
            options={
                "verbose_name": "Aviso de un centro de gasto",
                "verbose_name_plural": "Avisos de centros de gasto",
                "constraints": [models.UniqueConstraint(fields=("machine", "document_type"), name="unique_alert_rule_per_machine_type")],
            },
        ),
    ]
