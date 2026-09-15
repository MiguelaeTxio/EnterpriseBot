# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0088_documenttypecatalog_skip_light_ocr_engines_s106.py
"""
H35 (S106). Añade DocumentTypeCatalog.skip_light_ocr_engines.

Distinto de `ocr_unreliable` (que exige razonamiento de Gemini
Vision y descarta la fecha resuelta por este script standalone):
este campo únicamente indica que, para un tipo concreto, una muestra
real ya demostró que los motores OCR locales (Tesseract, EasyOCR)
nunca resuelven nada, así que `extract_personal_dates_bulk_fast.py`
va directo a Cloud Vision sin gastar tiempo en intentos locales sin
ningún valor -- ver docstring completo del campo en models.py.

Origen real: dry-run de 10 documentos AUTONOMO (S106), 10/10
agotaron los 4 motores hasta Cloud Vision, ninguno resuelto por
Tesseract/EasyOCR.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0087_personidentity_avatar_document_s105"),
    ]

    operations = [
        migrations.AddField(
            model_name="documenttypecatalog",
            name="skip_light_ocr_engines",
            field=models.BooleanField(
                default=False,
                verbose_name="Saltar motores OCR locales (H35, S106)",
            ),
        ),
    ]
