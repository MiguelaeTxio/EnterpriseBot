# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0086_seed_recurso_preventivo_s105.py
"""
H35 (S105). Alta de 1 tipo documental nuevo, confirmado con muestra
real (tercer lote, resto de los 89 BAJA_PERSONAL de Jorge Ramirez
Garcia, DNI 53696300V, OCR Tesseract español) durante el punto 2 de
la hoja de ruta S105.

RECURSO_PREVENTIVO: confirmado con 2 muestras reales (pk=32786,
32787) -- "DESIGNACION DE RECURSO PREVENTIVO. En [ciudad] a [fecha]
... Sr. D. [nombre] con DNI... Tanto la Ley 54/03 como el RD 171/04
incorporan medidas de prevencion a traves de la designacion -- por
parte de la empresa [EMPRESA] -- de un trabajador especialmente
designado...". Coincide letra por letra con la hipotesis del anexo
H35 S104.

domain PERSONAL, family PRL_FORMACION (mismo grupo que
FORMACION_PRL_GENERICA/FORMACION_PRL_MAQUINARIA, por ser una
designacion PRL), tracks_expiry False (designacion puntual fechada,
mismo criterio que AUTORIZACION_GENERICA/CAPACITACION -- no hay
"version vigente" que sustituya automaticamente a la anterior via
vigencia_service).

De paso, en el mismo commit se anaden a personal_content_
classification.py los signals de 2 codigos que YA existian en el
catalogo pero sin entrada de contenido todavia -- TACOGRAFO
(migracion 0004) y TARJETA_CUALIF_CONDUCTOR (migracion 0045) --
confirmados y diferenciados con muestra real de este mismo lote
(pk=32835/42316 "TARJETA DE CONDUCTOR" vs pk=32833 "TARJETA DE
CUALIFICACION DEL CONDUCTOR", frases sin solape entre si), y EPIS
(migracion 0004) -- confirmado con pk=42128/41145 "ENTREGA DE EPI'S".
"""
from django.db import migrations

NEW_TYPES = [
    {
        "code": "RECURSO_PREVENTIVO",
        "label": "Designación de recurso preventivo",
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
        ("document_explorer", "0085_seed_formacion_prl_generica_s105"),
    ]

    operations = [
        migrations.RunPython(seed_new_types, unseed_new_types),
    ]
