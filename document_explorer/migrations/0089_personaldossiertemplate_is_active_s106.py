# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0089_personaldossiertemplate_is_active_s106.py
"""
S106. Añade PersonalDossierTemplate.is_active -- marca cuál es la
plantilla que el supervisor tiene seleccionada para previsualizar y
usar dentro del gestor de plantillas de dosier. Ver docstring
completo del campo en models.py.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0088_documenttypecatalog_skip_light_ocr_engines_s106"),
    ]

    operations = [
        migrations.AddField(
            model_name="personaldossiertemplate",
            name="is_active",
            field=models.BooleanField(
                default=False,
                verbose_name="Plantilla activa",
            ),
        ),
    ]
