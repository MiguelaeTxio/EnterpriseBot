# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/budgets/migrations/0043_seed_driver_requirements_s133.py
"""
H37 (S133). Initial table of what a driver needs per machine type.

---

H37 (S133). Tabla inicial acordada con Miguel Ángel ("Perfecto", S133)
de lo que necesita un conductor en vigor por tipo de máquina de la
familia ASISTENCIA. Solo se crea para los tipos que existen en la flota
de cada empresa; lo demás se edita luego en base de datos.
"""
from django.db import migrations

DOCUMENTS = {
    "CAP": ("CAP", "TARJETA_CUALIF_CONDUCTOR"),
    "Carné de gruista": ("CARNET_GRUISTA",),
}
TABLE = {
    "ASISTENCIA EN CARRETERA": (("C",), ("CAP",)),
    "CABEZA TRACTORA": (("CE",), ("CAP",)),
    "CABEZA TRACTORA ASISTENCIA": (("CE",), ("CAP",)),
    "GRUA MOVIL 20 TM": (("C",), ("CAP", "Carné de gruista")),
    "GRUA MOVIL 30 TM": (("C",), ("CAP", "Carné de gruista")),
    "RESCATE CON GRUA MOVIL ASISTENCIA": (
        ("C",), ("CAP", "Carné de gruista"),
    ),
    "VEHICULOS DE PERSONAL": (("B",), ()),
}


def seed(apps, schema_editor):
    DocumentTypeCatalog = apps.get_model(
        "document_explorer", "DocumentTypeCatalog",
    )
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

    documents = {}
    for name, codes in DOCUMENTS.items():
        document, _created = DriverDocumentRequirement.objects.get_or_create(
            name=name,
        )
        document.document_types.set(
            DocumentTypeCatalog.objects.filter(code__in=codes),
        )
        documents[name] = document

    pairs = MachineAsset.objects.filter(
        family__iexact="ASISTENCIA", is_active=True,
    ).values_list("company_id", "type_name").distinct()
    for company_id, type_name in pairs:
        row = TABLE.get((type_name or "").strip().upper())
        if row is None:
            continue
        categories, document_names = row
        requirement, _created = MachineDriverRequirement.objects.get_or_create(
            company_id=company_id, machine_type_name=type_name.strip(),
        )
        requirement.required_categories.set(
            DrivingLicenceCategory.objects.filter(code__in=categories),
        )
        requirement.required_documents.set(
            [documents[name] for name in document_names],
        )


class Migration(migrations.Migration):

    dependencies = [
        ("budgets", "0042_driver_requirements_s133"),
        ("fleet", "0019_service_crane_hours_s131"),
    ]

    operations = [
        migrations.RunPython(seed, migrations.RunPython.noop),
    ]
