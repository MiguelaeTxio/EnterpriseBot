# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0046_seed_s65_segundo_lote.py
"""
H30 (S65). Segundo lote de tipos documentales, extraidos del listado
completo de los 599 archivos con nombre real que seguian sin tipo tras
el primer lote (EnterpriseBot_026_GET.txt), medidos contra volumen
real antes de aplicar (EnterpriseBot_027_GET.txt).

Volumen real medido:
  ALTA_IDC: 10
  AUTORIZACION_TEMPORAL_CONDUCIR: 9
  TARJETA_SANITARIA: 6
  DOC_MUTUA: 7
  COMUNICACION_CONTRATO: 7
  CERTIFICADO_GIBRALTAR: 11
  DECLARACION_EMPRESA: 8
  CIRCULAR_INFORMATIVA: 2

DECLARACION_EMPRESA y CIRCULAR_INFORMATIVA van con domain=COMPANY --
son declaraciones/circulares de la empresa (plantilla fija, corriente
de pagos, circular de permiso de conducir), no documentos de una
persona concreta, aunque el archivo viva fisicamente bajo el arbol de
carpetas DOC. PERSONAL. Mismo criterio ya aplicado a CSS en la
migracion 0041 (reasignado a COMPANY pese a vivir bajo una carpeta de
nombre distinto).

CERTIFICADO_GIBRALTAR agrupa los formularios de coordinacion de
Seguridad Social UE/Gibraltar (A1, Authorisation, Tax Return, TA.300,
Detached Permit) bajo un solo tipo -- confirmado con muestra real que
son variantes del mismo tramite cuando un conductor de grua movil
cruza a Gibraltar, siempre en ingles/formulario oficial.
"""
from django.db import migrations

NEW_TYPES = [
    {
        "code": "ALTA_IDC",
        "label": "Alta + IDC",
        "domain": "PERSONAL",
        "family": "IDENTIDAD_PERSONAL",
        "tracks_expiry": False,
    },
    {
        "code": "AUTORIZACION_TEMPORAL_CONDUCIR",
        "label": "Autorización temporal para conducir",
        "domain": "PERSONAL",
        "family": "CIRCULACION",
        "tracks_expiry": False,
    },
    {
        "code": "TARJETA_SANITARIA",
        "label": "Tarjeta sanitaria",
        "domain": "PERSONAL",
        "family": "SALUD_BAJAS_PERSONA",
        "tracks_expiry": False,
    },
    {
        "code": "DOC_MUTUA",
        "label": "Documentación de mutua",
        "domain": "PERSONAL",
        "family": "SALUD_BAJAS_PERSONA",
        "tracks_expiry": False,
    },
    {
        "code": "COMUNICACION_CONTRATO",
        "label": "Comunicación de contrato",
        "domain": "PERSONAL",
        "family": "LABORAL",
        "tracks_expiry": False,
    },
    {
        "code": "CERTIFICADO_GIBRALTAR",
        "label": "Certificado Gibraltar (A1 / Authorisation / Tax Return)",
        "domain": "PERSONAL",
        "family": "LABORAL",
        "tracks_expiry": False,
    },
    {
        "code": "DECLARACION_EMPRESA",
        "label": "Declaración de empresa (plantilla fija / corriente de pagos)",
        "domain": "COMPANY",
        "family": "ADMINISTRATIVO",
        "tracks_expiry": False,
    },
    {
        "code": "CIRCULAR_INFORMATIVA",
        "label": "Circular informativa",
        "domain": "COMPANY",
        "family": "ADMINISTRATIVO",
        "tracks_expiry": False,
    },
]


def seed_new_types(apps, schema_editor):
    DocumentTypeCatalog = apps.get_model(
        "document_explorer", "DocumentTypeCatalog",
    )
    for spec in NEW_TYPES:
        DocumentTypeCatalog.objects.get_or_create(
            code=spec["code"],
            defaults={
                "label": spec["label"],
                "domain": spec["domain"],
                "family": spec["family"],
                "tracks_expiry": spec["tracks_expiry"],
                "is_active": True,
            },
        )


def unseed_new_types(apps, schema_editor):
    DocumentTypeCatalog = apps.get_model(
        "document_explorer", "DocumentTypeCatalog",
    )
    DocumentTypeCatalog.objects.filter(
        code__in=[spec["code"] for spec in NEW_TYPES],
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0045_seed_s65_dossier_types"),
    ]

    operations = [
        migrations.RunPython(seed_new_types, unseed_new_types),
    ]
