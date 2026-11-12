# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0218_signedformfile_signature_config_s153.py
# S153: configuración de AutoFirma para la firma digital visible.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0217_signing_agent_s153"),
    ]

    operations = [
        migrations.AddField(
            model_name="signedformfile",
            name="signature_config",
            field=models.TextField(
                blank=True,
                default="",
                verbose_name="Configuración de la firma visible (AutoFirma)",
            ),
        ),
    ]
