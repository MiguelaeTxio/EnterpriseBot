# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0208_grupos_padre_integrantes_s147.py
"""
S147 (Miguel Ángel): "los integrantes de los subgrupos pertenecen al
grupo padre". La regla se aplica al guardar un grupo
(panel/person_groups.save_group); los grupos creados antes (Grúas,
Plataformas) no tenían como propias a las personas de sus subgrupos.
Se añaden ahora, a cada grupo, las de todos sus subgrupos. Solo añade,
nunca quita.
"""
from django.db import migrations


def forwards(apps, schema_editor):
    group_model = apps.get_model("document_explorer", "PersonGroupTemplate")
    groups = {g.pk: g for g in group_model.objects.all()}
    children = {}
    for group in groups.values():
        children.setdefault(group.parent_id, []).append(group.pk)

    def everyone(pk, seen):
        if pk in seen:
            return set()
        seen.add(pk)
        ids = set(groups[pk].members.values_list("pk", flat=True))
        for child in children.get(pk, []):
            ids |= everyone(child, seen)
        return ids

    for pk, group in groups.items():
        if children.get(pk):
            group.members.add(*everyone(pk, set()))


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0207_grupos_autor_s147"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
