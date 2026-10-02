# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0179_extincion_nacimiento_types_s127.py
"""
H30 (S127). Dos tipos nuevos aprobados por Miguel Ángel en la revisión
de NO CONFORMES:

- `EXTINCION_CONTRATO` ("Extinción de contrato"): comunicación de fin
  del contrato por la empresa (p. ej. no superar el periodo de prueba).
  Subtipo de `CONTRATO`, como prórroga y modificación (0159/0160): se ve
  dentro del periodo de su contrato y nunca cuenta como contrato del
  alta. `issue_date` = fecha de efectos.
- `PRESTACION_NACIMIENTO` ("Prestación por nacimiento y cuidado de
  menor"): informe de datos del INSS / certificado de empresa para la
  prestación. Misma familia que `ALTA` (Seguridad Social).
"""
from django.db import migrations


def forwards(apps, schema_editor):
    """Crea los dos tipos (idempotente)."""
    catalog = apps.get_model("document_explorer", "DocumentTypeCatalog")
    contract = catalog.objects.get(code="CONTRATO")
    catalog.objects.update_or_create(
        code="EXTINCION_CONTRATO",
        defaults={
            "label": "Extinción de contrato",
            "domain": "PERSONAL",
            "family": contract.family,
            "parent_type": contract,
            "tracks_expiry": False,
            "is_cumulative": True,
            "is_active": True,
        },
    )
    social_security = catalog.objects.get(code="ALTA")
    catalog.objects.update_or_create(
        code="PRESTACION_NACIMIENTO",
        defaults={
            "label": "Prestación por nacimiento y cuidado de menor",
            "domain": "PERSONAL",
            "family": social_security.family,
            "tracks_expiry": False,
            "is_cumulative": True,
            "is_active": True,
        },
    )


def backwards(apps, schema_editor):
    """Borra los dos tipos (solo si ningún documento los usa: PROTECT)."""
    catalog = apps.get_model("document_explorer", "DocumentTypeCatalog")
    catalog.objects.filter(
        code__in=["EXTINCION_CONTRATO", "PRESTACION_NACIMIENTO"],
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0178_noticeappointmentrequest_s126"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
