# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0209_grupos_sin_repetidos_s147.py
"""
S147 (Miguel Ángel): las cuentas de los grupos tienen que cuadrar (la
suma de los subgrupos es el total del padre). En Grúas, quien está en
"Administración" estaba también en "Operarios" (la migración 0206 pasó
a Operarios a las 28 personas del antiguo "Grúas", también a la de
administración): se le quita de Operarios.
"""
from django.db import migrations


def forwards(apps, schema_editor):
    group_model = apps.get_model("document_explorer", "PersonGroupTemplate")
    for parent in group_model.objects.filter(name="Grúas", parent=None):
        office = group_model.objects.filter(
            parent=parent, name="Administración").first()
        workers = group_model.objects.filter(
            parent=parent, name="Operarios").first()
        if office is None or workers is None:
            continue
        repeated = set(office.members.values_list("pk", flat=True)) & set(
            workers.members.values_list("pk", flat=True))
        if repeated:
            workers.members.remove(*repeated)


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0208_grupos_padre_integrantes_s147"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
