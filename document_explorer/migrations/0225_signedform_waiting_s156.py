# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0225_signedform_waiting_s156.py
# S156: lotes y documentos "Esperando a Gemini" (429 al localizar huecos).
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0224_signedformjob_kind_person_s153"),
    ]

    operations = [
        migrations.AlterField(
            model_name="signedformjob",
            name="status",
            field=models.CharField(
                choices=[("waiting", "Esperando a Gemini"),
                         ("pending", "Pendiente de firma digital"),
                         ("done", "Firmado"),
                         ("error", "Con errores"),
                         ("cancelled", "Cancelado")],
                default="pending", max_length=10, verbose_name="Estado",
            ),
        ),
        migrations.AlterField(
            model_name="signedformfile",
            name="status",
            field=models.CharField(
                choices=[("waiting", "Esperando a Gemini"),
                         ("pending", "Pendiente"),
                         ("signing", "Firmándose"),
                         ("done", "Firmado"),
                         ("error", "Error")],
                default="pending", max_length=10, verbose_name="Estado",
            ),
        ),
    ]
