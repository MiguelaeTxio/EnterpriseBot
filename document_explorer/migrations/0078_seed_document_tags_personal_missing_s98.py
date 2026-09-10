# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0078_seed_document_tags_personal_missing_s98.py
"""
H31 (S98). Corrige un descuido real de `0077_seed_document_tags_
personal_s98`: dos tipos PERSONAL activos (`ALTA_IDC`, `HUELLA_
CONTRATO`) se quedaron sin ninguna etiqueta por un olvido al
transcribir la lista de asignaciones -- detectado por la propia
consulta de verificación que Miguel Ángel pidió tras aplicar 0077
(EnterpriseBot_008_GET.txt de esta sesión: "Tipos PERSONAL activos SIN
ninguna etiqueta: 2").

- ALTA_IDC ("Alta + IDC", family IDENTIDAD_PERSONAL): combina alta en
  Seguridad Social e Informe de Datos para la Cotización -- reutiliza
  etiquetas ya creadas en 0077 (ALTA, IDC, SEGURIDAD_SOCIAL,
  COTIZACION, INFORME_DATOS_COTIZACION), ninguna nueva.
- HUELLA_CONTRATO ("Huella dactilar de contrato", family LABORAL):
  vocabulario real confirmado en el barrido (palabra "huella",
  19 documentos) -- etiqueta nueva HUELLA_DACTILAR, más CONTRATO
  (ya existente).

Reversible con el mismo criterio que 0077: solo deshace lo que esta
migración creó/asignó.
"""
from django.db import migrations


NEW_TAG_LABELS = {
    "HUELLA_DACTILAR": "Huella dactilar",
}

TYPE_TAGS = {
    "ALTA_IDC": [
        "ALTA", "IDC", "SEGURIDAD_SOCIAL", "COTIZACION",
        "INFORME_DATOS_COTIZACION",
    ],
    "HUELLA_CONTRATO": ["HUELLA_DACTILAR", "CONTRATO"],
}


def seed_missing_tags(apps, schema_editor):
    DocumentTag = apps.get_model("document_explorer", "DocumentTag")
    DocumentTypeCatalog = apps.get_model(
        "document_explorer", "DocumentTypeCatalog",
    )

    for code, label in NEW_TAG_LABELS.items():
        DocumentTag.objects.get_or_create(code=code, defaults={"label": label})

    for type_code, tag_codes in TYPE_TAGS.items():
        try:
            doc_type = DocumentTypeCatalog.objects.get(code=type_code)
        except DocumentTypeCatalog.DoesNotExist:
            continue
        tags = list(DocumentTag.objects.filter(code__in=tag_codes))
        doc_type.tags.set(tags)


def unseed_missing_tags(apps, schema_editor):
    DocumentTag = apps.get_model("document_explorer", "DocumentTag")
    DocumentTypeCatalog = apps.get_model(
        "document_explorer", "DocumentTypeCatalog",
    )
    for doc_type in DocumentTypeCatalog.objects.filter(
        code__in=list(TYPE_TAGS.keys()),
    ):
        doc_type.tags.clear()
    DocumentTag.objects.filter(code__in=list(NEW_TAG_LABELS.keys())).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0077_seed_document_tags_personal_s98"),
    ]

    operations = [
        migrations.RunPython(seed_missing_tags, unseed_missing_tags),
    ]
