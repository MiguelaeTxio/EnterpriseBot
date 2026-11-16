# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0221_certificate_alert_dismissal_s153.py
# S153: «No mostrar más» en los avisos de certificados digitales.
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("ivr_config", "0060_companyuser_signature_access_s153"),
        ("document_explorer", "0220_signing_certificates_s153"),
    ]

    operations = [
        migrations.CreateModel(
            name="CertificateAlertDismissal",
            fields=[
                ("id", models.BigAutoField(auto_created=True,
                                           primary_key=True,
                                           serialize=False,
                                           verbose_name="ID")),
                ("cif", models.CharField(max_length=20, verbose_name="CIF")),
                ("alert_key", models.CharField(
                    max_length=40, verbose_name="Situación avisada")),
                ("dismissed_at", models.DateTimeField(
                    auto_now_add=True, verbose_name="Ocultado el")),
                ("dismissed_by", models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="+", to="ivr_config.companyuser",
                    verbose_name="Ocultado por")),
            ],
            options={
                "verbose_name": "Aviso de certificado ocultado",
                "verbose_name_plural": "Avisos de certificado ocultados",
                "constraints": [models.UniqueConstraint(
                    fields=("cif", "alert_key"),
                    name="uniq_cert_alert_dismissal")],
            },
        ),
    ]
