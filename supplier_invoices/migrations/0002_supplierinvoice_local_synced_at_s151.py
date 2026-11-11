# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/supplier_invoices/migrations/0002_supplierinvoice_local_synced_at_s151.py
# H28 (S151): cuándo quedó cada factura en la carpeta local FACTURACIÓN
# de OneDrive (agente H28). Solo esquema.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("supplier_invoices", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="supplierinvoice",
            name="local_synced_at",
            field=models.DateTimeField(
                blank=True,
                help_text=(
                    "Cuándo quedó la factura en la carpeta FACTURACIÓN de "
                    "OneDrive (subida desde allí o bajada por el agente "
                    "H28). Vacío: el agente todavía tiene que bajarla."
                ),
                null=True,
                verbose_name="En la carpeta local desde",
            ),
        ),
    ]
