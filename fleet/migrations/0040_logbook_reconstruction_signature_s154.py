# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/fleet/migrations/0040_logbook_reconstruction_signature_s154.py
"""
H23 (S154, invasora) -- las revisiones que faltan se escanean; solo las
de registro extraviado se reconstruyen, y quedan pendientes hasta la
firma digital con el certificado de la empresa (agente de firmas del
PC de Yolanda). Quién la reconstruye, quién la envía a firmar, el
documento de la cola, el certificado y la declaración firmada.
"""
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("fleet", "0039_logbook_signed_reviews_s154"),
        ("document_explorer", "0224_signedformjob_kind_person_s153"),
        ("ivr_config", "0056_workdayscheduleday_holiday_s144"),
    ]

    operations = [
        migrations.AlterField(
            model_name="machinelogbookentry",
            name="signed_by",
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+", to="ivr_config.companyuser",
                verbose_name="Enviada a la firma digital por",
            ),
        ),
        migrations.AlterField(
            model_name="machinelogbookentry",
            name="signed_at",
            field=models.DateTimeField(
                blank=True, null=True,
                verbose_name="Firmada digitalmente el",
            ),
        ),
        migrations.AddField(
            model_name="machinelogbookentry",
            name="created_by",
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+", to="ivr_config.companyuser",
                verbose_name="Reconstruida por",
            ),
        ),
        migrations.AddField(
            model_name="machinelogbookentry",
            name="signing_file",
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+", to="document_explorer.signedformfile",
                verbose_name="Documento en la cola de firma",
            ),
        ),
        migrations.AddField(
            model_name="machinelogbookentry",
            name="signed_certificate",
            field=models.CharField(
                blank=True, default="", max_length=255,
                verbose_name="Certificado de la firma",
            ),
        ),
        migrations.AddField(
            model_name="machinelogbookentry",
            name="signed_document",
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="logbook_reconstructions",
                to="document_explorer.documentindexentry",
                verbose_name="Declaración firmada",
            ),
        ),
    ]
