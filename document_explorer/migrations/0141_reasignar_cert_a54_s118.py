# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0141_reasignar_cert_a54_s118.py
"""
H30 (S118). El documento id 9974 ("A-54 E-4658-BGW  Cert Mant
15-09-25.pdf"), archivado en la carpeta de la A-56 y vinculado a la A56,
certifica por contenido la grúa móvil A-54 con matrícula E-4658-BGW --
se reasigna a la máquina A54. Solo cambia el vínculo del índice; el
archivo en GCS no se toca.

Reverse: lo devuelve a la A56.
"""
from django.db import migrations

ENTRY_ID = 9974


def _move(apps, to_code):
    DocumentIndexEntry = apps.get_model(
        "document_explorer", "DocumentIndexEntry",
    )
    MachineAsset = apps.get_model("fleet", "MachineAsset")
    target = MachineAsset.objects.filter(code=to_code).first()
    if target is None:
        print("\n  [document_explorer 0141] No existe la máquina %s: no se "
              "toca nada." % to_code, flush=True)
        return
    moved = DocumentIndexEntry.objects.filter(
        pk=ENTRY_ID, deleted_at__isnull=True,
    ).update(domain_object_id=target.pk)
    print("\n  [document_explorer 0141] id %d -> %s (pk=%d): %d"
          % (ENTRY_ID, to_code, target.pk, moved), flush=True)


def forwards(apps, schema_editor):
    """
    Move the A-54 certificate to machine A54.
    ---
    Reasigna el certificado de la A-54 a la máquina A54.
    """
    _move(apps, "A54")


def backwards(apps, schema_editor):
    """
    Return it to machine A56.
    ---
    Lo devuelve a la máquina A56.
    """
    _move(apps, "A56")


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0140_revisiones_preventivas_cert_revision_s118"),
        ("fleet", "0012_fix_default_machine_photo_s118"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
