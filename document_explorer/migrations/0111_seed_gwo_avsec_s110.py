# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0111_seed_gwo_avsec_s110.py
"""
H36 (S110). Alta de 2 tipos de curso reales mas, encontrados en la
revision completa (no por muestra) de los 304 documentos restantes en
los 5 cajones genericos:

- FORMACION_GWO_SEGURIDAD_EOLICA: certificados reales "Global Wind
  Organisation / WINDA Delegate Training Certificate" (SGS TECNOS
  S.A., ~15 documentos), modulos de seguridad basica para trabajo en
  el sector eolico (Fire Awareness, Working at Height, First Aid,
  Manual Handling, Sea Survival -- distintos modulos, mismo emisor y
  formato, un solo tipo para todos).

- FORMACION_AVSEC_SEGURIDAD_AEROPORTUARIA: certificados reales
  "Formacion AVSEC" / "Concienciacion en Seguridad Aeroportuaria"
  (formacionavsec.com y avsecformacion.es, ~10 documentos):
  formacion basica de seguridad de la aviacion civil.

Mismos criterios que el resto de tipos de FORMACION_* (0097): domain
PERSONAL, family PRL_FORMACION, tracks_expiry True, is_cumulative
True.
"""
from django.db import migrations

NEW_TYPES = [
    {
        "code": "FORMACION_GWO_SEGURIDAD_EOLICA",
        "label": "Formación GWO seguridad eólica",
    },
    {
        "code": "FORMACION_AVSEC_SEGURIDAD_AEROPORTUARIA",
        "label": "Formación AVSEC seguridad aeroportuaria",
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
                "domain": "PERSONAL",
                "family": "PRL_FORMACION",
                "tracks_expiry": True,
                "is_cumulative": True,
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
        ("document_explorer", "0110_reclassify_from_cached_ocr_text_2_s110"),
    ]

    operations = [
        migrations.RunPython(seed_new_types, unseed_new_types),
    ]
