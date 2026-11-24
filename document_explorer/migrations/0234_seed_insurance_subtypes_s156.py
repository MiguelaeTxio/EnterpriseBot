# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0234_seed_insurance_subtypes_s156.py
"""
S156. Subtipos de seguro de EMPRESA que piden las plataformas de
coordinacion (egestiona: "Justificante pago Seguro Responsabilidad
Civil"; seguro de accidentes de convenio). Con el recibo generico no se
distinguia el de RC del de un vehiculo o del de vida.

Caducan (`expires=True`): su fecha es el fin del periodo cubierto.
"""
from django.db import migrations


INSURANCE_TYPES = (
    ("RECIBO_SEGURO_RC_EMPRESA",
     "Recibo del seguro de responsabilidad civil (empresa)"),
    ("POLIZA_SEGURO_RC_EMPRESA",
     "Póliza o certificado del seguro de responsabilidad civil (empresa)"),
    ("RECIBO_SEGURO_ACCIDENTES_EMPRESA",
     "Recibo del seguro de accidentes de convenio (empresa)"),
    ("POLIZA_SEGURO_ACCIDENTES_EMPRESA",
     "Póliza o certificado del seguro de accidentes de convenio "
     "(empresa)"),
)


def seed_types(apps, schema_editor):
    DocumentTypeCatalog = apps.get_model(
        "document_explorer", "DocumentTypeCatalog")
    for code, label in INSURANCE_TYPES:
        DocumentTypeCatalog.objects.get_or_create(
            code=code,
            defaults={
                "label": label,
                "domain": "COMPANY",
                "family": "SEGUROS",
                "tracks_expiry": True,
                "expires": True,
                "is_active": True,
            },
        )


def unseed_types(apps, schema_editor):
    DocumentTypeCatalog = apps.get_model(
        "document_explorer", "DocumentTypeCatalog")
    DocumentTypeCatalog.objects.filter(
        code__in=[row[0] for row in INSURANCE_TYPES]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0233_epidelivery_retired_s163"),
    ]

    operations = [
        migrations.RunPython(seed_types, unseed_types),
    ]
