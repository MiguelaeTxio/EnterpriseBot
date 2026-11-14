# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0219_seed_albaran_trabajo_s153.py
"""
S153. Tipo documental de los albaranes de trabajo del personal (Miguel
Ángel: "estos albaranes no son como los de taller, aquellos son de
terceros y estos son albaranes de trabajo. Van en carpetas
diferentes"). Los carga el supervisor desde la ficha de fichajes del
trabajador (S149) y se guardan en su carpeta, subcarpeta ALBARANES DE
TRABAJO; con tipo propio no quedan como documentos sin tipar.
`tracks_expiry=False`: es el registro de una jornada, no caduca.
"""
from django.db import migrations


def seed_type(apps, schema_editor):
    DocumentTypeCatalog = apps.get_model(
        "document_explorer", "DocumentTypeCatalog")
    DocumentTypeCatalog.objects.get_or_create(
        code="ALBARAN_TRABAJO",
        defaults={
            "label": "Albarán de trabajo",
            "domain": "PERSONAL",
            "family": "LABORAL",
            "tracks_expiry": False,
            "expires": False,
            "is_active": True,
        },
    )


def unseed_type(apps, schema_editor):
    DocumentTypeCatalog = apps.get_model(
        "document_explorer", "DocumentTypeCatalog")
    DocumentTypeCatalog.objects.filter(code="ALBARAN_TRABAJO").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0218_signedformfile_signature_config_s153"),
    ]

    operations = [
        migrations.RunPython(seed_type, unseed_type),
    ]
