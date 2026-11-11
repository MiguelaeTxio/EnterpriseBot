# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/supplier_invoices/migrations/0001_initial.py
# H28 (S151, sesión invasora): facturas de proveedor de la carpeta
# FACTURACIÓN de la bandeja de entrada. Solo esquema, ninguna fila.

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("document_explorer", "0213_machinealertrule_s148"),
        ("ivr_config", "0057_role_sales_s148"),
        ("spare_parts", "0017_sync_state_s120"),
        (
            "work_order_processor",
            "0037_workorderentry_is_intensive_shift_s139",
        ),
    ]

    operations = [
        migrations.CreateModel(
            name="SupplierInvoice",
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
                    "sha256",
                    models.CharField(
                        db_index=True,
                        max_length=64,
                        verbose_name="Huella SHA-256",
                    ),
                ),
                (
                    "original_name",
                    models.CharField(
                        max_length=255, verbose_name="Nombre del archivo"
                    ),
                ),
                (
                    "content_type",
                    models.CharField(
                        blank=True, max_length=100, verbose_name="Tipo MIME"
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("PENDING", "En cola"),
                            ("PROCESSING", "Procesando"),
                            ("PROCESSED", "Procesada"),
                            ("DUPLICATE", "Factura repetida"),
                            ("NOT_INVOICE", "No es una factura"),
                            ("ERROR", "Error"),
                        ],
                        default="PENDING",
                        max_length=12,
                        verbose_name="Estado",
                    ),
                ),
                (
                    "reason",
                    models.TextField(blank=True, verbose_name="Resultado"),
                ),
                (
                    "extraction",
                    models.JSONField(
                        blank=True,
                        default=dict,
                        verbose_name="Lectura de Gemini",
                    ),
                ),
                (
                    "supplier_name",
                    models.CharField(
                        blank=True, max_length=255, verbose_name="Proveedor"
                    ),
                ),
                (
                    "supplier_tax_id",
                    models.CharField(
                        blank=True,
                        max_length=50,
                        verbose_name="NIF/CIF proveedor",
                    ),
                ),
                (
                    "invoice_number",
                    models.CharField(
                        blank=True,
                        max_length=100,
                        verbose_name="Número de factura",
                    ),
                ),
                (
                    "invoice_date",
                    models.DateField(
                        blank=True, null=True, verbose_name="Fecha de factura"
                    ),
                ),
                (
                    "total_amount",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        max_digits=12,
                        null=True,
                        verbose_name="Importe total",
                    ),
                ),
                (
                    "lines_count",
                    models.PositiveIntegerField(
                        default=0, verbose_name="Líneas"
                    ),
                ),
                (
                    "covered_count",
                    models.PositiveIntegerField(
                        default=0, verbose_name="Con albarán"
                    ),
                ),
                (
                    "purchased_count",
                    models.PositiveIntegerField(
                        default=0, verbose_name="Compradas sin albarán"
                    ),
                ),
                (
                    "placed_count",
                    models.PositiveIntegerField(
                        default=0, verbose_name="Colocadas según partes"
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(
                        auto_now_add=True, verbose_name="Subida el"
                    ),
                ),
                (
                    "processed_at",
                    models.DateTimeField(
                        blank=True, null=True, verbose_name="Procesada el"
                    ),
                ),
                (
                    "company",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="supplier_invoices",
                        to="ivr_config.company",
                        verbose_name="Empresa",
                    ),
                ),
                (
                    "duplicate_of",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="duplicates",
                        to="supplier_invoices.supplierinvoice",
                        verbose_name="Repetida de",
                    ),
                ),
                (
                    "entry",
                    models.OneToOneField(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="supplier_invoice",
                        to="document_explorer.documentindexentry",
                        verbose_name="Archivo de la factura",
                    ),
                ),
                (
                    "supplier",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="invoices",
                        to="spare_parts.supplier",
                        verbose_name="Proveedor (resuelto por CIF)",
                    ),
                ),
                (
                    "uploaded_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="supplier_invoices",
                        to="ivr_config.companyuser",
                        verbose_name="Subida por",
                    ),
                ),
            ],
            options={
                "verbose_name": "Factura de proveedor",
                "verbose_name_plural": "Facturas de proveedor",
                "ordering": ["-created_at", "-pk"],
            },
        ),
        migrations.CreateModel(
            name="SupplierInvoiceLine",
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
                    "line_number",
                    models.PositiveIntegerField(verbose_name="Línea"),
                ),
                (
                    "reference",
                    models.CharField(
                        blank=True, max_length=100, verbose_name="Referencia"
                    ),
                ),
                (
                    "description",
                    models.CharField(
                        blank=True, max_length=255, verbose_name="Descripción"
                    ),
                ),
                (
                    "quantity",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        max_digits=10,
                        null=True,
                        verbose_name="Cantidad",
                    ),
                ),
                (
                    "unit_price",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        max_digits=10,
                        null=True,
                        verbose_name="Precio unitario",
                    ),
                ),
                (
                    "total_price",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        max_digits=12,
                        null=True,
                        verbose_name="Importe de la línea",
                    ),
                ),
                (
                    "delivery_number_raw",
                    models.CharField(
                        blank=True,
                        max_length=100,
                        verbose_name="Albarán citado en la factura",
                    ),
                ),
                (
                    "delivery_date",
                    models.DateField(
                        blank=True,
                        null=True,
                        verbose_name="Fecha del albarán citado",
                    ),
                ),
                (
                    "is_spare_part",
                    models.BooleanField(
                        default=True, verbose_name="Es un repuesto"
                    ),
                ),
                (
                    "outcome",
                    models.CharField(
                        choices=[
                            ("PENDING", "Sin procesar"),
                            ("COVERED", "Ya tenía albarán"),
                            (
                                "PURCHASED",
                                "Comprada sin albarán, entrada en almacén",
                            ),
                            (
                                "NO_QUANTITY",
                                "Sin cantidad legible, no entra en almacén",
                            ),
                            ("NOT_PART", "No es un repuesto"),
                        ],
                        default="PENDING",
                        max_length=12,
                        verbose_name="Destino",
                    ),
                ),
                (
                    "placed_quantity",
                    models.DecimalField(
                        decimal_places=2,
                        default=0,
                        max_digits=10,
                        verbose_name="Cantidad colocada según partes",
                    ),
                ),
                (
                    "delivery_note_line",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="invoice_lines",
                        to="spare_parts.deliverynoteline",
                        verbose_name="Línea de albarán que la cubre",
                    ),
                ),
                (
                    "invoice",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="lines",
                        to="supplier_invoices.supplierinvoice",
                        verbose_name="Factura",
                    ),
                ),
                (
                    "spare_part_entry",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="invoice_lines",
                        to="spare_parts.sparepartentry",
                        verbose_name="Repuesto del almacén",
                    ),
                ),
                (
                    "stock_movement",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="invoice_lines",
                        to="spare_parts.stockmovement",
                        verbose_name="Entrada en almacén",
                    ),
                ),
            ],
            options={
                "verbose_name": "Línea de factura de proveedor",
                "verbose_name_plural": "Líneas de facturas de proveedor",
                "ordering": ["invoice", "line_number"],
            },
        ),
        migrations.CreateModel(
            name="SupplierInvoicePlacement",
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
                    "quantity",
                    models.DecimalField(
                        decimal_places=2,
                        max_digits=10,
                        verbose_name="Cantidad",
                    ),
                ),
                (
                    "quantity_assumed",
                    models.BooleanField(
                        default=False,
                        help_text=(
                            "El parte no indicaba unidades: se ha "
                            "contado 1."
                        ),
                        verbose_name="Cantidad supuesta",
                    ),
                ),
                (
                    "match_kind",
                    models.CharField(
                        choices=[
                            ("REFERENCE", "Por referencia"),
                            ("DESCRIPTION", "Por descripción"),
                        ],
                        max_length=12,
                        verbose_name="Coincidencia",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "invoice_line",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="placements",
                        to="supplier_invoices.supplierinvoiceline",
                        verbose_name="Línea de factura",
                    ),
                ),
                (
                    "spare_part_line",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="invoice_placement",
                        to="work_order_processor.sparepartline",
                        verbose_name="Línea de repuesto del parte",
                    ),
                ),
                (
                    "stock_movement",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="invoice_placements",
                        to="spare_parts.stockmovement",
                        verbose_name="Salida de almacén",
                    ),
                ),
            ],
            options={
                "verbose_name": "Colocación según parte",
                "verbose_name_plural": "Colocaciones según partes",
                "ordering": ["invoice_line", "pk"],
            },
        ),
    ]
