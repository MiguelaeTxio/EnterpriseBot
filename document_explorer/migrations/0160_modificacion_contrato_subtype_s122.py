# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0160_modificacion_contrato_subtype_s122.py
"""
H30 (S122). Tipo nuevo `MODIFICACION_CONTRATO` ("Modificación de
contrato"), subtipo de `CONTRATO` -- mismo mecanismo que
`PRORROGA_CONTRATO` (0159).

Revisión visual real de los contratos de trabajadores activos cuya
fecha discrepaba del nombre: 5 no eran contratos ni prórrogas sino
modificaciones de un contrato ya existente -- transformación a
indefinido comunicada por la Seguridad Social, cambio de clave del
contrato, ampliación de jornada. Como la prórroga, se ven dentro del
periodo de su contrato y nunca cuentan como contrato del alta.
`issue_date` = fecha de efectos de la modificación.
"""
from django.db import migrations

PARENT_CODE = "CONTRATO"
SUBTYPE_CODE = "MODIFICACION_CONTRATO"
SUBTYPE_LABEL = "Modificación de contrato"


def forwards(apps, schema_editor):
    """Crea el subtipo de modificación colgado de CONTRATO (idempotente)."""
    catalog = apps.get_model("document_explorer", "DocumentTypeCatalog")
    parent = catalog.objects.get(code=PARENT_CODE)
    catalog.objects.update_or_create(
        code=SUBTYPE_CODE,
        defaults={
            "label": SUBTYPE_LABEL,
            "domain": "PERSONAL",
            "family": parent.family,
            "parent_type": parent,
            "tracks_expiry": False,
            "is_cumulative": True,
            "is_active": True,
        },
    )


def backwards(apps, schema_editor):
    """Borra el subtipo (solo si ningún documento lo usa: PROTECT)."""
    catalog = apps.get_model("document_explorer", "DocumentTypeCatalog")
    catalog.objects.filter(code=SUBTYPE_CODE).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0159_prorroga_contrato_subtype_s122"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
