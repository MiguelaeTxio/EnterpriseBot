# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0108_itc_minera_prl_maquinaria_skip_light_ocr_engines_s110.py
"""
H36 (S110). Activa skip_light_ocr_engines para FORMACION_ITC_MINERA
(5 activos) y FORMACION_PRL_MAQUINARIA (22 activos) -- mismos
certificados escaneados que ya demostraron 100% de fallo de
Tesseract/EasyOCR en el resto de tipos de FORMACION_* de esta sesion.
Decision directa, sin dry-run.
"""
from django.db import migrations

CODES = ["FORMACION_ITC_MINERA", "FORMACION_PRL_MAQUINARIA"]


def activate(apps, schema_editor):
    DocumentTypeCatalog = apps.get_model(
        "document_explorer", "DocumentTypeCatalog",
    )
    DocumentTypeCatalog.objects.filter(code__in=CODES).update(
        skip_light_ocr_engines=True,
    )


def revert(apps, schema_editor):
    DocumentTypeCatalog = apps.get_model(
        "document_explorer", "DocumentTypeCatalog",
    )
    DocumentTypeCatalog.objects.filter(code__in=CODES).update(
        skip_light_ocr_engines=False,
    )


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0107_fix_castilla_navarro_pacto_permanencia_s110"),
    ]

    operations = [
        migrations.RunPython(activate, revert),
    ]
