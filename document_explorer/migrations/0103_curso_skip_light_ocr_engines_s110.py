# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0103_curso_skip_light_ocr_engines_s110.py
"""
H36 (S110). Activa `DocumentTypeCatalog.skip_light_ocr_engines` para
CURSO. A diferencia de 0101 (FORMACION), aqui NO hay un dry-run de
muestra real previo que lo confirme documento a documento -- decision
directa de Miguel Angel, verbatim en esta sesion: "Directamente solo
con CGV [...] Por lo que cuesta, ahorramos mucho tiempo", visto que
CURSO son certificados escaneados del mismo tipo exacto (DIPLOMA /
CERTIFICADO DE APROVECHAMIENTO) que ya demostraron 100% de fallo de
Tesseract/EasyOCR bajo FORMACION en esta misma sesion (0101).

Con este flag activo, `extract_personal_dates_bulk_fast.py` salta
Tesseract/EasyOCR e invoca Cloud Vision directamente para CURSO.
"""
from django.db import migrations


def activate_skip_light_ocr_engines(apps, schema_editor):
    DocumentTypeCatalog = apps.get_model(
        "document_explorer", "DocumentTypeCatalog",
    )
    DocumentTypeCatalog.objects.filter(code="CURSO").update(
        skip_light_ocr_engines=True,
    )


def revert_skip_light_ocr_engines(apps, schema_editor):
    DocumentTypeCatalog = apps.get_model(
        "document_explorer", "DocumentTypeCatalog",
    )
    DocumentTypeCatalog.objects.filter(code="CURSO").update(
        skip_light_ocr_engines=False,
    )


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0102_merge_prl_generica_en_art_18_19_s110"),
    ]

    operations = [
        migrations.RunPython(
            activate_skip_light_ocr_engines, revert_skip_light_ocr_engines,
        ),
    ]
