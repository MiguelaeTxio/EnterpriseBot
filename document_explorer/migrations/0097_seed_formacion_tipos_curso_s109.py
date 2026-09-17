# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0097_seed_formacion_tipos_curso_s109.py
"""
H31 (S109), punto 2. Desdobla el tipo genérico "FORMACION" en 14
tipos documentales por curso real -- mismo patrón ya existente en el
catálogo (FORMACION_ITC_MINERA, FORMACION_PRL_GENERICA,
FORMACION_PRL_MAQUINARIA conviven con FORMACION desde antes de esta
sesión). Confirmado contra el Excel real de Miguel Ángel
("CURSOS TRABAJADORES GRUAS"), que ya mantiene estas 14 columnas fijas
como catálogo cerrado de cursos -- decisión tomada con esa evidencia,
nunca a ciegas.

Mismos criterios que FORMACION (domain PERSONAL, family PRL_FORMACION,
tracks_expiry True -- "puede tener o no fecha de caducidad", mismo
criterio confirmado en 0019_tracks_expiry_round_2; is_cumulative True
-- una persona puede tener varios cursos distintos vigentes a la vez,
mismo criterio que 0092).

Solo altas de catálogo -- el retipado de los documentos históricos
que hoy llevan el código genérico FORMACION es tarea aparte (ver
directriz 4.22 del documento maestro, añadida en esta misma sesión),
en curso durante S109 pero fuera del alcance de esta migración.
"""
from django.db import migrations

NEW_TYPES = [
    {
        "code": "FORMACION_EXTINCION_INCENDIOS",
        "label": "Formación extinción de incendios (4H)",
    },
    {
        "code": "FORMACION_ELECTRICIDAD",
        "label": "Formación electricidad (4H o 6H)",
    },
    {
        "code": "FORMACION_SUBESTACIONES",
        "label": "Formación subestaciones (6H)",
    },
    {
        "code": "FORMACION_PRIMEROS_AUXILIOS",
        "label": "Formación primeros auxilios",
    },
    {
        "code": "FORMACION_OPERADOR_CAMION_AUTOCARGANTE",
        "label": "Formación operador de camión autocargante",
    },
    {
        "code": "FORMACION_TRABAJOS_ALTURA",
        "label": "Formación trabajos en altura",
    },
    {
        "code": "FORMACION_PLATAFORMA_ELEVADORA",
        "label": "Formación plataforma elevadora",
    },
    {
        "code": "FORMACION_PRL_ART_18_19",
        "label": "Formación PRL Art. 18 y 19",
    },
    {
        "code": "FORMACION_OPERADOR_APARATOS_ELEVACION",
        "label": "Formación operador de aparatos de elevación",
    },
    {
        "code": "FORMACION_PRL_60H",
        "label": "Formación PRL (60H)",
    },
    {
        "code": "FORMACION_OPERADOR_MINIGRUA",
        "label": "Formación operador de minigrúa",
    },
    {
        "code": "FORMACION_CARRETILLAS_TRASPALETAS",
        "label": "Formación carretillas elevadoras y transpaletas",
    },
    {
        "code": "FORMACION_GRUAS_ASISTENCIA_CARRETERA",
        "label": "Formación grúas de asistencia en carretera",
    },
    {
        "code": "FORMACION_GRUA_HIDRAULICA_ARTICULADA",
        "label": "Formación operador de grúa hidráulica articulada",
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
                "domain": "PERSONAL",
                "family": "PRL_FORMACION",
                "tracks_expiry": True,
                "is_cumulative": True,
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
        ("document_explorer", "0096_persongrouptemplate_s109"),
    ]

    operations = [
        migrations.RunPython(seed_new_types, unseed_new_types),
    ]
