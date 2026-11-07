# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0207_grupos_autor_s147.py
"""
S147 (Miguel Ángel): los grupos de selección los usa cualquiera, pero
solo los cambia quien los creó. Los que no tienen autor (el padre
"Plataformas", creado por la migración 0206) pasan a alvarez_admin,
que es quien creó los demás.
"""
from django.db import migrations


def forwards(apps, schema_editor):
    group_model = apps.get_model("document_explorer", "PersonGroupTemplate")
    company_user_model = apps.get_model("ivr_config", "CompanyUser")
    author = company_user_model.objects.filter(
        user__username="alvarez_admin",
    ).first()
    if author is None:
        return
    group_model.objects.filter(created_by__isnull=True).update(
        created_by=author)


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0206_grupos_arbol_s147"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
