# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0121_personidentity_phone_secondary_professional_category_s113.py
"""
H31 (S113). Añade dos campos de texto libre a `PersonIdentity`,
petición explícita de Miguel Ángel:

- `phone_secondary`: segundo teléfono (trabajo/personal), complementa
  a `phone` sin que el esquema distinga cuál es cuál.
- `professional_category`: categoría profesional de referencia de la
  ficha, rellenada a mano -- la categoría que trae algún documento no
  siempre coincide con la del contrato, así que este campo es el
  valor único a mantener, nunca extraído automáticamente.

Solo esquema, ninguna fila sembrada -- ambas columnas quedan vacías
para el histórico ya existente.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0120_documentindexentry_prorroga_de_periodo_s111"),
    ]

    operations = [
        migrations.AddField(
            model_name="personidentity",
            name="phone_secondary",
            field=models.CharField(
                blank=True, max_length=30, verbose_name="Segundo teléfono",
            ),
        ),
        migrations.AddField(
            model_name="personidentity",
            name="professional_category",
            field=models.CharField(
                blank=True, max_length=150,
                verbose_name="Categoría profesional",
            ),
        ),
    ]
