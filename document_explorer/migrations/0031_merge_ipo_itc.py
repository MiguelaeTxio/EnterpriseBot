# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0031_merge_ipo_itc.py
"""
H30 (S50). Fusion de IPO e ITC en un unico tipo IPO_ITC.

Origen real: al construir `sample_known_type_ocr_text` para descubrir
patrones de contenido reales por tipo (S50), los 3 ejemplos reales de
IPO y los 3 de ITC arrojaron literalmente el mismo texto de fondo --
"ACTA DE INSPECCIÓN PERIÓDICA DE GRÚAS MÓVILES AUTOPROPULSADAS" (o
"PEMP segun UNE 58921" para plataformas). Es el mismo documento real
(el acta de inspeccion periodica oficial de la grua/plataforma); la
unica diferencia observada hasta ahora era que palabra aparecia en el
NOMBRE del archivo, no el contenido. Miguel Angel, verbatim: "si en
documentos conocidos no podemos discernir entre IPO e ITC lo suyo es
fusionar el tipo en IPO/ITC."

Family elegida: TECNICA_SEGURIDAD (la de IPO) -- ITC tenia
CIRCULACION, pero el contenido real (acta de inspeccion tecnica) es
mas TECNICA_SEGURIDAD que CIRCULACION. tracks_expiry=False, igual que
ambos tipos originales -- este merge no cambia esa decision, es
aparte.

No se borran los tipos antiguos (IPO id=19, ITC id=16) -- se
desactivan (`is_active=False`) para no perder el rastro historico,
pero TODOS los `DocumentIndexEntry` que apuntaban a ellos se
reasignan al nuevo `IPO_ITC` en esta misma migracion.
"""
from django.db import migrations


def merge_ipo_itc(apps, schema_editor):
    DocumentTypeCatalog = apps.get_model("document_explorer", "DocumentTypeCatalog")
    DocumentIndexEntry = apps.get_model("document_explorer", "DocumentIndexEntry")

    merged, _created = DocumentTypeCatalog.objects.get_or_create(
        code="IPO_ITC",
        defaults={
            "label": "IPO/ITC -- Inspección Periódica Oficial de grúa móvil",
            "domain": "MACHINE",
            "family": "TECNICA_SEGURIDAD",
            "tracks_expiry": False,
            "is_active": True,
        },
    )

    old_ids = list(
        DocumentTypeCatalog.objects.filter(code__in=["IPO", "ITC"])
        .values_list("id", flat=True)
    )
    if old_ids:
        DocumentIndexEntry.objects.filter(
            document_type_id__in=old_ids,
        ).update(document_type_id=merged.id)

    DocumentTypeCatalog.objects.filter(code__in=["IPO", "ITC"]).update(
        is_active=False,
    )


def unmerge_ipo_itc(apps, schema_editor):
    # Reversion best-effort: no se puede reconstruir con certeza cual
    # entrada era IPO y cual era ITC (esa es justo la razon de la
    # fusion) -- se deja IPO_ITC como esta y se reactivan los tipos
    # antiguos vacios, sin reasignar filas de vuelta.
    DocumentTypeCatalog = apps.get_model("document_explorer", "DocumentTypeCatalog")
    DocumentTypeCatalog.objects.filter(code__in=["IPO", "ITC"]).update(
        is_active=True,
    )


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0030_seed_s50_second_round_types"),
    ]

    operations = [
        migrations.RunPython(merge_ipo_itc, unmerge_ipo_itc),
    ]
