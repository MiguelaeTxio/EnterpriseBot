# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/fleet/models.py

"""
Models for the fleet application.
Defines MachineAsset (cost-centre entity for all machinery), MaintenanceLog
(one record per maintenance intervention) and MaintenanceItem (one line per
spare part or third-party labour item consumed in an intervention).

Together these three models form the maintenance logbook of each machine:
  MachineAsset → MaintenanceLog → MaintenanceItem

---

Modelos de la aplicación fleet.
Define MachineAsset (entidad centro de gasto para toda la maquinaria),
MaintenanceLog (un registro por intervención de mantenimiento) y
MaintenanceItem (una línea por repuesto o mano de obra de tercero consumido
en una intervención).

Los tres modelos forman el libro de mantenimiento de cada máquina:
  MachineAsset → MaintenanceLog → MaintenanceItem
"""

from django.db import models
from django.utils.translation import gettext_lazy as _

from ivr_config.models import Company


# ---------------------------------------------------------------------------
# MachineAsset — cost centre / centro de gasto
# ---------------------------------------------------------------------------

class MachineAsset(models.Model):
    """
    Represents a single machinery or vehicle unit registered in the company
    fleet catalogue. Each instance is a cost centre: maintenance hours from
    work orders and third-party delivery notes are imputed against it.

    The `codigo` field is the primary lookup key used when resolving the
    machine reference extracted from handwritten work-order slips
    (field `maquina_norm` in WorkOrderEntryLine). Normalisation rules D4
    from the partes-trabajo skill are applied before the lookup.

    ---

    Representa una unidad de maquinaria o vehículo registrada en el catálogo
    de flota de la empresa. Cada instancia es un centro de gasto: las horas de
    mecánica de los partes de trabajo y los albaranes de terceros se imputan
    contra ella.

    El campo `codigo` es la clave de búsqueda principal que se utiliza al
    resolver la referencia de máquina extraída de los partes manuscritos
    (campo `maquina_norm` en WorkOrderEntryLine). Las reglas de normalización
    D4 de la skill partes-trabajo se aplican antes de la búsqueda.
    """

    # ------------------------------------------------------------------
    # Company relation / Relación con empresa
    # ------------------------------------------------------------------
    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="machine_assets",
        verbose_name=_("Empresa"),
        help_text=_(
            "Empresa propietaria de esta unidad de maquinaria. "
            "Corresponde al campo EMPRESA del catálogo."
        ),
    )

    # ------------------------------------------------------------------
    # Catalogue origin fields / Campos de origen del catálogo
    # ------------------------------------------------------------------
    empresa_codigo = models.CharField(
        _("Código de Empresa"),
        max_length=20,
        db_index=True,
        help_text=_(
            "Código corto de la empresa en el catálogo (ej: GRA, TRA, GRH). "
            "Se usa para agrupación y filtrado por empresa origen."
        ),
    )
    empresa_nombre = models.CharField(
        _("Nombre de Empresa"),
        max_length=200,
        help_text=_("Nombre completo de la empresa tal como aparece en el catálogo."),
    )
    familia = models.CharField(
        _("Familia"),
        max_length=100,
        blank=True,
        help_text=_(
            "Familia de maquinaria del catálogo (ej: MOVILES, PLATAFOR, CARR, "
            "AUTOCARG, REMOLQUE, TTE.)."
        ),
    )
    tipo_codigo = models.CharField(
        _("Código de Tipo"),
        max_length=50,
        blank=True,
        help_text=_(
            "Código del tipo de maquinaria en el catálogo "
            "(ej: MV035, PLTJ-E08, CG050)."
        ),
    )
    tipo_nombre = models.CharField(
        _("Nombre de Tipo"),
        max_length=200,
        blank=True,
        help_text=_(
            "Descripción legible del tipo de maquinaria "
            "(ej: GRUA MOVIL DE 35 TM, TIJERA ELECTRICA DE 8 MTS.)."
        ),
    )

    # ------------------------------------------------------------------
    # Primary identification / Identificación principal
    # ------------------------------------------------------------------
    codigo = models.CharField(
        _("Código"),
        max_length=50,
        unique=True,
        db_index=True,
        help_text=_(
            "Código único de la máquina en el catálogo (ej: A54, Z45, B27). "
            "Es la clave de búsqueda principal para resolver referencias de "
            "partes de trabajo. Se almacena en mayúsculas."
        ),
    )
    matricula = models.CharField(
        _("Matrícula"),
        max_length=50,
        blank=True,
        help_text=_(
            "Matrícula o número de bastidor abreviado del vehículo o maquinaria. "
            "Puede coincidir con el código en equipos sin matrícula oficial."
        ),
    )
    num_bastidor = models.CharField(
        _("Nº Bastidor"),
        max_length=100,
        blank=True,
        help_text=_("Número de bastidor completo tal como figura en el catálogo."),
    )
    marca_modelo = models.CharField(
        _("Marca / Modelo"),
        max_length=200,
        blank=True,
        help_text=_(
            "Marca y modelo del vehículo o maquinaria "
            "(ej: LIEBHERR LTM 1055, LUNA GT-60/42, STILL RX20-20)."
        ),
    )

    # ------------------------------------------------------------------
    # Acquisition data / Datos de adquisición
    # ------------------------------------------------------------------
    fecha_compra = models.DateField(
        _("Fecha de Compra"),
        null=True,
        blank=True,
        help_text=_("Fecha de adquisición del vehículo o maquinaria."),
    )
    kms = models.IntegerField(
        _("Kilómetros"),
        default=0,
        help_text=_("Kilómetros registrados en el catálogo en el momento de la importación."),
    )
    horas = models.IntegerField(
        _("Horas de Trabajo"),
        default=0,
        help_text=_(
            "Horas de trabajo registradas en el catálogo "
            "en el momento de la importación."
        ),
    )

    # ------------------------------------------------------------------
    # Status / Estado
    # ------------------------------------------------------------------
    es_activo = models.BooleanField(
        _("Activo"),
        default=True,
        db_index=True,
        help_text=_(
            "Indica si la unidad está activa en la flota. "
            "Las unidades dadas de baja se marcan como inactivas."
        ),
    )

    # ------------------------------------------------------------------
    # Audit / Auditoría
    # ------------------------------------------------------------------
    importado_en = models.DateTimeField(
        _("Importado en"),
        auto_now_add=True,
        help_text=_(
            "Fecha y hora en que se importó este registro desde el catálogo."
        ),
    )
    actualizado_en = models.DateTimeField(
        _("Actualizado en"),
        auto_now=True,
        help_text=_("Fecha y hora de la última modificación del registro."),
    )

    class Meta:
        verbose_name        = _("Activo de Flota")
        verbose_name_plural = _("Activos de Flota")
        ordering            = ["empresa_codigo", "familia", "codigo"]
        indexes             = [
            models.Index(fields=["empresa_codigo", "familia"]),
            models.Index(fields=["codigo"]),
        ]

    def __str__(self) -> str:
        return f"{self.codigo} — {self.marca_modelo} [{self.empresa_codigo}]"

    def save(self, *args, **kwargs) -> None:
        """
        Normalises the `codigo` field to uppercase before saving to ensure
        consistent lookup regardless of the source casing.

        ---

        Normaliza el campo `codigo` a mayúsculas antes de guardar para
        garantizar búsquedas consistentes independientemente de las
        mayúsculas/minúsculas del origen.
        """
        self.codigo = self.codigo.strip().upper()
        super().save(*args, **kwargs)


# ---------------------------------------------------------------------------
# MaintenanceLog — one record per intervention / un registro por intervención
# ---------------------------------------------------------------------------

class MaintenanceLog(models.Model):
    """
    Records a single maintenance intervention on a MachineAsset.
    An intervention may originate from a processed work-order entry line
    (work_entry_line FK) or be entered manually by a supervisor.
    All spare parts and third-party labour items consumed are linked via
    MaintenanceItem records.

    ---

    Registra una intervención de mantenimiento individual sobre un MachineAsset.
    Una intervención puede originarse en una línea de parte de trabajo procesada
    (FK work_entry_line) o ser introducida manualmente por un supervisor.
    Todos los repuestos y conceptos de mano de obra de terceros consumidos se
    vinculan mediante registros MaintenanceItem.
    """

    # ------------------------------------------------------------------
    # Relations / Relaciones
    # ------------------------------------------------------------------
    machine_asset = models.ForeignKey(
        MachineAsset,
        on_delete=models.CASCADE,
        related_name="maintenance_logs",
        verbose_name=_("Activo de Flota"),
        help_text=_("Máquina o vehículo sobre el que se realiza la intervención."),
    )
    work_entry_line = models.ForeignKey(
        "work_order_processor.WorkOrderEntryLine",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="maintenance_logs",
        verbose_name=_("Línea de Parte de Trabajo"),
        help_text=_(
            "Línea del parte de trabajo que originó esta intervención. "
            "Nulo si la intervención se introdujo manualmente."
        ),
    )

    # ------------------------------------------------------------------
    # Intervention data / Datos de la intervención
    # ------------------------------------------------------------------
    fecha = models.DateField(
        _("Fecha"),
        help_text=_("Fecha en que se realizó la intervención de mantenimiento."),
    )
    descripcion = models.TextField(
        _("Descripción"),
        help_text=_(
            "Descripción detallada de los trabajos realizados durante "
            "la intervención."
        ),
    )
    operario = models.CharField(
        _("Operario"),
        max_length=200,
        blank=True,
        help_text=_(
            "Nombre del mecánico o técnico que realizó la intervención. "
            "Se propaga desde el parte de trabajo cuando procede."
        ),
    )
    horas_imputadas = models.DecimalField(
        _("Horas Imputadas"),
        max_digits=6,
        decimal_places=2,
        default=0,
        help_text=_(
            "Horas de mano de obra propia imputadas a esta intervención. "
            "Se calcula a partir del delta de horas del parte de trabajo."
        ),
    )
    observaciones = models.TextField(
        _("Observaciones"),
        blank=True,
        help_text=_("Observaciones adicionales del supervisor o del operario."),
    )

    # ------------------------------------------------------------------
    # Audit / Auditoría
    # ------------------------------------------------------------------
    creado_en = models.DateTimeField(
        _("Creado en"),
        auto_now_add=True,
    )
    actualizado_en = models.DateTimeField(
        _("Actualizado en"),
        auto_now=True,
    )

    class Meta:
        verbose_name        = _("Registro de Mantenimiento")
        verbose_name_plural = _("Registros de Mantenimiento")
        ordering            = ["-fecha", "machine_asset"]

    def __str__(self) -> str:
        return (
            f"[{self.fecha}] {self.machine_asset.codigo} — "
            f"{self.descripcion[:60]}"
        )


# ---------------------------------------------------------------------------
# MaintenanceItem — one line per spare part or third-party item
# Una línea por repuesto o concepto de tercero
# ---------------------------------------------------------------------------

class MaintenanceItem(models.Model):
    """
    Represents a single line item consumed in a maintenance intervention:
    a spare part sourced from the internal warehouse, a spare part or
    component sourced from a third party, or third-party labour (treated
    as a line item in the corresponding delivery note).

    The `tipo` field drives the accounting logic:
      - REPUESTO_ALMACEN  → cost deducted from internal warehouse stock (future).
      - REPUESTO_TERCERO  → cost from an external supplier delivery note.
      - MANO_OBRA_TERCERO → third-party labour detailed in a delivery note,
                            treated as a repuesto line per business convention.

    ---

    Representa una línea individual consumida en una intervención de
    mantenimiento: un repuesto del almacén interno, un repuesto o componente
    de tercero, o mano de obra de tercero (tratada como línea de albarán
    según el convenio del negocio).

    El campo `tipo` impulsa la lógica contable:
      - REPUESTO_ALMACEN  → coste deducido del stock del almacén interno (futuro).
      - REPUESTO_TERCERO  → coste procedente de un albarán de proveedor externo.
      - MANO_OBRA_TERCERO → mano de obra de tercero detallada en albarán,
                            tratada como línea de repuesto por convenio del negocio.
    """

    class ItemType(models.TextChoices):
        REPUESTO_ALMACEN  = "REPUESTO_ALMACEN",  _("Repuesto — Almacén propio")
        REPUESTO_TERCERO  = "REPUESTO_TERCERO",  _("Repuesto — Tercero")
        MANO_OBRA_TERCERO = "MANO_OBRA_TERCERO", _("Mano de obra — Tercero")

    # ------------------------------------------------------------------
    # Relation / Relación
    # ------------------------------------------------------------------
    maintenance_log = models.ForeignKey(
        MaintenanceLog,
        on_delete=models.CASCADE,
        related_name="items",
        verbose_name=_("Registro de Mantenimiento"),
        help_text=_("Intervención de mantenimiento a la que pertenece esta línea."),
    )

    # ------------------------------------------------------------------
    # Item classification / Clasificación del concepto
    # ------------------------------------------------------------------
    tipo = models.CharField(
        _("Tipo"),
        max_length=20,
        choices=ItemType.choices,
        db_index=True,
        help_text=_(
            "Tipo de concepto: repuesto de almacén propio, repuesto de tercero "
            "o mano de obra de tercero."
        ),
    )

    # ------------------------------------------------------------------
    # Item description / Descripción del concepto
    # ------------------------------------------------------------------
    descripcion = models.CharField(
        _("Descripción"),
        max_length=300,
        help_text=_(
            "Nombre o descripción del repuesto, pieza o concepto de mano de obra."
        ),
    )
    referencia = models.CharField(
        _("Referencia"),
        max_length=100,
        blank=True,
        help_text=_(
            "Referencia del repuesto o pieza (código de almacén, referencia del "
            "fabricante, etc.). Vacío para mano de obra de tercero."
        ),
    )

    # ------------------------------------------------------------------
    # Quantity and cost / Cantidad y coste
    # ------------------------------------------------------------------
    cantidad = models.DecimalField(
        _("Cantidad"),
        max_digits=10,
        decimal_places=3,
        default=1,
        help_text=_("Cantidad consumida del repuesto o pieza."),
    )
    coste_unitario = models.DecimalField(
        _("Coste Unitario (€)"),
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_(
            "Coste unitario del repuesto o concepto en euros. "
            "Puede quedar vacío si no se conoce en el momento del registro."
        ),
    )

    # ------------------------------------------------------------------
    # Third-party traceability / Trazabilidad de tercero
    # ------------------------------------------------------------------
    albaran_ref = models.CharField(
        _("Referencia de Albarán"),
        max_length=100,
        blank=True,
        help_text=_(
            "Referencia del albarán o factura del proveedor externo. "
            "Vacío para repuestos de almacén propio. Permite trazar el coste "
            "al documento de tercero cuando el módulo de albaranes esté disponible."
        ),
    )

    # ------------------------------------------------------------------
    # Audit / Auditoría
    # ------------------------------------------------------------------
    creado_en = models.DateTimeField(
        _("Creado en"),
        auto_now_add=True,
    )

    class Meta:
        verbose_name        = _("Línea de Mantenimiento")
        verbose_name_plural = _("Líneas de Mantenimiento")
        ordering            = ["maintenance_log", "tipo", "descripcion"]

    def __str__(self) -> str:
        coste = (
            f"{self.coste_unitario} €/ud."
            if self.coste_unitario is not None
            else "sin coste"
        )
        return (
            f"{self.get_tipo_display()} — {self.descripcion} "
            f"x{self.cantidad} ({coste})"
        )

    @property
    def coste_total(self) -> float | None:
        """
        Returns the total cost of the line item (quantity × unit cost),
        or None if the unit cost is not set.

        ---

        Devuelve el coste total de la línea (cantidad × coste unitario),
        o None si el coste unitario no está definido.
        """
        if self.coste_unitario is None:
            return None
        return float(self.cantidad * self.coste_unitario)
