# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0052_epiitemcatalog_replacement_cost_une_en_s72.py
"""
H30 (S72). Dos campos nuevos en EpiItemCatalog, confirmados por Miguel
Angel en S71: coste de reposicion (importe, nulo) y norma UNE-EN
(texto, nulo). El segundo motivado por ENTREGA_EPIS_GRUISTA_2026.docx,
que trae la norma UNE-EN incrustada por item.

Ambos campos nulos por diseno (null=True, blank=True) -- no requieren
default sobre EpiItemCatalog, que en S71 se confirmo vacia (0 filas)
en produccion.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0051_document_acknowledgment_s69"),
    ]

    operations = [
        migrations.AddField(
            model_name="epiitemcatalog",
            name="replacement_cost",
            field=models.DecimalField(
                max_digits=8,
                decimal_places=2,
                null=True,
                blank=True,
                verbose_name="Coste de reposición",
                help_text=(
                    "Importe de reposición del EPI, en euros. Nulo "
                    "hasta tener dato real confirmado (S71/S72)."
                ),
            ),
        ),
        migrations.AddField(
            model_name="epiitemcatalog",
            name="une_en_standard",
            field=models.CharField(
                max_length=100,
                null=True,
                blank=True,
                verbose_name="Norma UNE-EN",
                help_text=(
                    "Norma UNE-EN aplicable al EPI (p. ej. 'UNE-EN "
                    "397'). Nulo hasta tener dato real confirmado "
                    "(S71/S72, motivado por "
                    "ENTREGA_EPIS_GRUISTA_2026.docx)."
                ),
            ),
        ),
    ]
