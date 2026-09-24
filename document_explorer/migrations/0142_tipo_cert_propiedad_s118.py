# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0142_tipo_cert_propiedad_s118.py
"""
H30 (S118), punto 7 de la hoja de ruta. Tipo nuevo CERT_PROPIEDAD:
certificado de propiedad o titularidad de una máquina firmado por el
administrador ("ADOLFO ALVAREZ DIAZ [...] COMO ADMINISTRADOR DE
TRANSGRUAL S.L. [...] CERTIFICA QUE LA CABEZA TRACTORA P-14 [...] ES
PROPIEDAD DE DICHA EMPRESA"). Decisión de Miguel Ángel: "Correcto".
Familia Financiero y compraventa, sin caducidad, no acumulable.

Reverse: lo borra solo si no tiene documentos.
"""
from django.db import migrations

CODE = "CERT_PROPIEDAD"


def forwards(apps, schema_editor):
    DocumentTypeCatalog = apps.get_model(
        "document_explorer", "DocumentTypeCatalog",
    )
    _type, created = DocumentTypeCatalog.objects.get_or_create(
        code=CODE,
        defaults={
            "label": "Certificado de propiedad / titularidad",
            "domain": "MACHINE",
            "family": "FINANCIERO",
            "tracks_expiry": False,
            "is_cumulative": False,
            "is_active": True,
        },
    )
    print("\n  [document_explorer 0142] Tipo %s %s"
          % (CODE, "creado" if created else "ya existía"), flush=True)


def backwards(apps, schema_editor):
    DocumentTypeCatalog = apps.get_model(
        "document_explorer", "DocumentTypeCatalog",
    )
    DocumentIndexEntry = apps.get_model(
        "document_explorer", "DocumentIndexEntry",
    )
    if not DocumentIndexEntry.objects.filter(
        document_type__code=CODE,
    ).exists():
        DocumentTypeCatalog.objects.filter(code=CODE).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0141_reasignar_cert_a54_s118"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
