# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0068_seed_chaleco_chaqueton_chaqueta_trabajo_s83.py
"""
H30 (S83). Tres altas reales en EpiItemCatalog, confirmadas por
Miguel Angel verbatim tras revisar las etiquetas sin mapear que salio
la prueba dirigida del arreglo de OCR (--psm 11, commit 10bc3d2)
contra la muestra real de S82:

1. CHALECO_ABRIGO -- "chaleco" (sin la palabra "reflectante") es un
   item real distinto de CHALECO_REFLECTANTE: "el chaleco de trabajo,
   que no es reflectante, la ropa para proteccion contra el frio".

2. CHAQUETON_ALTA_VISIBILIDAD -- item real distinto de
   CHAQUETA_ALTA_VISIBILIDAD: "el chaqueton de alta visibilidad [...]
   es para la alta visibilidad".

3. CHAQUETA_TRABAJO -- CORRIGE un mapeo real equivocado: la etiqueta
   "CHAQUETA" (sin "alta visibilidad") venia mapeada desde S71/S72 a
   CHAQUETA_ALTA_VISIBILIDAD, pero Miguel Angel confirma que es un
   item distinto: "esta chaqueta es una chaqueta de un tejido mas
   duro para trabajar en mecanica, soldadura, etcetera [...] esta
   mas en el mismo caso que el chaleco" (ropa de trabajo, no de alta
   visibilidad). Las entregas ya creadas con el codigo antiguo NO se
   tocan aqui -- son datos historicos ya persistidos, fuera de
   alcance de esta migracion (solo siembra catalogo).
"""
from django.db import migrations

NEW_ITEMS = [
    {
        "family": "Ropa de trabajo",
        "code": "CHALECO_ABRIGO",
        "label": "Chaleco de abrigo (no reflectante)",
    },
    {
        "family": "Alta visibilidad",
        "code": "CHAQUETON_ALTA_VISIBILIDAD",
        "label": "Chaquetón alta visibilidad",
    },
    {
        "family": "Ropa de trabajo",
        "code": "CHAQUETA_TRABAJO",
        "label": "Chaqueta de trabajo (tejido reforzado, mecánica/soldadura)",
    },
]


def seed_new_items(apps, schema_editor):
    EpiItemCatalog = apps.get_model("document_explorer", "EpiItemCatalog")
    for item in NEW_ITEMS:
        EpiItemCatalog.objects.get_or_create(
            code=item["code"],
            defaults={
                "family": item["family"],
                "label": item["label"],
                "requires_periodic_review": False,
                "replacement_cost": None,
                "une_en_standard": None,
                "is_active": True,
            },
        )


def unseed_new_items(apps, schema_editor):
    EpiItemCatalog = apps.get_model("document_explorer", "EpiItemCatalog")
    EpiItemCatalog.objects.filter(
        code__in=[item["code"] for item in NEW_ITEMS]
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0067_personidentity_birth_date_s82"),
    ]

    operations = [
        migrations.RunPython(seed_new_items, unseed_new_items),
    ]
