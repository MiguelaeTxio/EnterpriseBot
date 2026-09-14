# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0085_seed_formacion_prl_generica_s105.py
"""
H35 (S105). Alta de 1 tipo documental nuevo, confirmado con muestra
real (segundo lote de 20 ficheros BAJA_PERSONAL de Jorge Ramirez
Garcia, DNI 53696300V, OCR Tesseract español) durante el punto 2 de
la hoja de ruta S105.

FORMACION_PRL_GENERICA: confirmado con 6 muestras reales de esta
sesion (pk=32753, 32754, 32757, 32762, 32763, 32764) -- cabecera
identica en las 6: "M.P.E. Servicio de Prevencion de Riesgos
Laborales. CERTIFICA: Que el trabajador que a continuacion se
relaciona perteneciente a [EMPRESA] ha recibido formacion e
informacion, en cumplimiento de los articulos 18 y 19, de la Ley de
Prevencion de Riesgos Laborales, por personal cualificado, referente
a la prevencion de riesgos laborales para [TEMA]".

Decision explicita de Miguel Angel (S105): las 6 muestras van a este
codigo nuevo independientemente de si el [TEMA] es maquinaria
(GRUA AUTOCARGANTE, GRUA MOVIL AUTOPROPULSADA, GRUA DE ASISTENCIA EN
CARRETERA -- 4 de las 6) u otro (TRABAJOS VERTICALES, PROXIMIDAD DE
INSTALACIONES ELECTRICAS -- 2 de las 6). El codigo ya existente
FORMACION_PRL_MAQUINARIA (migracion 0047) NO se reutiliza ni se
amplia -- queda reservado tal cual para si en el futuro aparece con
otro proveedor/formato distinto de esta cabecera M.P.E.

domain PERSONAL, family PRL_FORMACION (mismo grupo que
FORMACION_PRL_MAQUINARIA, por ser formacion/informacion PRL),
tracks_expiry False (certificado puntual fechado, sin version
"vigente" que sustituya a la anterior).
"""
from django.db import migrations

NEW_TYPES = [
    {
        "code": "FORMACION_PRL_GENERICA",
        "label": "Formación PRL genérica (certificado M.P.E.)",
        "domain": "PERSONAL",
        "family": "PRL_FORMACION",
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
        ("document_explorer", "0084_seed_autorizacion_generica_capacitacion_s105"),
    ]

    operations = [
        migrations.RunPython(seed_new_types, unseed_new_types),
    ]
