# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0182_contract_cover_types_s127.py
"""
H30 (S127). Dos documentos que, sin ser el contrato, demuestran que lo
hubo y CUBREN el alta (Miguel Ángel, opción a):

- SUBROGACION_CONTRATO: carta de subrogación (una empresa traspasa la
  relación laboral a otra). Fecha = la de efectos de la subrogación.
- CONVERSION_CONTRATO: conversión de temporal en indefinido. Fecha = la
  de CELEBRACIÓN del contrato temporal original ("celebrado el día..."),
  que es la que casa con su alta; la de la conversión va en el nombre.

Subtipos de CONTRATO (como prórroga y modificación), pero a diferencia
de ellos sí cuentan como contrato del alta
(employment_period_service.CONTRACT_COVER_CODES). La pista de qué fecha
leer va en la etiqueta, que es lo que ve Gemini en el catálogo.
"""
from django.db import migrations

NEW_TYPES = [
    ("SUBROGACION_CONTRATO",
     "Subrogación de la relación laboral (fecha: la de efectos)"),
    ("CONVERSION_CONTRATO",
     "Conversión de contrato temporal en indefinido (fecha: la de "
     "celebración del contrato temporal original)"),
]


def forwards(apps, schema_editor):
    """Crea los dos subtipos de CONTRATO (idempotente)."""
    catalog = apps.get_model("document_explorer", "DocumentTypeCatalog")
    contract = catalog.objects.get(code="CONTRATO")
    for code, label in NEW_TYPES:
        catalog.objects.update_or_create(
            code=code,
            defaults={
                "label": label, "domain": "PERSONAL",
                "family": contract.family, "parent_type": contract,
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
        ("document_explorer", "0181_review_types_s127"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
