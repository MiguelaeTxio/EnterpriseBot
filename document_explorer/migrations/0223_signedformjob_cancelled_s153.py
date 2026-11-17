# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0223_signedformjob_cancelled_s153.py
# S153: los lotes de firma digital se pueden cancelar.
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0222_signedformjob_all_pages_s153"),
    ]

    operations = [
        migrations.AlterField(
            model_name="signedformjob",
            name="status",
            field=models.CharField(
                choices=[("pending", "Pendiente de firma digital"),
                         ("done", "Firmado"),
                         ("error", "Con errores"),
                         ("cancelled", "Cancelado")],
                default="pending", max_length=10, verbose_name="Estado",
            ),
        ),
    ]
