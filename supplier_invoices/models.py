# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/supplier_invoices/models.py
"""
Supplier invoices uploaded by Ani's agent (warehouse pipeline).

---

H28 (S151, sesión invasora). Facturas de proveedor (pagadas) que el
agente de facturas del PC de Ani sube al cubo, a FACTURACION
PROVEEDORES (carpeta propia, separada de cualquier otra). Tarea de
Miguel Ángel, tal cual: el pipeline del almacén procesa cada factura
que entra, extrae sus repuestos (referencia, descripción, cantidad,
precio, proveedor, fecha), los coteja con los albaranes subidos desde
el pipeline de albaranes del taller para no duplicar, da por comprados
los que no tienen albarán, pone al día el almacén con ellos y lo
coteja con los partes de trabajo para saber lo que se ha colocado y lo
que no, en la medida de lo posible. Al terminar, la factura pasa a la
subcarpeta de procesadas.

- `SupplierInvoice`: la factura (su archivo en el índice, lo leído y
  el resultado).
- `SupplierInvoiceLine`: cada línea y su destino (cubierta por un
  albarán, comprada y entrada en almacén, o que no es un repuesto).
- `SupplierInvoicePlacement`: una línea de repuesto de un parte de
  trabajo que se ha dado por colocada con un repuesto de la factura.
  Cada línea de parte se usa una sola vez (restricción única).
"""
from django.db import models


class SupplierInvoice(models.Model):
    """
    One supplier invoice file and what the agent did with it.

    ---

    Una factura de proveedor (su archivo en FACTURACION PROVEEDORES) y
    lo que hizo con ella el pipeline del almacén.
    """

    STATUS_PENDING = "PENDING"
    STATUS_PROCESSING = "PROCESSING"
    STATUS_PROCESSED = "PROCESSED"
    STATUS_DUPLICATE = "DUPLICATE"
    STATUS_NOT_INVOICE = "NOT_INVOICE"
    STATUS_ERROR = "ERROR"
    STATUS_CHOICES = [
        (STATUS_PENDING, "En cola"),
        (STATUS_PROCESSING, "Procesando"),
        (STATUS_PROCESSED, "Procesada"),
        (STATUS_DUPLICATE, "Factura repetida"),
        (STATUS_NOT_INVOICE, "No es una factura"),
        (STATUS_ERROR, "Error"),
    ]
    OPEN_STATUSES = (STATUS_PENDING, STATUS_PROCESSING)
    RETRYABLE_STATUSES = (STATUS_NOT_INVOICE, STATUS_ERROR)
    # Estados con los que el archivo pasa a "Facturas procesadas".
    DONE_STATUSES = (STATUS_PROCESSED, STATUS_DUPLICATE)

    entry = models.OneToOneField(
        "document_explorer.DocumentIndexEntry",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="supplier_invoice",
        verbose_name="Archivo de la factura",
    )
    sha256 = models.CharField(
        max_length=64, db_index=True, verbose_name="Huella SHA-256",
    )
    original_name = models.CharField(
        max_length=255, verbose_name="Nombre del archivo",
    )
    content_type = models.CharField(
        max_length=100, blank=True, verbose_name="Tipo MIME",
    )
    company = models.ForeignKey(
        "ivr_config.Company",
        on_delete=models.CASCADE,
        related_name="supplier_invoices",
        verbose_name="Empresa",
    )
    uploaded_by = models.ForeignKey(
        "ivr_config.CompanyUser",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="supplier_invoices",
        verbose_name="Subida por",
    )
    status = models.CharField(
        max_length=12,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
        verbose_name="Estado",
    )
    reason = models.TextField(blank=True, verbose_name="Resultado")
    extraction = models.JSONField(
        default=dict, blank=True, verbose_name="Lectura de Gemini",
    )
    supplier = models.ForeignKey(
        "spare_parts.Supplier",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="invoices",
        verbose_name="Proveedor (resuelto por CIF)",
    )
    supplier_name = models.CharField(
        max_length=255, blank=True, verbose_name="Proveedor",
    )
    supplier_tax_id = models.CharField(
        max_length=50, blank=True, verbose_name="NIF/CIF proveedor",
    )
    invoice_number = models.CharField(
        max_length=100, blank=True, verbose_name="Número de factura",
    )
    invoice_date = models.DateField(
        null=True, blank=True, verbose_name="Fecha de factura",
    )
    total_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Importe total",
    )
    duplicate_of = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="duplicates",
        verbose_name="Repetida de",
    )
    lines_count = models.PositiveIntegerField(
        default=0, verbose_name="Líneas",
    )
    covered_count = models.PositiveIntegerField(
        default=0, verbose_name="Con albarán",
    )
    purchased_count = models.PositiveIntegerField(
        default=0, verbose_name="Compradas sin albarán",
    )
    placed_count = models.PositiveIntegerField(
        default=0, verbose_name="Colocadas según partes",
    )
    created_at = models.DateTimeField(
        auto_now_add=True, verbose_name="Subida el",
    )
    processed_at = models.DateTimeField(
        null=True, blank=True, verbose_name="Procesada el",
    )

    class Meta:
        verbose_name = "Factura de proveedor"
        verbose_name_plural = "Facturas de proveedor"
        ordering = ["-created_at", "-pk"]

    def __str__(self):
        return "%s %s (%s)" % (
            self.supplier_name or self.original_name,
            self.invoice_number or "s/n",
            self.status,
        )


class SupplierInvoiceLine(models.Model):
    """
    One line of an invoice and where it ended up.

    ---

    Una línea de la factura y su destino.
    """

    OUTCOME_PENDING = "PENDING"
    OUTCOME_COVERED = "COVERED"
    OUTCOME_PURCHASED = "PURCHASED"
    OUTCOME_NO_QUANTITY = "NO_QUANTITY"
    OUTCOME_NOT_PART = "NOT_PART"
    OUTCOME_CHOICES = [
        (OUTCOME_PENDING, "Sin procesar"),
        (OUTCOME_COVERED, "Ya tenía albarán"),
        (OUTCOME_PURCHASED, "Comprada sin albarán, entrada en almacén"),
        (OUTCOME_NO_QUANTITY, "Sin cantidad legible, no entra en almacén"),
        (OUTCOME_NOT_PART, "No es un repuesto"),
    ]

    invoice = models.ForeignKey(
        SupplierInvoice,
        on_delete=models.CASCADE,
        related_name="lines",
        verbose_name="Factura",
    )
    line_number = models.PositiveIntegerField(verbose_name="Línea")
    reference = models.CharField(
        max_length=100, blank=True, verbose_name="Referencia",
    )
    description = models.CharField(
        max_length=255, blank=True, verbose_name="Descripción",
    )
    quantity = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Cantidad",
    )
    unit_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Precio unitario",
    )
    total_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Importe de la línea",
    )
    delivery_number_raw = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="Albarán citado en la factura",
    )
    delivery_date = models.DateField(
        null=True, blank=True, verbose_name="Fecha del albarán citado",
    )
    is_spare_part = models.BooleanField(
        default=True, verbose_name="Es un repuesto",
    )
    outcome = models.CharField(
        max_length=12,
        choices=OUTCOME_CHOICES,
        default=OUTCOME_PENDING,
        verbose_name="Destino",
    )
    delivery_note_line = models.ForeignKey(
        "spare_parts.DeliveryNoteLine",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="invoice_lines",
        verbose_name="Línea de albarán que la cubre",
    )
    spare_part_entry = models.ForeignKey(
        "spare_parts.SparePartEntry",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="invoice_lines",
        verbose_name="Repuesto del almacén",
    )
    stock_movement = models.ForeignKey(
        "spare_parts.StockMovement",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="invoice_lines",
        verbose_name="Entrada en almacén",
    )
    placed_quantity = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        verbose_name="Cantidad colocada según partes",
    )

    class Meta:
        verbose_name = "Línea de factura de proveedor"
        verbose_name_plural = "Líneas de facturas de proveedor"
        ordering = ["invoice", "line_number"]

    def __str__(self):
        return "%s -- L%d: %s" % (
            self.invoice, self.line_number, self.description,
        )


class SupplierInvoicePlacement(models.Model):
    """
    A work-order spare part line taken as fitted with an invoice part.

    ---

    Línea de repuesto de un parte de trabajo que se ha dado por
    colocada con un repuesto de la factura (salida de almacén). Una
    línea de parte se usa una sola vez.
    """

    MATCH_REFERENCE = "REFERENCE"
    MATCH_DESCRIPTION = "DESCRIPTION"
    MATCH_CHOICES = [
        (MATCH_REFERENCE, "Por referencia"),
        (MATCH_DESCRIPTION, "Por descripción"),
    ]

    invoice_line = models.ForeignKey(
        SupplierInvoiceLine,
        on_delete=models.CASCADE,
        related_name="placements",
        verbose_name="Línea de factura",
    )
    spare_part_line = models.OneToOneField(
        "work_order_processor.SparePartLine",
        on_delete=models.CASCADE,
        related_name="invoice_placement",
        verbose_name="Línea de repuesto del parte",
    )
    quantity = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name="Cantidad",
    )
    quantity_assumed = models.BooleanField(
        default=False,
        verbose_name="Cantidad supuesta",
        help_text="El parte no indicaba unidades: se ha contado 1.",
    )
    match_kind = models.CharField(
        max_length=12,
        choices=MATCH_CHOICES,
        verbose_name="Coincidencia",
    )
    stock_movement = models.ForeignKey(
        "spare_parts.StockMovement",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="invoice_placements",
        verbose_name="Salida de almacén",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Colocación según parte"
        verbose_name_plural = "Colocaciones según partes"
        ordering = ["invoice_line", "pk"]

    def __str__(self):
        return "%s -> %s" % (self.invoice_line, self.spare_part_line)
