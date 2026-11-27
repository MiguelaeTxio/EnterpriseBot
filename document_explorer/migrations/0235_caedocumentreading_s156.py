# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0235_caedocumentreading_s156.py
"""S156. Lectura con Gemini de los archivos CAE sin tipo."""
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0234_seed_insurance_subtypes_s156"),
    ]

    operations = [
        migrations.CreateModel(
            name="CaeDocumentReading",
            fields=[
                ("id", models.BigAutoField(
                    auto_created=True, primary_key=True, serialize=False,
                    verbose_name="ID")),
                ("md5_hash", models.CharField(blank=True, max_length=64)),
                ("code", models.CharField(
                    blank=True, max_length=80, verbose_name="Tipo leído",
                    help_text="Código del catálogo, o vacío si no es de "
                              "la CAE.")),
                ("error", models.TextField(blank=True)),
                ("read_at", models.DateTimeField(auto_now=True)),
                ("entry", models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="cae_reading",
                    to="document_explorer.documentindexentry",
                    verbose_name="Documento")),
            ],
            options={
                "verbose_name": "Lectura de documento CAE",
                "verbose_name_plural": "Lecturas de documentos CAE",
            },
        ),
    ]
