# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0048_seed_s65_cuarto_lote.py
"""
H30 (S65). Cuarto lote -- Miguel Angel senalo correctamente que la
heuristica NO estaba agotada tras el tercer lote (CARNET_GRUISTA
seguia sin cubrir variantes con preposicion intermedia -- "CARNET DE
GRUISTA", "CARNE A GRUISTA" -- y dos carpetas reales, NOMBRAMIENTO
RECURSO PREVENTIVO y TC2, nunca tuvieron tipo propio, solo existian
como nombre de carpeta). Medido contra volumen real antes de aplicar
(EnterpriseBot_032_GET.txt).

Volumen real medido:
  CARNET_GRUISTA (extension de tipo ya existente): 10
  TC2 (tipo nuevo): 1
  NOMBRAMIENTO_RECURSO_PREVENTIVO (tipo nuevo): 6
"""
from django.db import migrations

NEW_TYPES = [
    {
        "code": "TC2",
        "label": "Boletín de cotización TC2",
        "domain": "PERSONAL",
        "family": "LABORAL",
        "tracks_expiry": False,
    },
    {
        "code": "NOMBRAMIENTO_RECURSO_PREVENTIVO",
        "label": "Nombramiento de recurso preventivo",
        "domain": "PERSONAL",
        "family": "PRL_FORMACION",
        "tracks_expiry": False,
    },
]


def seed_new_types(apps, schema_editor):
    DocumentTypeCatalog = apps.get_model(
        "document_explorer", "DocumentTypeCatalog",
    )
    for spec in NEW_TYPES:
        DocumentTypeCatalog.objects.get_or_create(
            code=spec["code"],
            defaults={
                "label": spec["label"],
                "domain": spec["domain"],
                "family": spec["family"],
                "tracks_expiry": spec["tracks_expiry"],
                "is_active": True,
            },
        )


def unseed_new_types(apps, schema_editor):
    DocumentTypeCatalog = apps.get_model(
        "document_explorer", "DocumentTypeCatalog",
    )
    DocumentTypeCatalog.objects.filter(
        code__in=[spec["code"] for spec in NEW_TYPES],
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0047_seed_s65_tercer_lote"),
    ]

    operations = [
        migrations.RunPython(seed_new_types, unseed_new_types),
    ]
