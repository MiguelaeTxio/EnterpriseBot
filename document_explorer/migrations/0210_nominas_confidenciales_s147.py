# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0210_nominas_confidenciales_s147.py
"""
S147 (Miguel Ángel): las nóminas solo las ven el trabajador y quien se
las envía. Campos de documento confidencial (cifrado y remitente), el
registro de accesos y el tipo NOMINA marcado como confidencial. Las
nóminas que ya hay no se tocan ("habrá que esperar a ver lo que se
decide hacer con ellas"): solo las que se suban a partir de ahora.
"""
import django.db.models.deletion
from django.db import migrations, models


def forwards(apps, schema_editor):
    catalog = apps.get_model("document_explorer", "DocumentTypeCatalog")
    catalog.objects.filter(code="NOMINA").update(is_confidential=True)


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0209_grupos_sin_repetidos_s147"),
        ("ivr_config", "0056_workdayscheduleday_holiday_s144"),
    ]

    operations = [
        migrations.AddField(
            model_name="documenttypecatalog",
            name="is_confidential",
            field=models.BooleanField(
                default=False,
                verbose_name="Confidencial (solo trabajador y quien lo envía)",
            ),
        ),
        migrations.AddField(
            model_name="documentindexentry",
            name="is_confidential",
            field=models.BooleanField(
                default=False, verbose_name="Confidencial (cifrado)"),
        ),
        migrations.AddField(
            model_name="documentindexentry",
            name="confidential_sender",
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="confidential_sent_entries",
                to="ivr_config.companyuser",
                verbose_name="Enviado por (confidencial)",
            ),
        ),
        migrations.CreateModel(
            name="ConfidentialAccessLog",
            fields=[
                ("id", models.BigAutoField(
                    auto_created=True, primary_key=True, serialize=False,
                    verbose_name="ID")),
                ("allowed", models.BooleanField(
                    default=False, verbose_name="Permitido")),
                ("opened_at", models.DateTimeField(
                    auto_now_add=True, verbose_name="Fecha")),
                ("company_user", models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="+", to="ivr_config.companyuser",
                    verbose_name="Usuario")),
                ("entry", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="confidential_accesses",
                    to="document_explorer.documentindexentry",
                    verbose_name="Documento")),
            ],
            options={
                "verbose_name": "Acceso a documento confidencial",
                "verbose_name_plural": "Accesos a documentos confidenciales",
                "ordering": ["-opened_at"],
            },
        ),
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
