# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0067_personidentity_birth_date_s82.py
"""
H30 (S82). Fecha de nacimiento en `PersonIdentity` -- Miguel Angel,
verbatim, al dar de alta a un trabajador nuevo (Estevao Veloso
Sampaio, DNI Z4448871D): "habra que anadir fecha de nacimiento en
los datos, y extraerla de los DNIs para el resto". Nullable: los
activos ya existentes no la tienen todavia, se rellena de forma
incremental -- sin backfill retroactivo en esta misma migracion.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0066_documentindexentry_ocr_text_s78"),
    ]

    operations = [
        migrations.AddField(
            model_name="personidentity",
            name="birth_date",
            field=models.DateField(
                null=True, blank=True, verbose_name="Fecha de nacimiento",
            ),
        ),
    ]
