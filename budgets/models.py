# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/budgets/models.py
"""
Data models for the budgets application.
Defines the full entity graph for the ASISTENCIA budget engine:
Insurer, VehicleType, InsurerTariff, TariffLine, Budget, BudgetLine.
---
Modelos de datos para la aplicación de presupuestos.
Define el grafo completo de entidades para el motor de presupuestos ASISTENCIA:
Insurer, VehicleType, InsurerTariff, TariffLine, Budget, BudgetLine.
"""

from django.db import models

from ivr_config.models import Company, CompanyUser


# ---------------------------------------------------------------------------
# 1. INSURER — Insurance company or direct client with its own tariff.
#    Compañía aseguradora o cliente directo con tarifa propia.
# ---------------------------------------------------------------------------

class Insurer(models.Model):
    """
    Represents an insurance company or direct client that has a negotiated
    tariff with the ASISTENCIA section. Each insurer has its own vehicle
    type catalogue and tariff lines.
    ---
    Representa una compañía aseguradora o cliente directo que tiene una tarifa
    negociada con la sección ASISTENCIA. Cada aseguradora tiene su propio
    catálogo de tipos de vehículo y líneas de tarifa.
    """

    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="insurers",
        verbose_name="Empresa",
        help_text="Empresa cliente a la que pertenece esta aseguradora.",
    )
    name = models.CharField(
        max_length=200,
        verbose_name="Nombre",
        help_text=(
            "Nombre combinado visible en el wizard: "
            "'<Aseguradora> / <Empresa prestadora>' "
            "(ej: 'Europ Assistance / Transgrual')."
        ),
    )
    # Pure insurance company name, without the service company.
    # Nombre puro de la aseguradora, sin la empresa prestadora.
    insurer_company_name = models.CharField(
        max_length=150,
        blank=True,
        default="",
        verbose_name="Nombre aseguradora",
        help_text=(
            "Nombre de la compañía aseguradora pura "
            "(ej: 'Europ Assistance', 'ARAG', 'Mapfre'). "
            "Permite agrupar y filtrar tarifas de la misma aseguradora "
            "atendidas por distintas empresas prestadoras."
        ),
    )
    # Name of the company that actually delivers the service.
    # Nombre de la empresa que presta el servicio en campo.
    service_company_name = models.CharField(
        max_length=150,
        blank=True,
        default="",
        verbose_name="Empresa prestadora",
        help_text=(
            "Empresa que presta el servicio en campo "
            "(ej: 'Transgrual', 'Grúas Alvarez', 'Asistencia y Grúas Granada'). "
            "Junto con insurer_company_name conforma el name combinado del wizard."
        ),
    )
    code = models.CharField(
        max_length=50,
        verbose_name="Código interno",
        help_text="Código identificador interno (ej: AXA, RACE, MAPFRE). Sin espacios.",
    )
    # Some insurers require a management fee percentage on top of the total.
    # Algunas aseguradoras aplican un porcentaje de gastos de gestión sobre el total.
    management_fee_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        verbose_name="Gastos de gestión (%)",
        help_text=(
            "Porcentaje de gastos de gestión aplicado sobre el total del presupuesto. "
            "0 si la aseguradora no aplica este concepto. Ejemplo: COVEI aplica 5%."
        ),
    )
    # Controls whether NYF and loaded surcharges are cumulative or mutually exclusive.
    # Controla si los recargos NYF y vehículo cargado son acumulables o excluyentes.
    surcharges_are_cumulative = models.BooleanField(
        default=False,
        verbose_name="Recargos acumulables",
        help_text=(
            "Si está activo, el recargo nocturno/festivo y el recargo por vehículo "
            "cargado se suman. Si está inactivo (por defecto), se aplica únicamente "
            "el mayor de los dos, conforme a las condiciones generales de la mayoría "
            "de aseguradoras."
        ),
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="Activa",
        help_text="Indica si esta aseguradora está disponible para generar presupuestos.",
    )
    # Distinguishes insurance companies from direct clients with a custom tariff.
    # Distingue compañías aseguradoras de clientes directos con tarifa propia.
    is_insurance_company = models.BooleanField(
        default=True,
        verbose_name="Es compañía aseguradora",
        help_text=(
            "True: compañía aseguradora. "
            "False: cliente particular con tarifa propia. "
            "Controla el label mostrado en el desplegable del asistente de presupuestos."
        ),
    )
    # When True, IVA is always applied on budgets for this insurer.
    # The wizard marks apply_iva automatically and does not allow the
    # operator to uncheck it.
    # Cuando es True, el IVA se aplica siempre en los presupuestos de
    # esta aseguradora. El wizard marca apply_iva automaticamente y no
    # permite al operario desmarcarlo.
    always_apply_iva = models.BooleanField(
        default=False,
        verbose_name="Aplicar IVA siempre",
        help_text=(
            "Si está activo, el IVA se aplica obligatoriamente en todos los "
            "presupuestos de esta aseguradora. El operario no puede desmarcarlo."
        ),
    )
    # When True, this insurer has a special rate table for night/holiday
    # services instead of a simple percentage surcharge.
    # The engine resolves SpecialRateTariff linked to the active InsurerTariff.
    # Cuando es True, esta aseguradora tiene una tabla de tarifas especiales
    # para servicios nocturnos/festivos en lugar de un recargo porcentual simple.
    # El motor resuelve el SpecialRateTariff vinculado a la InsurerTariff activa.
    special_night_holiday_tariff = models.BooleanField(
        default=False,
        verbose_name="Tarifa especial nocturno/festivo",
        help_text=(
            "Si está activo, el motor usa la tabla SpecialRateTariff vinculada "
            "a la tarifa activa en lugar del recargo porcentual estándar. "
            "Aplicable a aseguradoras como RACC/Zurich con precios diferenciados "
            "por franja horaria."
        ),
    )
    notes = models.TextField(
        blank=True,
        default="",
        verbose_name="Notas internas",
        help_text="Observaciones internas sobre esta aseguradora. No visible al operario.",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Fecha de creación")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Fecha de modificación")

    class Meta:
        verbose_name = "Aseguradora"
        verbose_name_plural = "Aseguradoras"
        ordering = ["company__name", "name"]
        unique_together = [("company", "code")]

    def __str__(self):
        return f"{self.company.name} — {self.name}"


# ---------------------------------------------------------------------------
# 2. VEHICLE TYPE — Vehicle type catalogue scoped to a specific insurer.
#    Catálogo de tipos de vehículo con ámbito de una aseguradora concreta.
# ---------------------------------------------------------------------------

class VehicleType(models.Model):
    """
    Defines a vehicle type entry within a specific insurer's catalogue.
    The name field uses the exact wording from the insurer's tariff document
    (e.g. "Camiones hasta 8.000 KG" for RACE, "De 3.501 Kg hasta 6.000 kg de P.M.A."
    for Inter Partner). This ensures the dropdown presented to the operator
    mirrors the official tariff nomenclature exactly.
    ---
    Define una entrada de tipo de vehículo dentro del catálogo de una aseguradora.
    El campo name usa la nomenclatura exacta del documento de tarifa de la aseguradora
    (ej: "Camiones hasta 8.000 KG" para RACE, "De 3.501 Kg hasta 6.000 kg de P.M.A."
    para Inter Partner). Esto garantiza que el desplegable presentado al operario
    refleja exactamente la nomenclatura oficial de la tarifa.
    """

    insurer = models.ForeignKey(
        Insurer,
        on_delete=models.CASCADE,
        related_name="vehicle_types",
        verbose_name="Aseguradora",
        help_text="Aseguradora a cuyo catálogo pertenece este tipo de vehículo.",
    )
    name = models.CharField(
        max_length=300,
        verbose_name="Nombre",
        help_text=(
            "Nombre exacto del tipo de vehículo según la tarifa de la aseguradora. "
            "Se muestra tal cual en el desplegable del formulario de presupuesto."
        ),
    )
    sort_order = models.PositiveSmallIntegerField(
        default=0,
        verbose_name="Orden",
        help_text="Posición en el desplegable. Menor número = aparece antes.",
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="Activo",
        help_text="Indica si este tipo de vehículo está disponible en el formulario.",
    )

    class Meta:
        verbose_name = "Tipo de vehículo"
        verbose_name_plural = "Tipos de vehículo"
        ordering = ["insurer__name", "sort_order", "name"]

    def __str__(self):
        return f"{self.insurer.name} — {self.name}"


# ---------------------------------------------------------------------------
# 3. INSURER TARIFF — Active tariff for a given insurer. Supports history.
#    Tarifa vigente de una aseguradora. Soporta historial de tarifas.
# ---------------------------------------------------------------------------

class InsurerTariff(models.Model):
    """
    Represents a versioned tariff for an insurer. Only one tariff should have
    valid_to=None per insurer at any time (the active tariff). When a new
    tariff is created, the previous one is closed by setting its valid_to date.
    ---
    Representa una tarifa versionada de una aseguradora. Solo una tarifa debe
    tener valid_to=None por aseguradora en cada momento (la tarifa activa).
    Al crear una nueva tarifa, la anterior se cierra estableciendo su valid_to.
    """

    insurer = models.ForeignKey(
        Insurer,
        on_delete=models.CASCADE,
        related_name="tariffs",
        verbose_name="Aseguradora",
        help_text="Aseguradora a la que pertenece esta tarifa.",
    )
    year = models.PositiveSmallIntegerField(
        verbose_name="Año",
        help_text="Año de vigencia de la tarifa (ej: 2026).",
    )
    valid_from = models.DateField(
        verbose_name="Válida desde",
        help_text="Fecha a partir de la cual esta tarifa está en vigor.",
    )
    valid_to = models.DateField(
        null=True,
        blank=True,
        verbose_name="Válida hasta",
        help_text=(
            "Fecha hasta la que esta tarifa estuvo en vigor. "
            "Null indica que es la tarifa actualmente activa."
        ),
    )
    notes = models.TextField(
        blank=True,
        default="",
        verbose_name="Notas",
        help_text="Observaciones sobre esta versión de tarifa (ej: cambios respecto a la anterior).",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Fecha de creación")

    class Meta:
        verbose_name = "Tarifa de aseguradora"
        verbose_name_plural = "Tarifas de aseguradora"
        ordering = ["insurer__name", "-valid_from"]

    def __str__(self):
        status = "activa" if self.valid_to is None else f"hasta {self.valid_to}"
        return f"{self.insurer.name} — {self.year} ({status})"


# ---------------------------------------------------------------------------
# 4. TARIFF LINE — A single billable concept within a tariff.
#    Un concepto facturable individual dentro de una tarifa.
# ---------------------------------------------------------------------------

class TariffLine(models.Model):
    """
    Defines a single billable concept within an insurer tariff.
    Each concept has a unit type (fixed, per km, per hour, per day, percent)
    and a price. Surcharge concepts (NYF, loaded vehicle) are stored as
    PERCENT unit lines with no vehicle_type — they apply to all vehicle types
    of the tariff. Optional fields (min_units, km_threshold) handle tariff
    particularities such as minimum rescue hours or long-distance km thresholds.
    ---
    Define un concepto facturable individual dentro de una tarifa de aseguradora.
    Cada concepto tiene un tipo de unidad (fijo, por km, por hora, por día, porcentaje)
    y un precio. Los conceptos de recargo (NYF, vehículo cargado) se almacenan como
    líneas de tipo PERCENT sin vehicle_type — aplican a todos los tipos de vehículo
    de la tarifa. Los campos opcionales (min_units, km_threshold) gestionan
    particularidades como mínimos de horas de rescate o umbrales de largo recorrido.
    """

    # --- Concept codes ---
    # --- Códigos de concepto ---
    CONCEPT_DEPARTURE       = "DEPARTURE"        # Salida / Enganche
    CONCEPT_SERVICE_LOCAL   = "SERVICE_LOCAL"     # Servicio local / Urbano (forfait sin km)
    CONCEPT_KM_NORMAL       = "KM_NORMAL"         # Kilometro normal
    CONCEPT_KM_LONG         = "KM_LONG"           # Kilometro largo recorrido (>umbral)
    CONCEPT_UNLOCK          = "UNLOCK"            # Desbloqueo / enganche eslingas
    CONCEPT_RESCUE_HOUR     = "RESCUE_HOUR"       # Hora de rescate / extraccion
    CONCEPT_WAIT_HOUR       = "WAIT_HOUR"         # Hora de espera
    CONCEPT_WORKER_HOUR     = "WORKER_HOUR"       # Hora de mano de obra mecanico
    CONCEPT_ASSISTANT_HOUR  = "ASSISTANT_HOUR"    # Hora de ayudante
    CONCEPT_CUSTODY_DAY     = "CUSTODY_DAY"       # Custodia por dia
    CONCEPT_NYF_PERCENT     = "NYF_PERCENT"       # Recargo nocturno / festivo (%)
    CONCEPT_LOADED_PERCENT  = "LOADED_PERCENT"    # Recargo vehiculo cargado (%)

    CONCEPT_CHOICES = [
        (CONCEPT_DEPARTURE,      "Salida / Enganche"),
        (CONCEPT_SERVICE_LOCAL,  "Servicio local / Urbano"),
        (CONCEPT_KM_NORMAL,      "Kilometro normal"),
        (CONCEPT_KM_LONG,        "Kilometro largo recorrido"),
        (CONCEPT_UNLOCK,         "Desbloqueo / Enganche eslingas"),
        (CONCEPT_RESCUE_HOUR,    "Hora de rescate"),
        (CONCEPT_WAIT_HOUR,      "Hora de espera"),
        (CONCEPT_WORKER_HOUR,    "Hora de mano de obra"),
        (CONCEPT_ASSISTANT_HOUR, "Hora de ayudante"),
        (CONCEPT_CUSTODY_DAY,    "Custodia por dia"),
        (CONCEPT_NYF_PERCENT,    "Recargo nocturno/festivo (%)"),
        (CONCEPT_LOADED_PERCENT, "Recargo vehiculo cargado (%)"),
    ]

    # --- Unit types ---
    # --- Tipos de unidad ---
    UNIT_FIXED    = "FIXED"
    UNIT_PER_KM   = "PER_KM"
    UNIT_PER_HOUR = "PER_HOUR"
    UNIT_PER_DAY  = "PER_DAY"
    UNIT_PERCENT  = "PERCENT"

    UNIT_CHOICES = [
        (UNIT_FIXED,    "Importe fijo"),
        (UNIT_PER_KM,   "Por kilometro"),
        (UNIT_PER_HOUR, "Por hora"),
        (UNIT_PER_DAY,  "Por dia"),
        (UNIT_PERCENT,  "Porcentaje"),
    ]

    tariff = models.ForeignKey(
        InsurerTariff,
        on_delete=models.CASCADE,
        related_name="lines",
        verbose_name="Tarifa",
        help_text="Tarifa a la que pertenece esta linea de concepto.",
    )
    # Null vehicle_type = concept applies to all vehicle types (surcharges, unlock, etc.)
    # vehicle_type nulo = concepto aplica a todos los tipos de vehiculo (recargos, desbloqueo, etc.)
    vehicle_type = models.ForeignKey(
        VehicleType,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="tariff_lines",
        verbose_name="Tipo de vehiculo",
        help_text=(
            "Tipo de vehiculo al que aplica esta linea. "
            "Dejar vacio para conceptos genericos de la tarifa "
            "(recargos NYF, vehículo cargado, desbloqueo cuando es precio unico)."
        ),
    )
    concept = models.CharField(
        max_length=30,
        choices=CONCEPT_CHOICES,
        verbose_name="Concepto",
        help_text="Tipo de concepto facturable que representa esta linea.",
    )
    unit = models.CharField(
        max_length=10,
        choices=UNIT_CHOICES,
        verbose_name="Unidad",
        help_text="Unidad de medida del concepto (fijo, por km, por hora, por dia, porcentaje).",
    )
    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name="Precio",
        help_text=(
            "Importe unitario del concepto. Para PERCENT, es el porcentaje "
            "(ej: 50 para un recargo del 50%). Para FIXED, es el importe fijo en euros."
        ),
    )
    # For KM_LONG: threshold above which this km price applies instead of KM_NORMAL.
    # Para KM_LONG: umbral a partir del cual aplica este precio en lugar de KM_NORMAL.
    km_threshold = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name="Umbral de km",
        help_text=(
            "Solo para KM_LARGO. Kilometraje total (ida+vuelta) a partir del cual "
            "aplica esta tarifa reducida. Habitualmente 200. Dejar vacio para KM_NORMAL."
        ),
    )
    # Minimum billable units (e.g. rescue minimum 2 hours in some tariffs).
    # Minimo facturable (ej: rescate minimo 2 horas en algunas tarifas).
    min_units = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Minimo facturable",
        help_text=(
            "Minimo de unidades a facturar aunque el valor real sea inferior. "
            "Ejemplo: hora de rescate con minimo 2 horas. Dejar vacio si no aplica."
        ),
    )
    # Whether this concept requires prior authorization from the insurer.
    # Si este concepto requiere autorizacion previa de la aseguradora.
    requires_authorization = models.BooleanField(
        default=False,
        verbose_name="Requiere autorizacion",
        help_text=(
            "Si esta activo, este concepto debe haber sido autorizado previamente "
            "por la central de la aseguradora antes de poder incluirse en el presupuesto."
        ),
    )

    class Meta:
        verbose_name = "Linea de tarifa"
        verbose_name_plural = "Lineas de tarifa"
        ordering = ["tariff", "vehicle_type__sort_order", "concept"]

    def __str__(self):
        vt = self.vehicle_type.name if self.vehicle_type else "General"
        return f"{self.tariff} — {vt} — {self.get_concept_display()}"


# ---------------------------------------------------------------------------
# 5. BUDGET — A generated budget for a service request.
#    Presupuesto generado para una solicitud de servicio.
# ---------------------------------------------------------------------------

class Budget(models.Model):
    """
    Represents a budget generated by an ASSISTANCE operator for an insurance
    company service request. The total_amount field is the only figure visible
    to the operator. The full breakdown is stored in BudgetLine records and
    is visible to ADMIN users only for audit purposes.
    ---
    Representa un presupuesto generado por un operario de ASISTENCIA para una
    solicitud de servicio de una aseguradora. El campo total_amount es la unica
    cifra visible para el operario. El desglose completo se almacena en registros
    BudgetLine y es visible unicamente para ADMIN con fines de auditoria.
    """

    STATUS_DRAFT    = "DRAFT"
    STATUS_ACCEPTED = "ACCEPTED"
    STATUS_REJECTED = "REJECTED"

    STATUS_CHOICES = [
        (STATUS_DRAFT,    "Borrador"),
        (STATUS_ACCEPTED, "Aceptado"),
        (STATUS_REJECTED, "Rechazado"),
    ]

    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="budgets",
        verbose_name="Empresa",
        help_text="Empresa cliente que genera el presupuesto.",
    )
    insurer = models.ForeignKey(
        Insurer,
        on_delete=models.PROTECT,
        related_name="budgets",
        verbose_name="Aseguradora",
        help_text="Aseguradora o cliente para el que se genera el presupuesto.",
    )
    # Snapshot of the tariff used — preserved even if the tariff is later replaced.
    # Snapshot de la tarifa usada — se conserva aunque la tarifa sea sustituida.
    tariff = models.ForeignKey(
        InsurerTariff,
        on_delete=models.PROTECT,
        related_name="budgets",
        verbose_name="Tarifa aplicada",
        help_text="Version de tarifa que se uso para calcular este presupuesto.",
    )
    operator = models.ForeignKey(
        CompanyUser,
        on_delete=models.PROTECT,
        related_name="budgets",
        verbose_name="Operario",
        help_text="Operario que genero el presupuesto.",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Fecha de creacion",
    )
    service_date = models.DateField(
        verbose_name="Fecha del servicio",
        help_text="Fecha en la que se va a realizar el servicio.",
    )
    vehicle_type = models.ForeignKey(
        VehicleType,
        on_delete=models.PROTECT,
        related_name="budgets",
        verbose_name="Tipo de vehiculo",
        help_text="Tipo de vehiculo asistido segun la nomenclatura de la aseguradora.",
    )
    # Service base — selected from the insurer's active bases in the wizard.
    # When the insurer has exactly one active base, it is assigned automatically.
    # Base de servicio — seleccionada entre las bases activas de la aseguradora.
    # Cuando la aseguradora tiene exactamente una base activa, se asigna automaticamente.
    base = models.ForeignKey(
        "Base",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="budgets",
        verbose_name="Base",
        help_text=(
            "Base de servicio desde la que se realiza el servicio. "
            "Determina el calendario laboral para la deteccion automatica "
            "de festivos. Nullable para compatibilidad con presupuestos "
            "anteriores a la implementacion del modelo Base."
        ),
    )
    # Overnight service: two departures + two km phases.
    # Servicio de pernocta: dos salidas + dos fases de kilometros.
    is_overnight = models.BooleanField(
        default=False,
        verbose_name="Pernocta",
        help_text=(
            "Activo cuando el servicio se realiza en dos fases: recogida del vehiculo "
            "el primer dia y traslado al destino al dia siguiente. Genera dos salidas "
            "y dos tramos de kilometraje independientes."
        ),
    )
    km_phase1 = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        verbose_name="Km fase 1 (ida+vuelta)",
        help_text=(
            "Kilometros totales ida y vuelta de la primera fase del servicio. "
            "Si no es pernocta, estos son los unicos kilometros del servicio."
        ),
    )
    km_phase2 = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Km fase 2 (ida+vuelta)",
        help_text=(
            "Kilometros totales ida y vuelta de la segunda fase del servicio. "
            "Solo aplica cuando is_overnight es True."
        ),
    )
    km_total = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        verbose_name="Km totales",
        help_text="Suma de km_phase1 + km_phase2. Calculado automaticamente al guardar.",
    )
    has_unlock = models.BooleanField(
        default=False,
        verbose_name="Desbloqueo",
        help_text=(
            "Indica si el servicio incluye desbloqueo o enganche con eslingas. "
            "No aplica a remolques (se desenganchan/enganchan directamente en la quinta rueda)."
        ),
    )
    # Marked manually by the operator when the service is performed at night.
    # Independently of is_holiday, which is calculated automatically by the engine.
    # Marcado manualmente por el operario cuando el servicio es nocturno.
    # Independiente de is_holiday, calculado automaticamente por el motor.
    is_night = models.BooleanField(
        default=False,
        verbose_name="Nocturno",
        help_text=(
            "Indica si el servicio se realiza en horario nocturno. "
            "Marcado manualmente por el operario en el wizard. "
            "Independiente de is_holiday, que es calculado automaticamente "
            "por el motor segun la fecha del servicio y el calendario laboral."
        ),
    )
    is_night_or_holiday = models.BooleanField(
        default=False,
        verbose_name="Nocturno / Festivo",
        help_text=(
            "Calculado automaticamente por el motor: True si is_night OR is_holiday. "
            "Activa el recargo NYF de la tarifa de la aseguradora. "
            "No editar directamente — se recalcula en cada llamada a calculate_budget()."
        ),
    )
    is_loaded = models.BooleanField(
        default=False,
        verbose_name="Vehiculo cargado",
        help_text=(
            "Indica si el vehiculo asistido va cargado. "
            "Activa el recargo por vehiculo cargado si la tarifa lo contempla."
        ),
    )
    # Optional service concepts — only shown in the form if the tariff includes them.
    # Conceptos opcionales — solo aparecen en el formulario si la tarifa los contempla.
    wait_hours = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Horas de espera",
        help_text="Numero de horas de espera facturables. Solo si la tarifa contempla este concepto.",
    )
    rescue_hours = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Horas de rescate",
        help_text="Numero de horas de rescate facturables. Solo si la tarifa contempla este concepto.",
    )
    assistant_hours = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Horas de ayudante",
        help_text="Numero de horas de ayudante facturables. Solo si la tarifa contempla este concepto.",
    )
    worker_hours = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Horas de mano de obra",
        help_text="Numero de horas de mano de obra mecanica. Solo si la tarifa contempla este concepto.",
    )
    custody_days = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        verbose_name="Dias de custodia",
        help_text="Numero de dias de custodia del vehiculo. Solo si la tarifa contempla este concepto.",
    )
    extra_notes = models.TextField(
        blank=True,
        default="",
        verbose_name="Notas adicionales",
        help_text="Observaciones libres del operario sobre este presupuesto. Uso interno.",
    )
    # Whether IVA should be applied to the total amount.
    # Si el IVA debe aplicarse al importe total.
    apply_iva = models.BooleanField(
        default=False,
        verbose_name="Aplicar IVA",
        help_text=(
            "Indica si se debe aplicar el IVA vigente sobre el importe base del presupuesto. "
            "El porcentaje de IVA se define como constante IVA_PERCENT en budgets/services.py."
        ),
    )
    total_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name="Total presupuesto",
        help_text="Importe total calculado por el motor. Es la unica cifra visible para el operario.",
    )
    # Total amount including IVA. Null when apply_iva is False.
    # Persisted in DB so the result view does not need to recalculate.
    # Importe total con IVA incluido. Nulo cuando apply_iva es False.
    # Persistido en BD para que la vista de resultado no necesite recalcular.
    total_amount_with_iva = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Total con IVA",
        help_text=(
            "Importe total del presupuesto con IVA incluido. "
            "Solo se rellena cuando apply_iva es True. "
            "El porcentaje de IVA aplicado se define en IVA_PERCENT en budgets/services.py."
        ),
    )
    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default=STATUS_DRAFT,
        verbose_name="Estado",
        help_text=(
            "DRAFT: presupuesto calculado, pendiente de respuesta. "
            "ACCEPTED: la aseguradora o cliente ha aceptado el presupuesto. "
            "REJECTED: el presupuesto ha sido rechazado."
        ),
    )

    class Meta:
        verbose_name = "Presupuesto"
        verbose_name_plural = "Presupuestos"
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        """
        Overrides save to auto-calculate km_total from phase values before persisting.
        ---
        Sobreescribe save para calcular km_total automaticamente desde las fases antes de persistir.
        """
        self.km_total = (self.km_phase1 or 0) + (self.km_phase2 or 0)
        super().save(*args, **kwargs)

    def __str__(self):
        return (
            f"Presupuesto #{self.pk} — {self.insurer.name} — "
            f"{self.vehicle_type.name} — {self.total_amount} EUR"
        )


# ---------------------------------------------------------------------------
# 6. BUDGET LINE — Breakdown line for a generated budget (ADMIN audit only).
#    Linea de desglose de un presupuesto generado (solo auditoria ADMIN).
# ---------------------------------------------------------------------------

class BudgetLine(models.Model):
    """
    Stores the individual calculation breakdown of a Budget. Each line
    represents one applied concept with its units, unit price and subtotal.
    These records are never visible to the ASSISTANCE operator — they exist
    exclusively for ADMIN audit and verification of the calculation engine.
    ---
    Almacena el desglose individual del calculo de un Budget. Cada linea
    representa un concepto aplicado con sus unidades, precio unitario y subtotal.
    Estos registros nunca son visibles para el operario ASSISTANCE — existen
    exclusivamente para la auditoria y verificacion ADMIN del motor de calculo.
    """

    budget = models.ForeignKey(
        Budget,
        on_delete=models.CASCADE,
        related_name="lines",
        verbose_name="Presupuesto",
        help_text="Presupuesto al que pertenece esta linea de desglose.",
    )
    concept_code = models.CharField(
        max_length=30,
        verbose_name="Codigo de concepto",
        help_text="Codigo interno del concepto aplicado (ej: DEPARTURE, KM_NORMAL, NYF_PERCENT).",
    )
    concept_label = models.CharField(
        max_length=200,
        verbose_name="Descripcion del concepto",
        help_text="Nombre legible en castellano del concepto aplicado.",
    )
    units = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        verbose_name="Unidades",
        help_text="Cantidad de unidades aplicadas (ej: 2 salidas, 115 km, 1.5 horas).",
    )
    unit_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name="Precio unitario",
        help_text="Precio unitario de la linea de tarifa aplicada.",
    )
    subtotal = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name="Subtotal",
        help_text="Resultado de units x unit_price para esta linea.",
    )
    # Distinguishes surcharge lines (NYF, loaded) from base concept lines.
    # Distingue las lineas de recargo (NYF, cargado) de las lineas de concepto base.
    is_surcharge = models.BooleanField(
        default=False,
        verbose_name="Es recargo",
        help_text=(
            "Activo para lineas de recargo porcentual (nocturno/festivo, vehiculo cargado). "
            "Inactivo para conceptos base (salida, km, desbloqueo, etc.)."
        ),
    )
    sort_order = models.PositiveSmallIntegerField(
        default=0,
        verbose_name="Orden",
        help_text="Orden de visualizacion en el desglose de auditoria ADMIN.",
    )

    class Meta:
        verbose_name = "Linea de presupuesto"
        verbose_name_plural = "Lineas de presupuesto"
        ordering = ["budget", "sort_order"]

    def __str__(self):
        return (
            f"Presupuesto #{self.budget_id} — "
            f"{self.concept_label} — {self.units} x {self.unit_price} = {self.subtotal}"
        )


# ---------------------------------------------------------------------------
# 7. SPECIAL RATE TARIFF — Night/holiday special rate table for an insurer.
#    Tabla de tarifas especiales nocturno/festivo vinculada a una InsurerTariff.
# ---------------------------------------------------------------------------

class SpecialRateTariff(models.Model):
    """
    Stores the night/holiday special rate table for an insurer that uses
    differentiated pricing instead of a flat percentage surcharge.
    Linked to the active InsurerTariff via a OneToOneField so there is
    exactly one special rate table per tariff version.
    When the insurer.special_night_holiday_tariff flag is True and a
    SpecialRateTariff exists for the active tariff, the engine uses
    SpecialRateLine records instead of applying NIGHT_HOLIDAY_PERCENT.
    ---
    Almacena la tabla de tarifas especiales nocturno/festivo para una
    aseguradora con precios diferenciados en lugar de recargo porcentual plano.
    Vinculada a la InsurerTariff activa mediante OneToOneField para garantizar
    exactamente una tabla especial por versión de tarifa.
    Cuando el flag insurer.special_night_holiday_tariff es True y existe un
    SpecialRateTariff para la tarifa activa, el motor usa los registros
    SpecialRateLine en lugar de aplicar NIGHT_HOLIDAY_PERCENT.
    """

    insurer_tariff = models.OneToOneField(
        InsurerTariff,
        on_delete=models.PROTECT,
        related_name="special_rate",
        verbose_name="Tarifa base",
        help_text=(
            "Tarifa activa de la aseguradora a la que está vinculada "
            "esta tabla de precios especiales nocturno/festivo."
        ),
    )
    notes = models.TextField(
        blank=True,
        default="",
        verbose_name="Notas internas",
        help_text="Observaciones internas sobre esta tabla de tarifas especiales.",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Fecha de creación",
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Fecha de modificación",
    )

    class Meta:
        verbose_name = "Tarifa especial nocturno/festivo"
        verbose_name_plural = "Tarifas especiales nocturno/festivo"

    def __str__(self):
        return f"Tarifa especial nocturno/festivo — {self.insurer_tariff}"


# ---------------------------------------------------------------------------
# 8. SPECIAL RATE LINE — Individual price line for the special rate table.
#    Línea de precio individual de la tabla de tarifas especiales.
# ---------------------------------------------------------------------------

class SpecialRateLine(models.Model):
    """
    Stores one price line within a SpecialRateTariff. Mirrors the structure
    of TariffLine (concept, unit, price, vehicle_type) but applies exclusively
    to night/holiday service conditions.
    When vehicle_type is None, the line applies to all vehicle types
    (generic concepts such as WAIT_HOUR, RESCUE_HOUR, UNLOCK).
    ---
    Almacena una línea de precio dentro de un SpecialRateTariff. Replica la
    estructura de TariffLine (concepto, unidad, precio, tipo de vehículo) pero
    aplica exclusivamente a condiciones de servicio nocturno/festivo.
    Cuando vehicle_type es None, la línea aplica a todos los tipos de vehículo
    (conceptos genéricos como WAIT_HOUR, RESCUE_HOUR, UNLOCK).
    """

    special_rate_tariff = models.ForeignKey(
        SpecialRateTariff,
        on_delete=models.CASCADE,
        related_name="lines",
        verbose_name="Tarifa especial",
        help_text="Tabla de tarifas especiales a la que pertenece esta línea.",
    )
    vehicle_type = models.ForeignKey(
        VehicleType,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="special_rate_lines",
        verbose_name="Tipo de vehículo",
        help_text=(
            "Tipo de vehículo al que aplica esta línea. "
            "Null indica que aplica a todos los tipos (concepto genérico)."
        ),
    )
    concept = models.CharField(
        max_length=30,
        verbose_name="Concepto",
        help_text="Código del concepto (DEPARTURE, KM_NORMAL, KM_LONG, SERVICE_LOCAL, etc.).",
    )
    unit = models.CharField(
        max_length=10,
        verbose_name="Unidad",
        help_text="Unidad de medida del concepto (FIXED, PER_KM, PERCENT).",
    )
    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name="Precio",
        help_text="Precio unitario para condiciones nocturnas/festivas.",
    )
    km_threshold = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Umbral km",
        help_text=(
            "Umbral de km a partir del cual se aplica la tarifa de largo recorrido. "
            "Solo relevante para conceptos KM_NORMAL que coexisten con KM_LONG."
        ),
    )
    min_units = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Unidades mínimas",
        help_text=(
            "Unidades mínimas facturables para este concepto. "
            "Ej: rescate mínimo 2 horas."
        ),
    )

    class Meta:
        verbose_name = "Línea de tarifa especial"
        verbose_name_plural = "Líneas de tarifa especial"
        ordering = ["special_rate_tariff", "vehicle_type__sort_order", "concept"]

    def __str__(self):
        vt = self.vehicle_type.name if self.vehicle_type else "Genérico"
        return (
            f"{self.special_rate_tariff} — "
            f"{vt} — {self.concept} — {self.price}"
        )


# ---------------------------------------------------------------------------
# 9. BASE — Physical service base linked to an insurer/provider pair.
#    Base fisica de servicio vinculada a un par aseguradora/prestadora.
# ---------------------------------------------------------------------------

class Base(models.Model):
    """
    Represents a physical service base for a specific insurer/provider pair.
    Each Insurer (which encapsulates one aseguradora+prestadora combination)
    may have one or more active bases. When more than one active base exists
    for the selected insurer, the wizard presents a dropdown to the operator.
    When exactly one active base exists, it is assigned automatically.

    Coordinates (latitude/longitude) are used as the route origin in the
    Google Maps Routes API call (future Hito). If specific coordinates are
    not provided, the municipality field is used for geocoding. Once geocoded,
    the result is persisted back to latitude/longitude so subsequent calls
    do not hit the geocoding API again.

    The labor_calendar field stores the public holidays for the base locality
    in JSON format, populated automatically by the scraper command
    `sync_base_calendars` which calls the calendariosnacionales.com public API.
    The _is_holiday() engine function reads this field to determine whether
    a given service date triggers the NYF surcharge.
    ---
    Representa una base fisica de servicio para un par aseguradora/prestadora.
    Cada Insurer (que encapsula una combinacion aseguradora+prestadora) puede
    tener una o mas bases activas. Cuando existe mas de una base activa para
    la aseguradora seleccionada, el wizard presenta un desplegable al operario.
    Cuando existe exactamente una base activa, se asigna automaticamente.

    Las coordenadas (latitud/longitud) se usan como origen de ruta en la llamada
    a la Routes API de Google Maps (hito futuro). Si no se dan coordenadas
    especificas, el campo municipality se usa para geocodificar. Una vez
    geocodificado, el resultado se persiste en latitud/longitud para que las
    llamadas posteriores no vuelvan a llamar a la API de geocodificacion.

    El campo labor_calendar almacena los festivos de la localidad de la base
    en formato JSON, poblado automaticamente por el comando scraper
    `sync_base_calendars` que llama a la API publica de calendariosnacionales.com.
    La funcion del motor _is_holiday() lee este campo para determinar si una
    fecha de servicio dada activa el recargo NYF.
    """

    insurer = models.ForeignKey(
        Insurer,
        on_delete=models.CASCADE,
        related_name="bases",
        verbose_name="Aseguradora",
        help_text=(
            "Par aseguradora/prestadora al que pertenece esta base. "
            "Una misma prestadora puede tener bases distintas por cada par."
        ),
    )
    name = models.CharField(
        max_length=150,
        verbose_name="Nombre de la base",
        help_text="Nombre identificativo de la base (ej: 'Sevilla', 'Granada Norte').",
    )
    municipality = models.CharField(
        max_length=150,
        verbose_name="Municipio",
        help_text=(
            "Municipio donde se ubica la base. Se usa para geocodificar las "
            "coordenadas y para consultar el calendario laboral local via API. "
            "Debe coincidir con el nombre oficial del municipio en espanol "
            "(ej: 'Sevilla', 'Granada', 'Jerez de la Frontera')."
        ),
    )
    # Optional precise coordinates. Populated by the geocoding pipeline
    # or entered manually from the panel. When null, municipality is used
    # as the geocoding source and the result is stored here on first call.
    # Coordenadas precisas opcionales. Pobladas por el pipeline de geocodificacion
    # o introducidas manualmente desde el panel. Cuando son nulas, municipality
    # se usa como fuente de geocodificacion y el resultado se almacena aqui.
    latitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
        verbose_name="Latitud",
        help_text=(
            "Latitud de la base en grados decimales. "
            "Si es nula, se geocodifica el municipio en la primera llamada "
            "y se persiste el resultado aqui automaticamente."
        ),
    )
    longitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
        verbose_name="Longitud",
        help_text=(
            "Longitud de la base en grados decimales. "
            "Si es nula, se geocodifica el municipio en la primera llamada "
            "y se persiste el resultado aqui automaticamente."
        ),
    )
    # Public holiday calendar for this base locality in JSON format.
    # Populated by the management command sync_base_calendars.
    # Format: list of ISO date strings, e.g. ["2026-01-01", "2026-01-06", ...]
    # Calendario de festivos publicos de la localidad de la base en formato JSON.
    # Poblado por el comando de gestion sync_base_calendars.
    # Formato: lista de cadenas de fecha ISO, ej: ["2026-01-01", "2026-01-06", ...]
    labor_calendar = models.TextField(
        blank=True,
        default="",
        verbose_name="Calendario laboral",
        help_text=(
            "Festivos locales de la base en formato JSON (lista de fechas ISO). "
            "Poblado automaticamente por el comando sync_base_calendars. "
            "Incluye festivos nacionales, autonomicos y locales del municipio."
        ),
    )
    # Calendar last synced timestamp — used to detect stale calendars.
    # Timestamp de ultima sincronizacion del calendario — detecta calendarios obsoletos.
    calendar_synced_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Ultimo sync de calendario",
        help_text=(
            "Fecha y hora de la ultima sincronizacion del calendario laboral "
            "con la API de calendariosnacionales.com. Null si nunca se ha sincronizado."
        ),
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="Activa",
        help_text="Indica si esta base esta disponible para seleccion en el wizard.",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Fecha de creacion")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Fecha de modificacion")

    class Meta:
        verbose_name = "Base"
        verbose_name_plural = "Bases"
        ordering = ["insurer__name", "name"]
        unique_together = [("insurer", "name")]

    def __str__(self):
        return f"{self.insurer.name} — {self.name}"
