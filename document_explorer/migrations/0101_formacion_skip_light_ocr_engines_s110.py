# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0101_formacion_skip_light_ocr_engines_s110.py
"""
H36 (S110). Activa `DocumentTypeCatalog.skip_light_ocr_engines` para
FORMACION, mismo mecanismo introducido en 0088 (H35, S106) para
AUTONOMO -- Tesseract (PSM automatico + PSM 6) y EasyOCR nunca
resuelven nada para este tipo, solo Cloud Vision lo hace.

Evidencia real, campaña --apply en curso de esta misma sesion contra
extract_personal_dates_bulk.py (no un dry-run de muestra reducida,
la propia campana real ya lo demuestra): 6 de 6 primeros documentos
FORMACION agotaron los 4 motores (Tesseract PSM automatico -> PSM 6
-> EasyOCR -> Cloud Vision) sin que ninguno de los tres primeros
resolviera una sola vez, cada uno tardando varios minutos
(EasyOCR en particular, ~3-4 min por documento) antes de caer a
Cloud Vision, que SI resuelve los 6/6. Mismo patron exacto que motivo
0088 para AUTONOMO (10/10 en su dry-run). Relanzar la cascada
completa sobre los ~830 documentos en alcance habria supuesto decenas
de horas de intentos locales sin ningun valor -- confirmado en
caliente por Miguel Angel, que corto la campana al ver el patron
repetirse sin excepcion.

Con este flag activo, `extract_personal_dates_bulk_fast.py` salta
Tesseract/EasyOCR e invoca Cloud Vision directamente para FORMACION
-- la fecha y el tipo resueltos se escriben con normalidad, sin el
descarte que aplicaria `ocr_unreliable` (campo distinto, ver 0088).
"""
from django.db import migrations


def activate_skip_light_ocr_engines(apps, schema_editor):
    DocumentTypeCatalog = apps.get_model(
        "document_explorer", "DocumentTypeCatalog",
    )
    DocumentTypeCatalog.objects.filter(code="FORMACION").update(
        skip_light_ocr_engines=True,
    )


def revert_skip_light_ocr_engines(apps, schema_editor):
    DocumentTypeCatalog = apps.get_model(
        "document_explorer", "DocumentTypeCatalog",
    )
    DocumentTypeCatalog.objects.filter(code="FORMACION").update(
        skip_light_ocr_engines=False,
    )


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0100_jobposition_personidentity_job_position_s109"),
    ]

    operations = [
        migrations.RunPython(
            activate_skip_light_ocr_engines, revert_skip_light_ocr_engines,
        ),
    ]
