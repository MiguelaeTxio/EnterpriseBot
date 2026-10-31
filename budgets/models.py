"""
Data models for the budgets application.
Defines the full entity graph for the ASISTENCIA budget engine:
Insurer, VehicleType, InsurerTariff, TariffLine, Budget, BudgetLine.
---
Modelos de datos para la aplicación de presupuestos.
Define el grafo completo de entidades para el motor de presupuestos ASISTENCIA:
Insurer, VehicleType, InsurerTariff, TariffLine, Budget, BudgetLine.
"""

import os as _os
from decimal import Decimal

from django.core.serializers.json import DjangoJSONEncoder
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
            "(ej: 'Transgrual', 'Grúas Alvarez', "
            "'Asistencia y Grúas Granada'). "
            "Junto con insurer_company_name conforma el name combinado "
            "del wizard."
        ),
    )
    code = models.CharField(
        max_length=50,
        verbose_name="Código interno",
        help_text=(
            "Código identificador interno (ej: AXA, RACE, MAPFRE). "
            "Sin espacios."
        ),
    )
    # Some insurers require a management fee percentage on top of the total.
    # Algunas aseguradoras aplican un porcentaje de gastos de gestión sobre
    # el total.
    management_fee_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        verbose_name="Gastos de gestión (%)",
        help_text=(
            "Porcentaje de gastos de gestión aplicado sobre el total del "
            "presupuesto. 0 si la aseguradora no aplica este concepto. "
            "Ejemplo: COVEI aplica 5%."
        ),
    )
    # Controls whether NYF and loaded surcharges are cumulative or mutually
    # exclusive.
    # Controla si los recargos NYF y vehículo cargado son acumulables o
    # excluyentes.
    surcharges_are_cumulative = models.BooleanField(
        default=False,
        verbose_name="Recargos acumulables",
        help_text=(
            "Si está activo, el recargo nocturno/festivo y el recargo por "
            "vehículo cargado se suman. Si está inactivo (por defecto), se "
            "aplica únicamente el mayor de los dos, conforme a las "
            "condiciones generales de la mayoría de aseguradoras."
        ),
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="Activa",
        help_text=(
            "Indica si esta aseguradora está disponible para generar "
            "presupuestos."
        ),
    )
    # Distinguishes insurance companies from direct clients with a custom
    # tariff.
    # Distingue compañías aseguradoras de clientes directos con tarifa propia.
    is_insurance_company = models.BooleanField(
        default=True,
        verbose_name="Es compañía aseguradora",
        help_text=(
            "True: compañía aseguradora. "
            "False: cliente particular con tarifa propia. "
            "Controla el label mostrado en el desplegable del asistente de "
            "presupuestos."
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
            "presupuestos de esta aseguradora. El operario no puede "
            "desmarcarlo."
        ),
    )
    # When True, this insurer has a special rate table for night/holiday
    # services instead of a simple percentage surcharge.
    # The engine resolves SpecialRateTariff linked to the active InsurerTariff.
    # Cuando es True, esta aseguradora tiene una tabla de tarifas especiales
    # para servicios nocturnos/festivos en lugar de un recargo porcentual
    # simple.
    # El motor resuelve el SpecialRateTariff vinculado a la InsurerTariff
    # activa.
    special_night_holiday_tariff = models.BooleanField(
        default=False,
        verbose_name="Tarifa especial nocturno/festivo",
        help_text=(
            "Si está activo, el motor usa la tabla SpecialRateTariff "
            "vinculada a la tarifa activa en lugar del recargo porcentual "
            "estándar. Aplicable a aseguradoras como RACC/Zurich con "
            "precios diferenciados por franja horaria."
        ),
    )
    # Km threshold below which a service is considered local
    # (SERVICE_LOCAL forfait).
    # Umbral de km por debajo del cual el servicio se considera local
    # (forfait SERVICE_LOCAL).
    local_service_km_threshold = models.PositiveSmallIntegerField(
        default=20,
        null=True,
        blank=True,
        verbose_name="Umbral servicio local (km)",
        help_text=(
            "Kilometraje total máximo (fase 1 + fase 2) para considerar el "
            "servicio como local y aplicar el forfait SERVICE_LOCAL de la "
            "tarifa. Valor por defecto: 20 km. "
            "Dejar vacío (null) si esta aseguradora no contempla servicio "
            "local."
        ),
    )
    notes = models.TextField(
        blank=True,
        default="",
        verbose_name="Notas internas",
        help_text=(
            "Observaciones internas sobre esta aseguradora. "
            "No visible al operario."
        ),
    )
    # Night schedule assigned to this insurer. When null, the engine falls back
    # to the company default NightSchedule (is_default=True), and further to
    # Company.night_start / Company.night_end for full backwards compatibility.
    # Horario nocturno asignado a esta aseguradora. Si es nulo, el motor usa
    # el NightSchedule por defecto de la empresa (is_default=True) y, en su
    # defecto, Company.night_start / Company.night_end para compatibilidad
    # hacia atrás.
    night_schedule = models.ForeignKey(
        "NightSchedule",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="insurers",
        verbose_name="Horario nocturno",
        help_text=(
            "Franja horaria nocturna asignada a esta aseguradora. "
            "Si no se asigna, el motor usa el horario nocturno por defecto "
            "de la empresa. Si tampoco existe, usa "
            "Company.night_start/night_end."
        ),
    )
    created_at = models.DateTimeField(
        auto_now_add=True, verbose_name="Fecha de creación"
    )
    updated_at = models.DateTimeField(
        auto_now=True, verbose_name="Fecha de modificación"
    )

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
    (e.g. "Camiones hasta 8.000 KG" for RACE,
    "De 3.501 Kg hasta 6.000 kg de P.M.A." for Inter Partner). This ensures
    the dropdown presented to the operator mirrors the official tariff
    nomenclature exactly.
    ---
    Define una entrada de tipo de vehículo dentro del catálogo de una
    aseguradora. El campo name usa la nomenclatura exacta del documento de
    tarifa de la aseguradora (ej: "Camiones hasta 8.000 KG" para RACE,
    "De 3.501 Kg hasta 6.000 kg de P.M.A." para Inter Partner). Esto
    garantiza que el desplegable presentado al operario refleja exactamente
    la nomenclatura oficial de la tarifa.
    """

    insurer = models.ForeignKey(
        Insurer,
        on_delete=models.CASCADE,
        related_name="vehicle_types",
        verbose_name="Aseguradora",
        help_text=(
            "Aseguradora a cuyo catálogo pertenece este tipo de vehículo."
        ),
    )
    name = models.CharField(
        max_length=300,
        verbose_name="Nombre",
        help_text=(
            "Nombre exacto del tipo de vehículo según la tarifa de la "
            "aseguradora. Se muestra tal cual en el desplegable del "
            "formulario de presupuesto."
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
        help_text=(
            "Indica si este tipo de vehículo está disponible en el "
            "formulario."
        ),
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
        help_text=(
            "Observaciones sobre esta versión de tarifa "
            "(ej: cambios respecto a la anterior)."
        ),
    )
    created_at = models.DateTimeField(
        auto_now_add=True, verbose_name="Fecha de creación"
    )

    class Meta:
        verbose_name = "Tarifa de aseguradora"
        verbose_name_plural = "Tarifas de aseguradora"
        ordering = ["insurer__name", "-valid_from"]

    def __str__(self):
        status = (
            "activa" if self.valid_to is None else f"hasta {self.valid_to}"
        )
        return f"{self.insurer.name} — {self.year} ({status})"


# ---------------------------------------------------------------------------
# 4. TARIFF CONCEPT — Catalogue of billable concept types.
#    Catálogo de tipos de concepto facturable.
# ---------------------------------------------------------------------------

class TariffConcept(models.Model):
    """
    Defines a billable concept type that can appear as a TariffLine.
    System concepts (is_system=True, company=None) represent the 12 built-in
    codes that the calculation engine knows how to handle. Custom concepts
    (is_system=False, company=FK) are defined per company and are treated
    as FIXED or PER_HOUR amounts by the engine — they appear in the
    add-line dropdown for that company's insurers only.
    ---
    Define un tipo de concepto facturable que puede aparecer como TariffLine.
    Los conceptos de sistema (is_system=True, company=None) representan los
    12 códigos internos que el motor de cálculo sabe manejar. Los conceptos
    personalizados (is_system=False, company=FK) se definen por empresa y el
    motor los trata como importe fijo o por hora — aparecen en el desplegable
    de añadir línea únicamente para las aseguradoras de esa empresa.
    """

    # System concept codes — referenced by the calculation engine.
    # Códigos de conceptos de sistema — referenciados por el motor de cálculo.
    CODE_DEPARTURE = "DEPARTURE"
    CODE_SERVICE_LOCAL = "SERVICE_LOCAL"
    CODE_KM_NORMAL = "KM_NORMAL"
    CODE_KM_LONG = "KM_LONG"
    CODE_UNLOCK = "UNLOCK"
    CODE_RESCUE_HOUR = "RESCUE_HOUR"
    CODE_WAIT_HOUR = "WAIT_HOUR"
    CODE_WORKER_HOUR = "WORKER_HOUR"
    CODE_ASSISTANT_HOUR = "ASSISTANT_HOUR"
    CODE_CUSTODY_DAY = "CUSTODY_DAY"
    CODE_NYF_PERCENT = "NYF_PERCENT"
    CODE_LOADED_PERCENT = "LOADED_PERCENT"
    # Toll breakdown codes — not TariffLine-backed; generated by the engine.
    # Códigos de desglose de peajes — no vinculados a TariffLine; los genera
    # el motor de cálculo dinámicamente.
    CODE_TOLL_SEGMENT = "TOLL_SEGMENT"
    CODE_TOLL_MARKUP = "TOLL_MARKUP"

    code = models.CharField(
        max_length=50,
        unique=True,
        verbose_name="Código",
        help_text=(
            "Identificador interno del concepto. Único en todo el sistema. "
            "Los conceptos de sistema usan mayúsculas (ej: DEPARTURE). "
            "Los conceptos personalizados se generan automáticamente."
        ),
    )
    label = models.CharField(
        max_length=200,
        verbose_name="Nombre visible",
        help_text=(
            "Texto mostrado en el desplegable al añadir una línea de tarifa "
            "y en los documentos exportados."
        ),
    )
    default_unit = models.CharField(
        max_length=10,
        verbose_name="Unidad por defecto",
        help_text=(
            "Tipo de unidad preseleccionado al crear una línea con este "
            "concepto. El usuario puede cambiarlo."
        ),
    )
    # True = built-in system concept. Protected from edit/delete via UI.
    # True = concepto de sistema incorporado. Protegido de edición/borrado
    # en UI.
    is_system = models.BooleanField(
        default=False,
        verbose_name="Concepto de sistema",
        help_text=(
            "Si está activo, este concepto forma parte del catálogo base "
            "del motor de cálculo y no puede editarse ni eliminarse desde "
            "el panel."
        ),
    )
    # Null = global concept (system). FK = concept owned by a specific
    # company.
    # Null = concepto global (sistema). FK = concepto propio de una empresa
    # concreta.
    company = models.ForeignKey(
        "ivr_config.Company",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="custom_tariff_concepts",
        verbose_name="Empresa",
        help_text=(
            "Empresa propietaria de este concepto. "
            "Nulo para conceptos de sistema accesibles a todas las empresas."
        ),
    )
    sort_order = models.PositiveSmallIntegerField(
        default=0,
        verbose_name="Orden",
        help_text="Posición en el desplegable. Menor número = aparece antes.",
    )

    class Meta:
        verbose_name = "Concepto de tarifa"
        verbose_name_plural = "Conceptos de tarifa"
        ordering = ["sort_order", "label"]

    def __str__(self):
        scope = "Sistema" if self.company is None else self.company.name
        return f"[{scope}] {self.label} ({self.code})"


# ---------------------------------------------------------------------------
# 5. TARIFF LINE — A single billable concept within a tariff.
#    Un concepto facturable individual dentro de una tarifa.
# ---------------------------------------------------------------------------

class TariffLine(models.Model):
    """
    Defines a single billable concept within an insurer tariff.
    Each concept has a unit type (fixed, per km, per hour, per day, percent)
    and a price. Surcharge concepts (NYF, loaded vehicle) are stored as
    PERCENT unit lines with no vehicle_type — they apply to all vehicle types
    of the tariff. Optional fields (min_units, km_threshold) handle tariff
    particularities such as minimum rescue hours or long-distance km
    thresholds.

    The concept field is a FK to TariffConcept. The calculation engine
    references concepts by their code (concept.code), not by PK.
    ---
    Define un concepto facturable individual dentro de una tarifa de
    aseguradora. Cada concepto tiene un tipo de unidad (fijo, por km, por
    hora, por día, porcentaje) y un precio. Los conceptos de recargo (NYF,
    vehículo cargado) se almacenan como líneas de tipo PERCENT sin
    vehicle_type — aplican a todos los tipos de vehículo de la tarifa. Los
    campos opcionales (min_units, km_threshold) gestionan particularidades
    como mínimos de horas de rescate o umbrales de largo recorrido.

    El campo concept es un FK a TariffConcept. El motor de cálculo referencia
    los conceptos por su code (concept.code), no por PK.
    """

    # --- Unit types ---
    # --- Tipos de unidad ---
    UNIT_FIXED = "FIXED"
    UNIT_PER_KM = "PER_KM"
    UNIT_PER_HOUR = "PER_HOUR"
    UNIT_PER_DAY = "PER_DAY"
    UNIT_PERCENT = "PERCENT"

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
    # Null vehicle_type = concept applies to all vehicle types (surcharges,
    # unlock, etc.)
    # vehicle_type nulo = concepto aplica a todos los tipos de vehiculo
    # (recargos, desbloqueo, etc.)
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
            "(recargos NYF, vehículo cargado, desbloqueo cuando es precio "
            "unico)."
        ),
    )
    concept = models.ForeignKey(
        TariffConcept,
        on_delete=models.PROTECT,
        related_name="tariff_lines",
        verbose_name="Concepto",
        help_text=(
            "Tipo de concepto facturable que representa esta línea. "
            "Selecciona un concepto del catálogo — sistema o personalizado "
            "de tu empresa."
        ),
    )
    unit = models.CharField(
        max_length=10,
        choices=UNIT_CHOICES,
        verbose_name="Unidad",
        help_text=(
            "Unidad de medida del concepto (fijo, por km, por hora, por dia, "
            "porcentaje)."
        ),
    )
    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name="Precio",
        help_text=(
            "Importe unitario del concepto. Para PERCENT, es el porcentaje "
            "(ej: 50 para un recargo del 50%). Para FIXED, es el importe "
            "fijo en euros."
        ),
    )
    # For KM_LONG: threshold above which this km price applies instead of
    # KM_NORMAL.
    # Para KM_LONG: umbral a partir del cual aplica este precio en lugar de
    # KM_NORMAL.
    km_threshold = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name="Umbral de km",
        help_text=(
            "Solo para KM_LARGO. Kilometraje total (ida+vuelta) a partir del "
            "cual aplica esta tarifa reducida. Habitualmente 200. Dejar "
            "vacio para KM_NORMAL."
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
            "Ejemplo: hora de rescate con minimo 2 horas. Dejar vacio si no "
            "aplica."
        ),
    )
    # Whether this concept requires prior authorization from the insurer.
    # Si este concepto requiere autorizacion previa de la aseguradora.
    requires_authorization = models.BooleanField(
        default=False,
        verbose_name="Requiere autorizacion",
        help_text=(
            "Si esta activo, este concepto debe haber sido autorizado "
            "previamente por la central de la aseguradora antes de poder "
            "incluirse en el presupuesto."
        ),
    )

    class Meta:
        verbose_name = "Linea de tarifa"
        verbose_name_plural = "Lineas de tarifa"
        ordering = [
            "tariff", "vehicle_type__sort_order", "concept__sort_order"
        ]

    def __str__(self):
        vt = self.vehicle_type.name if self.vehicle_type else "General"
        return f"{self.tariff} — {vt} — {self.concept.label}"


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
    cifra visible para el operario. El desglose completo se almacena en
    registros BudgetLine y es visible unicamente para ADMIN con fines de
    auditoria.
    """

    STATUS_DRAFT = "DRAFT"
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
        help_text=(
            "Aseguradora o cliente para el que se genera el presupuesto."
        ),
    )
    # Snapshot of the tariff used — preserved even if the tariff is later
    # replaced.
    # Snapshot de la tarifa usada — se conserva aunque la tarifa sea
    # sustituida.
    tariff = models.ForeignKey(
        InsurerTariff,
        on_delete=models.PROTECT,
        related_name="budgets",
        verbose_name="Tarifa aplicada",
        help_text=(
            "Version de tarifa que se uso para calcular este presupuesto."
        ),
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
        help_text=(
            "Tipo de vehiculo asistido segun la nomenclatura de la "
            "aseguradora."
        ),
    )
    # Service base — selected from the insurer's active bases in the wizard.
    # When the insurer has exactly one active base, it is assigned
    # automatically.
    # Base de servicio — seleccionada entre las bases activas de la
    # aseguradora.
    # Cuando la aseguradora tiene exactamente una base activa, se asigna
    # automaticamente.
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
            "Activo cuando el servicio se realiza en dos fases: recogida del "
            "vehiculo el primer dia y traslado al destino al dia siguiente. "
            "Genera dos salidas y dos tramos de kilometraje independientes."
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
        help_text=(
            "Suma de km_phase1 + km_phase2. Calculado automaticamente al "
            "guardar."
        ),
    )

    # ---------------------------------------------------------------------------
    # Route calculation fields — populated by the Routes API integration.
    # Campos de calculo de ruta — poblados por la integracion con Routes API.
    # Added in migration 0011_budget_route_fields (H18 S002).
    # ---------------------------------------------------------------------------

    # Name of the road where the vehicle is located (e.g. A-45, N-331).
    # Nombre de la via donde se encuentra el vehiculo averiado.
    road_name = models.CharField(
        max_length=50,
        blank=True,
        default="",
        verbose_name="Carretera",
        help_text=(
            "Nombre de la via donde se encuentra el vehiculo "
            "(ej: A-45, N-331)."
        ),
    )
    # Municipality or province of the destination, used to refine geocoding.
    # Municipio o provincia del destino, usado para refinar la geocodificacion.
    dest_location = models.CharField(
        max_length=150,
        blank=True,
        default="",
        verbose_name="Municipio / provincia destino",
        help_text=(
            "Municipio o provincia donde se encuentra el vehiculo averiado. "
            "Opcional. Se usa para refinar la geocodificacion del punto "
            "kilometrico en la llamada a la Routes API de Google."
        ),
    )
    # Kilometre marker on the road where the vehicle is located.
    # Punto kilometrico de la via donde se encuentra el vehiculo.
    pk_km = models.DecimalField(
        max_digits=8,
        decimal_places=3,
        null=True,
        blank=True,
        verbose_name="Punto kilometrico",
        help_text=(
            "Punto kilometrico de la via donde se encuentra el vehiculo "
            "averiado."
        ),
    )
    # Distance in km calculated by the Routes API for this service.
    # Distancia en km calculada por la Routes API para este servicio.
    route_distance_km = models.DecimalField(
        max_digits=8,
        decimal_places=3,
        null=True,
        blank=True,
        verbose_name="Distancia calculada (km)",
        help_text=(
            "Distancia en km calculada por la Routes API desde la base hasta "
            "el punto kilometrico del vehiculo averiado."
        ),
    )
    # Toll cost in EUR returned by the Routes API for this service.
    # Kept for backwards compatibility — mirrors route_toll_budget_cost.
    # Coste de peajes en EUR devuelto por la Routes API para este servicio.
    # Mantenido por compatibilidad — refleja route_toll_budget_cost.
    route_toll_cost = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Coste de peajes",
        help_text=(
            "Coste estimado de peajes en EUR. Alias de "
            "route_toll_budget_cost mantenido por compatibilidad con "
            "presupuestos anteriores."
        ),
    )

    # Budgeted toll cost: full tariff for each traversed TollSegment,
    # regardless of time of service (free-night windows are ignored).
    # This is the amount added to the budget total and the BudgetLine.
    # Coste de peajes presupuestado: tarifa completa de cada tramo
    # atravesado, ignorando los tramos gratuitos nocturnos. Es el importe
    # que se suma al total del presupuesto y a la línea BudgetLine
    # TOLL_COST.
    route_toll_budget_cost = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Coste peajes presupuestado",
        help_text=(
            "Coste de peajes que se añade al presupuesto. "
            "Aplica la tarifa completa del tramo sin tener en cuenta "
            "la gratuidad nocturna. Null cuando no hay peajes o el cálculo "
            "es manual."
        ),
    )

    # Real toll cost: applies free-night windows per TollSegment.
    # Informational only — never added to total_amount.
    # Only populated when route_calculation_mode=API and has_tolls=True.
    # Shown in BudgetLine ADMIN breakdown as is_informational=True.
    # Coste de peajes real: aplica gratuidad nocturna por tramo.
    # Solo informativo — nunca se suma a total_amount.
    # Solo se rellena cuando route_calculation_mode=API y has_tolls=True.
    # Aparece en el desglose ADMIN como línea is_informational=True.
    route_toll_real_cost = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Coste peajes real",
        help_text=(
            "Coste real de peajes aplicando gratuidad nocturna por tramo. "
            "Solo informativo: no se suma al total del presupuesto. "
            "Visible únicamente en el desglose ADMIN."
        ),
    )

    # Ordered list of route waypoints for the multi-stop planner.
    # Populated when route_calculation_mode=API and the operator uses the
    # interactive map in the wizard. Each element encodes one stop along
    # the closed circuit Base → stops → Base.
    # is_base_return=True marks an intermediate return to base (overnight
    # service): the engine splits the leg list at that waypoint to compute
    # km_phase1 and km_phase2 independently and sets is_overnight=True.
    #
    # Lista ordenada de paradas del planificador multi-parada.
    # Se rellena cuando route_calculation_mode=API y el operario usa el
    # mapa interactivo del wizard. Cada elemento codifica una parada del
    # circuito cerrado Base → paradas → Base.
    # is_base_return=True marca un retorno intermedio a base (servicio de
    # pernocta): el motor divide la lista de tramos en ese waypoint para
    # calcular km_phase1 y km_phase2 de forma independiente y activa
    # is_overnight=True.
    #
    # JSON schema per waypoint / Esquema JSON por parada:
    # {
    #   "label":          "Recogida — A-45 P.K. 127.5, Antequera",
    #   "address":        "A-45, P.K. 127.5, Antequera, Málaga",
    #   "lat":            37.0123,
    #   "lng":            -4.5590,
    #   "is_base_return": false
    # }
    waypoints_json = models.JSONField(
        null=True,
        blank=True,
        verbose_name="Paradas de ruta",
        help_text=(
            "Lista ordenada de paradas del planificador multi-parada. "
            "Cada elemento: {label, address, lat, lng, is_base_return}. "
            "is_base_return=True indica retorno intermedio a base "
            "(pernocta): el motor divide los tramos en ese punto para "
            "calcular km_phase1 y km_phase2 de forma independiente y activa "
            "is_overnight=True. Null en presupuestos con modo MANUAL o ruta "
            "punto a punto legacy."
        ),
    )

    # Google Encoded Polyline of the confirmed route (or two polylines
    # separated by \x01 for overnight services). Persisted so
    # calculate_budget() can cross-reference TollSegment without a new
    # API call. Null for MANUAL mode or legacy budgets without a polyline.
    #
    # Polyline codificada Google de la ruta confirmada (o dos polylines
    # separadas por \x01 en servicios con pernocta). Se persiste para que
    # calculate_budget() pueda cruzar con TollSegment sin nueva llamada
    # API.
    # Null en modo MANUAL o presupuestos legacy sin polyline.
    encoded_polyline = models.TextField(
        null=True,
        blank=True,
        verbose_name="Polyline codificada",
        help_text=(
            "Polyline Google Encoded de la ruta confirmada. "
            "En servicios con pernocta, dos polylines separadas por \\x01. "
            "Usada por calculate_budget() para el cruce con TollSegment."
        ),
    )

    # How km were calculated: MANUAL (operator input) or API (Routes API).
    # Como se calcularon los km: MANUAL (entrada operario) o API
    # (Routes API).
    ROUTE_MODE_MANUAL = "MANUAL"
    ROUTE_MODE_API = "API"
    ROUTE_MODE_CHOICES = [
        (ROUTE_MODE_MANUAL, "Manual"),
        (ROUTE_MODE_API,    "API Routes"),
    ]
    route_calculation_mode = models.CharField(
        max_length=10,
        choices=ROUTE_MODE_CHOICES,
        default=ROUTE_MODE_MANUAL,
        verbose_name="Modo de calculo km",
        help_text=(
            "MANUAL: el operario introduce los km directamente. "
            "API: distancia calculada automaticamente por la Routes API de "
            "Google."
        ),
    )
    # Time of service — used to build departureTime for toll calculation.
    # Hora del servicio — usada para construir departureTime en el calculo
    # de peajes.
    service_time = models.TimeField(
        null=True,
        blank=True,
        verbose_name="Hora del servicio",
        help_text=(
            "Hora en la que se realiza el servicio. Se combina con "
            "service_date para construir el departureTime en la llamada a "
            "la Routes API, necesario para el calculo de peajes con "
            "dependencia horaria."
        ),
    )

    has_unlock = models.BooleanField(
        default=False,
        verbose_name="Desbloqueo",
        help_text=(
            "Indica si el servicio incluye desbloqueo o enganche con "
            "eslingas. No aplica a remolques (se desenganchan/enganchan "
            "directamente en la quinta rueda)."
        ),
    )
    # Marked manually by the operator when the service is performed at
    # night. Independently of is_holiday, which is calculated automatically
    # by the engine.
    # Marcado manualmente por el operario cuando el servicio es nocturno.
    # Independiente de is_holiday, calculado automaticamente por el motor.
    is_night = models.BooleanField(
        default=False,
        verbose_name="Nocturno",
        help_text=(
            "Indica si el servicio se realiza en horario nocturno. "
            "Marcado manualmente por el operario en el wizard. "
            "Independiente de is_holiday, que es calculado automaticamente "
            "por el motor segun la fecha del servicio y el calendario "
            "laboral."
        ),
    )
    is_night_or_holiday = models.BooleanField(
        default=False,
        verbose_name="Nocturno / Festivo",
        help_text=(
            "Calculado automaticamente por el motor: True si is_night OR "
            "is_holiday. Activa el recargo NYF de la tarifa de la "
            "aseguradora. No editar directamente — se recalcula en cada "
            "llamada a calculate_budget()."
        ),
    )
    # Explicit manual override for is_night_or_holiday, set only from the
    # wizard's Manual calculation mode (route_calculation_mode=MANUAL).
    # The automatic calendar-based calculation (is_night OR calendar
    # holiday) ALWAYS runs, in both API and Manual mode. This field only
    # FORCES the result to True when the operator explicitly checks the
    # box — it never suppresses a True automatic result. Leaving it
    # unchecked (False) or unset (None) simply falls back to the automatic
    # result. Used when a service is agreed with the insurer to be billed
    # as nocturno/festivo even though the date/schedule wouldn't otherwise
    # qualify (see calculate_budget()).
    # ---
    # Override manual explícito de is_night_or_holiday, establecido solo
    # desde el modo de cálculo Manual del wizard
    # (route_calculation_mode=MANUAL). El cálculo automático basado en
    # calendario (is_night O festivo de calendario) SIEMPRE se ejecuta,
    # tanto en modo API como en modo Manual. Este campo solo FUERZA el
    # resultado a True cuando el operario marca explícitamente la casilla
    # — nunca suprime un resultado automático True. Dejarlo sin marcar
    # (False) o sin fijar (None) simplemente recurre al resultado
    # automático. Se usa cuando un servicio se acuerda con la aseguradora
    # como nocturno/festivo aunque la fecha/horario no lo justifiquen por
    # sí solos (ver calculate_budget()).
    is_night_or_holiday_manual_override = models.BooleanField(
        null=True,
        blank=True,
        default=None,
        verbose_name="Nocturno / Festivo (forzar)",
        help_text=(
            "Cuando es True, fuerza is_night_or_holiday a True aunque el "
            "calendario/horario no lo indiquen. El cálculo automático por "
            "calendario se ejecuta siempre — este campo no lo sustituye, "
            "solo puede forzarlo a True. Se establece desde el checkbox "
            "del modo Manual del wizard de presupuestos."
        ),
    )
    # Itemized manual selection of toll segments (troncal/salida, tipicamente
    # AP-7/AP-46) with pass count, chosen in the wizard's Manual calculation
    # mode. Stored as {str(TollSegment.pk): passes_int}. Additive with
    # route_toll_budget_cost (the free-text "Otros peajes" amount) — see
    # calculate_budget() section 3.
    # ---
    # Selección manual itemizada de tramos de peaje (troncal/salida,
    # tipicamente AP-7/AP-46) con número de pases, elegida en el modo de
    # cálculo Manual del wizard. Se almacena como
    # {str(TollSegment.pk): pases_int}. Es aditiva con
    # route_toll_budget_cost (el importe libre "Otros peajes") — ver
    # calculate_budget() sección 3.
    manual_toll_segments = models.JSONField(
        null=True,
        blank=True,
        default=None,
        verbose_name="Peajes por tramo (modo manual)",
        help_text=(
            "Selección itemizada de tramos TollSegment con número de "
            "pases, del modo Manual del wizard. Formato: "
            "{id_tramo: nº_pases}. Se suma a route_toll_budget_cost "
            "(Otros peajes), no lo sustituye."
        ),
    )
    is_loaded = models.BooleanField(
        default=False,
        verbose_name="Vehiculo cargado",
        help_text=(
            "Indica si el vehiculo asistido va cargado. "
            "Activa el recargo por vehiculo cargado si la tarifa lo "
            "contempla."
        ),
    )
    # Optional service concepts — only shown in the form if the tariff
    # includes them.
    # Conceptos opcionales — solo aparecen en el formulario si la tarifa los
    # contempla.
    wait_hours = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Horas de espera",
        help_text=(
            "Numero de horas de espera facturables. "
            "Solo si la tarifa contempla este concepto."
        ),
    )
    rescue_hours = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Horas de rescate",
        help_text=(
            "Numero de horas de rescate facturables. "
            "Solo si la tarifa contempla este concepto."
        ),
    )
    assistant_hours = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Horas de ayudante",
        help_text=(
            "Numero de horas de ayudante facturables. "
            "Solo si la tarifa contempla este concepto."
        ),
    )
    worker_hours = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Horas de mano de obra",
        help_text=(
            "Numero de horas de mano de obra mecanica. "
            "Solo si la tarifa contempla este concepto."
        ),
    )
    custody_days = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        verbose_name="Dias de custodia",
        help_text=(
            "Numero de dias de custodia del vehiculo. "
            "Solo si la tarifa contempla este concepto."
        ),
    )
    extra_notes = models.TextField(
        blank=True,
        default="",
        verbose_name="Notas adicionales",
        help_text=(
            "Observaciones libres del operario sobre este presupuesto. "
            "Uso interno."
        ),
    )
    # Whether IVA should be applied to the total amount.
    # Si el IVA debe aplicarse al importe total.
    apply_iva = models.BooleanField(
        default=False,
        verbose_name="Aplicar IVA",
        help_text=(
            "Indica si se debe aplicar el IVA vigente sobre el importe base "
            "del presupuesto. El porcentaje de IVA se define como constante "
            "IVA_PERCENT en budgets/services.py."
        ),
    )
    total_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name="Total presupuesto",
        help_text=(
            "Importe total calculado por el motor. "
            "Es la unica cifra visible para el operario."
        ),
    )
    # Total amount including IVA. Null when apply_iva is False.
    # Persisted in DB so the result view does not need to recalculate.
    # Importe total con IVA incluido. Nulo cuando apply_iva es False.
    # Persistido en BD para que la vista de resultado no necesite
    # recalcular.
    total_amount_with_iva = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Total con IVA",
        help_text=(
            "Importe total del presupuesto con IVA incluido. "
            "Solo se rellena cuando apply_iva es True. "
            "El porcentaje de IVA aplicado se define en IVA_PERCENT en "
            "budgets/services.py."
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
        Overrides save to auto-calculate km_total from phase values before
        persisting.
        ---
        Sobreescribe save para calcular km_total automaticamente desde las
        fases antes de persistir.
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
    representa un concepto aplicado con sus unidades, precio unitario y
    subtotal. Estos registros nunca son visibles para el operario
    ASSISTANCE — existen exclusivamente para la auditoria y verificacion
    ADMIN del motor de calculo.
    """

    budget = models.ForeignKey(
        Budget,
        on_delete=models.CASCADE,
        related_name="lines",
        verbose_name="Presupuesto",
        help_text="Presupuesto al que pertenece esta linea de desglose.",
    )
    concept_code = models.CharField(
        max_length=50,
        verbose_name="Codigo de concepto",
        help_text=(
            "Codigo interno del concepto aplicado "
            "(ej: DEPARTURE, KM_NORMAL, NYF_PERCENT). "
            "max_length=50 alineado con TariffConcept.code."
        ),
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
        help_text=(
            "Cantidad de unidades aplicadas "
            "(ej: 2 salidas, 115 km, 1.5 horas)."
        ),
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
    # Distingue las lineas de recargo (NYF, cargado) de las lineas de
    # concepto base.
    is_surcharge = models.BooleanField(
        default=False,
        verbose_name="Es recargo",
        help_text=(
            "Activo para lineas de recargo porcentual "
            "(nocturno/festivo, vehiculo cargado). "
            "Inactivo para conceptos base (salida, km, desbloqueo, etc.)."
        ),
    )

    # Informational lines are shown in the ADMIN breakdown but never
    # added to total_amount. Used for the real toll cost line that shows
    # the actual cost after applying free-night windows, contrasted
    # against the budgeted toll cost line (is_informational=False).
    # Las líneas informativas aparecen en el desglose ADMIN pero nunca
    # se suman a total_amount. Se usan para la línea de coste real de
    # peajes tras aplicar gratuidad nocturna, contrastada con la línea
    # de coste presupuestado (is_informational=False).
    is_informational = models.BooleanField(
        default=False,
        verbose_name="Solo informativo",
        help_text=(
            "Si es True, esta línea aparece en el desglose ADMIN pero "
            "no se suma al total del presupuesto. Reservado para la "
            "línea de coste real de peajes con gratuidad nocturna aplicada."
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
            f"{self.concept_label} — {self.units} x {self.unit_price} "
            f"= {self.subtotal}"
        )


# ---------------------------------------------------------------------------
# 7. SPECIAL RATE TARIFF — Night/holiday special rate table for an insurer.
#    Tabla de tarifas especiales nocturno/festivo vinculada a una
#    InsurerTariff.
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
    aseguradora con precios diferenciados en lugar de recargo porcentual
    plano. Vinculada a la InsurerTariff activa mediante OneToOneField para
    garantizar exactamente una tabla especial por versión de tarifa.
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
        help_text=(
            "Observaciones internas sobre esta tabla de tarifas especiales."
        ),
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
    of TariffLine (concept, unit, price, vehicle_type) but applies
    exclusively to night/holiday service conditions.
    When vehicle_type is None, the line applies to all vehicle types
    (generic concepts such as WAIT_HOUR, RESCUE_HOUR, UNLOCK).
    ---
    Almacena una línea de precio dentro de un SpecialRateTariff. Replica la
    estructura de TariffLine (concepto, unidad, precio, tipo de vehículo)
    pero aplica exclusivamente a condiciones de servicio nocturno/festivo.
    Cuando vehicle_type es None, la línea aplica a todos los tipos de
    vehículo (conceptos genéricos como WAIT_HOUR, RESCUE_HOUR, UNLOCK).
    """

    special_rate_tariff = models.ForeignKey(
        SpecialRateTariff,
        on_delete=models.CASCADE,
        related_name="lines",
        verbose_name="Tarifa especial",
        help_text=(
            "Tabla de tarifas especiales a la que pertenece esta línea."
        ),
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
    concept = models.ForeignKey(
        TariffConcept,
        on_delete=models.PROTECT,
        related_name="special_rate_lines",
        verbose_name="Concepto",
        help_text=(
            "Tipo de concepto facturable que representa esta línea "
            "especial nocturno/festivo. "
            "Referencia el mismo catálogo TariffConcept que TariffLine."
        ),
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
            "Umbral de km a partir del cual se aplica la tarifa de largo "
            "recorrido. Solo relevante para conceptos KM_NORMAL que "
            "coexisten con KM_LONG."
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
        ordering = [
            "special_rate_tariff", "vehicle_type__sort_order", "concept"
        ]

    def __str__(self):
        vt = self.vehicle_type.name if self.vehicle_type else "Genérico"
        return (
            f"{self.special_rate_tariff} — "
            f"{vt} — {self.concept} — {self.price}"
        )


# ---------------------------------------------------------------------------
# 9. BASE — Physical service base. Company-scoped, insurer-independent.
#    Base fisica de servicio. Con ambito de empresa, independiente de
#    aseguradora.
# ---------------------------------------------------------------------------

class Base(models.Model):
    """
    Represents a physical service base scoped to a company.
    A base is an independent entity — not linked to a specific insurer.
    The relationship between bases and insurers is managed via InsurerBase,
    which allows the same physical base to be assigned to multiple insurers
    with individual active/inactive flags per insurer.

    Coordinates (latitude/longitude) are used as the route origin in the
    Google Maps Routes API call. If not provided, municipality is used for
    geocoding and the result is persisted back on first call.

    The labor_calendar field stores public holidays for the base locality
    in JSON format, populated by the sync_base_calendars management command.
    The _is_holiday() engine function reads this field to determine whether
    a given service date triggers the NYF surcharge.
    ---
    Representa una base fisica de servicio con ambito de empresa.
    Una base es una entidad independiente — no vinculada a una aseguradora
    especifica. La relacion entre bases y aseguradoras se gestiona via
    InsurerBase, que permite asignar la misma base fisica a multiples
    aseguradoras con flags activa/inactiva individuales por aseguradora.

    Las coordenadas se usan como origen en la llamada a Routes API de Google
    Maps. Si no se dan, se geocodifica el municipio y se persiste en la
    primera llamada.

    El campo labor_calendar almacena los festivos de la localidad en formato
    JSON, poblado por el comando sync_base_calendars. La funcion
    _is_holiday() lo lee para determinar si una fecha activa el recargo NYF.
    """

    # Temporarily nullable to allow migration of existing rows.
    # Will be made NOT NULL in a follow-up data migration once populated.
    # Temporalmente nullable para permitir la migracion de filas existentes.
    # Se hara NOT NULL en una migracion de datos posterior una vez poblado.
    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="bases",
        null=True,
        blank=True,
        verbose_name="Empresa",
        help_text="Empresa a la que pertenece esta base.",
    )
    name = models.CharField(
        max_length=150,
        verbose_name="Nombre de la base",
        help_text=(
            "Nombre identificativo de la base "
            "(ej: 'Sevilla', 'Granada Norte')."
        ),
    )
    municipality = models.CharField(
        max_length=150,
        verbose_name="Municipio",
        help_text=(
            "Municipio donde se ubica la base. Se usa para geocodificar las "
            "coordenadas y para consultar el calendario laboral local via "
            "API. Debe coincidir con el nombre oficial del municipio en "
            "espanol (ej: 'Sevilla', 'Granada', 'Jerez de la Frontera')."
        ),
    )
    # Optional precise coordinates. Populated by the geocoding pipeline
    # or entered manually from the panel. When null, municipality is used
    # as the geocoding source and the result is stored here on first call.
    # Coordenadas precisas opcionales. Pobladas por el pipeline de
    # geocodificacion o introducidas manualmente desde el panel. Cuando son
    # nulas, municipality se usa como fuente de geocodificacion y el
    # resultado se almacena aqui.
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
    # Format: list of ISO date strings, e.g.
    # ["2026-01-01", "2026-01-06", ...]
    # Calendario de festivos publicos de la localidad de la base en formato
    # JSON.
    # Poblado por el comando de gestion sync_base_calendars.
    # Formato: lista de cadenas de fecha ISO, ej:
    # ["2026-01-01", "2026-01-06", ...]
    labor_calendar = models.TextField(
        blank=True,
        default="",
        verbose_name="Calendario laboral",
        help_text=(
            "Festivos locales de la base en formato JSON "
            "(lista de fechas ISO). "
            "Poblado automaticamente por el comando sync_base_calendars. "
            "Incluye festivos nacionales, autonomicos y locales del "
            "municipio."
        ),
    )
    # Calendar last synced timestamp — used to detect stale calendars.
    # Timestamp de ultima sincronizacion del calendario — detecta
    # calendarios obsoletos.
    calendar_synced_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Ultimo sync de calendario",
        help_text=(
            "Fecha y hora de la ultima sincronizacion del calendario laboral "
            "con la API de calendariosnacionales.com. Null si nunca se ha "
            "sincronizado."
        ),
    )
    # Global active flag — when False, the base cannot be used by any
    # insurer.
    # Flag activa global — cuando es False, ninguna aseguradora puede usar
    # la base.
    is_active = models.BooleanField(
        default=True,
        verbose_name="Activa globalmente",
        help_text=(
            "Indica si esta base esta disponible globalmente. "
            "Cuando es False, no puede usarse en ningun presupuesto "
            "independientemente de su configuracion por aseguradora."
        ),
    )
    created_at = models.DateTimeField(
        auto_now_add=True, verbose_name="Fecha de creacion"
    )
    updated_at = models.DateTimeField(
        auto_now=True, verbose_name="Fecha de modificacion"
    )

    class Meta:
        verbose_name = "Base"
        verbose_name_plural = "Bases"
        ordering = ["company__name", "name"]
        unique_together = [("company", "name")]

    def __str__(self):
        return f"{self.company.name} — {self.name}"


# ---------------------------------------------------------------------------
# 10. INSURER BASE — Many-to-many relation between Insurer and Base.
#     Relacion many-to-many entre Insurer y Base.
# ---------------------------------------------------------------------------

class InsurerBase(models.Model):
    """
    Links a Base to an Insurer with an individual active/inactive flag.
    This allows the same physical base to be assigned to multiple insurers
    and activated/deactivated independently per insurer without duplicating
    the base entity or its coordinates and labor calendar.

    When is_active is True and the global Base.is_active is also True,
    the base appears in the wizard dropdown for the operator.
    When the insurer has exactly one active InsurerBase, the base is
    assigned automatically without showing a dropdown.
    ---
    Vincula una Base a un Insurer con un flag activa/inactiva individual.
    Esto permite asignar la misma base fisica a multiples aseguradoras y
    activarla/desactivarla de forma independiente por aseguradora sin
    duplicar la entidad base ni sus coordenadas ni calendario laboral.

    Cuando is_active es True y el flag global Base.is_active tambien es True,
    la base aparece en el desplegable del wizard para el operario.
    Cuando la aseguradora tiene exactamente un InsurerBase activo, la base
    se asigna automaticamente sin mostrar desplegable.
    """

    insurer = models.ForeignKey(
        Insurer,
        on_delete=models.CASCADE,
        related_name="insurer_bases",
        verbose_name="Aseguradora",
        help_text="Aseguradora a la que se asigna esta base.",
    )
    base = models.ForeignKey(
        Base,
        on_delete=models.CASCADE,
        related_name="insurer_bases",
        verbose_name="Base",
        help_text="Base fisica asignada a esta aseguradora.",
    )
    # Per-insurer active flag — independent of the global Base.is_active.
    # Flag activa por aseguradora — independiente del global Base.is_active.
    is_active = models.BooleanField(
        default=True,
        verbose_name="Activa para esta aseguradora",
        help_text=(
            "Indica si esta base esta activa para esta aseguradora. "
            "Una base puede estar activa para una aseguradora e inactiva "
            "para otra. El flag global Base.is_active tiene precedencia: "
            "si es False, la base no aparece en el wizard aunque este "
            "flag sea True."
        ),
    )
    created_at = models.DateTimeField(
        auto_now_add=True, verbose_name="Fecha de creacion"
    )
    updated_at = models.DateTimeField(
        auto_now=True, verbose_name="Fecha de modificacion"
    )

    class Meta:
        verbose_name = "Base de aseguradora"
        verbose_name_plural = "Bases de aseguradora"
        ordering = ["insurer__name", "base__name"]
        unique_together = [("insurer", "base")]

    def __str__(self):
        status = "activa" if self.is_active else "inactiva"
        return f"{self.insurer.name} — {self.base.name} ({status})"


# ---------------------------------------------------------------------------
# 11. WORK ORDER ASSISTANCE — Service work order for the ASISTENCIA
#     section.
#     Orden de trabajo de asistencia. Entidad central del flujo H17.
# ---------------------------------------------------------------------------

class WorkOrderAssistance(models.Model):
    """
    Central document of the ASISTENCIA workflow. Represents a service work
    order that either originates from an accepted Budget or is created
    directly without a prior budget. Captures all data present on the
    physical albarán: client data, vehicle data, service location, machine
    assignments, per-phase service data (JSON), internal production report
    data and billing totals.

    The work_order_number is auto-generated in the format YYYYMMDDNNN,
    where NNN is a 3-digit daily ordinal per company (001-999), reset
    each calendar day. A unique constraint at database level guards against
    duplicates under concurrent writes.
    ---
    Documento central del flujo ASISTENCIA. Representa una orden de trabajo
    que puede originarse desde un Budget aceptado o crearse directamente
    sin presupuesto previo. Captura todos los datos del albarán físico:
    datos de cliente, vehículo, localización del servicio, asignación de
    máquinas, datos de servicio por fase (JSON), parte de producción interno
    y totales de facturación.

    El work_order_number se auto-genera en formato YYYYMMDDNNN, donde NNN
    es un ordinal diario de 3 dígitos por empresa (001-999), reiniciado
    cada día natural. Una restricción unique en BD protege frente a
    duplicados en escrituras concurrentes.
    """

    # --- Status choices ---
    # --- Opciones de estado ---
    STATUS_PENDING = "PENDING"
    STATUS_IN_PROGRESS = "IN_PROGRESS"
    STATUS_COMPLETED = "COMPLETED"
    STATUS_INVOICED = "INVOICED"

    STATUS_CHOICES = [
        (STATUS_PENDING,     "Pendiente"),
        (STATUS_IN_PROGRESS, "En curso"),
        (STATUS_COMPLETED,   "Completada"),
        (STATUS_INVOICED,    "Facturada"),
    ]

    # ── Relations ──────────────────────────────────────────────────────────
    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="work_orders_assistance",
        verbose_name="Empresa",
        help_text=(
            "Empresa cliente a la que pertenece esta orden de trabajo."
        ),
    )
    budget = models.ForeignKey(
        "Budget",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="work_orders_assistance",
        verbose_name="Presupuesto de origen",
        help_text=(
            "Presupuesto aceptado del que se origina esta orden de trabajo. "
            "Null cuando la orden se crea directamente sin presupuesto "
            "previo."
        ),
    )
    insurer = models.ForeignKey(
        "Insurer",
        on_delete=models.PROTECT,
        related_name="work_orders_assistance",
        verbose_name="Aseguradora",
        help_text=(
            "Aseguradora o cliente para el que se realiza el servicio. "
            "Heredado del Budget si existe, o seleccionado manualmente en "
            "entrada directa."
        ),
    )
    vehicle_type = models.ForeignKey(
        "VehicleType",
        on_delete=models.PROTECT,
        related_name="work_orders_assistance",
        verbose_name="Tipo de vehículo",
        help_text=(
            "Tipo de vehículo asistido según la nomenclatura de la "
            "aseguradora. Heredado del Budget si existe."
        ),
    )
    operator = models.ForeignKey(
        CompanyUser,
        on_delete=models.PROTECT,
        related_name="work_orders_assistance_primary",
        verbose_name="Conductor principal",
        help_text="Conductor principal asignado al servicio (Máquina 1).",
    )
    operator_2 = models.ForeignKey(
        CompanyUser,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="work_orders_assistance_secondary",
        verbose_name="Conductor secundario",
        help_text=(
            "Segundo conductor. Solo en servicios que requieren dos "
            "máquinas simultáneas."
        ),
    )
    created_by = models.ForeignKey(
        CompanyUser,
        on_delete=models.PROTECT,
        related_name="work_orders_assistance_created",
        verbose_name="Creado por",
        help_text="Usuario del panel que genera la orden de trabajo.",
    )
    base = models.ForeignKey(
        "Base",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="work_orders_assistance",
        verbose_name="Base de operación",
        help_text="Base de salida del servicio de asistencia.",
    )

    # H37 (S133): how the service came in (meeting with Pepe: photo of
    # TIREA or another platform, phone call to the robot or WhatsApp).
    # Por dónde entró el servicio (reunión con Pepe, S133: foto de TIREA
    # u otra plataforma, llamada al robot o WhatsApp).
    ORIGIN_PANEL = "PANEL"
    ORIGIN_PHOTO = "PHOTO"
    ORIGIN_WHATSAPP = "WHATSAPP"
    ORIGIN_PHONE = "PHONE"
    ORIGIN_CHOICES = [
        (ORIGIN_PANEL, "Panel (a mano)"),
        (ORIGIN_PHOTO, "Foto (TIREA u otra plataforma)"),
        (ORIGIN_WHATSAPP, "WhatsApp"),
        (ORIGIN_PHONE, "Llamada"),
    ]
    origin = models.CharField(
        max_length=10,
        choices=ORIGIN_CHOICES,
        default=ORIGIN_PANEL,
        verbose_name="Origen",
        help_text="Por dónde entró el servicio.",
    )

    # ── Reference / status ─────────────────────────────────────────────────
    work_order_number = models.CharField(
        max_length=11,
        unique=True,
        verbose_name="Número de orden",
        help_text=(
            "Número de orden auto-generado en formato YYYYMMDDNNN. "
            "Ejemplo: 20260601001. Ordinal diario de 3 dígitos por empresa, "
            "reiniciado cada día natural."
        ),
    )
    service_date = models.DateField(
        verbose_name="Fecha del servicio",
        help_text="Fecha en la que se realiza el servicio de asistencia.",
    )
    expediente = models.CharField(
        max_length=100,
        blank=True,
        default="",
        verbose_name="Expediente",
        help_text="Número de expediente facilitado por la aseguradora.",
    )
    status = models.CharField(
        max_length=15,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
        verbose_name="Estado",
        help_text=(
            "PENDING: orden creada, pendiente de enviar al operario. "
            "IN_PROGRESS: operario en camino o realizando el servicio. "
            "COMPLETED: servicio realizado y firmado por el cliente. "
            "INVOICED: albarán procesado y listo para facturación."
        ),
    )
    is_overnight = models.BooleanField(
        default=False,
        verbose_name="Pernocta",
        help_text=(
            "Activo cuando el servicio se realiza en dos fases en días "
            "distintos. Cuando es True, phase2_data debe estar informado."
        ),
    )

    # ── Machine identifiers ─────────────────────────────────────────────────
    machine_1 = models.CharField(
        max_length=100,
        blank=True,
        default="",
        verbose_name="Máquina 1",
        help_text=(
            "Identificador o matrícula de la primera máquina de servicio."
        ),
    )
    machine_2 = models.CharField(
        max_length=100,
        blank=True,
        default="",
        verbose_name="Máquina 2",
        help_text=(
            "Identificador o matrícula de la segunda máquina. "
            "Vacío en servicios de una sola máquina."
        ),
    )

    # ── Client data ─────────────────────────────────────────────────────────
    client_name = models.CharField(
        max_length=200,
        blank=True,
        default="",
        verbose_name="Cliente",
        help_text="Nombre completo o razón social del cliente.",
    )
    client_nif = models.CharField(
        max_length=20,
        blank=True,
        default="",
        verbose_name="N.I.F.",
        help_text="Número de identificación fiscal del cliente.",
    )
    client_address = models.CharField(
        max_length=300,
        blank=True,
        default="",
        verbose_name="Domicilio",
        help_text="Dirección postal del cliente.",
    )
    client_cp = models.CharField(
        max_length=10,
        blank=True,
        default="",
        verbose_name="C.P.",
        help_text="Código postal del domicilio del cliente.",
    )
    client_email = models.EmailField(
        blank=True,
        default="",
        verbose_name="E-mail",
        help_text="Correo electrónico del cliente.",
    )
    client_phone = models.CharField(
        max_length=50,
        blank=True,
        default="",
        verbose_name="Teléfono",
        help_text="Teléfono de contacto del cliente.",
    )

    # ── Vehicle data ────────────────────────────────────────────────────────
    vehicle_plate = models.CharField(
        max_length=20,
        blank=True,
        default="",
        verbose_name="Matrícula",
        help_text="Matrícula del vehículo asistido.",
    )
    # H37 (S133): the other vehicle of the set (tractor or semitrailer).
    # El otro vehículo del conjunto (tractora o semirremolque).
    second_vehicle_plate = models.CharField(
        max_length=20,
        blank=True,
        default="",
        verbose_name="Matrícula 2º vehículo",
        help_text=(
            "Matrícula del otro vehículo del conjunto (tractora o "
            "semirremolque), si lo hay."
        ),
    )
    vehicle_brand = models.CharField(
        max_length=100,
        blank=True,
        default="",
        verbose_name="Marca",
        help_text="Marca del vehículo asistido.",
    )
    vehicle_locality = models.CharField(
        max_length=150,
        blank=True,
        default="",
        verbose_name="Localidad",
        help_text="Localidad donde se encuentra el vehículo averiado.",
    )
    vehicle_province = models.CharField(
        max_length=100,
        blank=True,
        default="",
        verbose_name="Provincia",
        help_text="Provincia donde se encuentra el vehículo averiado.",
    )
    vehicle_pma = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="P.M.A. (kg)",
        help_text="Peso máximo autorizado del vehículo en kilogramos.",
    )
    vehicle_length = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Largo (m)",
        help_text="Longitud del vehículo en metros.",
    )
    vehicle_height = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Alto (m)",
        help_text="Altura del vehículo en metros.",
    )

    # ── Service location ────────────────────────────────────────────────────
    pickup_location = models.CharField(
        max_length=300,
        blank=True,
        default="",
        verbose_name="Recogida",
        help_text="Punto de recogida del vehículo averiado.",
    )
    base_pickup = models.BooleanField(
        default=False,
        verbose_name="Recogida en base",
        help_text=(
            "Activo cuando el vehículo se recoge directamente en la base."
        ),
    )
    destination = models.CharField(
        max_length=300,
        blank=True,
        default="",
        verbose_name="Destino",
        help_text="Punto de destino del servicio de asistencia.",
    )
    # H37 (S138): coordinates of both points, geocoded once from the
    # full address (budgets.service_geocode); *_geocoded is the text
    # they came from, so a changed address is geocoded again.
    # Coordenadas de los dos puntos, geocodificadas una vez desde la
    # dirección completa; *_geocoded es el texto del que salieron.
    pickup_latitude = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True,
        verbose_name="Latitud de la recogida",
    )
    pickup_longitude = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True,
        verbose_name="Longitud de la recogida",
    )
    pickup_geocoded = models.CharField(
        max_length=700, blank=True, default="",
        verbose_name="Dirección geocodificada de la recogida",
    )
    destination_latitude = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True,
        verbose_name="Latitud del destino",
    )
    destination_longitude = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True,
        verbose_name="Longitud del destino",
    )
    destination_geocoded = models.CharField(
        max_length=700, blank=True, default="",
        verbose_name="Dirección geocodificada del destino",
    )

    # ── Service phase data (JSON) ───────────────────────────────────────────
    # Each phase mirrors one billing column of the physical albarán.
    # For standard single-phase services, only phase1_data is populated.
    # For overnight services (is_overnight=True) or simultaneous two-machine
    # services, phase2_data holds the second column data independently.
    #
    # Cada fase corresponde a una columna de facturación del albarán físico.
    # Para servicios de fase única (caso habitual), solo se informa
    # phase1_data.
    # Para pernoctas (is_overnight=True) o servicios con dos máquinas
    # simultáneas, phase2_data recoge de forma independiente la segunda
    # columna.
    #
    # JSON schema (both phases share the same structure):
    # Esquema JSON (ambas fases comparten la misma estructura):
    # {
    #   "date": "2026-06-01",           -- Fecha de la fase
    #   "machine": "GR-1234",           -- Máquina asignada a la fase
    #   "departure_fee": 45.00,         -- Importe de salida (euros)
    #   "km_total": 115.0,              -- Kilómetros totales de la fase
    #   "km_unit_price": 0.85,          -- Precio unitario por kilómetro
    #   "unlock_hours": 0.0,            -- Horas de desbloqueo / enganche
    #   "unlock_unit_price": 0.0,       -- Precio por hora de desbloqueo
    #   "mechanic_hours": 0.0,          -- Horas de mecánico
    #   "mechanic_unit_price": 0.0,     -- Precio por hora de mecánico
    #   "assistant_hours": 0.0,         -- Horas de ayudante
    #   "assistant_unit_price": 0.0,    -- Precio por hora de ayudante
    #   "rescue_hours": 0.0,            -- Horas de rescate
    #   "rescue_unit_price": 0.0,       -- Precio por hora de rescate
    #   "nyf_applied": false,           -- Recargo nocturno/festivo aplicado
    #   "nyf_percent": 0.0,             -- Porcentaje recargo NYF
    #   "nyf_amount": 0.0,              -- Importe recargo NYF (euros)
    #   "loaded_applied": false,        -- Recargo vehículo cargado aplicado
    #   "loaded_percent": 0.0,          -- Porcentaje recargo vehículo cargado
    #   "loaded_amount": 0.0,           -- Importe recargo vehículo cargado
    #   "phase_total": 142.75           -- Total de la fase (euros)
    # }
    phase1_data = models.JSONField(
        default=dict,
        verbose_name="Datos fase 1",
        help_text=(
            "JSON con todos los datos de servicio de la primera "
            "fase/máquina. Siempre informado. Consultar docstring del "
            "modelo para el esquema."
        ),
    )
    phase2_data = models.JSONField(
        null=True,
        blank=True,
        verbose_name="Datos fase 2",
        help_text=(
            "JSON con los datos de la segunda fase (pernocta) o segunda "
            "máquina. Null en servicios de fase única. Mismo esquema que "
            "phase1_data."
        ),
    )

    # ── Billing totals ──────────────────────────────────────────────────────
    total_importe = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Total importe",
        help_text="Importe total del servicio antes de aplicar el IVA.",
    )
    iva_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="IVA (%)",
        help_text="Porcentaje de IVA aplicado al importe total.",
    )
    total_servicio = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Total servicio",
        help_text=(
            "Importe total del servicio con IVA incluido (TOTAL SERVICIO)."
        ),
    )

    # ── Production report — PARTE DE PRODUCCIÓN ─────────────────────────────
    # Internal operational data filled by the operator on site.
    # Not customer-facing — used for internal cost and time control.
    # Datos internos de operación rellenados por el operario in situ.
    # No visibles al cliente — usados para control interno de costes y
    # tiempos.
    parte_operator_number = models.CharField(
        max_length=20,
        blank=True,
        default="",
        verbose_name="Nº operario (parte)",
        help_text="Número de operario para el parte de producción interno.",
    )
    parte_departure_base_time = models.TimeField(
        null=True,
        blank=True,
        verbose_name="Hora salida base",
        help_text="Hora de salida desde la base de operaciones.",
    )
    parte_arrival_base_time = models.TimeField(
        null=True,
        blank=True,
        verbose_name="Hora llegada base",
        help_text="Hora de regreso a la base al finalizar el servicio.",
    )
    parte_arrival_job_time = models.TimeField(
        null=True,
        blank=True,
        verbose_name="Hora llegada trabajo",
        help_text="Hora de llegada al punto donde se encuentra el vehículo.",
    )
    parte_departure_job_time = models.TimeField(
        null=True,
        blank=True,
        verbose_name="Hora salida trabajo",
        help_text="Hora de salida del punto de trabajo.",
    )
    parte_km_departure = models.DecimalField(
        max_digits=8,
        decimal_places=1,
        null=True,
        blank=True,
        verbose_name="Km salida",
        help_text="Lectura del cuentakilómetros al salir de la base.",
    )
    parte_km_arrival = models.DecimalField(
        max_digits=8,
        decimal_places=1,
        null=True,
        blank=True,
        verbose_name="Km llegada",
        help_text="Lectura del cuentakilómetros al regresar a la base.",
    )
    parte_motor_a_hours = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Horas motor A",
        help_text="Horas de funcionamiento del motor A durante el servicio.",
    )
    parte_motor_b_hours = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Horas motor B",
        help_text="Horas de funcionamiento del motor B durante el servicio.",
    )
    parte_liters_motor_a = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Litros motor A",
        help_text="Litros de combustible consumidos por el motor A.",
    )
    parte_liters_motor_b = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Litros motor B",
        help_text="Litros de combustible consumidos por el motor B.",
    )
    parte_notes = models.TextField(
        blank=True,
        default="",
        verbose_name="Observaciones (parte)",
        help_text="Observaciones internas del parte de producción.",
    )

    # ── Control ─────────────────────────────────────────────────────────────
    whatsapp_notification_sent = models.BooleanField(
        default=False,
        verbose_name="Notificación WhatsApp enviada",
        help_text=(
            "Indica si se ha enviado la notificación WhatsApp al operario "
            "con el enlace al albarán digital."
        ),
    )
    extra_notes = models.TextField(
        blank=True,
        default="",
        verbose_name="Notas adicionales",
        help_text=(
            "Observaciones internas ADMIN. "
            "No visibles en el albarán exportado."
        ),
    )
    # ── TIREA service data — Datos del expediente TIREA ────────────────────
    # Provider code assigned by the insurer to Grúas Álvarez.
    # Código de proveedor asignado por la aseguradora a Grúas Álvarez.
    provider_code = models.CharField(
        max_length=50,
        blank=True,
        default="",
        verbose_name="Cód. proveedor",
        help_text=(
            "Código de proveedor asignado por la aseguradora "
            "(ej: GP700101)."
        ),
    )
    # Insurance policy number linked to the service request.
    # Número de póliza del asegurado vinculado a la solicitud de servicio.
    policy_number = models.CharField(
        max_length=100,
        blank=True,
        default="",
        verbose_name="Nº póliza",
        help_text=(
            "Número de póliza del asegurado facilitado por la aseguradora."
        ),
    )
    # Full name of the insured person (driver or policy holder).
    # Nombre completo del asegurado (conductor o titular de la póliza).
    insured_name = models.CharField(
        max_length=200,
        blank=True,
        default="",
        verbose_name="Nombre asegurado",
        help_text="Nombre completo del asegurado o conductor del vehículo.",
    )
    # Datetime when the operator located the vehicle on site.
    # Momento en que el operario localizó el vehículo en el lugar del
    # servicio.
    arrival_time = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="F. localizado",
        help_text="Fecha y hora en que el operario localizó el vehículo.",
    )
    # Datetime when the vehicle was loaded onto the crane.
    # Momento en que el vehículo fue cargado sobre la grúa.
    load_time = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="F. cargado",
        help_text="Fecha y hora en que el vehículo fue cargado.",
    )
    # Datetime when the service request was received from the insurer.
    # Momento en que la aseguradora cursó la solicitud de servicio.
    request_time = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="F. solicitud",
        help_text=(
            "Fecha y hora de recepción de la solicitud de la aseguradora."
        ),
    )
    # Datetime when the operator started travelling to the breakdown site.
    # Momento en que el operario inició el desplazamiento al punto de avería.
    service_start_time = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="F. inicio",
        help_text="Fecha y hora de inicio del desplazamiento del operario.",
    )
    # Datetime when the service was fully completed.
    # Momento en que el servicio quedó completamente finalizado.
    completion_time = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="F. finalizado",
        help_text="Fecha y hora de finalización completa del servicio.",
    )
    # Elapsed time between request and vehicle location, as a formatted
    # string.
    # Tiempo transcurrido entre solicitud y localización del vehículo
    # (cadena formateada).
    location_elapsed = models.CharField(
        max_length=20,
        blank=True,
        default="",
        verbose_name="Tiempo localizado",
        help_text=(
            "Tiempo transcurrido hasta localizar el vehículo (ej: 01h53m)."
        ),
    )
    # True when this is a follow-up second service for the same incident.
    # True cuando este es un segundo servicio de seguimiento del mismo
    # siniestro.
    second_service = models.BooleanField(
        default=False,
        verbose_name="Segundo servicio",
        help_text=(
            "Indica si este servicio es un segundo servicio del mismo "
            "siniestro."
        ),
    )
    # True when Grúas Álvarez manages the crane dispatch directly
    # (no intermediary).
    # True cuando Grúas Álvarez gestiona el envío de la grúa directamente.
    own_crane_management = models.BooleanField(
        default=False,
        verbose_name="Gestión propia grúa",
        help_text=(
            "Indica si la gestión de la grúa es propia, sin intermediario."
        ),
    )
    # True when the service is related to a traffic accident.
    # True cuando el servicio está relacionado con un accidente de tráfico.
    is_accident = models.BooleanField(
        default=False,
        verbose_name="Accidente",
        help_text=(
            "Indica si el servicio está relacionado con un accidente de "
            "tráfico."
        ),
    )
    # True when the service attempt failed (vehicle not found, no access,
    # etc.).
    # True cuando el intento de servicio resultó fallido.
    is_failed = models.BooleanField(
        default=False,
        verbose_name="Fallido",
        help_text=(
            "Indica si el servicio resultó fallido "
            "(vehículo no localizado, sin acceso, etc.)."
        ),
    )
    # True when the service is billable to the insurer.
    # True cuando el servicio es facturable a la aseguradora.
    is_billable = models.BooleanField(
        default=True,
        verbose_name="Facturable",
        help_text="Indica si el servicio es facturable. Por defecto True.",
    )
    # Free-text comments from the insurer about coverage, authorisations,
    # etc.
    # Comentarios de texto libre de la aseguradora sobre cobertura,
    # autorizaciones, etc.
    insurer_comments = models.TextField(
        blank=True,
        default="",
        verbose_name="Comentarios aseguradora",
        help_text=(
            "Comentarios de la aseguradora sobre cobertura, destino, "
            "autopista, etc."
        ),
    )
    # Free-text observations from the company operating the service.
    # Observaciones de texto libre de la empresa que presta el servicio.
    company_observations = models.TextField(
        blank=True,
        default="",
        verbose_name="Observaciones compañía",
        help_text=(
            "Observaciones internas de la empresa prestadora del servicio."
        ),
    )

    # ── TIREA vehicle data — Datos adicionales del vehículo ─────────────────
    # Vehicle model name (e.g. ACTROS, Sprinter).
    # Nombre del modelo del vehículo (ej: ACTROS, Sprinter).
    vehicle_model = models.CharField(
        max_length=100,
        blank=True,
        default="",
        verbose_name="Modelo",
        help_text="Modelo del vehículo asistido (ej: ACTROS, Sprinter).",
    )
    # Vehicle colour as reported in TIREA.
    # Color del vehículo tal como aparece en TIREA.
    vehicle_color = models.CharField(
        max_length=50,
        blank=True,
        default="",
        verbose_name="Color",
        help_text="Color del vehículo asistido.",
    )
    # Free-text vehicle type label from TIREA (e.g. Cabeza Tractora).
    # Etiqueta de tipo de vehículo en texto libre procedente de TIREA.
    vehicle_type_label = models.CharField(
        max_length=100,
        blank=True,
        default="",
        verbose_name="Tipo vehículo",
        help_text=(
            "Tipo de vehículo según TIREA (ej: Cabeza Tractora, Turismo)."
        ),
    )
    # Free-text vehicle subtype label from TIREA.
    # Etiqueta de subtipo de vehículo en texto libre procedente de TIREA.
    vehicle_subtype_label = models.CharField(
        max_length=100,
        blank=True,
        default="",
        verbose_name="Subtipo vehículo",
        help_text="Subtipo de vehículo según TIREA.",
    )
    # Gross vehicle weight in kg as reported in TIREA.
    # Masa total del vehículo en kg tal como aparece en TIREA.
    vehicle_weight = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Peso (kg)",
        help_text="Peso del vehículo en kilogramos.",
    )
    # Number of axles of the assisted vehicle.
    # Número de ejes del vehículo asistido.
    vehicle_axes = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        verbose_name="Ejes",
        help_text="Número de ejes del vehículo asistido.",
    )
    # Tare weight of the vehicle in kg.
    # Tara del vehículo en kg.
    vehicle_tare = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Tara (kg)",
        help_text="Tara del vehículo en kilogramos.",
    )
    # H37 (S133): "Vehículo / carga" of Pepe's service sheet.
    # "Vehículo / carga" de la hoja de servicio de Pepe.
    vehicle_load = models.CharField(
        max_length=255,
        blank=True,
        default="",
        verbose_name="Vehículo / carga",
        help_text="Qué es el vehículo asistido o qué carga lleva, según "
                  "lo apunta el conductor en la hoja de servicio.",
    )
    # Number of passengers in the vehicle at the time of the incident.
    # Número de ocupantes en el vehículo en el momento del siniestro.
    num_passengers = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        verbose_name="Ocupantes",
        help_text=(
            "Número de ocupantes del vehículo en el momento del siniestro."
        ),
    )
    # Free-text description of the breakdown as reported by the insured.
    # Descripción en texto libre de la avería según el asegurado.
    breakdown_description = models.CharField(
        max_length=300,
        blank=True,
        default="",
        verbose_name="Avería",
        help_text="Descripción de la avería facilitada por el asegurado.",
    )
    # Breakdown code assigned by the insurer.
    # Código de avería asignado por la aseguradora.
    breakdown_code = models.CharField(
        max_length=50,
        blank=True,
        default="",
        verbose_name="Cód. avería",
        help_text="Código de avería asignado por la aseguradora.",
    )
    # True when the vehicle was repaired on site without towing.
    # True cuando el vehículo fue reparado in situ sin necesidad de
    # remolque.
    repair_on_site = models.BooleanField(
        default=False,
        verbose_name="Reparación in situ",
        help_text="Indica si el vehículo fue reparado in situ sin remolque.",
    )

    # ── TIREA pickup data — Datos de recogida ───────────────────────────────
    # Type of pickup location: Población, Carretera, etc.
    # Tipo de punto de recogida: Población, Carretera, etc.
    pickup_type = models.CharField(
        max_length=30,
        blank=True,
        default="",
        verbose_name="Tipo recogida",
        help_text="Tipo de punto de recogida (ej: Población, Carretera).",
    )
    # Province of the pickup location.
    # Provincia del punto de recogida.
    pickup_province = models.CharField(
        max_length=100,
        blank=True,
        default="",
        verbose_name="Provincia recogida",
        help_text="Provincia del punto de recogida del vehículo.",
    )
    # Country of the pickup location.
    # País del punto de recogida.
    pickup_country = models.CharField(
        max_length=100,
        blank=True,
        default="",
        verbose_name="País recogida",
        help_text="País del punto de recogida del vehículo.",
    )
    # Postal code of the pickup location.
    # Código postal del punto de recogida.
    pickup_cp = models.CharField(
        max_length=10,
        blank=True,
        default="",
        verbose_name="C.P. recogida",
        help_text="Código postal del punto de recogida del vehículo.",
    )

    # ── TIREA delivery data — Datos de entrega ──────────────────────────────
    # Type of delivery: In situ, Taller, Depósito, etc.
    # Tipo de entrega: In situ, Taller, Depósito, etc.
    delivery_type = models.CharField(
        max_length=50,
        blank=True,
        default="",
        verbose_name="Tipo entrega",
        help_text=(
            "Tipo de punto de entrega (ej: In situ, Taller, Depósito)."
        ),
    )
    # Province of the delivery location.
    # Provincia del punto de entrega.
    delivery_province = models.CharField(
        max_length=100,
        blank=True,
        default="",
        verbose_name="Provincia entrega",
        help_text="Provincia del punto de entrega del vehículo.",
    )
    # Locality of the delivery location.
    # Localidad del punto de entrega.
    delivery_locality = models.CharField(
        max_length=150,
        blank=True,
        default="",
        verbose_name="Localidad entrega",
        help_text="Localidad del punto de entrega del vehículo.",
    )
    # Country of the delivery location.
    # País del punto de entrega.
    delivery_country = models.CharField(
        max_length=100,
        blank=True,
        default="",
        verbose_name="País entrega",
        help_text="País del punto de entrega del vehículo.",
    )
    # H37 (S133). Código postal del punto de entrega.
    delivery_cp = models.CharField(
        max_length=10,
        blank=True,
        default="",
        verbose_name="C.P. entrega",
        help_text="Código postal del punto de entrega del vehículo.",
    )
    # Full street address of the delivery location.
    # Dirección completa del punto de entrega.
    delivery_address = models.CharField(
        max_length=300,
        blank=True,
        default="",
        verbose_name="Dirección entrega",
        help_text="Dirección completa del punto de entrega del vehículo.",
    )
    # RIS motive — reason for roadside intervention service.
    # Pending completion with the actual dropdown values from TIREA.
    # Motivo RIS — razón de la intervención en carretera.
    # Pendiente de completar con los valores reales del desplegable TIREA.
    RIS_MOTIVE_CHOICES = [
        # Pendiente de completar con los valores reales del desplegable
        # TIREA.
    ]
    ris_motive = models.CharField(
        max_length=50,
        choices=RIS_MOTIVE_CHOICES,
        blank=True,
        null=True,
        verbose_name="Motivo RIS",
        help_text=(
            "Motivo de la intervención RIS según el desplegable de TIREA."
        ),
    )
    # Kilometres driven by the operator (chófer) as recorded in TIREA.
    # Kilómetros recorridos por el chófer según TIREA.
    driver_km = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Km chófer",
        help_text="Kilómetros recorridos por el chófer según TIREA.",
    )
    # Total kilometres of the service as recorded in TIREA.
    # Kilómetros totales del servicio según TIREA.
    total_km_tirea = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Km totales TIREA",
        help_text="Kilómetros totales del servicio registrados en TIREA.",
    )
    # H37 (S138): the TIREA document (photo or PDF) the service came
    # from, kept in GCS so the room bot can post it.
    # Documento de TIREA (foto o PDF) del que salió el servicio,
    # guardado en GCS para que el bot de la sala lo publique.
    source_document_blob = models.CharField(
        max_length=500,
        blank=True,
        default="",
        verbose_name="Documento de origen (blob en GCS)",
    )
    source_document_type = models.CharField(
        max_length=100,
        blank=True,
        default="",
        verbose_name="Tipo del documento de origen",
    )

    # ── Control ─────────────────────────────────────────────────────────────
    created_at = models.DateTimeField(
        auto_now_add=True, verbose_name="Fecha de creación"
    )
    updated_at = models.DateTimeField(
        auto_now=True, verbose_name="Fecha de modificación"
    )

    class Meta:
        verbose_name = "Orden de trabajo (asistencia)"
        verbose_name_plural = "Órdenes de trabajo (asistencia)"
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        """
        Overrides save to auto-generate work_order_number on first persist.
        Queries existing orders for the same company on today to build the
        3-digit daily ordinal. The unique constraint on work_order_number
        catches edge-case duplicates under concurrent writes.
        ---
        Sobreescribe save para auto-generar work_order_number en el primer
        guardado. Consulta las órdenes existentes de la misma empresa en el
        día de hoy para construir el ordinal diario de 3 dígitos. La
        restricción unique sobre work_order_number captura duplicados en
        escrituras concurrentes en casos límite.
        """
        if not self.work_order_number:
            import datetime
            today = datetime.date.today()
            date_str = today.strftime("%Y%m%d")
            # Count today orders for this company to determine next ordinal.
            # work_order_number starts with the 8-char date string
            # (YYYYMMDD).
            # Contamos las órdenes del día de esta empresa para el siguiente
            # ordinal.
            count = WorkOrderAssistance.objects.filter(
                company=self.company,
                work_order_number__startswith=date_str,
            ).count()
            self.work_order_number = f"{date_str}{count + 1:03d}"
        super().save(*args, **kwargs)

    def refresh_status(self):
        """
        Move the order status after a change of its albaranes.

        ---

        Estado de la orden según sus albaranes (S140; hasta ahora se
        quedaba siempre en "Pendiente"): en curso en cuanto uno sale del
        estado inicial; completada cuando todos están cerrados (en base,
        en ruta o anulados, con al menos uno cerrado). "Facturada" solo la
        pone la oficina y no se toca. Devuelve el estado.
        """
        Unit = WorkOrderAssistanceUnit
        if self.status == self.STATUS_INVOICED:
            return self.status
        statuses = list(self.units.values_list("status", flat=True))
        gone = (Unit.STATUS_CLOSED_BASE, Unit.STATUS_CANCELLED)
        waiting = (
            Unit.STATUS_PENDING, Unit.STATUS_NOTIFY_FAILED,
            Unit.STATUS_CANCELLED,
        )
        if not statuses:
            return self.status
        if all(s in gone for s in statuses):
            if Unit.STATUS_CLOSED_BASE not in statuses:
                return self.status
            new = self.STATUS_COMPLETED
        elif any(s not in waiting for s in statuses):
            new = self.STATUS_IN_PROGRESS
        else:
            new = self.STATUS_PENDING
        if new != self.status:
            WorkOrderAssistance.objects.filter(pk=self.pk).update(status=new)
            self.status = new
        return new

    def __str__(self):
        return (
            f"OT {self.work_order_number} — "
            f"{self.insurer.name} — {self.get_status_display()}"
        )


# ---------------------------------------------------------------------------
# 12. WORK ORDER ASSISTANCE UNIT — Individual albarán per vehicle unit.
#     Albarán individual por cada vehículo de Grúas Álvarez en el servicio.
# ---------------------------------------------------------------------------

class WorkOrderAssistanceUnit(models.Model):
    """
    Represents one individual albarán within a WorkOrderAssistance service
    order. Each vehicle dispatched by Grúas Álvarez (crane, workshop car,
    platform, etc.) generates its own independent unit. The printed albarán
    number is composed as: work_order_number-unit_number.

    A unit can itself be a deferred service (is_overnight=True), in which
    case operator_2 and machine_2 represent the second leg (base to
    destination), with its own independent km data in phase2_km.
    ---
    Representa un albarán individual dentro de una orden de servicio
    WorkOrderAssistance. Cada vehículo enviado por Grúas Álvarez (grúa,
    coche de taller, plataforma, etc.) genera su propia unidad
    independiente. El número de albarán impreso se compone como:
    work_order_number-unit_number.

    Una unidad puede ser a su vez un servicio diferido (is_overnight=True),
    en cuyo caso operator_2 y machine_2 representan el segundo tramo (base
    a destino), con sus propios km independientes en phase2_km.
    """

    # --- Status choices ---
    # --- Opciones de estado ---
    STATUS_PENDING = "PENDING"
    STATUS_NOTIFIED = "NOTIFIED"
    STATUS_DOWNLOADED = "DOWNLOADED"
    STATUS_IN_PROGRESS = "IN_PROGRESS"
    STATUS_COMPLETED = "COMPLETED"
    STATUS_CLOSED_UNSIGNED = "CLOSED_UNSIGNED"
    STATUS_SIGNED_RECEIVED = "SIGNED_RECEIVED"
    # H37 (S132): notice accepted by Twilio, delivery not confirmed yet.
    # Aviso aceptado por Twilio, entrega aún sin confirmar.
    STATUS_NOTIFY_SENDING = "NOTIFY_SENDING"
    # H37 (S132): Twilio reported the notice as not delivered.
    # Twilio ha informado de que el aviso no se ha entregado.
    STATUS_NOTIFY_FAILED = "NOTIFY_FAILED"
    # H37 (S133): closed in base by the driver (final km and refuelling);
    # driver and machine are free again. Dossier phase 4.
    # Cerrado en base por el conductor (km finales y repostaje);
    # conductor y máquina vuelven a estar libres. Fase 4 del dossier.
    STATUS_CLOSED_BASE = "CLOSED_BASE"
    # H37 (S133): cancelled from the office with a reason (test albaranes,
    # services called off); it leaves the board and the app and frees
    # the driver and the machine.
    # Anulado desde la oficina con motivo (albaranes de prueba, servicios
    # anulados); sale del panel y de la app y libera conductor y máquina.
    STATUS_CANCELLED = "CANCELLED"

    STATUS_CHOICES = [
        (STATUS_PENDING,         "Pendiente"),
        (STATUS_NOTIFY_SENDING,  "Enviando aviso"),
        (STATUS_NOTIFIED,        "Notificado"),
        (STATUS_NOTIFY_FAILED,   "Aviso fallido"),
        (STATUS_DOWNLOADED,      "Descargado"),
        (STATUS_IN_PROGRESS,     "En curso"),
        (STATUS_COMPLETED,       "Completado"),
        (STATUS_CLOSED_UNSIGNED, "Cerrado sin firma"),
        (STATUS_SIGNED_RECEIVED, "Firma recibida"),
        (STATUS_CLOSED_BASE,     "Cerrado en base"),
        (STATUS_CANCELLED,       "Anulado"),
    ]

    # ── Relations ───────────────────────────────────────────────────────────
    work_order = models.ForeignKey(
        WorkOrderAssistance,
        on_delete=models.CASCADE,
        related_name="units",
        verbose_name="Orden de trabajo",
        help_text=(
            "Orden de trabajo (expediente) a la que pertenece esta unidad."
        ),
    )
    # Operator assigned to phase 1 (pickup leg). H37 (S133): empty
    # until the office drags a driver onto the albarán in the traffic
    # panel; it cannot be sent without one.
    # Operario asignado a la fase 1 (tramo de recogida). H37 (S133):
    # vacío hasta que la oficina arrastra un conductor al albarán en
    # el panel de tráfico; sin conductor no se puede enviar.
    operator = models.ForeignKey(
        CompanyUser,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="assistance_units_primary",
        verbose_name="Chófer",
        help_text=(
            "Chófer asignado al primer tramo del servicio. Vacío "
            "mientras el albarán está sin asignar."
        ),
    )
    # Operator assigned to phase 2 (delivery leg). Only for deferred
    # services.
    # Operario asignado a la fase 2 (tramo de entrega). Solo en servicios
    # diferidos.
    operator_2 = models.ForeignKey(
        CompanyUser,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="assistance_units_secondary",
        verbose_name="Chófer (fase 2)",
        help_text=(
            "Chófer del segundo tramo (base a destino). "
            "Solo en servicios diferidos (is_overnight=True). "
            "Puede coincidir con el chófer del primer tramo."
        ),
    )

    # H37 (S133): queued service. The albarán already has its crew, but
    # the driver is still on another service; it is sent by itself when
    # that one finishes (meeting with Pepe: "darle otro servicio para
    # cuando acabe el primero"). Empty when it is not queued.
    # Servicio en cola: el albarán ya tiene su equipo, pero el conductor
    # sigue en otro servicio; se envía solo cuando termina ese. Vacío si
    # no está en cola.
    queued_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="En cola desde",
        help_text="Se envía solo cuando el conductor termina el servicio "
                  "anterior.",
    )

    # H37 (S133): helpers that go with the driver in this vehicle
    # (e.g. a service car with two workers). Chosen for each service;
    # they do not use the app, they only appear on the albarán.
    # Ayudantes que van con el conductor en este vehículo (p. ej. un
    # coche de servicio con dos operarios). Se eligen en cada servicio
    # (Miguel Ángel, S133); no usan la app, solo salen en el albarán.
    helpers = models.ManyToManyField(
        CompanyUser,
        blank=True,
        related_name="assistance_units_helper",
        verbose_name="Ayudantes",
        help_text="Operarios que acompañan al conductor en este vehículo.",
    )

    # ── Unit identifier ─────────────────────────────────────────────────────
    # Ordinal position of this unit within the work order (1, 2, 3...).
    # The printed albarán number is: work_order_number-unit_number.
    # Posición ordinal de esta unidad dentro de la orden (1, 2, 3...).
    # El número de albarán impreso es: work_order_number-unit_number.
    unit_number = models.PositiveSmallIntegerField(
        verbose_name="Nº unidad",
        help_text=(
            "Ordinal de esta unidad dentro de la orden de trabajo "
            "(1, 2, 3...). "
            "El albarán impreso se identifica como "
            "work_order_number-unit_number."
        ),
    )

    # ── Machine identifiers ─────────────────────────────────────────────────
    # Machine or plate assigned to phase 1.
    # Máquina o matrícula asignada a la fase 1.
    machine = models.CharField(
        max_length=100,
        blank=True,
        default="",
        verbose_name="Máquina",
        help_text=(
            "Matrícula o identificador de la máquina asignada al primer "
            "tramo."
        ),
    )
    # H37 (S133): fleet machine assigned in the traffic panel. The
    # text field `machine` keeps its label ("X11 9237LGN") for the
    # albarán and the PDF.
    # Máquina de la flota asignada en el panel de tráfico. El campo de
    # texto `machine` conserva su etiqueta para el albarán y el PDF.
    machine_asset = models.ForeignKey(
        "fleet.MachineAsset",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="assistance_units",
        verbose_name="Máquina de la flota",
        help_text=(
            "Máquina de la familia ASISTENCIA asignada al primer tramo "
            "desde el panel de tráfico."
        ),
    )
    # Machine or plate assigned to phase 2. Only for deferred services.
    # Máquina o matrícula asignada a la fase 2. Solo en servicios diferidos.
    machine_2 = models.CharField(
        max_length=100,
        blank=True,
        default="",
        verbose_name="Máquina (fase 2)",
        help_text=(
            "Matrícula o identificador de la máquina del segundo tramo. "
            "Solo en servicios diferidos. Puede coincidir con la máquina "
            "del primer tramo."
        ),
    )

    # ── Service flags ───────────────────────────────────────────────────────
    # True when this unit performs a deferred service (two legs on different
    # days).
    # True cuando esta unidad realiza un servicio diferido (dos tramos en
    # días distintos).
    is_overnight = models.BooleanField(
        default=False,
        verbose_name="Pernocta",
        help_text=(
            "Indica si esta unidad realiza un servicio diferido: recoge el "
            "vehículo un día y lo traslada a destino en otro momento. "
            "Cuando es True, operator_2, machine_2 y phase2_km deben estar "
            "informados."
        ),
    )

    # ── Kilometre data ──────────────────────────────────────────────────────
    # Kilometres for phase 1 (base to pickup and back, or base to
    # destination).
    # Kilómetros de la fase 1 (base a recogida y vuelta, o base a destino).
    phase1_km = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Km fase 1",
        help_text="Kilómetros del primer tramo del servicio.",
    )
    # Kilometres for phase 2. Only populated when is_overnight is True.
    # Kilómetros de la fase 2. Solo informado cuando is_overnight es True.
    phase2_km = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Km fase 2",
        help_text=(
            "Kilómetros del segundo tramo del servicio. "
            "Solo en servicios diferidos (is_overnight=True)."
        ),
    )

    # ── Billable service concepts ────────────────────────────────────────────
    # Departure fee — fixed charge per dispatch.
    # Importe de salida — cargo fijo por desplazamiento.
    departure_fee = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Salida",
        help_text="Importe fijo de salida/enganche del servicio.",
    )
    # Rescue hours billed for this unit.
    # Horas de rescate facturadas para esta unidad.
    rescue_hours = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Horas rescate",
        help_text="Horas de rescate/extracción facturables para esta unidad.",
    )
    # Wait hours billed for this unit.
    # Horas de espera facturadas para esta unidad.
    wait_hours = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Horas espera",
        help_text="Horas de espera facturables para esta unidad.",
    )

    # ── Synchronisation ─────────────────────────────────────────────────────
    # Timestamp of last successful sync from the Android app
    # (null = not synced yet).
    # Momento de la última sincronización exitosa desde la app Android
    # (null = sin sync).
    synced_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Sincronizado",
        help_text=(
            "Fecha y hora de la última sincronización exitosa desde la app "
            "Android. "
            "Null indica que la unidad aún no ha sido sincronizada."
        ),
    )

    # ── Status / control ────────────────────────────────────────────────────
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
        verbose_name="Estado",
        help_text=(
            "PENDING: unidad creada, pendiente de notificar al operario. "
            "NOTIFY_SENDING: aviso aceptado por Twilio, entrega sin "
            "confirmar. "
            "NOTIFIED: WhatsApp confirma la entrega del aviso al operario. "
            "NOTIFY_FAILED: Twilio informa de que el aviso no se entregó. "
            "DOWNLOADED: operario ha abierto el albarán en la app. "
            "IN_PROGRESS: operario en servicio activo. "
            "COMPLETED: albarán recibido en plataforma con firma. "
            "CLOSED_UNSIGNED: albarán recibido sin firma — pendiente de "
            "gestión. "
            "SIGNED_RECEIVED: supervisor confirma firma recibida del cliente. "
            "CLOSED_BASE: el conductor cierra en base con km finales y "
            "repostaje; conductor y máquina quedan libres. "
            "CANCELLED: anulado desde la oficina con motivo; conductor y "
            "máquina quedan libres."
        ),
    )

    # ── Traceability timestamps — Marcas de tiempo de trazabilidad ───────────
    # Datetime when the WhatsApp session renewal template was sent to the
    # operator.
    # Momento en que se envió el template de renovación de sesión WhatsApp
    # al operario.
    notified_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Notificado en",
        help_text=(
            "Fecha y hora en que se envió el template WhatsApp al operario. "
            "Null hasta que se ejecuta send_operator_albaran_notification()."
        ),
    )
    # H37 (S132): Twilio SID of the last notice, to match its delivery
    # status callback, and the reason when it was not delivered.
    # SID de Twilio del último aviso, para casar el informe de entrega
    # que manda Twilio, y el motivo cuando no se ha entregado.
    notify_message_sid = models.CharField(
        max_length=64,
        blank=True,
        default="",
        verbose_name="SID del aviso",
        help_text="SID de Twilio del último aviso por WhatsApp.",
    )
    notify_error = models.CharField(
        max_length=255,
        blank=True,
        default="",
        verbose_name="Error del aviso",
        help_text="Motivo por el que el último aviso no se entregó.",
    )
    # Datetime when the operator opened the albarán in the Android app or
    # panel.
    # Momento en que el operario abrió el albarán en la app Android o el
    # panel.
    downloaded_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Descargado en",
        help_text=(
            "Fecha y hora en que el operario descargó o abrió el albarán. "
            "Registrado por la app Android al cargar el albarán por primera "
            "vez."
        ),
    )
    # Datetime when the operator started the active service leg.
    # Momento en que el operario inició el tramo de servicio activo.
    started_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Iniciado en",
        help_text=(
            "Fecha y hora en que el operario marcó inicio del servicio en "
            "la app Android."
        ),
    )
    # Datetime when the signed albarán was received by the platform.
    # Momento en que el albarán firmado fue recibido por la plataforma.
    completed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Completado en",
        help_text=(
            "Fecha y hora en que la plataforma recibió el albarán firmado "
            "desde la app Android."
        ),
    )
    # Datetime when the unsigned albarán was closed by the operator.
    # Momento en que el operario cerró el albarán sin firma.
    closed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Cerrado en",
        help_text=(
            "Fecha y hora en que el operario cerró el albarán sin firma del "
            "cliente."
        ),
    )
    # Mandatory justification when closing without signature.
    # Justificación obligatoria al cerrar sin firma.
    unsigned_reason = models.TextField(
        blank=True,
        default="",
        verbose_name="Motivo cierre sin firma",
        help_text=(
            "Justificación obligatoria cuando el albarán se cierra sin "
            "firma del cliente. "
            "Vacío en albaranes cerrados con firma."
        ),
    )
    # Datetime when the supervisor confirmed the signed copy was received
    # from the client.
    # Momento en que el supervisor confirmó la recepción de la copia firmada
    # del cliente.
    signed_received_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Firma recibida en",
        help_text=(
            "Fecha y hora en que el supervisor confirmó la recepción de la "
            "firma del cliente. "
            "Solo aplica a albaranes cerrados sin firma "
            "(CLOSED_UNSIGNED → SIGNED_RECEIVED)."
        ),
    )
    # Supervisor who confirmed the signed copy reception.
    # Supervisor que confirmó la recepción de la copia firmada.
    signed_received_by = models.ForeignKey(
        CompanyUser,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="assistance_units_signed_received",
        verbose_name="Firma confirmada por",
        help_text=(
            "Supervisor que marcó la recepción de la firma del cliente. "
            "Null en todos los estados salvo SIGNED_RECEIVED."
        ),
    )
    # H37 (S133): base closing (dossier phase 4).
    # Cierre en base (fase 4 del dossier).
    base_km_end = models.DecimalField(
        max_digits=10,
        decimal_places=1,
        null=True,
        blank=True,
        verbose_name="Km finales",
        help_text="Cuentakilómetros de la máquina al llegar a base.",
    )
    refueled = models.BooleanField(
        null=True,
        blank=True,
        verbose_name="Ha repostado",
        help_text="Si el conductor repostó en el servicio. Vacío hasta "
                  "el cierre en base.",
    )
    refuel_liters = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Litros repostados",
    )
    base_closed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Cerrado en base en",
    )
    # H37 (S133): estimate of the service for the fuel cost, entered by
    # hand when the office closes it. The client is charged as if the
    # truck went from base to the service and back, even when it chains
    # services, so these figures are base-service-base, not the real
    # ones of the machine.
    # Estimado del servicio para repercutir el gasoil, metido a mano al
    # cerrar desde la oficina. Al cliente se le cobra como si el camión
    # volviera a base aunque encadene servicios (Miguel Ángel, S133),
    # así que son km y gasoil de base-servicio-base, no los reales.
    estimated_km = models.DecimalField(
        max_digits=8,
        decimal_places=1,
        null=True,
        blank=True,
        verbose_name="Km estimados del servicio",
        help_text="De base al servicio y vuelta, aunque la máquina "
                  "encadenara otro servicio.",
    )
    estimated_fuel_liters = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Gasoil estimado (l)",
        help_text="Consumo estimado del servicio, de base a base.",
    )
    base_closed_by = models.ForeignKey(
        CompanyUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="Cerrado en base por",
    )

    # H37 (S133): service sheet of Pepe (hoja de servicio). The driver
    # cannot see the sheet until he enters the km at departure; the
    # departure time (`started_at`) is entered by the driver too; the
    # departure base and the night flag are recorded by the system and
    # only the office sees them.
    # Hoja de servicio de Pepe. El conductor no ve la hoja hasta meter
    # los km y la hora de salida (`started_at`); la base de salida y el
    # nocturno los apunta el sistema y solo los ve la oficina.
    km_start = models.DecimalField(
        max_digits=10,
        decimal_places=1,
        null=True,
        blank=True,
        verbose_name="Km salida",
        help_text="Cuentakilómetros de la máquina al salir de base. "
                  "Obligatorio para abrir la hoja de servicio.",
    )
    departure_base = models.ForeignKey(
        "budgets.Base",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="Base de salida",
        help_text="Base del conductor (o de la máquina) al salir. Solo "
                  "oficina.",
    )
    is_night = models.BooleanField(
        null=True,
        blank=True,
        verbose_name="Nocturno",
        help_text="Si la salida cae en el horario nocturno de la "
                  "aseguradora (o el de la empresa). Solo oficina.",
    )
    arrived_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Hora entrada servicio",
        help_text="Cuando el conductor llega al servicio. Solo oficina.",
    )
    work_hours = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Horas trabajo",
    )
    driver_notes = models.TextField(
        blank=True,
        default="",
        verbose_name="Observaciones del conductor",
    )
    arrival_base = models.ForeignKey(
        "budgets.Base",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="Base de llegada",
        help_text="Base a la que vuelve el conductor al terminar.",
    )
    base_arrived_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Hora llegada base",
    )

    # H37 (S134): queue mode and time estimate. A queued albarán goes
    # either after the driver is back in base or straight from where
    # he finishes; the estimate gives the arrival at the pickup and the
    # end of the service, so a crew that will finish soon can be given
    # the next one (Miguel Ángel, S134).
    # Modo de cola y estimado de tiempos. Un albarán en cola sale con
    # vuelta a base o desde donde esté el conductor al terminar; el
    # estimado da la llegada a la recogida y el fin del servicio, para
    # dar el siguiente a quien va a terminar antes.
    QUEUE_FROM_BASE = "from_base"
    QUEUE_FROM_HERE = "from_here"
    QUEUE_MODE_CHOICES = [
        (QUEUE_FROM_BASE, "Con vuelta a base"),
        (QUEUE_FROM_HERE, "Desde donde esté"),
    ]
    queue_mode = models.CharField(
        max_length=10,
        choices=QUEUE_MODE_CHOICES,
        default=QUEUE_FROM_BASE,
        verbose_name="Cola",
        help_text="Con vuelta a base: sale cuando el conductor cierra el "
                  "anterior en base. Desde donde esté: sale al terminar "
                  "el anterior y va directo a la recogida.",
    )
    eta_pickup_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Llegada estimada a la recogida",
    )
    eta_finish_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Fin estimado",
        help_text="Hora en que se estima que el conductor termina el "
                  "servicio y queda libre (en el destino o in situ).",
    )
    eta_km = models.DecimalField(
        max_digits=8,
        decimal_places=1,
        null=True,
        blank=True,
        verbose_name="Km estimados hasta terminar",
    )
    eta_end_place = models.CharField(
        max_length=255,
        blank=True,
        default="",
        verbose_name="Lugar estimado de fin",
    )
    eta_detail = models.CharField(
        max_length=255,
        blank=True,
        default="",
        verbose_name="Detalle del estimado",
        help_text="Desde dónde se calcula y qué tiempos de trabajo suma.",
    )
    eta_computed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Estimado calculado en",
    )

    # H37 (S138): chained on the road. Coming back from this albarán the
    # driver left for the next one (`chained_to`) from where he was, so
    # the return to base he wrote in his km was never driven. Internal
    # only: the client and the insurer see the driver's km, as always.
    # Encadenado en ruta: volviendo de este albarán el chófer salió al
    # siguiente desde donde estaba, así que la vuelta a base que anotó
    # en sus km no se hizo. Solo interno: el cliente y la compañía ven
    # los km del chófer, como siempre.
    chained_to = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="chained_from",
        verbose_name="Encadenado en ruta con",
    )
    chain_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Hora del encadenamiento",
        help_text="Hora de salida del siguiente albarán.",
    )
    chain_odometer = models.DecimalField(
        max_digits=10,
        decimal_places=1,
        null=True,
        blank=True,
        verbose_name="Km al encadenar",
        help_text="Km de salida del siguiente albarán (cuentakilómetros).",
    )
    chain_latitude = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True,
        verbose_name="Latitud del encadenamiento",
    )
    chain_longitude = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True,
        verbose_name="Longitud del encadenamiento",
    )
    chain_return_km_est = models.DecimalField(
        max_digits=8,
        decimal_places=1,
        null=True,
        blank=True,
        verbose_name="Vuelta a base estimada (km)",
        help_text="Google: del punto de encadenamiento a la base.",
    )
    chain_return_minutes_est = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name="Vuelta a base estimada (min)",
    )
    # H37 (S140), Miguel Ángel tras la prueba de campo del 28/10: the
    # driver writes the odometer when he arrives (with the GPS km as a
    # guide) and the km back to base as a distance (with Google's
    # distance from where he is as a guide); the km of the service are
    # worked out from them.
    # El chófer anota el cuentakilómetros al llegar (con los km del GPS
    # como orientación) y los km de vuelta a base como distancia (con la
    # de Google desde donde está como orientación); los km del servicio
    # salen de ahí.
    km_arrival = models.DecimalField(
        max_digits=9,
        decimal_places=1,
        null=True,
        blank=True,
        verbose_name="Km al llegar al servicio",
        help_text="Cuentakilómetros al llegar a la recogida o al trabajo.",
    )
    km_delivery = models.DecimalField(
        max_digits=9,
        decimal_places=1,
        null=True,
        blank=True,
        verbose_name="Km en la entrega",
        help_text="Cuentakilómetros al entregar el vehículo (remolque).",
    )
    km_return = models.DecimalField(
        max_digits=7,
        decimal_places=1,
        null=True,
        blank=True,
        verbose_name="Km de vuelta a base",
        help_text="Distancia de vuelta a base que anota el chófer.",
    )
    closed_in_route = models.BooleanField(
        default=False,
        verbose_name="Cerrado en ruta",
        help_text=(
            "El chófer lo cerró en ruta: la vuelta a base no se hizo; el "
            "repostaje va con el siguiente albarán."
        ),
    )

    created_at = models.DateTimeField(
        auto_now_add=True, verbose_name="Fecha de creación"
    )
    updated_at = models.DateTimeField(
        auto_now=True, verbose_name="Fecha de modificación"
    )

    class Meta:
        verbose_name = "Unidad de orden de trabajo (asistencia)"
        verbose_name_plural = "Unidades de orden de trabajo (asistencia)"
        ordering = ["work_order", "unit_number"]
        unique_together = [("work_order", "unit_number")]

    def __str__(self):
        return (
            f"{self.work_order.work_order_number}-{self.unit_number:02d} — "
            f"{self.operator or 'sin chófer'} — "
            f"{self.get_status_display()}"
        )

    @property
    def billed_km(self):
        """
        Km the driver wrote (both legs with overnight), or None.

        ---

        Km que anotó el chófer (los dos tramos con pernocta), o None: lo
        que se cobra.
        """
        if self.phase1_km is None:
            return None
        return self.phase1_km + (self.phase2_km or 0)

    @property
    def chain_driven_km(self):
        """
        Km really driven until the chaining (odometer), or None.

        ---

        Km hechos de verdad hasta el encadenamiento (cuentakilómetros:
        salida del siguiente menos salida de este), o None.
        """
        if self.chain_odometer is None or self.km_start is None:
            return None
        return self.chain_odometer - self.km_start

    @property
    def chain_saved_km(self):
        """
        Km billed and not driven thanks to the chaining, or None.

        ---

        Km cobrados sin hacer por encadenar en ruta: los que anotó el
        chófer menos los hechos hasta el encadenamiento. None sin datos.
        """
        billed, driven = self.billed_km, self.chain_driven_km
        if self.chained_to_id is None or billed is None or driven is None:
            return None
        return billed - driven

    @property
    def albaran_number(self):
        """
        Printed albarán number (work order number and unit).

        ---

        Número de albarán impreso: número de orden y unidad.
        """
        return f"{self.work_order.work_order_number}-{self.unit_number:02d}"

    @property
    def helper_names(self):
        """
        Names of the helpers of the albarán (S133).

        ---

        Nombres de los ayudantes del albarán (S133).
        """
        return [
            helper.user.get_full_name() or helper.user.username
            for helper in self.helpers.all()
        ]


class WorkOrderAssistanceUnitEvent(models.Model):
    """
    H37 (S133). Audit trail of an albarán: every status change and
    every assignment, with its time and the panel user who made it.

    ---

    H37 (S133). Registro de auditoría de un albarán: cada cambio de
    estado y cada asignación, con la hora y el usuario del panel que
    lo hizo (dossier de Pepe: "cada cambio de estado guarda hora y
    usuario"). `created_by` vacío significa que lo hizo el sistema
    (informe de entrega de WhatsApp, el propio operario desde el
    albarán).
    """

    KIND_CREATED = "CREATED"
    KIND_STATUS = "STATUS"
    KIND_ASSIGN = "ASSIGN"
    KIND_UNASSIGN = "UNASSIGN"
    KIND_CHOICES = [
        (KIND_CREATED, "Albarán creado"),
        (KIND_STATUS, "Cambio de estado"),
        (KIND_ASSIGN, "Asignación"),
        (KIND_UNASSIGN, "Asignación retirada"),
    ]

    unit = models.ForeignKey(
        WorkOrderAssistanceUnit,
        on_delete=models.CASCADE,
        related_name="events",
        verbose_name="Unidad",
    )
    kind = models.CharField(
        max_length=10,
        choices=KIND_CHOICES,
        verbose_name="Tipo",
    )
    from_status = models.CharField(
        max_length=20,
        blank=True,
        default="",
        verbose_name="Estado anterior",
    )
    to_status = models.CharField(
        max_length=20,
        blank=True,
        default="",
        verbose_name="Estado nuevo",
    )
    detail = models.CharField(
        max_length=255,
        blank=True,
        default="",
        verbose_name="Detalle",
        help_text="Qué se asignó o retiró, o el motivo del cambio.",
    )
    created_by = models.ForeignKey(
        CompanyUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assistance_unit_events",
        verbose_name="Usuario",
        help_text="Usuario del panel. Vacío: lo hizo el sistema.",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Fecha y hora",
    )

    class Meta:
        verbose_name = "Evento de albarán (asistencia)"
        verbose_name_plural = "Eventos de albarán (asistencia)"
        ordering = ["unit", "created_at", "pk"]

    def __str__(self):
        return f"{self.unit_id} {self.kind} {self.created_at:%d/%m %H:%M}"

    @classmethod
    def status_change(cls, unit, from_status, to_status, by=None,
                      detail=""):
        """
        Record a status change of a unit (nothing if it did not change).

        ---

        Registra un cambio de estado de la unidad (nada si no cambió).
        """
        if from_status == to_status:
            return None
        event = cls.objects.create(
            unit=unit,
            kind=cls.KIND_STATUS,
            from_status=from_status or "",
            to_status=to_status or "",
            detail=(detail or "")[:255],
            created_by=by,
        )
        # S140: the order follows its albaranes (it stayed "Pendiente").
        # La orden sigue a sus albaranes (se quedaba en "Pendiente").
        unit.work_order.refresh_status()
        # S140 (Miguel Ángel): a driver coming back is given another
        # service by phone and does not even stop; when the new albarán
        # is sent to him, the one he comes back from is closed on the
        # road with the GPS.
        # A un chófer que vuelve le dan otro servicio por teléfono y ni
        # para; al enviarle el nuevo, el que volvía se cierra en ruta
        # con el GPS.
        if (
            to_status == WorkOrderAssistanceUnit.STATUS_NOTIFY_SENDING
            and from_status in (
                WorkOrderAssistanceUnit.STATUS_PENDING,
                WorkOrderAssistanceUnit.STATUS_NOTIFY_FAILED,
            )
            and unit.operator_id
        ):
            from budgets.service_chain import close_returning_in_route

            close_returning_in_route(unit, by)
        # S133: when a driver finishes, his next queued albarán is sent
        # (after the commit, so the finished one is already saved).
        # Al terminar un conductor se envía su siguiente albarán en cola
        # (tras el commit, con el terminado ya guardado).
        finished = (
            WorkOrderAssistanceUnit.STATUS_COMPLETED,
            WorkOrderAssistanceUnit.STATUS_CLOSED_UNSIGNED,
            WorkOrderAssistanceUnit.STATUS_SIGNED_RECEIVED,
            WorkOrderAssistanceUnit.STATUS_CLOSED_BASE,
            WorkOrderAssistanceUnit.STATUS_CANCELLED,
        )
        if unit.operator_id:
            from django.db import transaction

            company_id = unit.work_order.company_id
            driver_id = unit.operator_id
            release = to_status in finished

            def _after_commit():
                from budgets.assistance_traffic import release_queue
                from budgets.service_eta import refresh_driver_by_pk
                from ivr_config.models import Company

                company = Company.objects.filter(pk=company_id).first()
                if company is None:
                    return
                if release:
                    release_queue(
                        company, driver_id, finished_status=to_status,
                    )
                # S134: every status change moves the estimates of the
                # driver's albaranes.
                # Cada cambio de estado mueve los estimados del
                # conductor.
                refresh_driver_by_pk(company, driver_id)

            transaction.on_commit(_after_commit)
        return event


# ---------------------------------------------------------------------------
# 13. WORK ORDER ASSISTANCE SIGNATURE — Digital client signature per unit.
#     Firma digital del cliente por unidad de albarán.
# ---------------------------------------------------------------------------

class WorkOrderAssistanceSignature(models.Model):
    """
    Stores the digital signature captured from the client on the operator's
    Android device at the moment of service delivery. One signature per unit.
    The signature_data field stores the raw base64-encoded PNG produced by
    the AlbaranApp canvas. The signed_offline flag indicates the signature
    was captured without network coverage and synced later.
    ---
    Almacena la firma digital capturada del cliente en el dispositivo Android
    del operario en el momento de la entrega del servicio. Una firma por
    unidad. El campo signature_data almacena el PNG en base64 producido por
    el canvas de AlbaranApp. El flag signed_offline indica que la firma fue
    capturada sin cobertura y sincronizada posteriormente.
    """

    # One-to-one relation: each unit has at most one client signature.
    # Relación uno a uno: cada unidad tiene como máximo una firma del cliente.
    unit = models.OneToOneField(
        WorkOrderAssistanceUnit,
        on_delete=models.CASCADE,
        related_name="signature",
        verbose_name="Unidad",
        help_text="Unidad de albarán a la que pertenece esta firma.",
    )
    # Base64-encoded PNG of the client signature captured on the Android
    # canvas.
    # PNG en base64 de la firma del cliente capturada en el canvas Android.
    signature_data = models.TextField(
        verbose_name="Firma (base64)",
        help_text="Imagen PNG de la firma del cliente codificada en base64.",
    )
    # Optional name of the person who signed.
    # Nombre opcional de la persona que firma.
    signer_name = models.CharField(
        max_length=200,
        blank=True,
        default="",
        verbose_name="Firmante",
        help_text="Nombre de la persona que firma el albarán (opcional).",
    )
    # True when the signature was captured offline and synced later.
    # True cuando la firma fue capturada sin cobertura y sincronizada después.
    signed_offline = models.BooleanField(
        default=False,
        verbose_name="Firmado offline",
        help_text=(
            "Indica si la firma fue capturada sin cobertura de red "
            "y sincronizada posteriormente al recuperar conexión."
        ),
    )
    # Auto-set timestamp of when the signature record was created.
    # Timestamp automático del momento en que se creó el registro de firma.
    signed_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Fecha de firma",
        help_text="Fecha y hora en que se registró la firma en el sistema.",
    )

    class Meta:
        verbose_name = "Firma digital (asistencia)"
        verbose_name_plural = "Firmas digitales (asistencia)"

    def __str__(self):
        signer = self.signer_name or "Sin nombre"
        return f"Firma — {self.unit} — {signer}"


# ---------------------------------------------------------------------------
# 14. WORK ORDER ASSISTANCE INCIDENCE — Delta of changes per unit.
#     Delta de incidencias por unidad de albarán.
# ---------------------------------------------------------------------------

class WorkOrderAssistanceIncidence(models.Model):
    """
    Records post-completion changes to a WorkOrderAssistanceUnit. Only the
    fields that changed are populated — all service fields are nullable so
    that a null value means "no change for this field". A mandatory memo
    field requires the operator to justify every incidence. Each unit can
    have at most one incidence record.
    ---
    Registra cambios post-cierre sobre una WorkOrderAssistanceUnit. Solo se
    rellenan los campos que cambiaron — todos los campos de servicio son
    nullable para que un valor nulo signifique "sin cambio en este campo".
    Un campo memo obligatorio exige al operario justificar cada incidencia.
    Cada unidad puede tener como máximo un registro de incidencia.
    """

    # One-to-one relation: each unit has at most one incidence record.
    # Relación uno a uno: cada unidad tiene como máximo un registro de
    # incidencia.
    unit = models.OneToOneField(
        WorkOrderAssistanceUnit,
        on_delete=models.CASCADE,
        related_name="incidence",
        verbose_name="Unidad",
        help_text="Unidad de albarán a la que pertenece esta incidencia.",
    )
    recorded_by = models.ForeignKey(
        CompanyUser,
        on_delete=models.PROTECT,
        related_name="assistance_incidences",
        verbose_name="Registrado por",
        help_text="Usuario que registró la incidencia.",
    )
    # Mandatory justification memo for the incidence.
    # Memorándum de justificación obligatorio para la incidencia.
    memo = models.TextField(
        verbose_name="Memorándum",
        help_text=(
            "Justificación obligatoria de la incidencia. "
            "Debe describir el motivo del cambio respecto al albarán original."
        ),
    )
    # Delta fields — all nullable. Null means no change for that field.
    # Campos delta — todos nullable. Null significa sin cambio en ese campo.
    operator = models.ForeignKey(
        CompanyUser,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="assistance_incidences_operator",
        verbose_name="Chófer",
        help_text="Chófer modificado. Null si no cambia.",
    )
    operator_2 = models.ForeignKey(
        CompanyUser,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="assistance_incidences_operator_2",
        verbose_name="Chófer (fase 2)",
        help_text="Chófer de fase 2 modificado. Null si no cambia.",
    )
    machine = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        verbose_name="Máquina",
        help_text="Máquina modificada. Null si no cambia.",
    )
    machine_2 = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        verbose_name="Máquina (fase 2)",
        help_text="Máquina de fase 2 modificada. Null si no cambia.",
    )
    phase1_km = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Km fase 1",
        help_text="Kilómetros fase 1 modificados. Null si no cambian.",
    )
    phase2_km = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Km fase 2",
        help_text="Kilómetros fase 2 modificados. Null si no cambian.",
    )
    departure_fee = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Salida",
        help_text="Importe de salida modificado. Null si no cambia.",
    )
    rescue_hours = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Horas rescate",
        help_text="Horas de rescate modificadas. Null si no cambian.",
    )
    wait_hours = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Horas espera",
        help_text="Horas de espera modificadas. Null si no cambian.",
    )
    recorded_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Fecha de registro",
        help_text="Fecha y hora en que se registró la incidencia.",
    )

    class Meta:
        verbose_name = "Incidencia de unidad (asistencia)"
        verbose_name_plural = "Incidencias de unidad (asistencia)"

    def __str__(self):
        return f"Incidencia — {self.unit} — {self.recorded_by}"


# ---------------------------------------------------------------------------
# 21. NIGHT SCHEDULE — Configurable night-time window per company, assignable
#     to individual insurers.
#     Franja horaria nocturna configurable por empresa, asignable por
#     aseguradora.
# ---------------------------------------------------------------------------

class NightSchedule(models.Model):
    """
    Defines a named night-time window for the ASISTENCIA budget engine.
    Scoped to a Company and optionally assigned to individual Insurer records.
    The resolution order in the engine is:
      1. insurer.night_schedule (if assigned)
      2. Company NightSchedule with is_default=True
      3. Company.night_start / Company.night_end (backwards compatibility)

    Only one NightSchedule per company may have is_default=True.
    The save() method enforces this constraint automatically.
    ---
    Define una franja horaria nocturna con nombre para el motor de presupuestos
    ASISTENCIA. Con ámbito de empresa y asignable opcionalmente a instancias
    individuales de Insurer.
    Orden de resolución en el motor:
      1. insurer.night_schedule (si tiene horario asignado)
      2. NightSchedule de la empresa con is_default=True
      3. Company.night_start / Company.night_end (compatibilidad hacia atrás)

    Solo un NightSchedule por empresa puede tener is_default=True.
    El método save() impone esta restricción automáticamente.
    """

    company = models.ForeignKey(
        "ivr_config.Company",
        on_delete=models.CASCADE,
        related_name="night_schedules",
        verbose_name="Empresa",
        help_text="Empresa a la que pertenece este horario nocturno.",
    )
    name = models.CharField(
        max_length=100,
        verbose_name="Nombre",
        help_text=(
            "Nombre descriptivo del horario nocturno "
            "(ej: \"Nocturno estándar 18h–06h\", \"Nocturno amplio 20h–08h\")."
        ),
    )
    # Start of the night window. Services at or after this time are night
    # services.
    # Inicio de la franja nocturna. Servicios a esta hora o después son
    # nocturnos.
    night_start = models.TimeField(
        verbose_name="Inicio franja nocturna",
        help_text=(
            "Hora de inicio de la franja nocturna. "
            "Los servicios a esta hora o después se marcan como nocturnos."
        ),
    )
    # End of the night window. Services before this time are night services.
    # Fin de la franja nocturna. Servicios antes de esta hora son nocturnos.
    night_end = models.TimeField(
        verbose_name="Fin franja nocturna",
        help_text=(
            "Hora de fin de la franja nocturna. "
            "Los servicios antes de esta hora se marcan como nocturnos."
        ),
    )
    # When True, this schedule is used as the company fallback for insurers
    # that have no explicit night_schedule assigned.
    # Enforced unique-per-company via save().
    # Cuando es True, se usa como fallback de empresa para aseguradoras sin
    # horario nocturno explícito. Unicidad por empresa impuesta vía save().
    is_default = models.BooleanField(
        default=False,
        verbose_name="Horario por defecto",
        help_text=(
            "Si está activo, este horario se aplica a las aseguradoras de "
            "la empresa que no tengan horario nocturno explícitamente "
            "asignado. "
            "Solo puede haber un horario por defecto activo por empresa."
        ),
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="Activo",
        help_text=(
            "Desactivar para retirar el horario del motor sin eliminarlo. "
            "Un horario inactivo no se usa aunque sea el asignado de una "
            "aseguradora."
        ),
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
        verbose_name = "Horario nocturno"
        verbose_name_plural = "Horarios nocturnos"
        ordering = ["company__name", "-is_default", "name"]

    def save(self, *args, **kwargs):
        """
        Enforces the single-default constraint: when this instance is saved
        with is_default=True, all other NightSchedule records of the same
        company are set to is_default=False before persisting.
        ---
        Impone la restricción de horario único por defecto: cuando esta
        instancia se guarda con is_default=True, todos los demás registros
        NightSchedule de la misma empresa se ponen a is_default=False antes
        de persistir.
        """
        if self.is_default:
            NightSchedule.objects.filter(
                company=self.company,
                is_default=True,
            ).exclude(pk=self.pk).update(is_default=False)
        super().save(*args, **kwargs)

    def __str__(self):
        default_marker = " [por defecto]" if self.is_default else ""
        active_marker = "" if self.is_active else " [inactivo]"
        return (
            f"{self.company.name} — {self.name} "
            f"({self.night_start.strftime('%H:%M')}–"
            f"{self.night_end.strftime('%H:%M')})"
            f"{default_marker}{active_marker}"
        )


class TollSegment(models.Model):
    """
    Represents a single origin-destination toll fare segment on a Spanish
    toll road, as published by MITMA (Ministerio de Transportes). Each row
    encodes the toll price for all vehicle categories for a given OD pair
    on a specific road and tariff level.
    ---
    Representa un tramo tarifario origen-destino de una autopista de peaje
    española, según publicación del MITMA. Cada fila codifica el importe
    del peaje para todas las categorías de vehículo de un par OD dado en
    una vía y nivel tarifario concretos.
    """

    # Tariff level choices — normal (year-round for habituals + low season
    # for all) vs special (high season for non-habitual users).
    # Opciones de nivel tarifario — normal (todo el año para habituales +
    # temporada baja para todos) vs especial (temporada alta para
    # no habituales).
    TARIFF_NORMAL = "NORMAL"
    TARIFF_SPECIAL = "SPECIAL"
    TARIFF_LEVEL_CHOICES = [
        (TARIFF_NORMAL, "Normal"),
        (TARIFF_SPECIAL, "Especial (temporada alta)"),
    ]

    # Road identifier — e.g. 'AP-7', 'AP-68', 'AP-9'.
    # Identificador de la vía — p.ej. 'AP-7', 'AP-68', 'AP-9'.
    road_code = models.CharField(
        max_length=20,
        verbose_name="Código de vía",
        help_text="Identificador oficial de la autopista. Ej: AP-7, AP-68.",
        db_index=True,
    )

    # Human-readable name of the road section from the PDF.
    # Nombre legible del tramo de la vía según el PDF oficial.
    section_name = models.CharField(
        max_length=150,
        verbose_name="Nombre del tramo",
        help_text=(
            "Nombre del tramo tal como aparece en el PDF del MITMA. "
            "Ej: Málaga - Estepona."
        ),
    )

    # Origin toll point name — as it appears in the MITMA PDF table.
    # Nombre del punto de peaje origen — tal como aparece en la tabla PDF.
    origin_name = models.CharField(
        max_length=150,
        verbose_name="Origen",
        help_text="Nombre del peaje o salida de origen del recorrido.",
        db_index=True,
    )

    # Destination toll point name.
    # Nombre del punto de peaje destino.
    dest_name = models.CharField(
        max_length=150,
        verbose_name="Destino",
        help_text="Nombre del peaje o salida de destino del recorrido.",
        db_index=True,
    )

    # Geographic coordinates of the origin toll point.
    # Populated by the geocode_toll_segments management command via
    # the Google Geocoding API. Used to cross-reference the Routes API
    # polyline with toll segments in calculate_route().
    # Coordenadas geográficas del punto de peaje origen.
    # Pobladas por el comando geocode_toll_segments vía la Geocoding API.
    # Usadas para cruzar la polyline de la Routes API con los tramos.
    origin_lat = models.DecimalField(
        max_digits=10,
        decimal_places=6,
        null=True,
        blank=True,
        verbose_name="Latitud origen",
        help_text=(
            "Latitud del punto de peaje origen. "
            "Poblada automáticamente por geocode_toll_segments."
        ),
    )
    origin_lng = models.DecimalField(
        max_digits=10,
        decimal_places=6,
        null=True,
        blank=True,
        verbose_name="Longitud origen",
        help_text=(
            "Longitud del punto de peaje origen. "
            "Poblada automáticamente por geocode_toll_segments."
        ),
    )

    # Geographic coordinates of the destination toll point.
    # Coordenadas geográficas del punto de peaje destino.
    dest_lat = models.DecimalField(
        max_digits=10,
        decimal_places=6,
        null=True,
        blank=True,
        verbose_name="Latitud destino",
        help_text=(
            "Latitud del punto de peaje destino. "
            "Poblada automáticamente por geocode_toll_segments."
        ),
    )
    dest_lng = models.DecimalField(
        max_digits=10,
        decimal_places=6,
        null=True,
        blank=True,
        verbose_name="Longitud destino",
        help_text=(
            "Longitud del punto de peaje destino. "
            "Poblada automáticamente por geocode_toll_segments."
        ),
    )

    # Fare for light vehicles (category 1.0): motorcycles, cars, vans
    # up to 2 axles without twin-wheel trailer.
    # Tarifa para vehículos ligeros (cat. 1.0): motos, turismos, furgonetas
    # de hasta 2 ejes sin remolque de rueda gemela.
    price_light = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        verbose_name="Precio ligeros (€)",
        help_text="Tarifa para turismos, motos y furgonetas ligeras.",
    )

    # Fare for heavy vehicles category 1 (2.1 / 2.2): 2-3 axle trucks
    # and coaches, or light vehicle with single-axle twin-wheel trailer.
    # Tarifa para pesados categoría 1 (2.1 / 2.2): camiones y autocares
    # de 2-3 ejes, o ligero con remolque de 1 eje con rueda gemela.
    price_heavy_1 = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        verbose_name="Precio pesados 1 (€)",
        help_text=(
            "Tarifa para camiones/autocares de 2-3 ejes "
            "(categorías 2.1 y 2.2)."
        ),
    )

    # Fare for heavy vehicles category 2 (3.1 / 3.2): trucks/coaches
    # with 4+ axles total, or light vehicle with 2+ axle twin-wheel trailer.
    # Tarifa para pesados categoría 2 (3.1 / 3.2): camiones/autocares con
    # 4+ ejes en total, o ligero con remolque de 2+ ejes con rueda gemela.
    price_heavy_2 = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        verbose_name="Precio pesados 2 (€)",
        help_text=(
            "Tarifa para camiones/autocares de 4 o más ejes totales "
            "(categorías 3.1 y 3.2)."
        ),
    )

    # Tariff level: NORMAL (default) or SPECIAL (high season surcharge
    # applied by some MITMA roads to non-habitual users).
    # Nivel tarifario: NORMAL (por defecto) o SPECIAL (recargo en temporada
    # alta aplicado por algunas vías MITMA a usuarios no habituales).
    tariff_level = models.CharField(
        max_length=10,
        choices=TARIFF_LEVEL_CHOICES,
        default=TARIFF_NORMAL,
        verbose_name="Nivel tarifario",
        help_text=(
            "Normal: todo el año para habituales y temporada baja para todos. "
            "Especial: temporada alta para usuarios no habituales."
        ),
    )

    # Whether tolls are free on this road during night hours
    # (SEITT-managed roads are free 00:00-06:00 every day).
    # Si los peajes son gratuitos en esta vía en franja nocturna
    # (las vías SEITT son gratuitas de 00:00 a 06:00 todos los días).
    has_free_night = models.BooleanField(
        default=False,
        verbose_name="Gratuito nocturno",
        help_text=(
            "Si es True, el peaje es gratuito durante la franja nocturna "
            "definida en free_night_start / free_night_end."
        ),
    )

    # Start of the free night window (inclusive). Null if has_free_night=False.
    # Inicio de la franja nocturna gratuita (inclusive). Null si no aplica.
    free_night_start = models.TimeField(
        null=True,
        blank=True,
        verbose_name="Inicio gratuito nocturno",
        help_text=(
            "Hora de inicio de la franja gratuita nocturna (inclusive). "
            "Típicamente 00:00 en vías SEITT."
        ),
    )

    # End of the free night window (exclusive). Null if has_free_night=False.
    # Fin de la franja nocturna gratuita (exclusive). Null si no aplica.
    free_night_end = models.TimeField(
        null=True,
        blank=True,
        verbose_name="Fin gratuito nocturno",
        help_text=(
            "Hora de fin de la franja gratuita nocturna (exclusive). "
            "Típicamente 06:00 en vías SEITT."
        ),
    )

    # Date from which these fares are valid. Used to track tariff updates.
    # Fecha desde la que estas tarifas están vigentes. Permite seguimiento
    # de actualizaciones tarifarias anuales.
    valid_from = models.DateField(
        verbose_name="Vigente desde",
        help_text=(
            "Fecha de inicio de vigencia de la tarifa. "
            "Ej: 2026-01-01 para tarifas aprobadas para 2026."
        ),
    )

    # Soft-delete flag: set to False when a toll road is liberalised
    # (concession expires) without deleting historical records.
    # Borrado lógico: se pone a False cuando una vía se libera
    # (vence la concesión) sin eliminar registros históricos.
    is_active = models.BooleanField(
        default=True,
        verbose_name="Activo",
        db_index=True,
        help_text=(
            "Desactivar cuando la concesión expire y la vía quede libre "
            "de peaje, sin eliminar el histórico tarifario."
        ),
    )

    # Auto-updated timestamp for auditing tariff changes.
    # Marca de tiempo actualizada automáticamente para auditoría de cambios.
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Última actualización",
    )

    # High-season fares — null when no seasonal split exists for this segment.
    # The engine uses these when the service date falls within the high-season
    # range defined by season_high_start / season_high_end.
    # Tarifas de temporada alta — null cuando no hay distinción estacional.
    # El motor las usa cuando la fecha del servicio cae en el rango de
    # temporada alta definido por season_high_start / season_high_end.
    price_light_high = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Precio ligeros temporada alta (€)",
        help_text=(
            "Tarifa para turismos, motos y furgonetas ligeras en temporada "
            "alta. Dejar vacío si no hay distinción estacional."
        ),
    )
    price_heavy_1_high = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Precio pesados 1 temporada alta (€)",
        help_text=(
            "Tarifa para camiones/autocares de 2-3 ejes en temporada alta. "
            "Dejar vacío si no hay distinción estacional."
        ),
    )
    price_heavy_2_high = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Precio pesados 2 temporada alta (€)",
        help_text=(
            "Tarifa para camiones/autocares de 4+ ejes en temporada alta. "
            "Dejar vacío si no hay distinción estacional."
        ),
    )

    # High-season date range — used by the budget engine to select the
    # appropriate price (normal vs high-season) based on the service date.
    # Both fields must be set together; if either is null, a single price
    # applies year-round (no seasonal split).
    #
    # The year component of these dates is IGNORED — only month and day
    # matter, so a single pair covers every year without updates.
    # Rango de temporada alta — el motor de presupuestos lo usa para
    # seleccionar el precio correcto (normal vs temporada alta) según la
    # fecha del servicio. Ambos campos deben configurarse juntos; si
    # alguno es nulo, se aplica un único precio todo el año.
    # El componente de año se ignora — solo importan mes y día.
    season_high_start = models.DateField(
        null=True,
        blank=True,
        verbose_name="Inicio temporada alta",
        help_text=(
            "Fecha de inicio de la temporada alta (día/mes). "
            "Solo se usan el mes y el día — el año se ignora. "
            "Si no se configura, se aplica price_heavy_1 todo el año. "
            "Ej: 2026-06-15 → temporada alta desde el 15 de junio."
        ),
    )
    season_high_end = models.DateField(
        null=True,
        blank=True,
        verbose_name="Fin temporada alta",
        help_text=(
            "Fecha de fin de la temporada alta (día/mes, inclusive). "
            "Solo se usan el mes y el día — el año se ignora. "
            "Si no se configura, se aplica price_heavy_1 todo el año. "
            "Ej: 2026-09-30 → temporada alta hasta el 30 de septiembre."
        ),
    )

    class Meta:
        verbose_name = "Tramo de peaje"
        verbose_name_plural = "Tramos de peaje"
        ordering = ["road_code", "section_name", "origin_name", "dest_name"]
        indexes = [
            models.Index(
                fields=["road_code", "tariff_level", "is_active"],
                name="toll_road_tariff_active_idx",
            ),
            models.Index(
                fields=["origin_name", "dest_name"],
                name="toll_od_pair_idx",
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "road_code",
                    "origin_name",
                    "dest_name",
                    "tariff_level",
                    "valid_from",
                ],
                name="toll_segment_unique_od_tariff_date",
            ),
        ]

    def __str__(self):
        return (
            f"{self.road_code} | "
            f"{self.origin_name} → {self.dest_name} "
            f"[{self.tariff_level}] "
            f"€{self.price_light}/{self.price_heavy_1}/{self.price_heavy_2}"
        )


# ---------------------------------------------------------------------------
# 17. TARIFF PDF IMPORT — Tracks a tariff-PDF upload, its Gemini extraction
#     result, the copy Insurer created for comparison, and the processing
#     status.
#     Registra la subida de un PDF de tarifa, el resultado de la extracción
#     de Gemini, la Insurer copia creada para comparación y el estado.
# ---------------------------------------------------------------------------

def _tariff_pdf_upload_to(instance, filename):
    """
    Storage path for uploaded tariff PDFs.
    budgets/tariff_pdfs/<insurer_pk>/<filename>
    ---
    Ruta de almacenamiento para los PDF de tarifa subidos.
    budgets/tariff_pdfs/<insurer_pk>/<filename>
    """
    return _os.path.join(
        "budgets", "tariff_pdfs",
        str(instance.insurer.pk),
        filename,
    )


class TariffPdfImport(models.Model):
    """
    Records a tariff PDF import operation: the uploaded PDF, the
    Insurer copy created from it, the raw JSON extraction result from
    Gemini, and the current processing status.
    One record per upload attempt. A 'copy' Insurer is created
    atomically at upload time so the operator can compare original vs.
    extracted before committing the changes.

    ---

    Registra una operación de importación de tarifa por PDF: el PDF
    subido, la copia de Insurer creada a partir de él, el resultado
    JSON bruto de la extracción de Gemini, y el estado de procesamiento
    actual. Un registro por intento de subida. Se crea una Insurer
    'copia' atómicamente en el momento de la subida para que el
    operario pueda comparar el original con el resultado extraído antes
    de confirmar los cambios.
    """

    # Status choices / Opciones de estado
    STATUS_PENDING = "PENDING_REVIEW"
    STATUS_APPLIED = "APPLIED"
    STATUS_DISCARDED = "DISCARDED"
    STATUS_ERROR = "ERROR"

    STATUS_CHOICES = [
        (STATUS_PENDING, "Pendiente de revisión"),
        (STATUS_APPLIED, "Aplicado"),
        (STATUS_DISCARDED, "Descartado"),
        (STATUS_ERROR, "Error de extracción"),
    ]

    # Source insurer (original, never modified by the import).
    # Aseguradora origen (original, nunca modificada por la importación).
    insurer = models.ForeignKey(
        "Insurer",
        on_delete=models.CASCADE,
        related_name="tariff_pdf_imports",
        verbose_name="Aseguradora origen",
    )

    # Copy insurer created atomically at upload time (may be null if
    # cloning failed before the copy was saved).
    # Aseguradora copia creada atómicamente al subir (puede ser null si
    # el clonado falló antes de guardar la copia).
    insurer_copy = models.ForeignKey(
        "Insurer",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tariff_pdf_import_copy",
        verbose_name="Aseguradora copia",
    )

    # Uploaded PDF file.
    # Archivo PDF subido.
    pdf_file = models.FileField(
        upload_to=_tariff_pdf_upload_to,
        verbose_name="PDF de tarifa",
    )

    # Raw JSON extraction result from Gemini (stored for audit/debug).
    # Resultado JSON bruto de la extracción de Gemini (guardado para
    # auditoría/depuración).
    extraction_raw = models.JSONField(
        null=True,
        blank=True,
        verbose_name="Extracción bruta (JSON)",
    )

    # Processing status.
    # Estado de procesamiento.
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
        verbose_name="Estado",
    )

    # Error message if status == STATUS_ERROR.
    # Mensaje de error si status == STATUS_ERROR.
    error_message = models.TextField(
        blank=True,
        default="",
        verbose_name="Mensaje de error",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Importación de tarifa por PDF"
        verbose_name_plural = "Importaciones de tarifa por PDF"
        ordering = ["-created_at"]

    def __str__(self):
        return (
            f"PDF import #{self.pk} — {self.insurer.name} "
            f"[{self.get_status_display()}]"
        )


# ---------------------------------------------------------------------------
# H37 (S133). Device token of the driver app (EBotDeliveryNotes).
# Token de dispositivo de la app del conductor (EBotDeliveryNotes).
# ---------------------------------------------------------------------------

class DriverDeviceToken(models.Model):
    """
    Access token of one device of the driver app.

    The app signs in with the panel username and password once and
    keeps the token. Only the SHA-256 of the token is stored, so a
    copy of the database does not give access. Each device has its own
    token: signing out on one tablet does not sign out the others.

    ---

    Token de acceso de un dispositivo de la app del conductor.

    La app entra una vez con el usuario y la contraseña del panel y
    guarda el token. En BD solo se guarda su SHA-256: una copia de la
    BD no da acceso. Cada dispositivo tiene su token: cerrar sesión en
    una tablet no cierra las demás.
    """

    company_user = models.ForeignKey(
        CompanyUser,
        on_delete=models.CASCADE,
        related_name="driver_device_tokens",
        verbose_name="Usuario",
    )
    key_hash = models.CharField(
        max_length=64,
        unique=True,
        verbose_name="Huella del token",
        help_text="SHA-256 del token; el token en claro no se guarda.",
    )
    device_name = models.CharField(
        max_length=120,
        blank=True,
        default="",
        verbose_name="Dispositivo",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Creado",
    )
    last_used_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Último uso",
    )
    revoked_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Revocado",
        help_text="Vacío mientras el token es válido.",
    )

    class Meta:
        verbose_name = "Token de la app del conductor"
        verbose_name_plural = "Tokens de la app del conductor"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.company_user} — {self.device_name or 'dispositivo'}"


class AssistanceCrew(models.Model):
    """
    Assistance crew: a driver with the machine he drives.

    In the traffic panel the driver is put on a machine and the crew
    as a whole goes to the albarán, so driver and machine never travel
    apart. A driver has at most one machine and a machine at most one
    driver. Drivers can swap machines while their crews are free or
    returning (a crew finishing a 10 t service swaps with one coming
    back with a 35 t truck).

    ---

    Equipo de asistencia: un conductor con la máquina que lleva.

    En el panel de tráfico el conductor se pone en una máquina y al
    albarán va el equipo entero: conductor y máquina nunca van por
    separado. Un conductor lleva como mucho una máquina y una máquina
    como mucho un conductor. Los conductores se pueden cambiar de
    máquina mientras sus equipos están libres o regresando (Miguel
    Ángel, S133: el de la grúa de 10 t que termina se cambia con el
    que vuelve con la de 35 t).
    """

    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="assistance_crews",
        verbose_name="Empresa",
    )
    driver = models.OneToOneField(
        CompanyUser,
        on_delete=models.CASCADE,
        related_name="assistance_crew",
        verbose_name="Conductor",
    )
    machine = models.OneToOneField(
        "fleet.MachineAsset",
        on_delete=models.CASCADE,
        related_name="assistance_crew",
        verbose_name="Máquina",
    )
    created_by = models.ForeignKey(
        CompanyUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="Formado por",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Formado",
    )

    class Meta:
        verbose_name = "Equipo de asistencia"
        verbose_name_plural = "Equipos de asistencia"
        ordering = ["machine__code"]

    def __str__(self):
        return f"{self.driver} — {self.machine}"


class DriverPosition(models.Model):
    """
    Position sent by the driver app.

    The app only sends it while the driver has an albarán in progress
    (sent, in service or returning to base): drivers are not followed
    outside their services. The traffic map puts each crew out of base
    on the last position of its driver.

    ---

    Posición enviada por la app del conductor.

    La app solo la envía mientras el conductor tiene un albarán en
    curso (enviado, en servicio o regresando): fuera de servicio no se
    le sigue. El mapa de tráfico pone cada equipo que está fuera en la
    última posición de su conductor.
    """

    company_user = models.ForeignKey(
        CompanyUser,
        on_delete=models.CASCADE,
        related_name="driver_positions",
        verbose_name="Conductor",
    )
    # H37 (S138): the albarán in progress when the position came in, so
    # each albarán keeps its route (Miguel Ángel: "poder visualizar la
    # ruta en el mapa con las detenciones que haya tenido el vehículo").
    # Albarán en curso cuando llegó la posición: cada albarán guarda su
    # ruta.
    unit = models.ForeignKey(
        "WorkOrderAssistanceUnit",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="positions",
        verbose_name="Albarán",
    )
    latitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        verbose_name="Latitud",
    )
    longitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        verbose_name="Longitud",
    )
    accuracy_m = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name="Precisión (m)",
    )
    recorded_at = models.DateTimeField(
        verbose_name="Tomada",
        help_text="Hora del móvil al tomar la posición.",
    )
    received_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Recibida",
    )

    class Meta:
        verbose_name = "Posición del conductor"
        verbose_name_plural = "Posiciones de los conductores"
        ordering = ["-recorded_at"]
        indexes = [
            models.Index(
                fields=["company_user", "-recorded_at"],
                name="drvpos_user_recorded_idx",
            ),
            models.Index(
                fields=["unit", "recorded_at"],
                name="drvpos_unit_recorded_idx",
            ),
        ]

    def __str__(self):
        return f"{self.company_user} {self.recorded_at:%d/%m %H:%M}"


class ServiceIntake(models.Model):
    """
    A service being given by WhatsApp or by phone.

    Holds the data collected by the agent and the conversation until the
    service is launched or cancelled (meeting with Pepe, S133: services
    come in by photo, phone call or WhatsApp, and launching them must be
    automatic).

    ---

    Un servicio que se está dando por WhatsApp o por teléfono.

    Guarda los datos que va recogiendo el agente y la conversación hasta
    que el servicio se lanza o se cancela (reunión con Pepe, S133: los
    servicios entran por foto, llamada o WhatsApp, y su lanzamiento tiene
    que ser automático).
    """

    CHANNEL_WHATSAPP = "WHATSAPP"
    CHANNEL_PHONE = "PHONE"
    CHANNEL_CHOICES = [
        (CHANNEL_WHATSAPP, "WhatsApp"),
        (CHANNEL_PHONE, "Llamada"),
    ]
    STATUS_OPEN = "OPEN"
    STATUS_LAUNCHED = "LAUNCHED"
    STATUS_CANCELLED = "CANCELLED"
    STATUS_CHOICES = [
        (STATUS_OPEN, "En curso"),
        (STATUS_LAUNCHED, "Lanzado"),
        (STATUS_CANCELLED, "Cancelado"),
    ]

    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="service_intakes",
        verbose_name="Empresa",
    )
    requested_by = models.ForeignKey(
        CompanyUser,
        on_delete=models.CASCADE,
        related_name="service_intakes",
        verbose_name="Quién da el servicio",
    )
    channel = models.CharField(
        max_length=10,
        choices=CHANNEL_CHOICES,
        verbose_name="Canal",
    )
    phone_number = models.CharField(
        max_length=30,
        blank=True,
        default="",
        verbose_name="Teléfono",
    )
    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default=STATUS_OPEN,
        verbose_name="Estado",
    )
    data = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Datos recogidos",
    )
    conversation = models.JSONField(
        default=list,
        blank=True,
        verbose_name="Conversación",
    )
    work_order = models.ForeignKey(
        WorkOrderAssistance,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="intakes",
        verbose_name="Orden creada",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Empezado",
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Último mensaje",
    )

    class Meta:
        verbose_name = "Alta de servicio por conversación"
        verbose_name_plural = "Altas de servicio por conversación"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_channel_display()} — {self.requested_by}"


class WorkOrderAssistanceUnitPhoto(models.Model):
    """
    Photo of a service sheet taken by the driver.

    ---

    H37 (S133). Foto de la hoja de servicio que hace el conductor con la
    app: antes de cargar, cargado en altura y descargado (hoja de
    servicio de Pepe). Sin las de cargado y descargado no aparece la
    firma del cliente, salvo reparación en el sitio. La imagen va al
    cubo de GCS; aquí queda su ruta.
    """

    KIND_BEFORE = "BEFORE"
    KIND_LOADED = "LOADED"
    KIND_UNLOADED = "UNLOADED"
    # S140: a repair on site also has its photos (Miguel Ángel: "hay que
    # terminar todas las fotos y cuando esté todo terminado, entonces
    # podemos firmar").
    # Una reparación en el sitio también lleva sus fotos.
    KIND_REPAIR_BEFORE = "REP_BEFORE"
    KIND_REPAIR_DONE = "REP_DONE"
    KIND_CHOICES = [
        (KIND_BEFORE, "Antes de cargar"),
        (KIND_LOADED, "Cargado en altura"),
        (KIND_UNLOADED, "Descargado"),
        (KIND_REPAIR_BEFORE, "Antes de la reparación"),
        (KIND_REPAIR_DONE, "Reparación terminada"),
    ]
    TOW_KINDS = (KIND_BEFORE, KIND_LOADED, KIND_UNLOADED)
    REPAIR_KINDS = (KIND_REPAIR_BEFORE, KIND_REPAIR_DONE)

    unit = models.ForeignKey(
        WorkOrderAssistanceUnit,
        on_delete=models.CASCADE,
        related_name="photos",
        verbose_name="Albarán",
    )
    kind = models.CharField(
        max_length=10, choices=KIND_CHOICES, verbose_name="Tipo",
    )
    blob_name = models.CharField(
        max_length=300, verbose_name="Ruta en GCS",
    )
    content_type = models.CharField(
        max_length=40, default="image/jpeg", verbose_name="Tipo MIME",
    )
    # Id made by the phone: a retried upload (lost answer without
    # coverage) does not duplicate the photo.
    # Id que pone el móvil: un reenvío (respuesta perdida sin
    # cobertura) no duplica la foto.
    client_uid = models.CharField(
        max_length=64, verbose_name="Id del móvil",
    )
    taken_at = models.DateTimeField(
        null=True, blank=True, verbose_name="Hecha en",
    )
    uploaded_by = models.ForeignKey(
        CompanyUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="Subida por",
    )
    created_at = models.DateTimeField(
        auto_now_add=True, verbose_name="Recibida en",
    )

    class Meta:
        verbose_name = "Foto de albarán (asistencia)"
        verbose_name_plural = "Fotos de albarán (asistencia)"
        ordering = ["unit", "kind", "taken_at", "pk"]
        unique_together = [("unit", "client_uid")]

    def __str__(self):
        return "%s — %s" % (self.unit.albaran_number, self.get_kind_display())


class DriverDocumentRequirement(models.Model):
    """
    A document a driver must have in force (any of several types).

    ---

    H37 (S133). Documento que un conductor debe tener en vigor para
    llevar una máquina, con los tipos del catálogo que lo acreditan
    (cualquiera vale): "CAP" se acredita con el certificado (`CAP`) o
    con la tarjeta de cualificación del conductor
    (`TARJETA_CUALIF_CONDUCTOR`); "Carné de gruista" con
    `CARNET_GRUISTA`. Datos en base de datos, no en el código.
    """

    name = models.CharField(
        max_length=80, unique=True, verbose_name="Documento",
    )
    document_types = models.ManyToManyField(
        "document_explorer.DocumentTypeCatalog",
        related_name="+",
        verbose_name="Tipos que lo acreditan",
    )

    class Meta:
        verbose_name = "Documento exigido al conductor"
        verbose_name_plural = "Documentos exigidos al conductor"
        ordering = ["name"]

    def __str__(self):
        return self.name


class MachineDriverRequirement(models.Model):
    """
    What a driver needs in force to take a type of machine.

    ---

    H37 (S133). Lo que un conductor necesita en vigor para llevar un
    tipo de máquina (`MachineAsset.type_name`): clases del permiso de
    conducción y documentos (CAP, carné de gruista). Miguel Ángel, S133:
    "tenemos los permisos de conducción para poder determinar a quien
    podemos enviar según su permiso". Tabla inicial acordada en S133:
    asistencia en carretera C + CAP; cabeza tractora CE + CAP; grúa
    móvil y rescate con grúa móvil C + CAP + carné de gruista;
    vehículos de personal B.
    """

    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="machine_driver_requirements",
        verbose_name="Empresa",
    )
    machine_type_name = models.CharField(
        max_length=120,
        verbose_name="Tipo de máquina",
        help_text="Igual que el tipo de la ficha de la máquina "
                  "(p. ej. CABEZA TRACTORA).",
    )
    required_categories = models.ManyToManyField(
        "document_explorer.DrivingLicenceCategory",
        blank=True,
        related_name="+",
        verbose_name="Clases del permiso",
    )
    required_documents = models.ManyToManyField(
        DriverDocumentRequirement,
        blank=True,
        related_name="machine_requirements",
        verbose_name="Documentos",
    )
    is_active = models.BooleanField(default=True, verbose_name="Activo")

    class Meta:
        verbose_name = "Requisito del conductor por tipo de máquina"
        verbose_name_plural = "Requisitos del conductor por tipo de máquina"
        ordering = ["company", "machine_type_name"]
        constraints = [
            models.UniqueConstraint(
                fields=("company", "machine_type_name"),
                name="unique_driver_requirement_per_machine_type",
            ),
        ]

    def __str__(self):
        return self.machine_type_name


class AssistanceTimes(models.Model):
    """
    Working times added to the travel times of an assistance service.

    ---

    Tiempos de trabajo que se suman a los trayectos para estimar el fin
    de un servicio de asistencia. H37 (S134), Miguel Ángel: carga y
    descarga media hora cada una (*"mientras ata, desata, lo baja,
    firma... son 30 minutos"*), reparación in situ 30 minutos y levantar
    un vehículo volcado o caído 60 minutos. Uno por empresa.
    """

    company = models.OneToOneField(
        Company,
        on_delete=models.CASCADE,
        related_name="assistance_times",
        verbose_name="Empresa",
    )
    load_minutes = models.PositiveSmallIntegerField(
        default=30, verbose_name="Carga (min)",
    )
    unload_minutes = models.PositiveSmallIntegerField(
        default=30, verbose_name="Descarga (min)",
    )
    on_site_minutes = models.PositiveSmallIntegerField(
        default=30, verbose_name="Reparación in situ (min)",
        help_text="Rueda, batería, combustible o avería pequeña.",
    )
    lift_minutes = models.PositiveSmallIntegerField(
        default=60, verbose_name="Levantar un vehículo (min)",
        help_text="Volcado, salido de la vía o caído.",
    )
    updated_at = models.DateTimeField(
        auto_now=True, verbose_name="Fecha de modificación",
    )

    class Meta:
        verbose_name = "Tiempos de trabajo de asistencia"
        verbose_name_plural = "Tiempos de trabajo de asistencia"

    def __str__(self):
        return "Tiempos de asistencia de %s" % self.company

    @classmethod
    def for_company(cls, company):
        """
        The times of a company, created with the defaults if missing.

        ---

        Los tiempos de la empresa; si no existen, se crean con los
        valores por defecto.
        """
        times, _created = cls.objects.get_or_create(company=company)
        return times


class RouteTest(models.Model):
    """
    A route recorded with the test button of the driver app.

    ---

    Ruta grabada con el botón de prueba de la app del conductor (H37,
    S140). Miguel Ángel, tras la prueba de campo del 28/10: *"tener un
    botón de prueba y vamos a probar rutas [...] vemos cómo se guardan
    las rutas"*; cuando se guarden bien, la grabación pasa al albarán.
    No está ligada a ningún albarán.
    """

    company_user = models.ForeignKey(
        CompanyUser,
        on_delete=models.CASCADE,
        related_name="route_tests",
        verbose_name="Conductor",
    )
    started_at = models.DateTimeField(verbose_name="Inicio")
    finished_at = models.DateTimeField(verbose_name="Fin")
    settings = models.CharField(
        max_length=200,
        blank=True,
        default="",
        verbose_name="Ajustes de la grabación",
        help_text="Cómo grabó la app los puntos (intervalo, distancia...).",
    )
    created_at = models.DateTimeField(
        auto_now_add=True, verbose_name="Recibida",
    )

    class Meta:
        verbose_name = "Prueba de ruta"
        verbose_name_plural = "Pruebas de ruta"
        ordering = ["-started_at"]

    def __str__(self):
        return f"{self.company_user} {self.started_at:%d/%m %H:%M}"


class RouteTestPoint(models.Model):
    """
    A point of a test route.

    ---

    Punto de una prueba de ruta, tal cual lo guardó el móvil.
    """

    route = models.ForeignKey(
        RouteTest,
        on_delete=models.CASCADE,
        related_name="points",
        verbose_name="Prueba de ruta",
    )
    latitude = models.DecimalField(
        max_digits=9, decimal_places=6, verbose_name="Latitud",
    )
    longitude = models.DecimalField(
        max_digits=9, decimal_places=6, verbose_name="Longitud",
    )
    accuracy_m = models.PositiveIntegerField(
        null=True, blank=True, verbose_name="Precisión (m)",
    )
    recorded_at = models.DateTimeField(verbose_name="Tomado")

    class Meta:
        verbose_name = "Punto de prueba de ruta"
        verbose_name_plural = "Puntos de prueba de ruta"
        ordering = ["recorded_at"]


# ---------------------------------------------------------------------------
# H37 (S142, invasive session). Service evaluation: estimated budget by
# tariff, estimated cost and yield of the services uploaded from a folder.
# Valoración de servicios: presupuesto estimado según tarifa, coste
# estimado y rendimiento de los servicios subidos desde una carpeta.
# ---------------------------------------------------------------------------

# Fuel consumption given by Miguel Ángel (S142), litres per 100 km, and
# the assistance machine types (budgets.dispatch_vehicle) of each kind.
# Consumos dados por Miguel Ángel (S142), litros a los 100 km, y los
# tipos de máquina de asistencia de cada clase.
DEFAULT_VEHICLE_COSTS = (
    ("Turismo", "5", ""),
    ("Furgoneta", "8", "VEHICULOS DE PERSONAL"),
    ("Remolcador/tractora", "20", (
        "ASISTENCIA EN CARRETERA\nCABEZA TRACTORA\n"
        "CABEZA TRACTORA ASISTENCIA"
    )),
    ("Grúa móvil", "25", (
        "RESCATE CON GRUA MOVIL ASISTENCIA\nGRUA MOVIL DE 20 TM\n"
        "GRUA MOVIL DE 30 TM"
    )),
)


# S142: cost per worked hour of an operator, from a real payslip of the
# group (Miguel Ángel: "calcula como si los trabajadores cobran como yo";
# "las vacaciones y festivos van repercutidos en las horas que se
# pagan"): yearly company cost (gross pay with prorated extra payments
# plus employer social security) divided by the hours really worked in a
# year, 1.800 (225 working days of 8 h, after weekends, 22 working days
# of holidays and 14 bank holidays). Editable in "Medias de coste".
# ---
# Coste por hora trabajada de un operario, sacado de una nómina real del
# grupo: coste empresa anual entre 1.800 horas trabajadas al año.
DEFAULT_OPERATOR_COST_HOUR = Decimal("15.34")


class AssistanceCostSettings(models.Model):
    """
    Average costs used to estimate what an assistance service costs.

    ---

    Medias de coste para estimar lo que cuesta un servicio de
    asistencia (S142): precio del gasoil y coste por hora de operario.
    Los consumos y el coste por km de cada clase de vehículo van en
    `AssistanceVehicleCost`. Uno por empresa. Miguel Ángel: "a medida
    que se vayan teniendo lecturas, iremos sacando medias de los
    propios servicios".
    """

    company = models.OneToOneField(
        Company,
        on_delete=models.CASCADE,
        related_name="assistance_cost_settings",
        verbose_name="Empresa",
    )
    fuel_price_per_liter = models.DecimalField(
        max_digits=6,
        decimal_places=3,
        null=True,
        blank=True,
        verbose_name="Precio del gasoil (€/l)",
    )
    operator_cost_per_hour = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Coste por operario (€/h)",
        help_text="Coste medio de una hora de un operario en servicio.",
    )
    updated_at = models.DateTimeField(
        auto_now=True, verbose_name="Fecha de modificación",
    )

    class Meta:
        verbose_name = "Medias de coste de asistencia"
        verbose_name_plural = "Medias de coste de asistencia"

    def __str__(self):
        return "Medias de coste de %s" % self.company

    @classmethod
    def for_company(cls, company):
        """
        The settings of a company, created with the defaults if missing.

        ---

        Las medias de la empresa; si no existen, se crean, y también
        las clases de vehículo con los consumos dados por Miguel Ángel.
        """
        settings, _created = cls.objects.get_or_create(
            company=company,
            defaults={"operator_cost_per_hour": DEFAULT_OPERATOR_COST_HOUR},
        )
        if not AssistanceVehicleCost.objects.filter(company=company).exists():
            for order, (name, liters, types) in enumerate(
                DEFAULT_VEHICLE_COSTS, start=1,
            ):
                AssistanceVehicleCost.objects.create(
                    company=company, name=name,
                    fuel_liters_per_100km=Decimal(liters),
                    machine_types=types, sort_order=order,
                    # S142: una grúa de gran tonelaje, 75 km/h como mucho.
                    max_speed_kmh=75 if name == "Grúa móvil" else None,
                    dead_time_hours=(
                        Decimal("1") if name == "Grúa móvil" else None
                    ),
                )
        return settings


class AssistanceVehicleCost(models.Model):
    """
    Average consumption and cost of one kind of our vehicles.

    ---

    Consumo y coste medios de una clase de vehículo nuestro (turismo,
    furgoneta, remolcador/tractora, grúa móvil) y qué tipos de máquina
    de asistencia (`budgets.dispatch_vehicle`) entran en ella.
    """

    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="assistance_vehicle_costs",
        verbose_name="Empresa",
    )
    name = models.CharField(max_length=60, verbose_name="Clase de vehículo")
    fuel_liters_per_100km = models.DecimalField(
        max_digits=5,
        decimal_places=1,
        default=0,
        verbose_name="Consumo (l/100 km)",
    )
    cost_per_km = models.DecimalField(
        max_digits=6,
        decimal_places=3,
        null=True,
        blank=True,
        verbose_name="Coste del vehículo (€/km)",
        help_text="Desgaste, mantenimiento... sin el gasoil.",
    )
    # S142: mobile cranes meter hours in the pump, not km.
    # Las grúas móviles apuntan horas en el surtidor, no km.
    fuel_liters_per_hour = models.DecimalField(
        max_digits=5,
        decimal_places=1,
        null=True,
        blank=True,
        verbose_name="Consumo (l/h)",
        help_text="Si se rellena, el gasoil se calcula por horas del "
                  "servicio (viaje y trabajo) en vez de por km.",
    )
    max_speed_kmh = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        verbose_name="Velocidad máxima (km/h)",
        help_text="El viaje dura como mínimo los km a esta velocidad, "
                  "aunque Google diga menos.",
    )
    # S142, Miguel Ángel: "el camión no va a ir a 75 km/h el 100 por
    # cien del tiempo [...] siempre hay tiempos muertos": una hora más.
    dead_time_hours = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Tiempos muertos (h)",
        help_text="Horas que se suman a cada servicio de esta clase.",
    )
    machine_types = models.TextField(
        blank=True,
        default="",
        verbose_name="Tipos de máquina",
        help_text="Tipos de máquina de asistencia de esta clase, uno por "
                  "línea.",
    )
    sort_order = models.PositiveSmallIntegerField(
        default=0, verbose_name="Orden",
    )

    class Meta:
        verbose_name = "Clase de vehículo (coste)"
        verbose_name_plural = "Clases de vehículo (coste)"
        ordering = ["sort_order", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=("company", "name"),
                name="unique_assistance_vehicle_cost_name",
            ),
        ]

    def __str__(self):
        return self.name

    def type_names(self):
        """
        Machine types of this kind, one per line.

        ---

        Tipos de máquina de esta clase.
        """
        return [
            line.strip() for line in self.machine_types.splitlines()
            if line.strip()
        ]


class ServiceEvaluation(models.Model):
    """
    A service uploaded to be valued: estimated budget, cost and yield.

    ---

    Servicio subido para valorarlo (S142, pestaña Servicios): su
    documento (foto o PDF de TIREA), los datos leídos, el presupuesto
    estimado según la tarifa, el coste estimado y el rendimiento. No
    crea ninguna orden; desde aquí se puede crear.
    """

    STATUS_PENDING = "PENDING"
    STATUS_PROCESSING = "PROCESSING"
    STATUS_DONE = "DONE"
    STATUS_ERROR = "ERROR"
    STATUS_CHOICES = [
        (STATUS_PENDING, "En cola"),
        (STATUS_PROCESSING, "Valorando"),
        (STATUS_DONE, "Valorado"),
        (STATUS_ERROR, "Error"),
    ]

    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="service_evaluations",
        verbose_name="Empresa",
    )
    created_by = models.ForeignKey(
        CompanyUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="service_evaluations",
        verbose_name="Subido por",
    )
    created_at = models.DateTimeField(
        auto_now_add=True, verbose_name="Subido",
    )
    file_name = models.CharField(max_length=255, verbose_name="Archivo")
    source_document_blob = models.CharField(
        max_length=500, blank=True, default="",
        verbose_name="Documento (GCS)",
    )
    source_document_type = models.CharField(
        max_length=100, blank=True, default="",
        verbose_name="Tipo del documento",
    )
    status = models.CharField(
        max_length=12,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
        verbose_name="Estado",
    )
    error = models.TextField(blank=True, default="", verbose_name="Error")
    data = models.JSONField(
        default=dict,
        blank=True,
        encoder=DjangoJSONEncoder,
        verbose_name="Datos leídos",
    )
    insurer = models.ForeignKey(
        Insurer,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="service_evaluations",
        verbose_name="Aseguradora",
    )
    vehicle_type = models.ForeignKey(
        VehicleType,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="service_evaluations",
        verbose_name="Tipo de vehículo",
    )
    base = models.ForeignKey(
        Base,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="service_evaluations",
        verbose_name="Base",
    )
    km = models.DecimalField(
        max_digits=8, decimal_places=1, null=True, blank=True,
        verbose_name="Km (base a base)",
    )
    hours = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True,
        verbose_name="Horas estimadas",
    )
    crews = models.PositiveSmallIntegerField(
        default=0, verbose_name="Vehículos (y operarios)",
    )
    job_label = models.CharField(
        max_length=255, blank=True, default="", verbose_name="Trabajo",
    )
    budget_amount = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        verbose_name="Presupuesto estimado según tarifa",
    )
    operators_cost = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        verbose_name="Coste de operarios",
    )
    vehicles_cost = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        verbose_name="Coste de vehículos",
    )
    fuel_cost = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        verbose_name="Coste de gasoil",
    )
    total_cost = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        verbose_name="Coste estimado",
    )
    margin = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        verbose_name="Rendimiento",
        help_text="Presupuesto estimado menos coste estimado.",
    )
    notes = models.TextField(
        blank=True, default="", verbose_name="Avisos del cálculo",
    )
    work_order = models.ForeignKey(
        WorkOrderAssistance,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="evaluations",
        verbose_name="Orden creada",
    )
    processed_at = models.DateTimeField(
        null=True, blank=True, verbose_name="Valorado",
    )

    class Meta:
        verbose_name = "Servicio a valorar"
        verbose_name_plural = "Servicios a valorar"
        ordering = ["-created_at"]

    def __str__(self):
        return self.file_name
