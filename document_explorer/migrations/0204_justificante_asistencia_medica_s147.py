# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0204_justificante_asistencia_medica_s147.py
"""
H24 (S147 invasora). Document type for the worker's own medical
attendance proof.

---

Tipo "Justificante de asistencia médica": el justificante de que el
propio trabajador fue al médico (Mis solicitudes). Decidido por Miguel
Ángel en S147 (opción 1: tipo nuevo y retipado de los históricos que lo
sean, directriz 4.22). Sin fecha de caducidad; acumulable (cada
justificante es de un día distinto, ninguno sustituye a otro).
"""
from django.db import migrations

CODE = "JUSTIFICANTE_ASISTENCIA_MEDICA"


def forwards(apps, schema_editor):
    """Crea el tipo (idempotente)."""
    catalog = apps.get_model("document_explorer", "DocumentTypeCatalog")
    catalog.objects.update_or_create(
        code=CODE,
        defaults={
            "label": "Justificante de asistencia médica",
            "domain": "PERSONAL", "family": "SALUD_BAJAS_PERSONA",
            "tracks_expiry": False, "expires": False,
            "is_cumulative": True, "is_active": True,
        },
    )


def backwards(apps, schema_editor):
    """Borra el tipo (solo si ningún documento lo usa: PROTECT)."""
    catalog = apps.get_model("document_explorer", "DocumentTypeCatalog")
    catalog.objects.filter(code=CODE).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0203_databasebackup_restore_s146"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
