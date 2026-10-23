# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0191_seed_v16_catalog_item_s135.py
"""
H31 (S135, desvío desde H30). Alta del ítem V16 (luz de emergencia de
vehículo) en EpiItemCatalog, con el mismo mecanismo que el botiquín
(0055). Miguel Ángel, verbatim: "La entrega debe ser análoga a los
botiquines, persona y máquina" -- se usa con
`EpiDelivery.destination_machine`, igual que el botiquín.

Familia propia, un único ítem. Norma, coste y vida útil a nulo hasta
tener dato real confirmado (mismo criterio que el botiquín, S72). La
pantalla de alta de EPIs y la entrega con máquina desde el panel quedan
pendientes en el anexo V31.
"""
from django.db import migrations


def seed_v16(apps, schema_editor):
    EpiItemCatalog = apps.get_model("document_explorer", "EpiItemCatalog")
    EpiItemCatalog.objects.get_or_create(
        code="V16",
        defaults={
            "family": "Señalización de emergencia",
            "label": "Luz de emergencia V16",
            "requires_periodic_review": False,
            "replacement_cost": None,
            "une_en_standard": None,
            "standard_expiry_years": None,
            "is_active": True,
        },
    )


def unseed_v16(apps, schema_editor):
    EpiItemCatalog = apps.get_model("document_explorer", "EpiItemCatalog")
    EpiItemCatalog.objects.filter(code="V16").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0190_person_id_photo_manual_s134"),
    ]

    operations = [
        migrations.RunPython(seed_v16, unseed_v16),
    ]
