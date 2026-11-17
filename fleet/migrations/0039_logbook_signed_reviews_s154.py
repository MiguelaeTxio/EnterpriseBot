# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/fleet/migrations/0039_logbook_signed_reviews_s154.py
"""
H23 (S154, invasora) -- revisiones técnicas periódicas anotadas en la
plataforma y firmadas por el responsable: la fila deja de exigir
documento de origen y guarda quién la firmó, cuándo y si reconstruye
un registro original extraviado.
"""
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("fleet", "0038_machine_logbook_s154"),
        ("ivr_config", "0056_workdayscheduleday_holiday_s144"),
    ]

    operations = [
        migrations.AlterField(
            model_name="machinelogbookentry",
            name="source",
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="entries", to="fleet.machinelogbooksource",
                verbose_name="Documento de origen",
            ),
        ),
        migrations.AddField(
            model_name="machinelogbookentry",
            name="signed_by",
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+", to="ivr_config.companyuser",
                verbose_name="Firmada por",
            ),
        ),
        migrations.AddField(
            model_name="machinelogbookentry",
            name="signed_at",
            field=models.DateTimeField(
                blank=True, null=True, verbose_name="Firmada el",
            ),
        ),
        migrations.AddField(
            model_name="machinelogbookentry",
            name="is_reconstructed",
            field=models.BooleanField(
                default=False,
                verbose_name="Registro original extraviado (reconstruida)",
            ),
        ),
    ]
