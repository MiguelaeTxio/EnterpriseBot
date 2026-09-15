# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0090_remove_personaldossiertemplate_output_format_s106.py
"""
S106. Elimina PersonalDossierTemplate.output_format -- el formato de
salida (PDF/ZIP) ya no vive en la plantilla, se pregunta siempre al
aplicarla. Ver docstring completo de PersonalDossierTemplate en
models.py. Solo 2 filas reales en producción a fecha de esta
migración ("CAE" y "CAE (ZIP)"), ambas con el mismo conjunto de
tipos documentales -- consolidar en una sola queda a criterio de
Miguel Ángel desde el propio gestor de plantillas, esta migración
solo retira el campo.
"""
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0089_personaldossiertemplate_is_active_s106"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="personaldossiertemplate",
            name="output_format",
        ),
    ]
