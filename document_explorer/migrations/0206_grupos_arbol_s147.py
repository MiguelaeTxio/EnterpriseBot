# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0206_grupos_arbol_s147.py
"""
H24 (S147 invasora). Selection groups as a tree.

---

Grupos de selección en árbol (Miguel Ángel, S147): campo "Dentro de"
(parent) y reorganización de los grupos que ya había, como él la
decidió:
- "Grúas" pasa a ser carpeta: sus 28 personas van al subgrupo nuevo
  "Operarios" y "Grúas-administración" pasa a "Administración" dentro
  de Grúas.
- "Plataformas" (nuevo, carpeta) con "Administración", "Comercial",
  "Taller" y "Transportistas" (los cuatro "Plataformas ..." que había).
Un grupo con subgrupos no tiene miembros sueltos. Se buscan por
nombre; el que no esté se salta.
"""
import django.db.models.deletion
from django.db import migrations, models

PLATAFORMAS = (
    ("Plataformas Administración", "Administración"),
    ("Plataformas Comercial", "Comercial"),
    ("Plataformas Taller", "Taller"),
    ("Plataformas Transportistas", "Transportistas"),
)


def forwards(apps, schema_editor):
    """Reorganiza los grupos existentes en árbol."""
    group = apps.get_model("document_explorer", "PersonGroupTemplate")
    gruas = group.objects.filter(name="Grúas", parent__isnull=True).first()
    if gruas is not None:
        members = list(gruas.members.all())
        if members:
            operarios = group.objects.create(
                name="Operarios", parent=gruas,
                created_by_id=gruas.created_by_id,
            )
            operarios.members.set(members)
            gruas.members.clear()
        admin = group.objects.filter(name="Grúas-administración").first()
        if admin is not None:
            admin.name = "Administración"
            admin.parent = gruas
            admin.save(update_fields=["name", "parent"])
    children = [group.objects.filter(name=old).first()
                for old, _new in PLATAFORMAS]
    if any(children):
        plataformas = group.objects.filter(
            name="Plataformas", parent__isnull=True).first()
        if plataformas is None:
            plataformas = group.objects.create(name="Plataformas")
        for child, (_old, new) in zip(children, PLATAFORMAS):
            if child is not None:
                child.name = new
                child.parent = plataformas
                child.save(update_fields=["name", "parent"])


def backwards(apps, schema_editor):
    """Deshace los nombres y devuelve las personas a Grúas."""
    group = apps.get_model("document_explorer", "PersonGroupTemplate")
    gruas = group.objects.filter(name="Grúas", parent__isnull=True).first()
    if gruas is not None:
        operarios = group.objects.filter(
            name="Operarios", parent=gruas).first()
        if operarios is not None:
            gruas.members.set(operarios.members.all())
            operarios.delete()
        group.objects.filter(name="Administración", parent=gruas).update(
            name="Grúas-administración", parent=None)
    plataformas = group.objects.filter(
        name="Plataformas", parent__isnull=True).first()
    if plataformas is not None:
        for old, new in PLATAFORMAS:
            group.objects.filter(name=new, parent=plataformas).update(
                name=old, parent=None)
        plataformas.delete()


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0205_grupos_seleccion_s147"),
    ]

    operations = [
        migrations.AddField(
            model_name="persongrouptemplate",
            name="parent",
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="children",
                to="document_explorer.persongrouptemplate",
                verbose_name="Dentro de",
            ),
        ),
        migrations.RunPython(forwards, backwards),
    ]
