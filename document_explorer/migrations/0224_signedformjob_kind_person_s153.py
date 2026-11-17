# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0224_signedformjob_kind_person_s153.py
"""
S153: los lotes de documentos firmados guardan el tipo (digital o solo
con la imagen) y el trabajador, para listarlos todos en Firmas.
"""
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0223_signedformjob_cancelled_s153"),
    ]

    operations = [
        migrations.AddField(
            model_name="signedformjob",
            name="kind",
            field=models.CharField(
                choices=[("digital", "Digital"),
                         ("image", "Normal (imagen)")],
                default="digital", max_length=10, verbose_name="Tipo"),
        ),
        migrations.AddField(
            model_name="signedformjob",
            name="person",
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to="document_explorer.personidentity",
                verbose_name="Trabajador"),
        ),
        migrations.AlterField(
            model_name="signedformjob",
            name="certificate_alias",
            field=models.CharField(blank=True, default="", max_length=255,
                                   verbose_name="Certificado (alias)"),
        ),
        migrations.AlterModelOptions(
            name="signedformjob",
            options={"ordering": ["-created_at"],
                     "verbose_name": "Lote de documentos firmados",
                     "verbose_name_plural":
                         "Lotes de documentos firmados"},
        ),
    ]
