# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0040_seed_cert_limitaciones_s60.py
"""
H30 (S60). Alta de 1 tipo documental nuevo: CERT_LIMITACIONES.

---

H30 (S60). New document type: CERT_LIMITACIONES.

Detectado al calibrar el patron nuevo de RECONOCIMIENTO_MEDICO contra
un ejemplo SIN_PATRON real
(`DOC. PERSONAL/RECONOCIMIENTOS MEDICOS/RM 2016/CERT.LIMITACIONES RM
Perez Fernandez 2-3-16.pdf`): no es un examen de aptitud (no tiene
APTO/NO APTO ni la estructura de un RM real), es una declaracion del
administrador (Adolfo Alvarez) de que un trabajador con limitaciones
medicas va a usar los EPIs recomendados por el medico.

Confirmado por Miguel Angel en S60: se indexa como tipo documental
nuevo, no como RECONOCIMIENTO_MEDICO.

- domain=PERSONAL (declaracion sobre un trabajador concreto).
- family=SALUD_BAJAS_PERSONA, mismo criterio que RECONOCIMIENTO_MEDICO
  (migracion 0028): vinculado a la salud/limitaciones de la persona,
  no laboral generico ni identidad.
- tracks_expiry=False, mismo criterio que RECONOCIMIENTO_MEDICO/
  AUTONOMO: es una declaracion puntual fechada, no hay una version
  "vigente" que sustituya a la anterior via vigencia_service.
  evaluate_substitution().
"""
from django.db import migrations

NEW_TYPES = [
    {
        "code": "CERT_LIMITACIONES",
        "label": "Certificado de limitaciones médicas / uso de EPIs",
        "domain": "PERSONAL",
        "family": "SALUD_BAJAS_PERSONA",
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
        ("document_explorer", "0039_seed_autonomo_s59"),
    ]

    operations = [
        migrations.RunPython(seed_new_types, unseed_new_types),
    ]
