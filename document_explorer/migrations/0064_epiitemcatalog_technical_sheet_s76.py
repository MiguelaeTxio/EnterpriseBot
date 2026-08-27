# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0064_epiitemcatalog_technical_sheet_s76.py
"""
H31 (S76). Campo technical_sheet (FK a DocumentIndexEntry) en
EpiItemCatalog -- mismo patrón exacto que DocumentTypeCatalog.
current_template (H30 S69). Miguel Ángel, verbatim: la columna de
método de extracción ('heurística de nombre', etc.) en la ficha de
persona "es superflua [...] en vez de eso, si hay un manual de uso o
una ficha técnica, deberíamos presentar ahí un enlace al documento."
Nulo por defecto -- sin backfill, ningún EPI tiene manual/ficha
técnica subida todavía.
"""
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0063_personidentity_address_dates_s76"),
    ]

    operations = [
        migrations.AddField(
            model_name="epiitemcatalog",
            name="technical_sheet",
            field=models.ForeignKey(
                null=True,
                blank=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="technical_sheet_for_epis",
                to="document_explorer.documentindexentry",
                verbose_name="Manual de uso / ficha técnica",
                help_text=(
                    "H31 (S76). Un DocumentIndexEntry más (nunca un "
                    "archivo fuera del sistema) -- mismo patrón exacto "
                    "que DocumentTypeCatalog.current_template (H30 "
                    "S69). Nulo hasta que se suba el manual/ficha "
                    "técnica de ese EPI del catálogo."
                ),
            ),
        ),
    ]
