# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0076_documenttag_s98.py
"""
H31 (S98). Solo esquema -- crea `DocumentTag` y el M2M
`DocumentTypeCatalog.tags`, ambos vacios. Decision explicita de
Miguel Angel: la propuesta real de etiquetas (que codigos de
DocumentTypeCatalog lleva cada una) se revisa primero fuera de
migracion, igual que se hizo con el propio renombrado canonico --
nunca se puebla un dato real sin que la revise antes. Ver
`DocumentTag` en `models.py` para el detalle completo del diseno.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0075_reenganchar_poliza_rc_grupo_s96"),
    ]

    operations = [
        migrations.CreateModel(
            name="DocumentTag",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "code",
                    models.CharField(
                        max_length=40,
                        unique=True,
                        verbose_name="Código",
                    ),
                ),
                (
                    "label",
                    models.CharField(
                        max_length=100,
                        verbose_name="Nombre visible",
                    ),
                ),
            ],
            options={
                "verbose_name": "Etiqueta de búsqueda",
                "verbose_name_plural": "Etiquetas de búsqueda",
                "ordering": ["label"],
            },
        ),
        migrations.AddField(
            model_name="documenttypecatalog",
            name="tags",
            field=models.ManyToManyField(
                blank=True,
                related_name="document_types",
                to="document_explorer.documenttag",
                verbose_name="Etiquetas de búsqueda",
            ),
        ),
    ]
