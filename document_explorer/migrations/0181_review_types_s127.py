# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0181_review_types_s127.py
"""
H30 (S127). Tipos aprobados por Miguel Ángel en la revisión de los NO
CONFORMES de la pasada de DOC. PERSONAL (letra A).
"""
from django.db import migrations

NEW_TYPES = [
    # (código, etiqueta, dominio, familia)
    ("LISTADO_EXAMEN_OFICIAL",
     "Listado oficial de admitidos/aprobados en un examen", "COMPANY",
     "PRL_FORMACION"),
    ("EMBARGO_SALARIO", "Embargo de salario (juzgado / AEAT)", "PERSONAL",
     "LABORAL"),
    ("CERTIFICADO_MATRIMONIO", "Certificado o acta de matrimonio",
     "PERSONAL", "IDENTIDAD_PERSONAL"),
    ("JUSTIFICANTE_ACOMPANAMIENTO",
     "Justificante de acompañamiento médico de un familiar", "PERSONAL",
     "SALUD_BAJAS_PERSONA"),
    ("INFORME_MEDICO", "Informe médico (no laboral)", "PERSONAL",
     "SALUD_BAJAS_PERSONA"),
]


def forwards(apps, schema_editor):
    """Crea los tipos (idempotente)."""
    catalog = apps.get_model("document_explorer", "DocumentTypeCatalog")
    for code, label, domain, family in NEW_TYPES:
        catalog.objects.update_or_create(
            code=code,
            defaults={
                "label": label, "domain": domain, "family": family,
                "tracks_expiry": False, "is_cumulative": True,
                "is_active": True,
            },
        )


def backwards(apps, schema_editor):
    """Borra los tipos (solo si ningún documento los usa: PROTECT)."""
    catalog = apps.get_model("document_explorer", "DocumentTypeCatalog")
    catalog.objects.filter(code__in=[row[0] for row in NEW_TYPES]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0180_company_types_s127"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
