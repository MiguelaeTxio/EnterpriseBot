# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0144_tipo_condiciones_generales_seguro_s119.py
"""
H30 (S119), punto 1. Tipo nuevo CONDICIONES_GENERALES_SEGURO: el
cuadernillo de condiciones generales de una aseguradora (Generali
Maquinaria, Europ Assistance "Libre Elección"), genérico y sin fecha
propia, que acompaña a la póliza de una máquina. Estaba tipado como
POLIZA_SEGURO, que caduca, y no se podía fechar. Decisión de Miguel
Ángel en S119 ("2": tipo nuevo, conservarlas junto a la póliza).
Familia Seguros, sin caducidad; acumulable, porque una máquina puede
tener a la vez las de su seguro y las de su asistencia en viaje.

Reverse: lo borra solo si no tiene documentos.
"""
from django.db import migrations

CODE = "CONDICIONES_GENERALES_SEGURO"


def forwards(apps, schema_editor):
    DocumentTypeCatalog = apps.get_model(
        "document_explorer", "DocumentTypeCatalog",
    )
    _type, created = DocumentTypeCatalog.objects.get_or_create(
        code=CODE,
        defaults={
            "label": "Condiciones generales de seguro",
            "domain": "MACHINE",
            "family": "SEGUROS",
            "tracks_expiry": False,
            "is_cumulative": True,
            "is_active": True,
        },
    )
    print("\n  [document_explorer 0144] Tipo %s %s"
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
        ("document_explorer", "0143_dossier_template_scope_s119"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
