# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0055_seed_botiquin_catalog_item_s72.py
"""
H30 (S72). Alta del ítem BOTIQUIN en EpiItemCatalog -- mismo
mecanismo que cualquier otro EPI del catálogo (Miguel Ángel,
verbatim: "Damos de alta un EPI para los botiquines igual que
tenemos guantes"). Familia propia ("Botiquín"), un único ítem -- no
hay evidencia real de variantes distintas en los 14 documentos reales
de la carpeta BOTIQUINES (a diferencia de guantes, que sí tiene 4
variantes reales documentadas).

Este ítem se usa junto con el campo destination_machine ya añadido en
0054 -- las entregas de botiquín llevan asignación a Centro de Gasto
además de a la persona.
"""
from django.db import migrations


def seed_botiquin(apps, schema_editor):
    EpiItemCatalog = apps.get_model("document_explorer", "EpiItemCatalog")
    EpiItemCatalog.objects.get_or_create(
        code="BOTIQUIN",
        defaults={
            "family": "Botiquín",
            "label": "Botiquín",
            "requires_periodic_review": False,
            "replacement_cost": None,
            "une_en_standard": None,
            "is_active": True,
        },
    )


def unseed_botiquin(apps, schema_editor):
    EpiItemCatalog = apps.get_model("document_explorer", "EpiItemCatalog")
    EpiItemCatalog.objects.filter(code="BOTIQUIN").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0054_epidelivery_destination_machine_s72"),
    ]

    operations = [
        migrations.RunPython(seed_botiquin, unseed_botiquin),
    ]
