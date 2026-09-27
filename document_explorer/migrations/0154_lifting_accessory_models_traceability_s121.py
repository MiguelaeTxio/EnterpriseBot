# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0154_lifting_accessory_models_traceability_s121.py
"""
H30 (S121). Catálogo de MODELOS de accesorio de elevación y
trazabilidad por unidad.

Decisión de Miguel Ángel (S121, opción 1): se entrega eligiendo el
modelo (p. ej. "Poliéster plana 2 t × 3 m"), la cantidad, el centro de
gasto y la persona; el sistema propone las unidades del almacén y el
supervisor las confirma según sus etiquetas. La etiqueta de una eslinga
lleva el CÓDIGO DE TRAZABILIDAD (EN 1492-1), no el nº de certificado:
se guarda en cada unidad tal como viene impreso en su certificado.

Solo esquema; los 13 modelos y la asignación de modelo/trazabilidad a
los 259 accesorios los hace el comando backfill_lifting_accessories_s121
(datos revisados sobre el contenido real de cada certificado).
"""
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        (
            "document_explorer",
            "0153_tipo_componente_maquina_eslinga_redonda_s121",
        ),
    ]

    operations = [
        migrations.CreateModel(
            name="LiftingAccessoryModel",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "name",
                    models.CharField(
                        help_text="P. ej. 'Poliéster plana 2 t × 3 m'.",
                        max_length=150,
                        verbose_name="Modelo",
                    ),
                ),
                (
                    "dimensions",
                    models.CharField(
                        blank=True, max_length=100, verbose_name="Medidas",
                    ),
                ),
                (
                    "working_load_kg",
                    models.PositiveIntegerField(
                        blank=True, null=True,
                        verbose_name="Carga de trabajo (kg)",
                    ),
                ),
                (
                    "standard",
                    models.CharField(
                        blank=True, max_length=100, verbose_name="Norma",
                    ),
                ),
                (
                    "display_order",
                    models.PositiveSmallIntegerField(
                        default=0, verbose_name="Orden",
                    ),
                ),
                (
                    "is_active",
                    models.BooleanField(default=True, verbose_name="Activo"),
                ),
                (
                    "created_at",
                    models.DateTimeField(
                        auto_now_add=True, verbose_name="Fecha de alta",
                    ),
                ),
                (
                    "accessory_type",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="models",
                        to="document_explorer.liftingaccessorytype",
                        verbose_name="Tipo",
                    ),
                ),
            ],
            options={
                "verbose_name": "Modelo de accesorio de elevación",
                "verbose_name_plural": "Modelos de accesorio de elevación",
                "ordering": ["display_order", "name"],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("accessory_type", "name"),
                        name="unique_lifting_model_name_per_type",
                    ),
                ],
            },
        ),
        migrations.AddField(
            model_name="liftingaccessory",
            name="model",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="accessories",
                to="document_explorer.liftingaccessorymodel",
                verbose_name="Modelo",
            ),
        ),
        migrations.AddField(
            model_name="liftingaccessory",
            name="traceability",
            field=models.CharField(
                blank=True,
                help_text=(
                    "Tal como viene impreso en el certificado (puede ser de "
                    "unidad o de lote). Se muestra junto al nº de "
                    "certificado para localizar la eslinga por su etiqueta."
                ),
                max_length=100,
                verbose_name="Nº de trazabilidad",
            ),
        ),
    ]
