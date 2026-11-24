# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0233_epidelivery_retired_s163.py
# H31 (S163, sesión invasora): extintores y botiquines retirados o
# sustituidos -- fecha y motivo; no se borran (las filas que hay quedan
# en uso, sin fecha de retirada).
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0232_company_requirements_dossier_scope_s156"),
    ]

    operations = [
        migrations.AddField(
            model_name="epidelivery",
            name="retired_at",
            field=models.DateField(blank=True, null=True, verbose_name="Retirado el"),
        ),
        migrations.AddField(
            model_name="epidelivery",
            name="retired_note",
            field=models.CharField(blank=True, default="", max_length=200, verbose_name="Motivo de la retirada"),
        ),
    ]
