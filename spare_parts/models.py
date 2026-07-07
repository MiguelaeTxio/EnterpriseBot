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


class Supplier(models.Model):
    """
    Supplier of spare parts -- external companies AND the internal
    salvage/recycling circuit, modelled as the same kind of entity.
    Confirmed by Miguel Ángel (2026-07-06): the traceability of a
    spare part (where it physically came from) is given by which
    Supplier it references, not by a separate origin_type flag --
    "reciclado interno" is just another Supplier record (TYPE_SALVAGE),
    not a different mechanism.

    This model is additive in this commit: SparePartEntry gains a
    nullable `supplier` FK alongside its existing supplier_name/
    supplier_tax_id/supplier_address free-text fields and origin_type,
    which remain untouched for now. Wiring the delivery-note ingestion
    pipeline (confirm_delivery_note, Gemini Vision extraction) and the
    salvage flow (Paso 7 canibalización) to resolve/create a Supplier
    record instead of writing free text is a separate, larger step --
    both are already-validated production flows and Miguel Ángel has
    not yet confirmed how the resolution (by tax_id? by name?) should
    work, so it is intentionally left for a follow-up decision.

    ---

    Proveedor de repuestos -- tanto empresas externas COMO el circuito
    interno de reciclado/canibalización, modelados como el mismo tipo
    de entidad. Confirmado por Miguel Ángel (2026-07-06): la
    trazabilidad de un repuesto (de dónde viene físicamente) la da a
    qué Supplier referencia, no un flag origin_type aparte --
    "reciclado interno" es solo otro registro de Supplier
    (TYPE_SALVAGE), no un mecanismo distinto.

    Este modelo es aditivo en este commit: SparePartEntry gana un FK
    `supplier` nullable junto a sus campos de texto libre existentes
    supplier_name/supplier_tax_id/supplier_address y origin_type, que
    de momento no se tocan. Conectar el pipeline de ingesta de
    albaranes (confirm_delivery_note, extracción Gemini Vision) y el
    flujo de reciclado (Paso 7 canibalización) para que resuelvan/creen
    un Supplier en vez de escribir texto libre es un paso aparte y
    mayor -- ambos son flujos ya validados en producción y Miguel
    Ángel todavía no ha confirmado cómo debe funcionar la resolución
    (¿por CIF? ¿por nombre?), así que se deja intencionadamente para
    una decisión de seguimiento.
    """

    TYPE_EXTERNAL = 'EXTERNAL'
    TYPE_SALVAGE = 'SALVAGE'
    TYPE_CHOICES = [
        (TYPE_EXTERNAL, 'Proveedor externo'),
        (TYPE_SALVAGE, 'Reciclado interno'),
    ]

    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name='suppliers',
        verbose_name='Empresa',
    )
    supplier_type = models.CharField(
        max_length=10,
        choices=TYPE_CHOICES,
        default=TYPE_EXTERNAL,
        verbose_name='Tipo de proveedor',
    )
    name = models.CharField(
        max_length=255,
        verbose_name='Nombre',
    )
    tax_id = models.CharField(
        max_length=50,
        blank=True,
        verbose_name='NIF/CIF',
        help_text='Vacío para el proveedor de tipo Reciclado interno.',
    )
    address = models.CharField(
        max_length=255,
        blank=True,
        verbose_name='Dirección',
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name='Activo',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Proveedor'
        verbose_name_plural = 'Proveedores'
        ordering = ['name']
        constraints = [
            models.UniqueConstraint(
                fields=['company', 'tax_id'],
                condition=~models.Q(tax_id=''),
                name='unique_supplier_tax_id_per_company',
            ),
        ]

    def __str__(self):
        return f'{self.name} ({self.get_supplier_type_display()})'


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
    # ------------------------------------------------------------------
    # Empresa destinataria del grupo (S004-H10, TAREA INMEDIATA punto 1).
    # Grupo Álvarez es una única Company en ivr_config, pero un albarán
    # va dirigido a una empresa concreta del grupo (razón social + CIF
    # propios). recipient_company_code reutiliza el mismo catálogo corto
    # que fleet.MachineAsset.company_code (GRA, TRA, GRG...) para no
    # duplicar catálogo -- ver resolve_recipient_company_code() en
    # services.py. Campo libre, no choices: el catálogo de empresas del
    # grupo emerge orgánicamente igual que los centros de gasto.
    # ------------------------------------------------------------------
    # Recipient company within the group (S004-H10, TAREA INMEDIATA
    # point 1). Grupo Álvarez is a single Company in ivr_config, but a
    # delivery note is addressed to a specific company within the group
    # (its own legal name + tax ID). recipient_company_code reuses the
    # same short catalogue as fleet.MachineAsset.company_code (GRA, TRA,
    # GRG...) to avoid a duplicate catalogue -- see
    # resolve_recipient_company_code() in services.py. Free field, no
    # choices: the group company catalogue emerges organically just
    # like cost centres do.
    # ------------------------------------------------------------------
    recipient_name = models.CharField(
        max_length=255,
        blank=True,
        verbose_name='Razón social destinataria',
        help_text=(
            'Nombre legal de la empresa del grupo a la que va dirigido '
            'el albarán, tal como figura impreso en el documento.'
        ),
    )
    recipient_tax_id = models.CharField(
        max_length=50,
        blank=True,
        verbose_name='NIF/CIF destinatario',
        help_text=(
            'CIF de la empresa destinataria tal como figura en el '
            'albarán. Es la clave usada para resolver '
            'recipient_company_code de forma fiable, ya que la razón '
            'social aparece con variantes de texto en el catálogo.'
        ),
    )
    recipient_company_code = models.CharField(
        max_length=20,
        blank=True,
        verbose_name='Código de empresa destinataria',
        help_text=(
            'Código corto de la empresa del grupo, resuelto desde '
            'recipient_tax_id (ej: GRA, TRA, GRG). Vacío si el CIF no '
            'se ha podido leer o no está todavía en el catálogo -- '
            'requiere revisión manual en ese caso.'
        ),
    )
    # ------------------------------------------------------------------
    # Anotación general de máquina/centro de gasto (S007-H10). Confirmado
    # por Miguel Ángel (2026-07-07): además de la anotación #CODIGO# junto
    # a cada línea, un albarán puede llevar una única anotación #CODIGO#
    # general (fuera de cualquier línea concreta, p. ej. en la cabecera o
    # el margen del documento) indicando que el albarán ENTERO es para esa
    # máquina/centro de gasto. Actúa como fallback: solo se usa para
    # resolver las líneas que no tengan su propia anotación individual --
    # ver resolve_line_assignment() y confirm_delivery_note() en
    # services.py. Campo libre, mismo formato bruto que
    # DeliveryNoteLine.machine_code_raw (sin normalizar).
    # ------------------------------------------------------------------
    # General machine/cost-centre annotation (S007-H10). Confirmed by
    # Miguel Ángel (2026-07-07): besides the #CODE# annotation next to
    # each line, a delivery note can carry a single general #CODE#
    # annotation (outside any specific line, e.g. in the header or
    # document margin) indicating the WHOLE delivery note is for that
    # machine/cost centre. Acts as a fallback: only used to resolve
    # lines that don't have their own individual annotation -- see
    # resolve_line_assignment() and confirm_delivery_note() in
    # services.py. Free field, same raw format as
    # DeliveryNoteLine.machine_code_raw (unnormalised).
    # ------------------------------------------------------------------
    general_machine_code_raw = models.CharField(
        max_length=100,
        blank=True,
        verbose_name='Código general del albarán',
        help_text=(
            'Anotación #CODIGO# general del albarán completo (fuera de '
            'cualquier línea concreta), tal como se extrajo o se '
            'corrigió a mano. Se usa solo como respaldo para las '
            'líneas sin anotación propia. Vacío si el albarán no lleva '
            'una anotación general.'
        ),
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
        verbose_name='Referencia proveedor',
    )
    internal_reference = models.CharField(
        max_length=20,
        blank=True,
        verbose_name='Referencia interna',
        help_text=(
            'Referencia propia de la empresa, estable frente a cambios de '
            'proveedor. Generada automáticamente, nunca importada de un '
            'albarán externo. Ver anexo H10, confirmado por Miguel Ángel '
            'el 2026-07-06: la referencia del proveedor puede cambiar si '
            'se cambia de proveedor para la misma pieza física, así que '
            'el catálogo y el consumo se identifican por esta referencia '
            'interna, no por la del proveedor.'
        ),
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
    supplier = models.ForeignKey(
        Supplier,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='spare_part_entries',
        verbose_name='Proveedor',
        help_text=(
            'Referencia real al modelo Supplier (2026-07-06, aditivo). '
            'Los campos supplier_name/supplier_tax_id/supplier_address '
            'de abajo son el texto libre extraído por Gemini Vision del '
            'albarán -- todavía no se resuelven automáticamente contra '
            'este FK. Ver docstring de Supplier.'
        ),
    )
    supplier_name = models.CharField(
        max_length=255,
        blank=True,
        verbose_name='Proveedor (texto libre, histórico)',
    )
    supplier_tax_id = models.CharField(
        max_length=50,
        blank=True,
        verbose_name='NIF/CIF proveedor (texto libre, histórico)',
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
        constraints = [
            models.UniqueConstraint(
                fields=['company', 'internal_reference'],
                condition=~models.Q(internal_reference=''),
                name='unique_internal_reference_per_company',
            ),
        ]

    def __str__(self):
        if self.internal_reference:
            return f'[{self.internal_reference}] {self.description} ({self.get_status_display()})'
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

