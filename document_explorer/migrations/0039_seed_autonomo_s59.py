# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0039_seed_autonomo_s59.py
"""
H30 (S59). Alta de 1 tipo documental nuevo: AUTONOMO.

---

H30 (S59). New document type: AUTONOMO.

Detectado al revisar la carpeta real `DOC. PERSONAL/PERSONAL/
ADMINISTRACION` (punto 2 de la hoja de ruta de S59): dominada por
recibos mensuales de cuota de autónomo de miembros de la propia
familia Álvarez (`AUTONOMO ADOLFO AGOSTO.pdf`, `Autonomo agosto 2021
Adelaida Alvarez.pdf`, `AUTONOMO ALBERTO ENERO 2011.pdf`...), sin
ningún tipo del catálogo cerrado que los cubra hoy.

Confirmado verbatim por Miguel Ángel en S59: "Sí, habría que crear
ese nuevo tipo de autónomo para controlar todos esos recibos."

- domain=PERSONAL (recibo de una persona concreta, nunca de una
  máquina).
- family=LABORAL, mismo criterio ya usado para NOMINA/PAGO_CORRIENTE
  (migración 0028): documento económico-laboral recurrente, no de
  identidad ni administrativo genérico.
- tracks_expiry=False: cada recibo es un mes concreto, no hay una
  versión "vigente" que sustituya a la anterior (mismo criterio que
  NOMINA/PAGO_CORRIENTE, nunca participan en vigencia_service.
  evaluate_substitution()).
"""
from django.db import migrations

NEW_TYPES = [
    {
        "code": "AUTONOMO",
        "label": "Recibo de cuota de autónomo",
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
        ("document_explorer", "0038_company_worksite"),
    ]

    operations = [
        migrations.RunPython(seed_new_types, unseed_new_types),
    ]
