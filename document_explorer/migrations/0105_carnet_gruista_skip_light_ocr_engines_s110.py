# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0105_carnet_gruista_skip_light_ocr_engines_s110.py
"""
H36 (S110). Activa `DocumentTypeCatalog.skip_light_ocr_engines` para
CARNET_GRUISTA. Decision directa de Miguel Angel, sin dry-run previo
-- mismo criterio que 0103 (CURSO): son fotocopias/escaneos oficiales
del mismo tipo de calidad que ya demostraron 100% de fallo de
Tesseract/EasyOCR en FORMACION (0101).

Con este flag activo, `extract_personal_dates_bulk_fast.py` salta
Tesseract/EasyOCR e invoca Cloud Vision directamente para
CARNET_GRUISTA -- usado aqui no solo para retipar candidatos
genericos, sino como auditoria de contenido real: cualquier documento
archivado bajo CARNET_GRUISTA cuyo contenido real dispare la senal de
otro tipo (FORMACION_*, etc.) sale a la luz y se retipa solo, sin
tener que revisar los 154 documentos activos uno a uno a mano.
"""
from django.db import migrations


def activate_skip_light_ocr_engines(apps, schema_editor):
    DocumentTypeCatalog = apps.get_model(
        "document_explorer", "DocumentTypeCatalog",
    )
    DocumentTypeCatalog.objects.filter(code="CARNET_GRUISTA").update(
        skip_light_ocr_engines=True,
    )


def revert_skip_light_ocr_engines(apps, schema_editor):
    DocumentTypeCatalog = apps.get_model(
        "document_explorer", "DocumentTypeCatalog",
    )
    DocumentTypeCatalog.objects.filter(code="CARNET_GRUISTA").update(
        skip_light_ocr_engines=False,
    )


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0104_fix_diaz_quintero_grua_hidraulica_s110"),
    ]

    operations = [
        migrations.RunPython(
            activate_skip_light_ocr_engines, revert_skip_light_ocr_engines,
        ),
    ]
