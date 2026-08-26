# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0057_seed_camiseta_alta_visibilidad_s73.py
"""
H30 (S73). Alta de CAMISETA_ALTA_VISIBILIDAD en EpiItemCatalog,
confirmado con contenido real: "PORTWEST DECLARACION CONFORMIDAD
CAMISETA T181.pdf" y "PORTWEST FICHA TECNICA CAMISETA T181.pdf"
(DOC. PERSONAL/ENTREGA EPIS/EPIS ALTA VISIBILIDAD) documentan una
prenda real (camiseta T181) sin fila propia en el catalogo -- la
familia "Alta visibilidad" ya cubria POLO_ALTA_VISIBILIDAD y
PANTALON_ALTA_VISIBILIDAD (T501) pero no la camiseta. Confirmado
explicitamente por Miguel Angel en S73.

Sin coste de reposicion ni norma UNE-EN confirmados todavia (mismo
criterio que la mayoria de items de la migracion 0053: solo se
rellena cuando hay dato real explicito en un documento).
"""
from django.db import migrations

NEW_ITEM = {
    "family": "Alta visibilidad",
    "code": "CAMISETA_ALTA_VISIBILIDAD",
    "label": "Camiseta alta visibilidad (T181)",
}


def seed_new_item(apps, schema_editor):
    EpiItemCatalog = apps.get_model("document_explorer", "EpiItemCatalog")
    EpiItemCatalog.objects.get_or_create(
        code=NEW_ITEM["code"],
        defaults={
            "family": NEW_ITEM["family"],
            "label": NEW_ITEM["label"],
            "requires_periodic_review": False,
            "replacement_cost": None,
            "une_en_standard": None,
            "is_active": True,
        },
    )


def unseed_new_item(apps, schema_editor):
    EpiItemCatalog = apps.get_model("document_explorer", "EpiItemCatalog")
    EpiItemCatalog.objects.filter(code=NEW_ITEM["code"]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0056_seed_ficha_tecnica_epi_s73"),
    ]

    operations = [
        migrations.RunPython(seed_new_item, unseed_new_item),
    ]
