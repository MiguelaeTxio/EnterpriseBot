# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0159_prorroga_contrato_subtype_s122.py
"""
H30 (S122). Tipo nuevo `PRORROGA_CONTRATO` ("Prórroga de contrato"),
subtipo de `CONTRATO` (mecanismo `parent_type` de S120).

Revisión visual real de los 33 contratos sin fecha de trabajadores
activos (S122): 31 eran comunicaciones de PRÓRROGA (SEPE o impreso
firmado), no contratos -- alargan un contrato existente, nunca
corresponden a un alta. Decisión de Miguel Ángel: "perfecto que se
vea dentro del periodo y dentro de su contrato la prórroga. Y que no
cuente como contrato de alta".

Misma familia que CONTRATO (leída de la BD), dominio Personal,
acumulable (varias prórrogas a la vez son hechos distintos), sin
control de caducidad: `issue_date` = inicio de la prórroga,
`expiry_date` = término, solo informativos -- nunca generan avisos.
"""
from django.db import migrations

PARENT_CODE = "CONTRATO"
SUBTYPE_CODE = "PRORROGA_CONTRATO"
SUBTYPE_LABEL = "Prórroga de contrato"


def forwards(apps, schema_editor):
    """Crea el subtipo de prórroga colgado de CONTRATO (idempotente)."""
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
        ("document_explorer", "0158_contratos_altas_acumulables_s122"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
