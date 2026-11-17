# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/warehouse_inventory/models.py
"""
Photo-based warehouse inventory: counts, locations, photos, items read
and the differences against the digital warehouse.

---

H10 (S151, sesión invasora). Inventario del almacén por fotos:

- InventoryCount: un recuento (se abre, se fotografía, se cierra).
- InventoryLocation: dónde está cada cosa (estantería, balda, cajón).
- InventoryPhoto: cada foto, guardada en el cubo e indexada.
- InventoryItem: cada artículo que Gemini ve en una foto (etiqueta o
  pieza suelta), con su cruce con el almacén digital.
- InventoryDifference: lo que no cuadra con el stock. No toca nada hasta
  que Miguel Ángel lo confirma (o lo descarta) una a una.
"""
from django.db import models

from document_explorer.models import DocumentIndexEntry
from ivr_config.models import Company, CompanyUser
from spare_parts.models import SparePartEntry, StockMovement


class InventoryCount(models.Model):
    """
    One stocktake: opened, photographed, closed.

    ---

    Un recuento del almacén. Mientras está abierto se suben fotos; al
    cerrarlo aparece además lo que el sistema tiene y no se ha visto.
    """

    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="inventory_counts",
        verbose_name="Empresa",
    )
    started_by = models.ForeignKey(
        CompanyUser,
        on_delete=models.PROTECT,
        related_name="inventory_counts",
        verbose_name="Empezado por",
    )
    started_at = models.DateTimeField(
        auto_now_add=True, verbose_name="Empezado",
    )
    closed_at = models.DateTimeField(
        null=True, blank=True, verbose_name="Cerrado",
    )

    class Meta:
        verbose_name = "Recuento del almacén"
        verbose_name_plural = "Recuentos del almacén"
        ordering = ["-started_at"]

    def __str__(self):
        return "Recuento %s del %s" % (
            self.pk, self.started_at.strftime("%d/%m/%Y"),
        )

    @property
    def is_open(self):
        return self.closed_at is None


class InventoryLocation(models.Model):
    """
    Where things are kept (shelf, rack level, drawer).

    ---

    Ubicación del almacén físico (estantería, balda, cajón), con el
    nombre que le da Miguel Ángel al hacer las fotos.
    """

    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="inventory_locations",
        verbose_name="Empresa",
    )
    name = models.CharField(max_length=120, verbose_name="Ubicación")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Ubicación del almacén"
        verbose_name_plural = "Ubicaciones del almacén"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "name"],
                name="unique_inventory_location_per_company",
            ),
        ]

    def __str__(self):
        return self.name


class InventoryPhoto(models.Model):
    """
    One photo of a location, stored in the bucket and indexed.

    ---

    Una foto de una ubicación, guardada en el cubo e indexada (se ve en
    el explorador), y lo que Gemini leyó en ella.
    """

    STATUS_PENDING = "PENDING"
    STATUS_PROCESSING = "PROCESSING"
    STATUS_DONE = "DONE"
    STATUS_ERROR = "ERROR"
    STATUS_CHOICES = [
        (STATUS_PENDING, "En cola"),
        (STATUS_PROCESSING, "Leyendo"),
        (STATUS_DONE, "Leída"),
        (STATUS_ERROR, "Error"),
    ]
    OPEN_STATUSES = (STATUS_PENDING, STATUS_PROCESSING)

    count = models.ForeignKey(
        InventoryCount,
        on_delete=models.CASCADE,
        related_name="photos",
        verbose_name="Recuento",
    )
    location = models.ForeignKey(
        InventoryLocation,
        on_delete=models.PROTECT,
        related_name="photos",
        verbose_name="Ubicación",
    )
    entry = models.OneToOneField(
        DocumentIndexEntry,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="inventory_photo",
        verbose_name="Archivo en el cubo",
    )
    blob_name = models.TextField(verbose_name="Objeto en el cubo")
    content_type = models.CharField(max_length=100, blank=True)
    uploaded_by = models.ForeignKey(
        CompanyUser,
        on_delete=models.PROTECT,
        related_name="inventory_photos",
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
        null=True, blank=True, verbose_name="Lectura de Gemini",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Foto del inventario"
        verbose_name_plural = "Fotos del inventario"
        ordering = ["-created_at"]

    def __str__(self):
        return "Foto %s (%s)" % (self.pk, self.location)


class InventoryItem(models.Model):
    """
    One article seen in a photo and its match in the warehouse.

    ---

    Un artículo visto en una foto (por su etiqueta o como pieza suelta)
    y el repuesto del almacén digital con el que casa, si casa.
    """

    SOURCE_LABEL = "LABEL"
    SOURCE_PART = "PART"
    SOURCE_CHOICES = [
        (SOURCE_LABEL, "Etiqueta o caja"),
        (SOURCE_PART, "Pieza suelta"),
    ]
    MATCH_REFERENCE = "REFERENCE"
    MATCH_DESCRIPTION = "DESCRIPTION"
    MATCH_NONE = "NONE"
    MATCH_CHOICES = [
        (MATCH_REFERENCE, "Por referencia"),
        (MATCH_DESCRIPTION, "Por descripción"),
        (MATCH_NONE, "Sin casar"),
    ]

    photo = models.ForeignKey(
        InventoryPhoto,
        on_delete=models.CASCADE,
        related_name="items",
        verbose_name="Foto",
    )
    location = models.ForeignKey(
        InventoryLocation,
        on_delete=models.PROTECT,
        related_name="items",
        verbose_name="Ubicación",
    )
    source = models.CharField(
        max_length=10, choices=SOURCE_CHOICES, verbose_name="Visto en",
    )
    reference = models.CharField(
        max_length=100, blank=True, verbose_name="Referencia",
    )
    brand = models.CharField(max_length=100, blank=True, verbose_name="Marca")
    description = models.CharField(max_length=255, verbose_name="Descripción")
    quantity = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Cantidad contada",
    )
    quantity_is_estimate = models.BooleanField(
        default=False, verbose_name="Cantidad estimada",
    )
    spare_part_entry = models.ForeignKey(
        SparePartEntry,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="inventory_items",
        verbose_name="Repuesto del almacén",
    )
    match_kind = models.CharField(
        max_length=12,
        choices=MATCH_CHOICES,
        default=MATCH_NONE,
        verbose_name="Cruce",
    )

    class Meta:
        verbose_name = "Artículo visto"
        verbose_name_plural = "Artículos vistos"
        ordering = ["photo", "pk"]

    def __str__(self):
        return self.description


class InventoryDifference(models.Model):
    """
    What does not match the warehouse, pending Miguel Ángel's review.

    ---

    Lo que no cuadra con el almacén digital. Se recalcula al leer cada
    foto (y al cerrar el recuento) mientras está pendiente; una vez
    confirmada o descartada ya no cambia.
    """

    KIND_NEW = "NEW"
    KIND_QUANTITY = "QUANTITY"
    KIND_NOT_SEEN = "NOT_SEEN"
    KIND_CHOICES = [
        (KIND_NEW, "No está en el almacén"),
        (KIND_QUANTITY, "Cantidad distinta"),
        (KIND_NOT_SEEN, "No se ha visto"),
    ]
    STATUS_PENDING = "PENDING"
    STATUS_APPLIED = "APPLIED"
    STATUS_DISCARDED = "DISCARDED"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pendiente"),
        (STATUS_APPLIED, "Confirmada"),
        (STATUS_DISCARDED, "Descartada"),
    ]

    count = models.ForeignKey(
        InventoryCount,
        on_delete=models.CASCADE,
        related_name="differences",
        verbose_name="Recuento",
    )
    kind = models.CharField(
        max_length=10, choices=KIND_CHOICES, verbose_name="Tipo",
    )
    group_key = models.CharField(
        max_length=255, verbose_name="Clave de agrupación",
    )
    spare_part_entry = models.ForeignKey(
        SparePartEntry,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="inventory_differences",
        verbose_name="Repuesto del almacén",
    )
    reference = models.CharField(
        max_length=100, blank=True, verbose_name="Referencia",
    )
    description = models.CharField(max_length=255, verbose_name="Descripción")
    locations = models.CharField(
        max_length=500, blank=True, verbose_name="Ubicaciones",
    )
    counted_quantity = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Contado",
    )
    counted_is_estimate = models.BooleanField(default=False)
    system_quantity = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="En el sistema",
    )
    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
        verbose_name="Estado",
    )
    stock_movement = models.ForeignKey(
        StockMovement,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="inventory_differences",
        verbose_name="Movimiento de stock",
    )
    resolved_by = models.ForeignKey(
        CompanyUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="inventory_differences_resolved",
        verbose_name="Revisada por",
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Diferencia del inventario"
        verbose_name_plural = "Diferencias del inventario"
        ordering = ["kind", "description"]
        constraints = [
            models.UniqueConstraint(
                fields=["count", "group_key"],
                name="unique_inventory_difference_per_count",
            ),
        ]

    def __str__(self):
        return "%s: %s" % (self.get_kind_display(), self.description)
