# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/supplier_invoices/migrations/0003_remove_local_synced_at_s151.py
# H28 (S151): fuera la carpeta local FACTURACIÓN del agente H28 (Miguel
# Ángel: las facturas las sube al cubo el agente de facturas de Ani).

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("supplier_invoices", "0002_supplierinvoice_local_synced_at_s151"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="supplierinvoice",
            name="local_synced_at",
        ),
    ]
