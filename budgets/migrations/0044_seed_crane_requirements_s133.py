# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/budgets/migrations/0044_seed_crane_requirements_s133.py
"""
H37 (S133). Mobile cranes: the fleet names them "GRUA MOVIL DE 20 TM".

---

H37 (S133). 0043 buscaba "GRUA MOVIL 20 TM" y en la flota real los
tipos se llaman "GRUA MOVIL DE 20 TM" y "GRUA MOVIL DE 30 TM"
(comprobado en producción): se crean aquí con lo acordado (C + CAP +
carné de gruista).
"""
from django.db import migrations

CRANE_TYPES = ("GRUA MOVIL DE 20 TM", "GRUA MOVIL DE 30 TM")


def seed(apps, schema_editor):
    DrivingLicenceCategory = apps.get_model(
        "document_explorer", "DrivingLicenceCategory",
    )
    MachineAsset = apps.get_model("fleet", "MachineAsset")
    DriverDocumentRequirement = apps.get_model(
        "budgets", "DriverDocumentRequirement",
    )
    MachineDriverRequirement = apps.get_model(
        "budgets", "MachineDriverRequirement",
    )
    documents = DriverDocumentRequirement.objects.filter(
        name__in=("CAP", "Carné de gruista"),
    )
    pairs = MachineAsset.objects.filter(
        family__iexact="ASISTENCIA", is_active=True,
        type_name__in=CRANE_TYPES,
    ).values_list("company_id", "type_name").distinct()
    for company_id, type_name in pairs:
        requirement, _created = MachineDriverRequirement.objects.get_or_create(
            company_id=company_id, machine_type_name=type_name,
        )
        requirement.required_categories.set(
            DrivingLicenceCategory.objects.filter(code="C"),
        )
        requirement.required_documents.set(documents)


class Migration(migrations.Migration):

    dependencies = [
        ("budgets", "0043_seed_driver_requirements_s133"),
    ]

    operations = [
        migrations.RunPython(seed, migrations.RunPython.noop),
    ]
