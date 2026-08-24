# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0047_seed_s65_tercer_lote.py
"""
H30 (S65). Tercer lote, mismo barrido del listado completo de 599
archivos con nombre real (EnterpriseBot_026_GET.txt), medido contra
volumen real antes de aplicar (EnterpriseBot_029_GET.txt).

Volumen real medido:
  LISTADO_PERSONAL_MAQUINARIA_OBRA: 29
  FORMACION_PRL_MAQUINARIA: 18
  ENTREGA_MOVIL: 3

LISTADO_PERSONAL_MAQUINARIA_OBRA va con domain=COMPANY -- son listados
agregados de trabajadores/maquinaria por obra concreta ("RELACION DE
TRABAJADORES (GR) EMTE...", "LISTADO DE MAQUINARIA GRUPO ALVAREZ Spa
La Viñuela..."), nunca de una sola persona, aunque vivan bajo el arbol
DOC. PERSONAL/LISTADOS MAQUINARIA Y PERSONAL. Mismo criterio que
DECLARACION_EMPRESA y CIRCULAR_INFORMATIVA (migracion 0046).
"""
from django.db import migrations

NEW_TYPES = [
    {
        "code": "LISTADO_PERSONAL_MAQUINARIA_OBRA",
        "label": "Relación de trabajadores/maquinaria por obra",
        "domain": "COMPANY",
        "family": "ADMINISTRATIVO",
        "tracks_expiry": False,
    },
    {
        "code": "FORMACION_PRL_MAQUINARIA",
        "label": "Formación PRL de maquinaria (camión/grúa autopropulsada)",
        "domain": "PERSONAL",
        "family": "PRL_FORMACION",
        "tracks_expiry": False,
    },
    {
        "code": "ENTREGA_MOVIL",
        "label": "Entrega de teléfono móvil",
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
        ("document_explorer", "0046_seed_s65_segundo_lote"),
    ]

    operations = [
        migrations.RunPython(seed_new_types, unseed_new_types),
    ]
