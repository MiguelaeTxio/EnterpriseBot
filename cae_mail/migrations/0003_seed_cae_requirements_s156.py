# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/cae_mail/migrations/0003_seed_cae_requirements_s156.py
"""
S156. Requisitos de documentación sacados de lo que piden los avisos de
las plataformas CAE (egestiona para Orange, Totem y Siemens; Cellnex;
Nidus), agrupados por conjunto de documentos (Miguel Ángel: si varias
piden lo mismo, un solo requisito; si piden cosas distintas, otro).
Se asignan a Grúas Álvarez y Transgrual y a las máquinas y trabajadores
que nombran los avisos de cada plataforma. Fuera: ENEL y SAP Ariba
(altas de proveedor), la nómina de Nalanda (mensual, va por su circuito)
y Quioo (sus avisos no dicen qué documentos piden).
"""
from django.db import migrations

COMPANY = "CAE · Empresa"
MACHINE = "CAE · Máquina"
WORKER = "CAE · Trabajador"
WORKER_CELLNEX = "CAE · Trabajador Cellnex"

REQUIREMENTS = {
    COMPANY: (
        "CERT_CORRIENTE_AEAT", "CERT_CORRIENTE_SS_EMPRESA", "TC1_EMPRESA",
        "ITA_EMPRESA", "CERT_SERVICIO_PREVENCION",
        "EVALUACION_RIESGOS_EMPRESA", "POLIZA_SEGURO_EMPRESA",
        "RECIBO_SEGURO_EMPRESA",
    ),
    MACHINE: (
        "CE", "ITV", "POLIZA_SEGURO", "SEGURO", "PERMISO_CIRCULACION",
        "TARJETA_TRANSPORTE", "MANUAL_USO", "CERT_MANTENIMIENTO",
        "ORDEN_TRABAJO_MANTENIMIENTO",
    ),
    WORKER: ("DNI", "RECONOCIMIENTO_MEDICO", "EPIS", "CARNET_CONDUCIR"),
    WORKER_CELLNEX: (
        "FORMACION_PRL_60H", "FORMACION_PRL_ART_18_19",
        "FORMACION_PRL_MAQUINARIA", "TITULACION_ACADEMICA",
    ),
}
# CIF de Grúas Adolfo Álvarez y Transgrual (CompanyFiscalProfile, S113).
COMPANY_TAX_IDS = ("B29405040", "B92493022")
MACHINE_PLATFORMS = ("egestiona", "Nidus Prevención")
WORKER_PLATFORMS = ("egestiona", "Cellnex (Cosmos)")
CELLNEX = "Cellnex (Cosmos)"


def seed(apps, schema_editor):
    JobPosition = apps.get_model("document_explorer", "JobPosition")
    DocumentTypeCatalog = apps.get_model(
        "document_explorer", "DocumentTypeCatalog")
    CompanyFiscalProfile = apps.get_model(
        "document_explorer", "CompanyFiscalProfile")
    PersonIdentity = apps.get_model("document_explorer", "PersonIdentity")
    MachineAsset = apps.get_model("fleet", "MachineAsset")
    CaeDemand = apps.get_model("cae_mail", "CaeDemand")

    positions = {}
    for name, codes in REQUIREMENTS.items():
        position, _created = JobPosition.objects.get_or_create(
            name=name, defaults={"is_active": True})
        position.required_document_types.add(
            *DocumentTypeCatalog.objects.filter(code__in=codes))
        positions[name] = position

    for company in CompanyFiscalProfile.objects.filter(
            tax_id__in=COMPANY_TAX_IDS):
        company.document_requirements.add(positions[COMPANY])

    machine_ids = set(CaeDemand.objects.filter(
        subject_type="MAQUINA", machine__isnull=False,
        mail__platform__in=MACHINE_PLATFORMS,
    ).values_list("machine_id", flat=True))
    for machine in MachineAsset.objects.filter(pk__in=machine_ids):
        machine.document_requirements.add(positions[MACHINE])

    worker_ids = set(CaeDemand.objects.filter(
        subject_type="TRABAJADOR", person__isnull=False,
        mail__platform__in=WORKER_PLATFORMS,
    ).values_list("person_id", flat=True))
    for person in PersonIdentity.objects.filter(pk__in=worker_ids):
        person.document_requirements.add(positions[WORKER])

    cellnex_ids = set(CaeDemand.objects.filter(
        subject_type="TRABAJADOR", person__isnull=False,
        mail__platform=CELLNEX,
    ).values_list("person_id", flat=True))
    for person in PersonIdentity.objects.filter(pk__in=cellnex_ids):
        person.document_requirements.add(positions[WORKER_CELLNEX])


def unseed(apps, schema_editor):
    JobPosition = apps.get_model("document_explorer", "JobPosition")
    JobPosition.objects.filter(name__in=list(REQUIREMENTS)).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("cae_mail", "0002_cae_demand_links_s156"),
        ("document_explorer", "0232_company_requirements_dossier_scope_s156"),
        ("fleet", "0045_qr_editor_settings_s154"),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
