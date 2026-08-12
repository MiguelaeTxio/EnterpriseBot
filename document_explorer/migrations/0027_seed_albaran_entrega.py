# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0027_seed_albaran_entrega.py
"""
H30 (S49). Alta de tipo documental nuevo, confirmado por Miguel Ángel
al cierre del caso real HOEFLON (S-19 SEPARADOR): el segundo de los
dos archivos reales que originaron `CERT_ACCESORIO_ELEVACION`
(0026_seed_cert_accesorio_elevacion.py) era el albarán de entrega
("Delivery Note") de Hoeflon International BV a Geogruas SL del mismo
accesorio -- documento de naturaleza distinta al certificado (registra
la entrega física, no la conformidad/inspección), sin tipo propio
hasta ahora en el catálogo `MACHINE`.

`tracks_expiry=False` -- es un documento puntual del hecho de la
entrega, no caduca ni tiene versión más reciente que lo sustituya.
"""
from django.db import migrations


def seed_new_type(apps, schema_editor):
    DocumentTypeCatalog = apps.get_model("document_explorer", "DocumentTypeCatalog")
    DocumentTypeCatalog.objects.get_or_create(
        code="ALBARAN_ENTREGA",
        defaults={
            "label": "Albarán de entrega",
            "domain": "MACHINE",
            "tracks_expiry": False,
            "is_active": True,
        },
    )


def unseed_new_type(apps, schema_editor):
    DocumentTypeCatalog = apps.get_model("document_explorer", "DocumentTypeCatalog")
    DocumentTypeCatalog.objects.filter(code="ALBARAN_ENTREGA").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0026_seed_cert_accesorio_elevacion"),
    ]

    operations = [
        migrations.RunPython(seed_new_type, unseed_new_type),
    ]
