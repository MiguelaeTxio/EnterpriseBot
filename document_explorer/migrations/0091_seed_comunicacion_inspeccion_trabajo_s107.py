# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0091_seed_comunicacion_inspeccion_trabajo_s107.py
"""
H35 (S107). Alta de 1 tipo documental nuevo, confirmado con muestra
real (2 documentos idénticos, pk=28255/28256, N/REF: 29/0117186/21,
FECHA: 25/10/2021, bajo la ficha de Grana Alvarez, Paloma) durante el
barrido de "sin senal" de BAJA_PERSONAL heredado de S105.

COMUNICACION_INSPECCION_TRABAJO: comunicacion oficial real del
Organismo Estatal Inspeccion de Trabajo y Seguridad Social a la
empresa, notificando resultados de un "Plan de Choque contra el
fraude en la contratacion temporal" y requiriendo la conversion a
fijo de plantilla de trabajadores concretos. Cabecera identificativa:
"COMUNICACION" + "ORGANISMO ESTATAL INSPECCION DE TRABAJO Y SEGURIDAD
SOCIAL" + "N/REF:". Distinto de COMUNICACION_CONTRATO (esa es la
empresa comunicando UN contrato al SEPE, esta es la Inspeccion
comunicando a la empresa un requerimiento sobre varios).

domain PERSONAL (el documento afecta a un trabajador concreto
nombrado en la comunicacion, aunque vaya dirigido formalmente a la
empresa), family LABORAL (mismo grupo que COMUNICACION_CONTRATO/
COMUNICADO_SEPE, comunicaciones oficiales de caracter laboral),
tracks_expiry False (comunicacion puntual fechada, sin version
"vigente" que sustituya a la anterior).
"""
from django.db import migrations

NEW_TYPES = [
    {
        "code": "COMUNICACION_INSPECCION_TRABAJO",
        "label": "Comunicación de la Inspección de Trabajo",
        "domain": "PERSONAL",
        "family": "LABORAL",
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
        ("document_explorer", "0090_remove_personaldossiertemplate_output_format_s106"),
    ]

    operations = [
        migrations.RunPython(seed_new_types, unseed_new_types),
    ]
