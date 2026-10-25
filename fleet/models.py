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

    The `code` field is the primary lookup key used when resolving the
    machine reference extracted from handwritten work-order slips
    (field `machine_norm` in WorkOrderEntryLine). Normalisation rules D4
    from the partes-trabajo skill are applied before the lookup.

    ---

    Representa una unidad de maquinaria o vehículo registrada en el catálogo
    de flota de la empresa. Cada instancia es un centro de gasto: las horas de
    mecánica de los partes de trabajo y los albaranes de terceros se imputan
    contra ella.

    El campo `code` es la clave de búsqueda principal que se utiliza al
    resolver la referencia de máquina extraída de los partes manuscritos
    (campo `machine_norm` en WorkOrderEntryLine). Las reglas de normalización
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
    company_code = models.CharField(
        _("Código de Empresa"),
        max_length=20,
        db_index=True,
        help_text=_(
            "Código corto de la empresa en el catálogo (ej: GRA, TRA, GRH). "
            "Se usa para agrupación y filtrado por empresa origen."
        ),
    )
    company_name = models.CharField(
        _("Nombre de Empresa"),
        max_length=200,
        help_text=_(
            "Nombre completo de la empresa tal como aparece en el catálogo."
        ),
    )
    family = models.CharField(
        _("Familia"),
        max_length=100,
        blank=True,
        help_text=_(
            "Familia de maquinaria del catálogo (ej: PLATAFORMAS, "
            "CARRETILLAS, AUTOCARGANTES, ASISTENCIA)."
        ),
    )
    document_requirement = models.ForeignKey(
        "document_explorer.JobPosition",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="machines",
        verbose_name=_("Requisito de documentación"),
        help_text=_(
            "S119 -- mismo catálogo único que el de una persona "
            "(Requisitos de documentación): sin requisito asignado, "
            "esta máquina no avisa de ningún documento faltante ni "
            "caducado. Para exigirle otro conjunto de documentos, se "
            "reasigna a otro requisito ya existente o nuevo, nunca se "
            "marca una excepción dentro de este mismo."
        ),
    )
    type_code = models.CharField(
        _("Código de Tipo"),
        max_length=50,
        blank=True,
        help_text=_(
            "Código del tipo de maquinaria en el catálogo "
            "(ej: MV035, PLTJ-E08, CG050)."
        ),
    )
    type_name = models.CharField(
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
    code = models.CharField(
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
    plate = models.CharField(
        _("Matrícula"),
        max_length=50,
        blank=True,
        help_text=_(
            "Matrícula o número de bastidor abreviado del vehículo o "
            "maquinaria. "
            "Puede coincidir con el código en equipos sin matrícula oficial."
        ),
    )
    chassis_number = models.CharField(
        _("Nº Bastidor"),
        max_length=100,
        blank=True,
        help_text=_(
            "Número de bastidor completo tal como figura en el catálogo."
        ),
    )
    brand_model = models.CharField(
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
    purchase_date = models.DateField(
        _("Fecha de Compra"),
        null=True,
        blank=True,
        help_text=_("Fecha de adquisición del vehículo o maquinaria."),
    )
    mileage = models.IntegerField(
        _("Kilómetros"),
        default=0,
        help_text=_(
            "Kilómetros registrados en el catálogo en el momento de la "
            "importación."
        ),
    )
    hours = models.IntegerField(
        _("Horas de Trabajo"),
        default=0,
        help_text=_(
            "Horas de trabajo registradas en el catálogo "
            "en el momento de la importación."
        ),
    )

    # ------------------------------------------------------------------
    # Instrumentation flags — Hito 7 / SEGUNDA ACCIÓN (sesión 010)
    # Flags de instrumentación — Hito 7 / SEGUNDA ACCIÓN (sesión 010)
    #
    # Indicate which readings the operator must supply when submitting
    # a work-order entry for this asset. Validated by rules R6/R7/R8
    # in work_order_processor/validators.py.
    #
    # Indican qué lecturas debe aportar el operario al enviar un parte
    # para este activo. Validadas por las reglas R6/R7/R8 en
    # work_order_processor/validators.py.
    # ------------------------------------------------------------------
    has_odometer = models.BooleanField(
        _("Tiene odómetro"),
        default=False,
        help_text=_(
            "Si está activo, el operario debe registrar la lectura de "
            "kilómetros (odómetro) al enviar un parte para este activo."
        ),
    )
    has_engine_hours = models.BooleanField(
        _("Tiene horómetro de motor"),
        default=False,
        help_text=_(
            "Si está activo, el operario debe registrar la lectura del "
            "horómetro de motor al enviar un parte para este activo."
        ),
    )
    has_crane_hours = models.BooleanField(
        _("Tiene horómetro de grúa"),
        default=False,
        help_text=_(
            "Si está activo, el operario debe registrar la lectura del "
            "horómetro de grúa al enviar un parte para este activo."
        ),
    )
    first_repair = models.BooleanField(
        _("Primera reparación"),
        default=True,
        db_index=True,
        help_text=_(
            "True mientras el activo no ha entrado en taller ninguna vez. "
            "En la primera reparación se permite introducir lecturas de "
            "contador a cero para establecer la línea base y desactivar "
            "los contadores que no apliquen. Una vez guardado el primer "
            "parte, este flag pasa automáticamente a False y ya no se "
            "permiten lecturas a cero."
        ),
    )

    # ------------------------------------------------------------------
    # Status / Estado
    # ------------------------------------------------------------------
    is_active = models.BooleanField(
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
    imported_at = models.DateTimeField(
        _("Importado en"),
        auto_now_add=True,
        help_text=_(
            "Fecha y hora en que se importó este registro desde el catálogo."
        ),
    )
    updated_at = models.DateTimeField(
        _("Actualizado en"),
        auto_now=True,
        help_text=_("Fecha y hora de la última modificación del registro."),
    )

    # ------------------------------------------------------------------
    # H30 (S54). Datos reales de cumplimiento, importados desde el
    # Excel de administración (import_worker_machine_excel, hoja
    # MAQUINARIA). insurance_info se guarda como texto libre porque el
    # Excel real mezcla aseguradora+fecha en una sola celda (p.ej.
    # "AXA 31/12/2026") -- no partir en campos separados sin
    # confirmar con Miguel Angel el formato real de todas las filas.
    # ------------------------------------------------------------------
    itv_date = models.DateField(
        null=True, blank=True, verbose_name=_("Última ITV (Excel)"),
    )
    itv_next_appointment = models.DateField(
        null=True, blank=True, verbose_name=_("Próxima cita ITV (Excel)"),
    )
    insurance_info = models.CharField(
        max_length=100, blank=True,
        verbose_name=_("Seguro (Excel)"),
        help_text=_(
            "Texto libre tal como viene en el Excel real (aseguradora "
            "+ fecha en la misma celda, p.ej. 'AXA 31/12/2026')."
        ),
    )
    oca_date = models.DateField(
        null=True, blank=True, verbose_name=_("Inspección OCA (Excel)"),
    )
    excel_imported_at = models.DateTimeField(
        null=True, blank=True,
        verbose_name=_("Última importación real del Excel"),
    )

    # ------------------------------------------------------------------
    # H30 (S118) -- foto de la máquina. Mismo mecanismo que
    # PersonIdentity.avatar_document (H35, S105): FK opcional al
    # documento-imagen YA indexado de esta máquina que se elige como
    # foto, sin tocar su tipo documental. Referencia en cadena para no
    # importar document_explorer desde fleet.
    # ---
    # H30 (S118) -- machine photo, same mechanism as
    # PersonIdentity.avatar_document: optional FK to an already indexed
    # image document of this machine, never retyping it.
    # ------------------------------------------------------------------
    avatar_document = models.ForeignKey(
        "document_explorer.DocumentIndexEntry",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        verbose_name=_("Documento-imagen usado como foto de la máquina"),
    )

    # ------------------------------------------------------------------
    # H30 (S131) -- plan de revisiones por horas y kilómetros. Por
    # horas, cada máquina pasa la suya a las 800 o a las 1200 (Miguel
    # Ángel: "unas máquinas la pasan a las 800 horas y otras máquinas
    # la pasan a las 1200"), nunca las dos; aparte, un intervalo en km.
    # Sin ninguno de los dos, el centro de gasto no tiene revisión.
    # ---
    # H30 (S131) -- service plan: one hours interval (800 or 1200)
    # and/or a km interval; with none set, there is no service plan.
    # ------------------------------------------------------------------
    SERVICE_HOURS_CHOICES = [
        (800, _("Cada 800 horas")),
        (1200, _("Cada 1200 horas")),
    ]
    service_hours_interval = models.PositiveSmallIntegerField(
        _("Revisión por horas"),
        choices=SERVICE_HOURS_CHOICES,
        null=True,
        blank=True,
        help_text=_(
            "Cada cuántas horas pasa la revisión esta máquina. Vacío: "
            "sin revisión por horas."
        ),
    )
    # H30 (S137) -- la grúa tiene su propio intervalo, separado del del
    # camión. Miguel Ángel: "la grúa que va en horas y el camión que va
    # en km" (A43: grúa cada 1200 h, camión por km). Hasta S137 la
    # revisión de grúa tomaba el intervalo de `service_hours_interval`.
    # ---
    # H30 (S137) -- the crane has its own hours interval, apart from the
    # truck's (hours or km).
    service_crane_hours_interval = models.PositiveSmallIntegerField(
        _("Revisión de la grúa por horas"),
        choices=SERVICE_HOURS_CHOICES,
        null=True,
        blank=True,
        help_text=_(
            "Cada cuántas horas de grúa pasa la revisión la grúa. Vacío: "
            "sin revisión de grúa. Solo cuenta si tiene horómetro de grúa."
        ),
    )
    service_every_km = models.PositiveIntegerField(
        _("Revisión cada N km"),
        null=True,
        blank=True,
        help_text=_(
            "Kilómetros entre revisiones. Vacío: sin revisión por "
            "kilómetros."
        ),
    )

    class Meta:
        verbose_name = _("Centro de gasto")
        verbose_name_plural = _("Centros de gasto")
        ordering = ["company_code", "family", "code"]
        indexes = [
            models.Index(fields=["company_code", "family"]),
            models.Index(fields=["code"]),
        ]

    def __str__(self) -> str:
        return f"{self.code} — {self.brand_model} [{self.company_code}]"

    def save(self, *args, **kwargs) -> None:
        """
        Normalises the `code` field to uppercase before saving to ensure
        consistent lookup regardless of the source casing.

        ---

        Normaliza el campo `code` a mayúsculas antes de guardar para
        garantizar búsquedas consistentes independientemente de las
        mayúsculas/minúsculas del origen.
        """
        self.code = self.code.strip().upper()
        super().save(*args, **kwargs)

    @property
    def has_service_plan(self) -> bool:
        """
        True if any service interval is configured.

        ---

        True si tiene alguna revisión configurada (por horas o por km).
        """
        return bool(
            self.service_hours_interval or self.service_every_km
            or (self.has_crane_hours and self.service_crane_hours_interval)
        )


# ---------------------------------------------------------------------------
# H30 (S131) -- revisiones y lecturas de horas/km, introducidas a mano
# H30 (S131) -- services and hour/km readings, entered by hand
# ---------------------------------------------------------------------------

class MachineServiceRecord(models.Model):
    """
    One service already done on a cost centre (date, hours, km).

    ---

    Una revisión ya hecha de un centro de gasto: fecha, horas y
    kilómetros de la revisión. Con horas cuenta para la revisión por
    horas y con km para la de km. Sin una revisión anotada, ese centro
    de gasto no avisa de esa revisión.
    """

    machine = models.ForeignKey(
        MachineAsset,
        on_delete=models.CASCADE,
        related_name="service_records",
        verbose_name=_("Centro de gasto"),
    )
    service_date = models.DateField(_("Fecha de la revisión"))
    hours = models.PositiveIntegerField(
        _("Horas en la revisión"), null=True, blank=True,
    )
    km = models.PositiveIntegerField(
        _("Kilómetros en la revisión"), null=True, blank=True,
    )
    crane_hours = models.PositiveIntegerField(
        _("Horas de grúa en la revisión"), null=True, blank=True,
    )
    notes = models.CharField(_("Observaciones"), max_length=255, blank=True)
    created_by = models.ForeignKey(
        "ivr_config.CompanyUser",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        verbose_name=_("Anotada por"),
    )
    created_at = models.DateTimeField(_("Anotada el"), auto_now_add=True)

    class Meta:
        verbose_name = _("Revisión de centro de gasto")
        verbose_name_plural = _("Revisiones de centros de gasto")
        ordering = ["-service_date", "-id"]

    def __str__(self) -> str:
        return f"{self.machine.code} -- revisión {self.service_date}"


class MachineMeterReading(models.Model):
    """
    One manual hours/km reading of a cost centre, with its date.

    ---

    Una lectura manual de horas y/o kilómetros de un centro de gasto,
    con su fecha. Hoy se apuntan a mano (más adelante vendrán del
    programa del surtidor, S131).
    """

    machine = models.ForeignKey(
        MachineAsset,
        on_delete=models.CASCADE,
        related_name="meter_readings",
        verbose_name=_("Centro de gasto"),
    )
    reading_date = models.DateField(_("Fecha de la lectura"))
    hours = models.PositiveIntegerField(_("Horas"), null=True, blank=True)
    km = models.PositiveIntegerField(_("Kilómetros"), null=True, blank=True)
    crane_hours = models.PositiveIntegerField(
        _("Horas de grúa"), null=True, blank=True,
    )
    created_by = models.ForeignKey(
        "ivr_config.CompanyUser",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        verbose_name=_("Anotada por"),
    )
    created_at = models.DateTimeField(_("Anotada el"), auto_now_add=True)
    # H30 (S135): de dónde sale la lectura -- a mano (panel) o de un
    # suministro del surtidor (GasoGes, ver GasoGesSupply.reading).
    # ---
    # H30 (S135): reading source -- typed in the panel or GasoGes.
    SOURCE_MANUAL = "MANUAL"
    SOURCE_GASOGES = "GASOGES"
    SOURCE_CHOICES = [
        (SOURCE_MANUAL, _("A mano")),
        (SOURCE_GASOGES, _("Surtidor (GasoGes)")),
    ]
    source = models.CharField(
        _("Origen"),
        max_length=10,
        choices=SOURCE_CHOICES,
        default=SOURCE_MANUAL,
    )

    class Meta:
        verbose_name = _("Lectura de horas y kilómetros")
        verbose_name_plural = _("Lecturas de horas y kilómetros")
        ordering = ["-reading_date", "-id"]

    def __str__(self) -> str:
        return f"{self.machine.code} -- lectura {self.reading_date}"


class MachineServiceAlertSettings(models.Model):
    """
    Advance notice of the service notices of one company.

    ---

    Antelación de los avisos de revisión de una empresa, en horas y en
    kilómetros. La fija Miguel Ángel en Avisos > Configuración; vacía,
    solo se avisa de revisiones vencidas (S131).
    """

    company = models.OneToOneField(
        Company,
        on_delete=models.CASCADE,
        related_name="machine_service_alert_settings",
        verbose_name=_("Empresa"),
    )
    hours_advance = models.PositiveIntegerField(
        _("Avisar con antelación de (horas)"), null=True, blank=True,
    )
    km_advance = models.PositiveIntegerField(
        _("Avisar con antelación de (km)"), null=True, blank=True,
    )
    updated_by = models.ForeignKey(
        "ivr_config.CompanyUser",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        verbose_name=_("Último cambio por"),
    )
    updated_at = models.DateTimeField(_("Último cambio"), auto_now=True)

    class Meta:
        verbose_name = _("Antelación de avisos de revisión")
        verbose_name_plural = _("Antelación de avisos de revisión")

    def __str__(self) -> str:
        return f"Avisos de revisión -- {self.company}"


# ---------------------------------------------------------------------------
# H30 (S135) -- programa del surtidor (GasoGes)
# H30 (S135) -- fuel pump software (GasoGes)
# ---------------------------------------------------------------------------

class GasoGesVehicle(models.Model):
    """
    One vehicle record of GasoGes, linked to its cost centre.

    ---

    Un registro de vehículo de GasoGes (`ID VEHICULO`), enlazado con su
    centro de gasto. Una máquina puede tener varios registros en uso
    (S135: A56 reposta con el 119 y el 120); los tanques, el taller y
    similares quedan sin centro de gasto. `unit` dice qué apunta el
    chófer en el campo KM del surtidor: kilómetros u horas (S135: A44
    apunta horas, A30 km, aunque las dos tienen horómetro).
    """

    UNIT_UNKNOWN = "UNKNOWN"
    UNIT_KM = "KM"
    UNIT_HOURS = "HOURS"
    UNIT_CHOICES = [
        (UNIT_UNKNOWN, _("Sin saber")),
        (UNIT_KM, _("Kilómetros")),
        (UNIT_HOURS, _("Horas")),
    ]
    UNIT_SOURCE_DEDUCED = "DEDUCED"
    UNIT_SOURCE_DRIVER = "DRIVER"
    UNIT_SOURCE_MANUAL = "MANUAL"
    UNIT_SOURCE_CHOICES = [
        (UNIT_SOURCE_DEDUCED, _("Deducida")),
        (UNIT_SOURCE_DRIVER, _("Confirmada por el chófer")),
        (UNIT_SOURCE_MANUAL, _("Puesta a mano")),
    ]

    gasoges_id = models.PositiveIntegerField(
        _("ID en GasoGes"), unique=True,
    )
    plate = models.CharField(_("Matrícula (GasoGes)"), max_length=50,
                             blank=True)
    name = models.CharField(_("Nombre (GasoGes)"), max_length=150,
                            blank=True)
    machine = models.ForeignKey(
        MachineAsset,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="gasoges_vehicles",
        verbose_name=_("Centro de gasto"),
    )
    link_method = models.CharField(
        _("Cómo se enlazó"), max_length=40, blank=True,
    )
    unit = models.CharField(
        _("Qué apunta en KM"), max_length=10, choices=UNIT_CHOICES,
        default=UNIT_UNKNOWN,
    )
    unit_source = models.CharField(
        _("Origen de la unidad"), max_length=10,
        choices=UNIT_SOURCE_CHOICES, blank=True,
    )
    last_km = models.BigIntegerField(
        _("Últimos KM (GasoGes)"), null=True, blank=True,
    )
    # S135, Miguel Ángel: no se pregunta por los vehículos que lleva
    # siempre la misma persona (administradores, comerciales: "ese
    # vehículo siempre lo lleva Carlos Carlín"), sino por los camiones
    # y grúas que coge gente distinta. Sus lecturas siguen entrando.
    # ---
    # Whether the driver gets WhatsApp questions about this vehicle.
    ask_driver = models.BooleanField(
        _("Preguntar al chófer"), default=True,
        help_text=_(
            "Si no, sus repostajes dan lecturas igual, pero el robot "
            "no pregunta nunca por ellos."
        ),
    )
    updated_at = models.DateTimeField(_("Actualizado"), auto_now=True)

    class Meta:
        verbose_name = _("Vehículo de GasoGes")
        verbose_name_plural = _("Vehículos de GasoGes")
        ordering = ["gasoges_id"]

    def __str__(self) -> str:
        return f"GasoGes {self.gasoges_id} ({self.plate or self.name})"


class GasoGesUser(models.Model):
    """
    One GasoGes user (who refuels), matched with a worker.

    ---

    Un usuario de GasoGes (quien reposta), cruzado por nombre con su
    ficha de trabajador para poder escribirle por WhatsApp. GasoGes
    solo da el nombre, cortado a 30 caracteres. Nunca se guardan el
    PIN ni la llave.
    """

    gasoges_id = models.PositiveIntegerField(
        _("ID en GasoGes"), unique=True,
    )
    name = models.CharField(_("Nombre (GasoGes)"), max_length=150,
                            blank=True)
    person = models.ForeignKey(
        "document_explorer.PersonIdentity",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="gasoges_users",
        verbose_name=_("Trabajador"),
    )
    match_note = models.CharField(
        _("Cruce con la ficha"), max_length=255, blank=True,
    )
    updated_at = models.DateTimeField(_("Actualizado"), auto_now=True)

    class Meta:
        verbose_name = _("Usuario de GasoGes")
        verbose_name_plural = _("Usuarios de GasoGes")
        ordering = ["name"]

    def __str__(self) -> str:
        return f"GasoGes {self.gasoges_id} ({self.name})"


class GasoGesSupply(models.Model):
    """
    One fuel supply read from GasoGes, stored once.

    ---

    Un suministro leído de GasoGes, guardado una sola vez (la API no da
    ID de suministro: `dedupe_key` junta vehículo, fecha y hora, KM,
    litros y surtidor). Los litros los da la máquina y son exactos; el
    KM lo teclea el chófer y puede estar mal (S135, Miguel Ángel: el
    chófer con prisa que pone "555", o un cero de más). Solo los
    suministros que pasan la comprobación crean lectura.
    """

    STATUS_PENDING = "PENDING"
    STATUS_READING = "READING"
    STATUS_ANOMALY = "ANOMALY"
    STATUS_NO_MACHINE = "NO_MACHINE"
    STATUS_NO_UNIT = "NO_UNIT"
    STATUS_CHOICES = [
        (STATUS_PENDING, _("Pendiente")),
        (STATUS_READING, _("Lectura creada")),
        (STATUS_ANOMALY, _("Lectura dudosa")),
        (STATUS_NO_MACHINE, _("Sin centro de gasto")),
        (STATUS_NO_UNIT, _("Sin saber si son km u horas")),
    ]

    dedupe_key = models.CharField(max_length=120, unique=True)
    vehicle = models.ForeignKey(
        GasoGesVehicle,
        on_delete=models.PROTECT,
        related_name="supplies",
        verbose_name=_("Vehículo (GasoGes)"),
    )
    user = models.ForeignKey(
        GasoGesUser,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="supplies",
        verbose_name=_("Quién repostó"),
    )
    gasoges_user_id = models.PositiveIntegerField(
        _("ID de usuario (GasoGes)"), null=True, blank=True,
    )
    supplied_at = models.DateTimeField(_("Fecha y hora"), db_index=True)
    meter_value = models.BigIntegerField(
        _("KM tecleado"), null=True, blank=True,
    )
    litres = models.DecimalField(
        _("Litros"), max_digits=9, decimal_places=2, null=True, blank=True,
    )
    price = models.DecimalField(
        _("Precio"), max_digits=9, decimal_places=4, null=True,
        blank=True,
    )
    pump_serial = models.BigIntegerField(
        _("Nº de serie del surtidor"), null=True, blank=True,
    )
    tank_id = models.PositiveIntegerField(
        _("Depósito"), null=True, blank=True,
    )
    fuel_id = models.PositiveIntegerField(
        _("Combustible"), null=True, blank=True,
    )
    status = models.CharField(
        _("Estado"), max_length=12, choices=STATUS_CHOICES,
        default=STATUS_PENDING, db_index=True,
    )
    status_note = models.CharField(_("Motivo"), max_length=255,
                                   blank=True)
    reading = models.OneToOneField(
        MachineMeterReading,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="gasoges_supply",
        verbose_name=_("Lectura creada"),
    )
    created_at = models.DateTimeField(_("Leído el"), auto_now_add=True)

    class Meta:
        verbose_name = _("Suministro de GasoGes")
        verbose_name_plural = _("Suministros de GasoGes")
        ordering = ["-supplied_at", "-id"]

    def __str__(self) -> str:
        return f"Suministro {self.vehicle.gasoges_id} {self.supplied_at}"


class RefuelQuestion(models.Model):
    """
    One WhatsApp question to a driver about a GasoGes supply.

    ---

    Una pregunta por WhatsApp al chófer sobre un repostaje de GasoGes
    (S135, Miguel Ángel: dos plantillas con botones). Guarda a quién se
    preguntó, qué y en qué quedó, para no repetir y para saber a qué
    pregunta corresponde cada respuesta:
    - VALUE (`refuel_value_check`): el KM tecleado parece erróneo.
    - UNIT (`refuel_unit_check`): no se sabe si el vehículo apunta km u
      horas.
    """

    KIND_VALUE = "VALUE"
    KIND_UNIT = "UNIT"
    KIND_CHOICES = [
        (KIND_VALUE, _("¿Es correcto el dato?")),
        (KIND_UNIT, _("¿Kilómetros u horas?")),
    ]
    STATUS_SENT = "SENT"
    STATUS_AWAITING_VALUE = "AWAITING_VALUE"
    STATUS_CONFIRMED = "CONFIRMED"
    STATUS_CORRECTED = "CORRECTED"
    STATUS_UNIT_SET = "UNIT_SET"
    STATUS_EXPIRED = "EXPIRED"
    STATUS_CHOICES = [
        (STATUS_SENT, _("Enviada, sin respuesta")),
        (STATUS_AWAITING_VALUE, _("Esperando el valor correcto")),
        (STATUS_CONFIRMED, _("El chófer dice que es correcto")),
        (STATUS_CORRECTED, _("Corregido por el chófer")),
        (STATUS_UNIT_SET, _("Unidad confirmada por el chófer")),
        (STATUS_EXPIRED, _("Sin respuesta a tiempo")),
    ]

    kind = models.CharField(_("Pregunta"), max_length=6,
                            choices=KIND_CHOICES)
    supply = models.ForeignKey(
        GasoGesSupply,
        on_delete=models.CASCADE,
        related_name="questions",
        verbose_name=_("Repostaje"),
    )
    vehicle = models.ForeignKey(
        GasoGesVehicle,
        on_delete=models.CASCADE,
        related_name="questions",
        verbose_name=_("Vehículo (GasoGes)"),
    )
    person = models.ForeignKey(
        "document_explorer.PersonIdentity",
        on_delete=models.CASCADE,
        related_name="refuel_questions",
        verbose_name=_("Chófer"),
    )
    phone = models.CharField(_("Teléfono"), max_length=20)
    status = models.CharField(
        _("Estado"), max_length=16, choices=STATUS_CHOICES,
        default=STATUS_SENT, db_index=True,
    )
    message_sid = models.CharField(max_length=64, blank=True)
    sent_at = models.DateTimeField(_("Enviada"), auto_now_add=True)
    answered_at = models.DateTimeField(_("Respondida"), null=True,
                                       blank=True)
    answer = models.CharField(_("Respuesta"), max_length=255, blank=True)

    class Meta:
        verbose_name = _("Pregunta de repostaje")
        verbose_name_plural = _("Preguntas de repostaje")
        ordering = ["-sent_at", "-id"]

    def __str__(self) -> str:
        return f"{self.get_kind_display()} -- {self.supply}"


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

    Registra una intervención de mantenimiento individual sobre un
    MachineAsset. Una intervención puede originarse en una línea de parte
    de trabajo procesada (FK work_entry_line) o ser introducida
    manualmente por un supervisor.
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
        verbose_name=_("Centro de gasto"),
        help_text=_(
            "Máquina o vehículo sobre el que se realiza la intervención."
        ),
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
    date = models.DateField(
        _("Fecha"),
        help_text=_(
            "Fecha en que se realizó la intervención de mantenimiento."
        ),
    )
    description = models.TextField(
        _("Descripción"),
        help_text=_(
            "Descripción detallada de los trabajos realizados durante "
            "la intervención."
        ),
    )
    worker = models.CharField(
        _("Operario"),
        max_length=200,
        blank=True,
        help_text=_(
            "Nombre del mecánico o técnico que realizó la intervención. "
            "Se propaga desde el parte de trabajo cuando procede."
        ),
    )
    charged_hours = models.DecimalField(
        _("Horas Imputadas"),
        max_digits=6,
        decimal_places=2,
        default=0,
        help_text=_(
            "Horas de mano de obra propia imputadas a esta intervención. "
            "Se calcula a partir del delta de horas del parte de trabajo."
        ),
    )
    notes = models.TextField(
        _("Observaciones"),
        blank=True,
        help_text=_(
            "Observaciones adicionales del supervisor o del operario."
        ),
    )

    # ------------------------------------------------------------------
    # Audit / Auditoría
    # ------------------------------------------------------------------
    created_at = models.DateTimeField(
        _("Creado en"),
        auto_now_add=True,
    )
    updated_at = models.DateTimeField(
        _("Actualizado en"),
        auto_now=True,
    )

    class Meta:
        verbose_name = _("Registro de Mantenimiento")
        verbose_name_plural = _("Registros de Mantenimiento")
        ordering = ["-date", "machine_asset"]

    def __str__(self) -> str:
        return (
            f"[{self.date}] {self.machine_asset.code} — "
            f"{self.description[:60]}"
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

    The `item_type` field drives the accounting logic:
      - WAREHOUSE_PART   → cost deducted from internal warehouse stock
                           (future).
      - THIRD_PARTY_PART → cost from an external supplier delivery note.
      - THIRD_PARTY_LABOUR → third-party labour detailed in a delivery note,
                             treated as a part line per business convention.

    ---

    Representa una línea individual consumida en una intervención de
    mantenimiento: un repuesto del almacén interno, un repuesto o componente
    de tercero, o mano de obra de tercero (tratada como línea de albarán
    según el convenio del negocio).

    El campo `item_type` impulsa la lógica contable:
      - WAREHOUSE_PART     → coste deducido del stock del almacén interno
                             (futuro).
      - THIRD_PARTY_PART   → coste procedente de un albarán de proveedor
                             externo.
      - THIRD_PARTY_LABOUR → mano de obra de tercero detallada en albarán,
                             tratada como línea de repuesto por convenio
                             del negocio.
    """

    class ItemType(models.TextChoices):
        WAREHOUSE_PART = "WAREHOUSE_PART",    _("Repuesto — Almacén propio")
        THIRD_PARTY_PART = "THIRD_PARTY_PART",  _("Repuesto — Tercero")
        THIRD_PARTY_LABOUR = "THIRD_PARTY_LABOUR", _("Mano de obra — Tercero")

    # ------------------------------------------------------------------
    # Relation / Relación
    # ------------------------------------------------------------------
    maintenance_log = models.ForeignKey(
        MaintenanceLog,
        on_delete=models.CASCADE,
        related_name="items",
        verbose_name=_("Registro de Mantenimiento"),
        help_text=_(
            "Intervención de mantenimiento a la que pertenece esta línea."
        ),
    )

    # ------------------------------------------------------------------
    # Item classification / Clasificación del concepto
    # ------------------------------------------------------------------
    item_type = models.CharField(
        _("Tipo"),
        max_length=20,
        choices=ItemType.choices,
        db_index=True,
        help_text=_(
            "Tipo de concepto: repuesto de almacén propio, repuesto de tercero"
            " "
            "o mano de obra de tercero."
        ),
    )

    # ------------------------------------------------------------------
    # Item description / Descripción del concepto
    # ------------------------------------------------------------------
    description = models.CharField(
        _("Descripción"),
        max_length=300,
        help_text=_(
            "Nombre o descripción del repuesto, pieza o concepto de mano de "
            "obra."
        ),
    )
    reference = models.CharField(
        _("Referencia"),
        max_length=100,
        blank=True,
        help_text=_(
            "Referencia del repuesto o pieza (código de almacén, referencia "
            "del "
            "fabricante, etc.). Vacío para mano de obra de tercero."
        ),
    )

    # ------------------------------------------------------------------
    # Quantity and cost / Cantidad y coste
    # ------------------------------------------------------------------
    quantity = models.DecimalField(
        _("Cantidad"),
        max_digits=10,
        decimal_places=3,
        default=1,
        help_text=_("Cantidad consumida del repuesto o pieza."),
    )
    unit_cost = models.DecimalField(
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
    delivery_note_ref = models.CharField(
        _("Referencia de Albarán"),
        max_length=100,
        blank=True,
        help_text=_(
            "Referencia del albarán o factura del proveedor externo. "
            "Vacío para repuestos de almacén propio. Permite trazar el coste "
            "al documento de tercero cuando el módulo de albaranes esté "
            "disponible."
        ),
    )

    # ------------------------------------------------------------------
    # Audit / Auditoría
    # ------------------------------------------------------------------
    created_at = models.DateTimeField(
        _("Creado en"),
        auto_now_add=True,
    )

    class Meta:
        verbose_name = _("Línea de Mantenimiento")
        verbose_name_plural = _("Líneas de Mantenimiento")
        ordering = ["maintenance_log", "item_type", "description"]

    def __str__(self) -> str:
        cost = (
            f"{self.unit_cost} €/ud."
            if self.unit_cost is not None
            else "sin coste"
        )
        return (
            f"{self.get_item_type_display()} — {self.description} "
            f"x{self.quantity} ({cost})"
        )

    @property
    def total_cost(self) -> float | None:
        """
        Returns the total cost of the line item (quantity × unit cost),
        or None if the unit cost is not set.

        ---

        Devuelve el coste total de la línea (cantidad × coste unitario),
        o None si el coste unitario no está definido.
        """
        if self.unit_cost is None:
            return None
        return float(self.quantity * self.unit_cost)
