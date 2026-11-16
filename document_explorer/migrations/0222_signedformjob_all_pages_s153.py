# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0222_signedformjob_all_pages_s153.py
# S153 (agente de firmas v4): firmar en todas las páginas o solo donde lo
# pide el documento.
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0221_certificate_alert_dismissal_s153"),
    ]

    operations = [
        migrations.AddField(
            model_name="signedformjob",
            name="all_pages",
            field=models.BooleanField(
                default=False, verbose_name="Firmar en todas las páginas"),
        ),
    ]
