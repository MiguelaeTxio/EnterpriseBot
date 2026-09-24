# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0140_revisiones_preventivas_cert_revision_s118.py
"""
H30 (S118), punto 6 de la hoja de ruta -- cierre del reparto de
CERT_MANTENIMIENTO. Las 4 "REVISION ANUAL" que no son órdenes de
Prologic pasan a CERT_REVISION (decisión de Miguel Ángel: "Ok"):

- Z-42, ids 14078, 14079, 14080 (2018-2020): lista de revisión
  preventiva firmada por el técnico Carlos Carlín.
- Z-57, id 14347: informe de mantenimiento preventivo del fabricante
  con la lista de comprobación marcada (18/07/2023).

Reverse: las devuelve a CERT_MANTENIMIENTO.
"""
from django.db import migrations

PREVENTIVE_REVISION_IDS = [14078, 14079, 14080, 14347]


def _retype(apps, from_code, to_code):
    DocumentTypeCatalog = apps.get_model(
        "document_explorer", "DocumentTypeCatalog",
    )
    DocumentIndexEntry = apps.get_model(
        "document_explorer", "DocumentIndexEntry",
    )
    target = DocumentTypeCatalog.objects.filter(code=to_code).first()
    if target is None:
        print("\n  [document_explorer 0140] No existe %s: no se toca nada."
              % to_code, flush=True)
        return
    changed = DocumentIndexEntry.objects.filter(
        pk__in=PREVENTIVE_REVISION_IDS,
        document_type__code=from_code,
        deleted_at__isnull=True,
    ).update(document_type=target)
    print("\n  [document_explorer 0140] %s -> %s: %d de %d"
          % (from_code, to_code, changed, len(PREVENTIVE_REVISION_IDS)),
          flush=True)


def forwards(apps, schema_editor):
    """
    Retype the preventive revision sheets to CERT_REVISION.
    ---
    Retipa las hojas de revisión preventiva a CERT_REVISION.
    """
    _retype(apps, "CERT_MANTENIMIENTO", "CERT_REVISION")


def backwards(apps, schema_editor):
    """
    Return them to CERT_MANTENIMIENTO.
    ---
    Las devuelve a CERT_MANTENIMIENTO.
    """
    _retype(apps, "CERT_REVISION", "CERT_MANTENIMIENTO")


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0139_orden_trabajo_mantenimiento_s118"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
