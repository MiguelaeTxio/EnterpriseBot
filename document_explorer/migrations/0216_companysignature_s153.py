# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0216_companysignature_s153.py
# S153: firmas de las empresas del grupo (CompanySignature), cifradas,
# para generar los documentos firmados (pestaña Firmas).

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer",
         "0215_personidentity_document_requirements_s153"),
        ("ivr_config", "0060_companyuser_signature_access_s153"),
    ]

    operations = [
        migrations.CreateModel(
            name="CompanySignature",
            fields=[
                ("id", models.BigAutoField(
                    auto_created=True, primary_key=True, serialize=False,
                    verbose_name="ID")),
                ("label", models.CharField(
                    help_text='Quién firma (p. ej. "Adolfo").',
                    max_length=120, verbose_name="Nombre de la firma")),
                ("image_encrypted", models.BinaryField(
                    verbose_name="Imagen de la firma (cifrada, PNG)")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("company", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="signatures",
                    to="document_explorer.companyfiscalprofile",
                    verbose_name="Empresa")),
                ("created_by", models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="+", to="ivr_config.companyuser",
                    verbose_name="Guardada por")),
            ],
            options={
                "verbose_name": "Firma de empresa",
                "verbose_name_plural": "Firmas de empresa",
                "ordering": ["company__legal_name", "label"],
            },
        ),
    ]
