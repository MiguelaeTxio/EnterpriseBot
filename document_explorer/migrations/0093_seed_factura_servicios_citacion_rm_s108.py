# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0093_seed_factura_servicios_citacion_rm_s108.py
"""
H35 (S108). Alta de 2 tipos documentales nuevos, decision explicita de
Miguel Angel al revisar el contenido real de 2 de los 25 IDs "sin
senal" de RECONOCIMIENTO_MEDICO de la hoja de ruta de S107.

FACTURA_SERVICIOS_PERSONAL: confirmado con muestra real (pk=28456,
BANDERA_DIAZ_YOLANDA_MARINA) -- el contenido real es una factura de
Medios de Prevencion Externos Sur S.L. (MPE) por "VS GESTION CUPO"
(37,12EUR), nunca un reconocimiento medico. Domain PERSONAL (vive en
la ficha de la persona a la que se factura el servicio, no es un
documento de empresa/maquina), family FINANCIERO. tracks_expiry False
(una factura no caduca). is_cumulative True: una persona puede tener
varias facturas de servicios reales a la vez, ninguna sustituye a la
anterior -- mismo criterio que FORMACION/EPIS.

CITACION_RECONOCIMIENTO_MEDICO: confirmado con muestra real (pk=35241,
DIAZ_QUINTERO_ANTONIO_JESUS) -- el contenido real es una carta de cita
("Estimados Sr: El proximo dia... esta citado en nuestro Centro
Medico... para la realizacion de las Evaluaciones de la Salud
Especificas por Riesgo"), nunca el resultado del reconocimiento.
Domain PERSONAL, family SALUD_BAJAS_PERSONA (mismo grupo que
RECONOCIMIENTO_MEDICO, id=7, por ser parte del mismo proceso).
tracks_expiry False (una citacion no tiene vigencia propia, queda
obsoleta en cuanto se realiza el reconocimiento real). is_cumulative
True: una persona puede tener varias citaciones reales a lo largo del
tiempo, cada una un hecho propio, ninguna sustituye a la anterior.
"""
from django.db import migrations

NEW_TYPES = [
    {
        "code": "FACTURA_SERVICIOS_PERSONAL",
        "label": "Factura de servicios (PRL/médicos) a nombre de un trabajador",
        "domain": "PERSONAL",
        "family": "FINANCIERO",
        "tracks_expiry": False,
        "is_cumulative": True,
    },
    {
        "code": "CITACION_RECONOCIMIENTO_MEDICO",
        "label": "Citación para reconocimiento médico",
        "domain": "PERSONAL",
        "family": "SALUD_BAJAS_PERSONA",
        "tracks_expiry": False,
        "is_cumulative": True,
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
                "is_cumulative": spec["is_cumulative"],
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
        ("document_explorer", "0092_documenttypecatalog_is_cumulative_s107"),
    ]

    operations = [
        migrations.RunPython(seed_new_types, unseed_new_types),
    ]
