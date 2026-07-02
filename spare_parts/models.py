# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/spare_parts/models.py
"""
Data models for the spare parts and supplier delivery note module.
---
Modelos de datos del módulo de albaranes de proveedores y repuestos.
"""
from django.db import models

from fleet.models import MachineAsset
from chat.models import BreakdownTicket
from ivr_config.models import Company, CompanyUser
from work_order_processor.models import WorkOrderEntryLine, SparePartLine


class DeliveryNote(models.Model):
    """
    Supplier delivery note, ingested via photo or PDF using Gemini
    Vision extraction.
    ---
    Albarán de proveedor, ingerido vía foto o PDF mediante extracción
    con Gemini Vision.
    """

    SOURCE_TYPE_CHOICES = [
        ('PHOTO', 'Foto'),
        ('PDF', 'PDF'),
    ]

    STATUS_CHOICES = [
        ('PENDING', 'Pendiente'),
        ('PROCESSED', 'Procesado'),
        ('ASSIGNED', 'Asignado'),
    ]

    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name='delivery_notes',
        verbose_name='Empresa',
    )
    source_type = models.CharField(
        max_length=10,
        choices=SOURCE_TYPE_CHOICES,
        verbose_name='Tipo de origen',
    )
    image = models.ImageField(
        upload_to='delivery_notes/photos/',
        null=True,
        blank=True,
        verbose_name='Foto del albarán',
    )
    pdf_file = models.FileField(
        upload_to='delivery_notes/pdfs/',
        null=True,
        blank=True,
        verbose_name='PDF del albarán',
    )
    supplier_name = models.CharField(
        max_length=255,
        blank=True,
        verbose_name='Proveedor',
    )
    supplier_tax_id = models.CharField(
        max_length=50,
        blank=True,
        verbose_name='NIF/CIF proveedor',
    )
    delivery_number = models.CharField(
        max_length=100,
        blank=True,
        verbose_name='Número de albarán',
    )
    delivery_date = models.DateField(
        null=True,
        blank=True,
        verbose_name='Fecha de albarán',
    )
    extraction_raw = models.JSONField(
        default=dict,
        blank=True,
        verbose_name='Respuesta bruta de extracción',
    )
    status = models.CharField(
        max_length=15,
        choices=STATUS_CHOICES,
        default='PENDING',
        verbose_name='Estado',
    )
    processed_by = models.ForeignKey(
        CompanyUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='processed_delivery_notes',
        verbose_name='Revisado por',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Albarán de proveedor'
        verbose_name_plural = 'Albaranes de proveedor'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.supplier_name} — {self.delivery_number or "s/n"}'


class DeliveryNoteLine(models.Model):
    """
    Single line item within a supplier delivery note.
    ---
    Línea individual de artículo dentro de un albarán de proveedor.
    """

    ASSIGNMENT_TYPE_CHOICES = [
        ('MACHINE', 'Máquina'),
        ('WAREHOUSE', 'Almacén'),
        ('UNASSIGNED', 'Sin asignar'),
    ]

    delivery_note = models.ForeignKey(
        DeliveryNote,
        on_delete=models.CASCADE,
        related_name='lines',
        verbose_name='Albarán',
    )
    line_number = models.PositiveIntegerField(
        verbose_name='Número de línea',
    )
    reference = models.CharField(
        max_length=100,
        blank=True,
        verbose_name='Referencia',
    )
    description = models.CharField(
        max_length=255,
        verbose_name='Descripción',
    )
    quantity = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        verbose_name='Cantidad',
    )
    unit_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name='Precio unitario',
    )
    total_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name='Precio total línea',
    )
    machine_code_raw = models.CharField(
        max_length=100,
        blank=True,
        verbose_name='Código máquina/almacén (bruto)',
        help_text=(
            'Código de máquina o almacén anotado a mano en el albarán, tal '
            'como lo transcribió Gemini Vision (sin normalizar). Editable '
            'en la revisión antes de confirmar la asignación. Añadido en '
            'S002-H10 para soportar el Paso 3 del anexo (revisión de '
            'DeliveryNoteDetailView).'
        ),
    )
    assignment_type = models.CharField(
        max_length=15,
        choices=ASSIGNMENT_TYPE_CHOICES,
        default='UNASSIGNED',
        verbose_name='Tipo de asignación',
    )
    machine = models.ForeignKey(
        MachineAsset,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='delivery_note_lines',
        verbose_name='Máquina asignada',
    )
    work_order_line = models.ForeignKey(
        WorkOrderEntryLine,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='delivery_note_lines',
        verbose_name='Línea de parte vinculada',
    )
    spare_part_entry = models.ForeignKey(
        'SparePartEntry',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='source_delivery_note_lines',
        verbose_name='Entrada en stock resultante',
    )

    class Meta:
        verbose_name = 'Línea de albarán'
        verbose_name_plural = 'Líneas de albarán'
        ordering = ['delivery_note', 'line_number']

    def __str__(self):
        return f'{self.delivery_note} — L{self.line_number}: {self.description}'


class SparePartEntry(models.Model):
    """
    Spare part entry in the digital warehouse, the pre-assignment
    limbo, or already consumed in a work order.
    ---
    Repuesto en el almacén digital, en el limbo de pre-asignación, o
    ya consumido en un parte de trabajo.

    The `status` field is the central axis of this model. While
    status=PRE_ASSIGNED the part is reserved for a specific machine
    or ticket but does not count towards any warehouse stock — this
    prevents double-assignment of the same physical item. See annex
    H10, section 3.2.

    The `origin_type` field tracks where the part physically came
    from: a supplier delivery note (SUPPLIER) or a donor machine in
    the company's own fleet (SALVAGED, e.g. a gearbox removed from a
    decommissioned machine). Only one of the two field blocks below
    is populated depending on this value. See annex H10, section 3.6.

    ---

    El campo `status` es el eje central de este modelo. Mientras
    status=PRE_ASSIGNED la pieza está reservada para una máquina o
    ticket concreto pero no cuenta para ningún stock de almacén —
    esto evita la doble asignación del mismo artículo físico. Ver
    anexo H10, sección 3.2.

    El campo `origin_type` rastrea de dónde proviene físicamente la
    pieza: un albarán de proveedor (SUPPLIER) o una máquina donante
    de la propia flota (SALVAGED, ej. una caja de cambios retirada
    de una máquina de baja). Solo uno de los dos bloques de campos
    siguientes se rellena según este valor. Ver anexo H10,
    sección 3.6.
    """

    STATUS_WAREHOUSE = 'WAREHOUSE'
    STATUS_PRE_ASSIGNED = 'PRE_ASSIGNED'
    STATUS_CONSUMED = 'CONSUMED'
    STATUS_CHOICES = [
        (STATUS_WAREHOUSE, 'Almacén'),
        (STATUS_PRE_ASSIGNED, 'Pre-asignado (limbo)'),
        (STATUS_CONSUMED, 'Consumido'),
    ]

    ORIGIN_SUPPLIER = 'SUPPLIER'
    ORIGIN_SALVAGED = 'SALVAGED'
    ORIGIN_TYPE_CHOICES = [
        (ORIGIN_SUPPLIER, 'Proveedor'),
        (ORIGIN_SALVAGED, 'Reciclado interno'),
    ]

    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name='spare_part_entries',
        verbose_name='Empresa',
    )
    reference = models.CharField(
        max_length=100,
        blank=True,
        verbose_name='Referencia',
    )
    description = models.CharField(
        max_length=255,
        verbose_name='Descripción',
    )
    is_uncountable = models.BooleanField(
        default=False,
        verbose_name='Es incontable',
    )
    stock_quantity = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        verbose_name='Cantidad en stock',
    )
    stock_level = models.CharField(
        max_length=10,
        blank=True,
        verbose_name='Nivel de stock',
    )
    status = models.CharField(
        max_length=15,
        choices=STATUS_CHOICES,
        default=STATUS_WAREHOUSE,
        verbose_name='Estado',
    )
    machine = models.ForeignKey(
        MachineAsset,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='spare_part_entries',
        verbose_name='Máquina destino',
    )
    breakdown_ticket = models.ForeignKey(
        BreakdownTicket,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='spare_part_entries',
        verbose_name='Ticket de avería destino',
    )
    pre_assigned_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Fecha de entrada en el limbo',
    )
    consumed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Fecha de consumo real',
    )

    # ------------------------------------------------------------------
    # Origin / Procedencia (H10, S001)
    # ------------------------------------------------------------------
    origin_type = models.CharField(
        max_length=10,
        choices=ORIGIN_TYPE_CHOICES,
        default=ORIGIN_SUPPLIER,
        verbose_name='Tipo de origen',
    )

    # --- Supplier block / Bloque proveedor (origin_type=SUPPLIER) -----
    supplier_name = models.CharField(
        max_length=255,
        blank=True,
        verbose_name='Proveedor',
    )
    supplier_tax_id = models.CharField(
        max_length=50,
        blank=True,
        verbose_name='NIF/CIF proveedor',
    )
    supplier_address = models.CharField(
        max_length=255,
        blank=True,
        verbose_name='Dirección proveedor',
    )
    purchase_unit_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name='Precio unitario de compra',
    )
    purchase_discount_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name='Descuento de compra (%)',
    )
    purchase_total_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name='Precio total de compra',
    )
    source_delivery_note_line = models.ForeignKey(
        DeliveryNoteLine,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='resulting_spare_part_entries',
        verbose_name='Línea de albarán de origen',
    )

    # --- Salvaged block / Bloque reciclado (origin_type=SALVAGED) -----
    origin_machine = models.ForeignKey(
        MachineAsset,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='salvaged_spare_part_entries',
        verbose_name='Máquina donante',
    )
    origin_work_order_entry_line = models.ForeignKey(
        WorkOrderEntryLine,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='salvaged_spare_part_entries',
        verbose_name='Línea de parte donde se documentó la retirada',
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Repuesto'
        verbose_name_plural = 'Repuestos'
        ordering = ['-updated_at']

    def __str__(self):
        return f'{self.description} [{self.get_status_display()}]'


class StockMovement(models.Model):
    """
    Stock movement affecting a spare part entry: warehouse intake,
    consumption, manual adjustment, return from the pre-assignment
    limbo back to the warehouse, or salvage intake from a donor
    machine.
    ---
    Movimiento de stock que afecta a un repuesto: entrada de almacén,
    consumo, ajuste manual, devolución desde el limbo de
    pre-asignación de vuelta a almacén, o entrada por canibalización
    desde una máquina donante.
    """

    MOVEMENT_IN = 'IN'
    MOVEMENT_OUT = 'OUT'
    MOVEMENT_ADJUST = 'ADJUST'
    MOVEMENT_RETURN_TO_WAREHOUSE = 'RETURN_TO_WAREHOUSE'
    MOVEMENT_SALVAGE = 'SALVAGE'
    MOVEMENT_TYPE_CHOICES = [
        (MOVEMENT_IN, 'Entrada'),
        (MOVEMENT_OUT, 'Salida'),
        (MOVEMENT_ADJUST, 'Ajuste'),
        (MOVEMENT_RETURN_TO_WAREHOUSE, 'Devolución a almacén'),
        (MOVEMENT_SALVAGE, 'Entrada por reciclado interno'),
    ]

    spare_part_entry = models.ForeignKey(
        SparePartEntry,
        on_delete=models.CASCADE,
        related_name='movements',
        verbose_name='Repuesto',
    )
    movement_type = models.CharField(
        max_length=20,
        choices=MOVEMENT_TYPE_CHOICES,
        verbose_name='Tipo de movimiento',
    )
    quantity = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        verbose_name='Cantidad movida',
    )
    level_before = models.CharField(
        max_length=10,
        blank=True,
        verbose_name='Nivel antes',
    )
    level_after = models.CharField(
        max_length=10,
        blank=True,
        verbose_name='Nivel después',
    )
    machine = models.ForeignKey(
        MachineAsset,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='stock_movements',
        verbose_name='Máquina destino',
    )
    breakdown_ticket = models.ForeignKey(
        BreakdownTicket,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='stock_movements',
        verbose_name='Ticket de avería vinculado',
    )
    work_order_entry_line = models.ForeignKey(
        WorkOrderEntryLine,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='stock_movements',
        verbose_name='Línea de parte vinculada',
    )
    spare_part_line = models.ForeignKey(
        SparePartLine,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='stock_movements',
        verbose_name='Línea de repuesto del parte (consumo materializado)',
    )
    delivery_note_line = models.ForeignKey(
        DeliveryNoteLine,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='stock_movements',
        verbose_name='Línea de albarán origen',
    )
    notes = models.TextField(
        blank=True,
        verbose_name='Notas',
    )
    created_by = models.ForeignKey(
        CompanyUser,
        on_delete=models.PROTECT,
        related_name='stock_movements',
        verbose_name='Registrado por',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Movimiento de stock'
        verbose_name_plural = 'Movimientos de stock'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.get_movement_type_display()} — {self.spare_part_entry}'

