# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0026_seed_cert_accesorio_elevacion.py
"""
H30 (S49). Alta de un tipo documental nuevo, confirmado por Miguel
Ángel al revisar dos archivos reales mal ubicados bajo el nombre
"HOEFLON" (S-19 SEPARADOR): un certificado neerlandés de accesorio de
elevación ("CERTIFICAAT HIJSMIDDELEN" / "CERTIFICATE OF HOISTING
EQUIPMENT") de un balancín/separador extensible, fabricado por Deij
Hijstechniek B.V., suministrado a Grupo Álvarez (Geogruas SL) vía
Hoeflon International BV como intermediario.

El documento no encaja en ningún tipo existente sin forzarlo:
- No es `CE` (declaración CE de conformidad genérica, sin
  `tracks_expiry`) -- este certificado fija además una frecuencia de
  re-inspección obligatoria explícita ("Keurings frequentie: 12
  Maanden") con una tabla para ir anotando cada inspección sucesiva.
- No es `CERT_REVISION` (revisión periódica de la máquina/vehículo
  principal) -- este es un accesorio de elevación, no la grúa/camión
  en sí.

`CERT_ACCESORIO_ELEVACION`: `tracks_expiry=True` -- la fecha de la
última inspección más la periodicidad indicada en el propio
certificado (12 meses en el caso real que originó este tipo, aunque
puede variar por accesorio) es el dato real que debe alimentar
`vigencia_service.evaluate_substitution()`.
"""
from django.db import migrations


def seed_new_type(apps, schema_editor):
    DocumentTypeCatalog = apps.get_model("document_explorer", "DocumentTypeCatalog")
    DocumentTypeCatalog.objects.get_or_create(
        code="CERT_ACCESORIO_ELEVACION",
        defaults={
            "label": "Certificado de accesorio de elevación (CE + revisión periódica)",
            "domain": "MACHINE",
            "tracks_expiry": True,
            "is_active": True,
        },
    )


def unseed_new_type(apps, schema_editor):
    DocumentTypeCatalog = apps.get_model("document_explorer", "DocumentTypeCatalog")
    DocumentTypeCatalog.objects.filter(code="CERT_ACCESORIO_ELEVACION").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0025_poliza_poderes_factura_terceros"),
    ]

    operations = [
        migrations.RunPython(seed_new_type, unseed_new_type),
    ]
