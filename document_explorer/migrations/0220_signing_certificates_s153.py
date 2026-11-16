# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0220_signing_certificates_s153.py
# S153 (agente de firmas v3): certificados con huella y fechas, firma
# asociada al CIF de la empresa y huella del certificado en cada lote.
# Las firmas que ya tenían un alias con "(R: CIF)" pasan a ese CIF.
import re

from django.db import migrations, models

CIF_RE = re.compile(r"\(R:\s*([A-Z0-9]{8,10})\)", re.IGNORECASE)


def alias_to_cif(apps, schema_editor):
    CompanySignature = apps.get_model("document_explorer",
                                      "CompanySignature")
    for signature in CompanySignature.objects.exclude(certificate_alias=""):
        match = CIF_RE.search(signature.certificate_alias)
        if match:
            signature.certificate_cif = match.group(1).upper()
            signature.save(update_fields=["certificate_cif"])


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0219_seed_albaran_trabajo_s153"),
    ]

    operations = [
        migrations.AddField(
            model_name="signingagent",
            name="certificates",
            field=models.JSONField(
                blank=True, default=list,
                verbose_name="Certificados de empresa (huella y fechas)"),
        ),
        migrations.AddField(
            model_name="companysignature",
            name="certificate_cif",
            field=models.CharField(
                blank=True, default="", max_length=20,
                verbose_name="Certificado digital (CIF de la empresa)"),
        ),
        migrations.AddField(
            model_name="signedformjob",
            name="certificate_thumbprint",
            field=models.CharField(
                blank=True, default="", max_length=64,
                verbose_name="Certificado (huella SHA-1)"),
        ),
        migrations.RunPython(alias_to_cif, migrations.RunPython.noop),
    ]
