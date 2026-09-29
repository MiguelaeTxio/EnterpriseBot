# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0164_medidas_proteccion_obra_s124.py
# H30 (S124): en INFORMACION_MEDIDAS_PROTECCION los datos de la obra eran
# rayas para rellenar a mano ("Identificación de la obra: ____", "las
# instalaciones de la empresa ____ en ____"). Pasan a variables de obra,
# que se rellenan con la obra elegida al generar o al preparar la firma
# en Docuten. Solo cambia esos dos huecos exactos; los [corchetes] de la
# deficiencia concreta siguen siendo texto que se escribe en cada caso.

import re

from django.db import migrations

_REPLACEMENTS = [
    (re.compile(r"Identificación de la obra: _{3,}"),
     "Identificación de la obra: {{obra.nombre}}"),
    (re.compile(r"instalaciones de la empresa _{3,} en _{3,}"),
     "instalaciones de la empresa {{obra.cliente}} en {{obra.direccion}}"),
]


def use_worksite_variables(apps, schema_editor):
    catalog = apps.get_model("document_explorer", "DocumentTypeCatalog")
    for item in catalog.objects.filter(code="INFORMACION_MEDIDAS_PROTECCION"):
        html = item.content_html
        for pattern, replacement in _REPLACEMENTS:
            html = pattern.sub(replacement, html)
        if html != item.content_html:
            item.content_html = html
            item.save(update_fields=["content_html"])


class Migration(migrations.Migration):

    dependencies = [
        ('document_explorer', '0163_circular_templates_s124'),
    ]

    operations = [
        migrations.RunPython(use_worksite_variables, migrations.RunPython.noop),
    ]
