# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0066_documentindexentry_ocr_text_s78.py
"""
H30 (S78). Cache de texto OCR en `DocumentIndexEntry.ocr_text` --
Miguel Ángel, pregunta real de sesión: si el barrido de hoy solo buscó
fecha, ¿hay que repetir descarga+OCR de cada documento por cada campo
nuevo que se quiera extraer más adelante (número de DNI, categorías
de permiso, número de tarjeta...)? Sin este campo, sí -- cada pasada
de extracción sería un barrido OCR completo nuevo, repitiendo el coste
de VM ya pagado hoy. Con este campo, el texto se guarda una vez y
cualquier extracción futura de campos adicionales se hace contra el
texto ya cacheado, instantáneo, sin volver a tocar GCS ni Tesseract.
Vacío por defecto -- sin backfill retroactivo del texto OCR ya perdido
en el barrido de hoy (ese habría que repetirlo si se quiere cachear
también, decisión aparte).
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0065_remove_epiitemcatalog_technical_sheet_s76"),
    ]

    operations = [
        migrations.AddField(
            model_name="documentindexentry",
            name="ocr_text",
            field=models.TextField(
                blank=True, verbose_name="Texto OCR cacheado",
            ),
        ),
    ]
