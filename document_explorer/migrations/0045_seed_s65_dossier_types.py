# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0045_seed_s65_dossier_types.py
"""
H30 (S65). Alta de 9 tipos documentales nuevos, detectados y medidos
contra volumen real (EnterpriseBot_023_GET.txt) dentro de los dossiers
individuales de DOC. PERSONAL/PERSONAL/OPERARIOS, ADMINISTRACION y
TALLER -- confirmado que estas carpetas mezclan tipos ya resueltos con
patrones reales repetidos que nunca tuvieron regla propia.

Volumen real medido sobre los 822 archivos sin tipo de PERSONAL en el
momento de escribir esto (antes de aplicar):
  CLAUSULA_PROTECCION_DATOS: 11
  CAMBIO_EMPRESA_SUBROGACION: 9
  CAMBIO_IRPF: 13
  TARJETA_CUALIF_CONDUCTOR: 3
  HUELLA_CONTRATO: 21
  COMUNICADO_SEPE: 1
  VOLANTE_MUTUA: 1
  CERTIFICADO_BANCARIO: 8

TARJETA_CUALIF_CONDUCTOR lleva tracks_expiry=True -- confirmado con
muestra real que lleva fecha de caducidad explicita en el nombre
("TARJETA CUALIF. DEL CONDUCTOR DIAZ QUINTERO, ANT. JESUS 30-7-2027"),
mismo patron que TACOGRAFO (migracion 0020).
"""
from django.db import migrations

NEW_TYPES = [
    {
        "code": "CLAUSULA_PROTECCION_DATOS",
        "label": "Cláusula de protección de datos",
        "domain": "PERSONAL",
        "family": "ADMINISTRATIVO",
        "tracks_expiry": False,
    },
    {
        "code": "CAMBIO_EMPRESA_SUBROGACION",
        "label": "Cambio de empresa / subrogación",
        "domain": "PERSONAL",
        "family": "LABORAL",
        "tracks_expiry": False,
    },
    {
        "code": "CAMBIO_IRPF",
        "label": "Cambio de retención IRPF",
        "domain": "PERSONAL",
        "family": "LABORAL",
        "tracks_expiry": False,
    },
    {
        "code": "TARJETA_CUALIF_CONDUCTOR",
        "label": "Tarjeta de cualificación del conductor (CAP)",
        "domain": "PERSONAL",
        "family": "CIRCULACION",
        "tracks_expiry": True,
    },
    {
        "code": "HUELLA_CONTRATO",
        "label": "Huella dactilar de contrato",
        "domain": "PERSONAL",
        "family": "LABORAL",
        "tracks_expiry": False,
    },
    {
        "code": "COMUNICADO_SEPE",
        "label": "Comunicado al SEPE",
        "domain": "PERSONAL",
        "family": "LABORAL",
        "tracks_expiry": False,
    },
    {
        "code": "VOLANTE_MUTUA",
        "label": "Volante de mutua",
        "domain": "PERSONAL",
        "family": "SALUD_BAJAS_PERSONA",
        "tracks_expiry": False,
    },
    {
        "code": "CERTIFICADO_BANCARIO",
        "label": "Certificado / extracto bancario",
        "domain": "PERSONAL",
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
        ("document_explorer", "0044_seed_cert_exencion_tacografo_s65"),
    ]

    operations = [
        migrations.RunPython(seed_new_types, unseed_new_types),
    ]
