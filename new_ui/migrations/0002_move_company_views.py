# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/new_ui/migrations/0002_move_company_views.py
"""
Move the grants of the views that went from Personal to Empresa.

---

S163 (23/11): horarios, tipos de fichaje, catálogo de EPIs y nóminas pasan de
Personal a Empresa (clave "doc"); sus permisos ya dados pasan a la
clave nueva (new_ui/catalog.MOVED_VIEWS).
"""
from django.db import migrations

MOVED = {
    "per.lista_horarios": "doc.lista_horarios",
    "per.tipos_fichaje": "doc.tipos_fichaje",
    "per.catalogo_epis": "doc.catalogo_epis",
    "per.nominas": "doc.nominas",
}


def forwards(apps, schema_editor):
    grant = apps.get_model("new_ui", "UiViewGrant")
    for old, new in MOVED.items():
        grant.objects.filter(view_key=old).update(view_key=new)


def backwards(apps, schema_editor):
    grant = apps.get_model("new_ui", "UiViewGrant")
    for old, new in MOVED.items():
        grant.objects.filter(view_key=new).update(view_key=old)


class Migration(migrations.Migration):

    dependencies = [
        ("new_ui", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
