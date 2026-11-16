# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/hr_calendar/models.py
"""
Data models for the hr_calendar app (Hito 24).

VacationPeriod is the single source of truth for a registered vacation
period of a CompanyUser (any role -- open to all per Miguel Ángel's
explicit decision in S018, even though today only WORKSHOP/DRIVER are
expected to use it). date_start/date_end are the actual vacation days
(both inclusive); the calendar view (not built yet in this session)
derives its green days directly from this range, no day-by-day record
needed.

Design decision (S018): registering a VacationPeriod is the source of
truth, NOT the automatic PERSONAL/VACATION task generated on the last
working day before date_start. That task is a *consequence* of creating
a VacationPeriod, kept purely for consistency with the existing manual
absence-block flow (fault/repair fields, hour totals, etc. -- see
work_order_processor.models.WorkOrderEntryLine and
ivr_config.models.AbsenceCategory, both already built in H7/H10). The
reasons a separate model was chosen over embedding the range inside that
task line, discussed explicitly with Miguel Ángel:
  1. A WorkOrderEntryLine lives inside a WorkOrder, whose lifecycle
     (PENDING_GAPS -> DONE, corrections) is unrelated to vacation
     tracking -- a later correction to that work order should never be
     able to silently alter or lose the vacation dates.
  2. Direct queries ("who is on vacation this week", calendar
     rendering, the future H23 WhatsApp expiry-alert style feature)
     need a flat VacationPeriod.objects.filter(...), not a join through
     WorkOrder -> WorkOrderEntry -> WorkOrderEntryLine every time.
  3. WorkOrderEntryLine.repair_notes is free-text (TextField) -- using
     it to encode a structured end date would mean parsing a date out
     of free text to drive calendar logic, exactly the class of
     fragility this project has deliberately avoided elsewhere (e.g.
     the "machine code must be printed, never handwritten" rule). With
     VacationPeriod.date_end as the real source of truth, repair_notes
     on the generated task can stay purely human-readable, nothing
     parses it.

generated_entry_line is a nullable pointer to the automatic task once
it exists (not built yet in this session -- see H24 annex, hoja de
ruta), kept for traceability and so a retry of the generation step
never creates a duplicate task for the same period.

---

Modelos de datos para la app hr_calendar (Hito 24).

VacationPeriod es la única fuente de verdad de un periodo de vacaciones
registrado para un CompanyUser (cualquier rol -- abierto a todos por
decisión explícita de Miguel Ángel en S018, aunque hoy solo se esperan
WORKSHOP/DRIVER). date_start/date_end son los días reales de vacaciones
(ambos inclusive); la vista de calendario (todavía no construida en esta
sesión) deriva sus días verdes directamente de este rango, sin
necesidad de un registro día a día.

Decisión de diseño (S018): registrar un VacationPeriod es la fuente de
verdad, NO la tarea automática PERSONAL/VACACIONES generada en la
última jornada laboral antes de date_start. Esa tarea es una
*consecuencia* de crear un VacationPeriod, mantenida únicamente por
coherencia con el flujo manual de bloques de ausencia ya existente
(campos avería/reparación, cómputo de horas, etc. -- ver
work_order_processor.models.WorkOrderEntryLine e
ivr_config.models.AbsenceCategory, ambos ya construidos en H7/H10). Los
motivos para elegir un modelo aparte en vez de incrustar el rango
dentro de esa línea de tarea, discutidos explícitamente con Miguel
Ángel:
  1. Un WorkOrderEntryLine vive dentro de un WorkOrder, cuyo ciclo de
     vida (PENDING_GAPS -> DONE, correcciones) no tiene relación con el
     seguimiento de vacaciones -- una corrección posterior de ese parte
     nunca debería poder alterar o perder silenciosamente las fechas de
     vacaciones.
  2. Las consultas directas ("quién está de vacaciones esta semana",
     pintar el calendario, la futura funcionalidad de alarmas WhatsApp
     al estilo de H23) necesitan un VacationPeriod.objects.filter(...)
     plano, no un join a través de
     WorkOrder -> WorkOrderEntry -> WorkOrderEntryLine cada vez.
  3. WorkOrderEntryLine.repair_notes es texto libre (TextField) --
     usarlo para codificar una fecha de fin estructurada implicaría
     parsear una fecha de texto libre para gobernar la lógica del
     calendario, exactamente el tipo de fragilidad que este proyecto ha
     evitado deliberadamente en otros sitios (p. ej. la regla de
     "código de máquina siempre impreso, nunca manuscrito"). Con
     VacationPeriod.date_end como fuente de verdad real, repair_notes
     en la tarea generada puede quedar puramente legible para humanos,
     sin que nada lo parsee.

generated_entry_line es un puntero opcional a la tarea automática una
vez exista (todavía no construida en esta sesión -- ver hoja de ruta
del anexo H24), mantenido para trazabilidad y para que un reintento del
paso de generación nunca cree una tarea duplicada para el mismo
periodo.
"""
import datetime

from django.db import models

from document_explorer.models import DocumentIndexEntry, PersonIdentity
from ivr_config.models import Company, CompanyUser


class VacationPeriod(models.Model):
    """
    A registered vacation period for a worker. Source of truth for the
    HR calendar's green days and for the automatic PERSONAL/VACATION
    task generated on the last working day before date_start.

    REDESIGNED H31 (S94), real incident reported by Miguel Ángel with
    screenshot evidence: this model originally (H24) linked only to
    CompanyUser (panel account), conflating "is a company worker"
    with "has panel login access" -- two genuinely different sets.
    Real symptom: the panel dropdown only ever offered CompanyUser
    accounts, so a worker without panel access (e.g. Antonio Jesús
    Díaz Quintero, a real active employee) could never be given a
    vacation period, while an admin-only account with no worker
    identity (alvarez_admin) could be selected by mistake (and was,
    S94, test row later deleted -- see migration 0003).

    `person` (PersonIdentity, document_explorer/H30) is now the real
    "who" -- every one of the ~72 active workers, panel access or not.
    `operator` (CompanyUser) is now OPTIONAL, resolved automatically
    from `person.company_user` (the bridge already built in S74) --
    used exclusively to attempt the automatic ghost-task generation
    below, which genuinely requires a CompanyUser (CompanyUser.base
    for the working-day calendar, CompanyUser.user for a display
    name). When a worker has no panel account, the VacationPeriod is
    still created normally -- simply without a ghost task, since there
    is no digital work-order/calendar concept for someone who never
    submits digital partes in the first place.
    ---
    Un periodo de vacaciones registrado para un trabajador. Fuente de
    verdad de los días verdes del calendario de RRHH y de la tarea
    automática PERSONAL/VACACIONES generada en la última jornada
    laboral antes de date_start.

    REDISEÑADO EN H31 (S94), incidente real reportado por Miguel Ángel
    con evidencia de captura de pantalla: este modelo originalmente
    (H24) solo enlazaba con CompanyUser (cuenta de panel), confundiendo
    "es trabajador de la empresa" con "tiene acceso de login al panel"
    -- dos conjuntos genuinamente distintos. Síntoma real: el
    desplegable del panel solo ofrecía cuentas CompanyUser, así que un
    trabajador sin acceso al panel (p. ej. Antonio Jesús Díaz Quintero,
    empleado activo real) nunca podía recibir un periodo vacacional,
    mientras que una cuenta solo-administrativa sin identidad de
    trabajador (alvarez_admin) podía seleccionarse por error (y así
    fue, S94, fila de prueba borrada después -- ver migración 0003).

    `person` (PersonIdentity, document_explorer/H30) es ahora el
    "quién" real -- cualquiera de los ~72 trabajadores activos, tenga o
    no acceso al panel. `operator` (CompanyUser) es ahora OPCIONAL,
    resuelto automáticamente desde `person.company_user` (el puente ya
    construido en S74) -- usado exclusivamente para intentar la
    generación automática de la tarea fantasma de abajo, que sí
    necesita genuinamente un CompanyUser (CompanyUser.base para el
    calendario laboral, CompanyUser.user para un nombre de
    visualización). Cuando un trabajador no tiene cuenta de panel, el
    VacationPeriod se crea igualmente -- simplemente sin tarea
    fantasma, porque no existe ningún concepto de parte digital/
    calendario para alguien que nunca presenta partes digitales.
    """

    # ------------------------------------------------------------------
    # Relations / Relaciones
    # ------------------------------------------------------------------
    person = models.ForeignKey(
        PersonIdentity,
        on_delete=models.CASCADE,
        related_name="vacation_periods",
        verbose_name="Persona",
        help_text="Trabajador real al que pertenecen estas vacaciones "
                  "-- identidad de personal (document_explorer, H30), "
                  "no cuenta de panel. Obligatorio: cualquier "
                  "trabajador activo puede tener vacaciones, tenga o "
                  "no acceso al panel.",
    )
    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="vacation_periods",
        verbose_name="Empresa",
        help_text="Empresa a la que pertenece este periodo, "
                  "denormalizada desde la empresa del usuario del "
                  "panel que lo registra en el momento de creación "
                  "(mismo patrón que MachineDocument/TaskPhoto).",
    )
    operator = models.ForeignKey(
        CompanyUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="vacation_periods_as_operator",
        verbose_name="Cuenta de panel vinculada",
        help_text="CompanyUser correspondiente a person.company_user, "
                  "cuando existe -- resuelto automáticamente, nunca "
                  "elegido a mano. Nulo cuando la persona no tiene "
                  "cuenta de panel: en ese caso no se genera tarea "
                  "fantasma (ver generated_entry_line), pero el "
                  "periodo de vacaciones se registra igual.",
    )
    generated_entry_line = models.ForeignKey(
        "work_order_processor.WorkOrderEntryLine",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="vacation_period",
        verbose_name="Tarea automática generada",
        help_text="Bloque de tarea (centro de gasto PERSONAL, "
                  "categoría VACATION) generado automáticamente en la "
                  "última jornada laboral antes de date_start. Nulo "
                  "hasta que el paso de generación automática exista y "
                  "se ejecute (no construido todavía -- ver hoja de "
                  "ruta del anexo H24). Puntero de trazabilidad, no la "
                  "fuente de verdad de las fechas -- ver docstring del "
                  "módulo.",
    )
    created_by = models.ForeignKey(
        CompanyUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="vacation_periods_created",
        verbose_name="Registrado por",
        help_text="Usuario del panel que registró este periodo de "
                  "vacaciones.",
    )

    # ------------------------------------------------------------------
    # Dates / Fechas
    # ------------------------------------------------------------------
    date_start = models.DateField(
        verbose_name="Fecha de inicio",
        help_text="Primer día de vacaciones (inclusive). La tarea "
                  "automática se genera en la última jornada laboral "
                  "anterior a esta fecha.",
    )
    date_end = models.DateField(
        verbose_name="Fecha de fin",
        help_text="Último día de vacaciones (inclusive). Fuente de "
                  "verdad de la fecha de fin -- no se deriva de ningún "
                  "campo de texto libre.",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Fecha de creación",
    )

    class Meta:
        verbose_name = "Periodo de vacaciones"
        verbose_name_plural = "Periodos de vacaciones"
        ordering = ["-date_start"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(date_end__gte=models.F("date_start")),
                name="vacationperiod_date_end_gte_date_start",
            ),
        ]

    def __str__(self) -> str:
        return (
            f"{self.person} — {self.date_start:%d/%m/%Y} a "
            f"{self.date_end:%d/%m/%Y}"
        )

    def save(self, *args, **kwargs):
        """
        On first creation, triggers the automatic generation of the
        PERSONAL/VACATION ghost task (hr_calendar/services.py::
        generate_vacation_task) on the last working day before date_start,
        inside the same atomic transaction as this save -- if generation
        fails (e.g. PERSONAL/VACATION seed data missing for the company),
        the VacationPeriod row itself is rolled back too, so a period can
        never exist without its ghost task once this save() returns
        successfully. Skipped on subsequent saves (edits) -- generation is
        create-only, see hoja de ruta H24 paso 1.

        REDESIGNED H31 (S94): also skipped whenever operator_id is None
        -- a worker with no panel account (person.company_user is null)
        has no CompanyUser.base to compute a working-day calendar
        against, and never submits digital partes to begin with, so
        there is nothing for a ghost task to exclude. The VacationPeriod
        itself is still created normally; only the ghost task step is
        skipped, silently and by design, not as an error path.
        ---
        En la primera creación, dispara la generación automática de la
        tarea fantasma PERSONAL/VACACIONES (hr_calendar/services.py::
        generate_vacation_task) en la última jornada laboral antes de
        date_start, dentro de la misma transacción atómica que este save
        -- si la generación falla (p. ej. faltan los datos seed de
        PERSONAL/VACATION para la empresa), la propia fila de
        VacationPeriod se revierte también, de forma que un periodo nunca
        puede existir sin su tarea fantasma una vez este save() retorna
        con éxito. Se omite en saves posteriores (ediciones) -- la
        generación es solo-al-crear, ver hoja de ruta H24 paso 1.

        REDISEÑADO EN H31 (S94): también se omite siempre que
        operator_id sea nulo -- un trabajador sin cuenta de panel
        (person.company_user es nulo) no tiene CompanyUser.base contra
        el que calcular un calendario laboral, y tampoco presenta
        partes digitales, así que no hay nada que una tarea fantasma
        pueda excluir. El propio VacationPeriod se crea igualmente;
        solo se omite el paso de la tarea fantasma, en silencio y por
        diseño, no como camino de error.
        """
        from django.db import transaction

        is_new = self._state.adding
        with transaction.atomic():
            super().save(*args, **kwargs)
            if (
                is_new
                and self.generated_entry_line_id is None
                and self.operator_id is not None
            ):
                from hr_calendar.services import generate_vacation_task
                generate_vacation_task(self)


class MedicalLeavePeriod(models.Model):
    """
    A structured record of a worker's medical leave (baja médica),
    sibling in spirit to VacationPeriod (period with start/end dates
    feeding the "Laboral" accordion of the personnel file), but linked
    to PersonIdentity (document_explorer) rather than CompanyUser --
    decision of Miguel Ángel in S093: "modelo estructurado, es mejor
    para esto [...] son documentos prácticamente iguales y van a variar
    poco con el tiempo, todos tendrán datos parecidos y fácil de captar
    y trasladar a la BBDD." Built from H31 roadmap point 1 (S94).

    date_end is nullable: a leave still in progress has no end date
    yet, unlike VacationPeriod where both dates are always known at
    creation time.

    source_document is a nullable pointer to the DocumentIndexEntry
    (PARTE_BAJA_MEDICA) this record was created from, when one exists
    -- same traceability pattern as
    VacationPeriod.generated_entry_line, but pointing the opposite
    direction (from the structured record back to its originating
    document, not to a task it generates).

    ---

    Registro estructurado de una baja médica de un trabajador, hermano
    en espíritu de VacationPeriod (periodo con fecha de inicio/fin que
    alimenta el acordeón "Laboral" de la ficha de personal), pero
    enlazado a PersonIdentity (document_explorer) en vez de a
    CompanyUser -- decisión de Miguel Ángel en S093: "modelo
    estructurado, es mejor para esto [...] son documentos prácticamente
    iguales y van a variar poco con el tiempo, todos tendrán datos
    parecidos y fácil de captar y trasladar a la BBDD." Construido
    desde el punto 1 de la hoja de ruta de H31 (S94).

    date_end es nullable: una baja en curso todavía no tiene fecha de
    fin, a diferencia de VacationPeriod donde ambas fechas se conocen
    siempre en el momento de creación.

    source_document es un puntero opcional al DocumentIndexEntry
    (PARTE_BAJA_MEDICA) del que se creó este registro, cuando existe
    -- mismo patrón de trazabilidad que
    VacationPeriod.generated_entry_line, pero en sentido inverso (del
    registro estructurado hacia el documento de origen, no hacia una
    tarea que genera).
    """

    class ContingencyType(models.TextChoices):
        """
        Categorías reales de contingencia según LGSS/Ministerio de
        Trabajo, investigadas en S76 (ver anexo H31 sección 5.4,
        punto 4) -- no inventadas, citadas tal cual en la hoja de
        ruta de S94.
        """
        COMUN = "COMUN", "Contingencia común"
        PROFESIONAL = "PROFESIONAL", "Contingencia profesional"
        MATERNIDAD_PATERNIDAD = (
            "MATERNIDAD_PATERNIDAD", "Maternidad/Paternidad"
        )
        RIESGO_EMBARAZO_LACTANCIA = (
            "RIESGO_EMBARAZO_LACTANCIA",
            "Riesgo durante el embarazo/lactancia",
        )
        SALUD_MENSTRUAL_REPRODUCTIVA = (
            "SALUD_MENSTRUAL_REPRODUCTIVA",
            "Salud menstrual/reproductiva",
        )

    # ------------------------------------------------------------------
    # Relations / Relaciones
    # ------------------------------------------------------------------
    person = models.ForeignKey(
        PersonIdentity,
        on_delete=models.CASCADE,
        related_name="medical_leave_periods",
        verbose_name="Persona",
        help_text="Trabajador al que pertenece esta baja médica, "
                  "identificado por PersonIdentity (dominio personal "
                  "de H30), no por CompanyUser.",
    )
    source_document = models.ForeignKey(
        DocumentIndexEntry,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="Documento de origen (PARTE_BAJA_MEDICA)",
        help_text="DocumentIndexEntry del que se extrajo este registro, "
                  "cuando existe uno real ya clasificado como "
                  "PARTE_BAJA_MEDICA. Nulo si el registro se crea por "
                  "otra vía (alta manual desde el panel).",
    )

    # ------------------------------------------------------------------
    # Dates / Fechas
    # ------------------------------------------------------------------
    date_start = models.DateField(
        verbose_name="Fecha de inicio",
        help_text="Primer día de la baja médica.",
    )
    date_end = models.DateField(
        null=True,
        blank=True,
        verbose_name="Fecha de alta/fin",
        help_text="Fecha de alta médica. Nulo cuando la baja sigue en "
                  "curso -- a diferencia de VacationPeriod, aquí ambas "
                  "fechas no se conocen siempre en el momento de "
                  "creación.",
    )

    contingency_type = models.CharField(
        max_length=32,
        choices=ContingencyType.choices,
        verbose_name="Tipo de contingencia",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Fecha de creación",
    )

    class Meta:
        verbose_name = "Periodo de baja médica"
        verbose_name_plural = "Periodos de baja médica"
        ordering = ["-date_start"]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(date_end__isnull=True)
                    | models.Q(date_end__gte=models.F("date_start"))
                ),
                name="medicalleaveperiod_date_end_gte_date_start_or_null",
            ),
        ]

    def __str__(self) -> str:
        fin = f"{self.date_end:%d/%m/%Y}" if self.date_end else "en curso"
        return f"{self.person} — {self.date_start:%d/%m/%Y} a {fin}"


class AbsencePeriod(models.Model):
    """
    An absence that is neither vacation nor medical leave (personal
    matters, medical appointment, work accident...), registered for a
    worker with its dates (H24, S130, roadmap point 4 of annex V24
    section 7.5). Same mechanism as VacationPeriod: `person` is the real
    worker (PersonIdentity, directive 4.19), whole days from date_start
    to date_end, both inclusive. The kind comes from the company's
    AbsenceCategory catalogue (the one the partes already use), except
    VACATION, which has its own VacationPeriod. It does not change the
    vacation balance; the HR calendar paints these days as an absence
    with the category's label.
    ---
    Una ausencia que no es ni vacaciones ni baja médica (asuntos
    propios, cita médica, accidente de trabajo...), registrada para un
    trabajador con sus fechas (H24, S130, punto 4 de la hoja de ruta 7.5
    del anexo V24). Mismo mecanismo que VacationPeriod: `person` es el
    trabajador real (PersonIdentity, directriz 4.19), días completos de
    date_start a date_end, ambos inclusive. El tipo sale del catálogo
    AbsenceCategory de la empresa (el que ya usan los partes), salvo
    VACATION, que tiene su propio VacationPeriod. No cambia el saldo de
    vacaciones; el calendario pinta estos días como ausencia con el
    nombre del tipo.
    """

    person = models.ForeignKey(
        PersonIdentity,
        on_delete=models.CASCADE,
        related_name="absence_periods",
        verbose_name="Trabajador",
    )
    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="absence_periods",
        verbose_name="Empresa",
    )
    category = models.ForeignKey(
        "ivr_config.AbsenceCategory",
        on_delete=models.PROTECT,
        related_name="absence_periods",
        verbose_name="Tipo de ausencia",
    )
    date_start = models.DateField(
        verbose_name="Desde",
        help_text="Primer día de la ausencia (inclusive).",
    )
    date_end = models.DateField(
        verbose_name="Hasta",
        help_text="Último día de la ausencia (inclusive).",
    )
    note = models.TextField(
        blank=True,
        verbose_name="Nota",
        help_text="Obligatoria si el tipo de ausencia la exige.",
    )
    created_by = models.ForeignKey(
        CompanyUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="absence_periods_created",
        verbose_name="Registrada por",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Fecha de registro",
    )

    class Meta:
        verbose_name = "Ausencia"
        verbose_name_plural = "Ausencias"
        ordering = ["-date_start"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(date_end__gte=models.F("date_start")),
                name="absenceperiod_date_end_gte_date_start",
            ),
        ]

    def __str__(self) -> str:
        return (
            f"{self.person} — {self.category.label} "
            f"{self.date_start:%d/%m/%Y} a {self.date_end:%d/%m/%Y}"
        )


class VacationRule(models.Model):
    """
    Vacation entitlement rule of a section (or the company-wide rule
    for workers without a section), in force from `valid_from` until
    the next rule of the same section. H24 (S129), decided by Miguel
    Ángel with Carolina (HR): days per year set by the company per
    section, natural or working days, whether leftover days carry over
    and until when. A change of rule is a new row with its own
    `valid_from`, never an edit of the old one: past years keep being
    computed with the rule that applied then.

    Lives apart from ivr_config.Section on purpose: saving a Section
    regenerates its switchboard call flow (signal
    auto_manage_section_call_flow), so vacation settings never touch
    the Section row.

    ---

    Regla de vacaciones de una sección (o la general de la empresa
    para quien aún no tiene sección), vigente desde `valid_from` hasta
    la siguiente regla de la misma sección. H24 (S129), decidido por
    Miguel Ángel con Carolina (RRHH): días al año que fija la empresa
    por sección, naturales o laborables, si los sobrantes pasan al año
    siguiente y hasta cuándo. Un cambio de regla es una fila nueva con
    su propia fecha, nunca la edición de la anterior: los años pasados
    se siguen calculando con la regla que tenían.

    Vive aparte de ivr_config.Section a propósito: guardar una Section
    regenera su flujo de la centralita (señal
    auto_manage_section_call_flow), así que la configuración de
    vacaciones nunca toca la fila de la sección.
    """

    class DayKind(models.TextChoices):
        NATURAL = "NATURAL", "Naturales"
        WORKING = "WORKING", "Laborables"

    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="vacation_rules",
        verbose_name="Empresa",
    )
    section = models.ForeignKey(
        "ivr_config.Section",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="vacation_rules",
        verbose_name="Sección",
        help_text="Vacío = regla general de la empresa, para los "
                  "trabajadores que aún no tienen sección asignada.",
    )
    valid_from = models.DateField(
        verbose_name="Vigente desde",
    )
    days_per_year = models.DecimalField(
        max_digits=4,
        decimal_places=1,
        verbose_name="Días al año",
        help_text="Días de vacaciones de un año completo (p. ej. 30 "
                  "naturales o 22 laborables).",
    )
    day_kind = models.CharField(
        max_length=8,
        choices=DayKind.choices,
        verbose_name="Tipo de días",
        help_text="Naturales: cuenta cualquier día. Laborables: solo de "
                  "lunes a viernes que no sean festivo.",
    )
    carry_over = models.BooleanField(
        default=True,
        verbose_name="Los sobrantes pasan al año siguiente",
    )
    carry_over_deadline_month = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        verbose_name="Plazo de los sobrantes (mes)",
        help_text="Mes del año siguiente hasta el que se pueden gastar "
                  "los sobrantes. Vacío = sin plazo.",
    )
    carry_over_deadline_day = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        verbose_name="Plazo de los sobrantes (día)",
        help_text="Día de ese mes (inclusive). Vacío = sin plazo.",
    )
    holiday_base = models.ForeignKey(
        "budgets.Base",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="vacation_rules",
        verbose_name="Calendario de festivos",
        help_text="Base cuyos festivos no cuentan como laborables. Vacío "
                  "= la base de la cuenta de panel del trabajador, si "
                  "la tiene; si no, solo se descuentan los fines de "
                  "semana.",
    )
    created_by = models.ForeignKey(
        CompanyUser,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        verbose_name="Creada por",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Fecha de creación",
    )

    class Meta:
        verbose_name = "Regla de vacaciones"
        verbose_name_plural = "Reglas de vacaciones"
        ordering = ["section__name", "-valid_from"]
        constraints = [
            models.UniqueConstraint(
                fields=("company", "section", "valid_from"),
                name="vacationrule_unique_section_valid_from",
            ),
        ]

    def __str__(self) -> str:
        section = self.section.name if self.section_id else "General"
        return (
            f"{section} desde {self.valid_from:%d/%m/%Y}: "
            f"{self.days_per_year} {self.get_day_kind_display().lower()}"
        )


class PersonSectionAssignment(models.Model):
    """
    Section a worker belongs to from `valid_from` on (H24, S129). The
    section in force on a given day is the assignment with the latest
    `valid_from` not after that day, so a change mid-year is just a new
    row and each stretch of the year keeps its own vacation rule.
    Sections here are membership; ivr_config.SectionContact is who the
    switchboard transfers calls to, an unrelated concept.

    ---

    Sección a la que pertenece un trabajador desde `valid_from` (H24,
    S129). La vigente un día dado es la asignación con la fecha más
    reciente que no sea posterior a ese día, así que un cambio a mitad
    de año es solo una fila nueva y cada tramo del año conserva su
    regla. Aquí la sección es pertenencia; ivr_config.SectionContact es
    a quién pasa las llamadas la centralita, otra cosa.
    """

    person = models.ForeignKey(
        PersonIdentity,
        on_delete=models.CASCADE,
        related_name="section_assignments",
        verbose_name="Persona",
    )
    section = models.ForeignKey(
        "ivr_config.Section",
        on_delete=models.CASCADE,
        related_name="person_assignments",
        verbose_name="Sección",
    )
    valid_from = models.DateField(
        verbose_name="Desde",
    )
    created_by = models.ForeignKey(
        CompanyUser,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        verbose_name="Asignada por",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Fecha de creación",
    )

    class Meta:
        verbose_name = "Sección de un trabajador"
        verbose_name_plural = "Secciones de los trabajadores"
        ordering = ["person", "-valid_from"]
        constraints = [
            models.UniqueConstraint(
                fields=("person", "valid_from"),
                name="personsectionassignment_unique_valid_from",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.person} — {self.section} desde {self.valid_from}"


class VacationBalanceAdjustment(models.Model):
    """
    Correction of a worker's vacation balance for one year (H24,
    S129). Two kinds come from Carolina's spreadsheet (one row per
    worker, year and kind, overwritten by a later import): days already
    taken that year before the system tracked them, and days left over
    from the previous year. The third kind is a manual adjustment by a
    supervisor, signed, always with a reason.

    ---

    Corrección del saldo de vacaciones de un trabajador en un año (H24,
    S129). Dos tipos vienen de la hoja de cálculo de Carolina (una fila
    por trabajador, año y tipo, que una importación posterior
    sobrescribe): días ya disfrutados ese año antes de que el sistema
    los registrara, y días que sobraron del año anterior. El tercero es
    un ajuste manual de un supervisor, con signo y siempre con motivo.
    """

    class Kind(models.TextChoices):
        OPENING_TAKEN = "OPENING_TAKEN", "Disfrutados (saldo de partida)"
        OPENING_CARRYOVER = (
            "OPENING_CARRYOVER", "Del año anterior (saldo de partida)"
        )
        MANUAL = "MANUAL", "Ajuste manual"
        # S143 (Miguel Ángel): días libres que da el supervisor a cambio
        # de horas acumuladas; suman al saldo y restan de la bolsa
        # (OvertimeAdjustment enlazado).
        OVERTIME = "OVERTIME", "Días libres por horas acumuladas"

    person = models.ForeignKey(
        PersonIdentity,
        on_delete=models.CASCADE,
        related_name="vacation_adjustments",
        verbose_name="Persona",
    )
    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="vacation_adjustments",
        verbose_name="Empresa",
    )
    year = models.PositiveSmallIntegerField(
        verbose_name="Año",
    )
    kind = models.CharField(
        max_length=20,
        choices=Kind.choices,
        verbose_name="Tipo",
    )
    days = models.DecimalField(
        max_digits=5,
        decimal_places=1,
        verbose_name="Días",
        help_text="En un ajuste manual, positivo suma días al saldo y "
                  "negativo los resta.",
    )
    reason = models.TextField(
        blank=True,
        verbose_name="Motivo",
    )
    created_by = models.ForeignKey(
        CompanyUser,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        verbose_name="Registrado por",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Fecha de creación",
    )

    class Meta:
        verbose_name = "Ajuste de saldo de vacaciones"
        verbose_name_plural = "Ajustes de saldo de vacaciones"
        ordering = ["-year", "person", "kind", "-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(kind="MANUAL") | ~models.Q(reason=""),
                name="vacationadjustment_manual_needs_reason",
            ),
        ]

    def __str__(self) -> str:
        return (
            f"{self.person} — {self.year} "
            f"{self.get_kind_display()}: {self.days}"
        )


class ImmutableClockRecord(Exception):
    """
    A clock record (press or correction) was about to be changed or
    deleted (H24, S141).

    ---

    Se iba a modificar o borrar un registro de jornada (pulsación o
    corrección) (H24, S141). Un fichaje solo se corrige con
    ClockCorrection, que conserva el original.
    """


# Campos de una pulsación que se pueden escribir después de crearla:
# solo los derivados (municipio de las coordenadas, S129). Nunca el
# tipo, la hora, la posición ni quién fichó.
CLOCK_EVENT_DERIVED_FIELDS = frozenset({"municipality"})


class ClockEventQuerySet(models.QuerySet):
    """
    Presses: append-only, plus the current ones (H24, S141).

    ---

    Pulsaciones: solo se añaden. `update()` solo admite los campos
    derivados y `delete()` no se permite. `current()` son las vigentes:
    las que no tienen corrección (una corregida queda sustituida por la
    pulsación nueva de su corrección, o anulada).
    """

    def current(self):
        return self.filter(correction__isnull=True)

    def update(self, **kwargs):
        blocked = set(kwargs) - CLOCK_EVENT_DERIVED_FIELDS
        if blocked:
            raise ImmutableClockRecord(
                "Los fichajes no se modifican (%s); se corrigen con "
                "ClockCorrection." % ", ".join(sorted(blocked))
            )
        return super().update(**kwargs)

    def delete(self):
        raise ImmutableClockRecord(
            "Los fichajes no se borran; se anulan con ClockCorrection."
        )


class ClockEvent(models.Model):
    """
    One clock-in or clock-out press (H24, S129, roadmap point 3). The
    press is made on the worker's trusted device, possibly without
    coverage: the phone keeps the press time and the GPS position and
    sends them later. Both times are stored -- the press as the phone
    gave it and the moment the server received it -- so a late send is
    visible. `client_id` is generated on the phone for each press: a
    press sent twice (the Android test sent one twice) is stored once.

    Records are never edited or deleted (S141: enforced here, see
    ClockEventQuerySet and save/delete): art. 34.9 ET requires keeping
    them four years. A wrong press is corrected with ClockCorrection,
    which keeps the original.

    ---

    Una pulsación de entrada o salida (H24, S129, punto 3 de la hoja de
    ruta). Se hace desde el dispositivo de confianza del trabajador,
    quizá sin cobertura: el móvil guarda la hora de la pulsación y la
    posición GPS y las envía después. Se guardan las dos horas -- la de
    la pulsación tal como la da el móvil y la de llegada al servidor --
    para que un envío tardío se vea. `client_id` lo genera el móvil en
    cada pulsación: una pulsación enviada dos veces (en la prueba de
    Android llegó una dos veces) se guarda una sola vez.

    Los registros no se editan ni se borran (S141: lo impide el propio
    modelo, ver ClockEventQuerySet y save/delete): el art. 34.9 ET
    obliga a conservarlos cuatro años. Una pulsación equivocada se
    corrige con ClockCorrection, que conserva la original.
    """

    class Kind(models.TextChoices):
        IN = "IN", "Entrada"
        OUT = "OUT", "Salida"
        # S141: cambio de tipo de fichaje con la jornada abierta (secciones
        # que fichan por tipos): cierra el tramo anterior y abre otro del
        # tipo nuevo en el mismo momento, sin salida ni entrada.
        CHANGE = "CHG", "Cambio de tipo"

    class SentBy(models.TextChoices):
        # S130: MANUAL pasa a ser el fichaje manual por olvido (anexo
        # V24, 7.5 punto 1); el botón «Enviar pendientes» envía como
        # PAGE. Comprobado en BD antes del cambio: ningún fichaje con
        # MANUAL.
        ONLINE = "ONLINE", "Al momento"
        BACKGROUND = "BACKGROUND", "Al volver la cobertura (segundo plano)"
        PAGE = "PAGE", "Desde la página (al abrirla o con su botón)"
        MANUAL = "MANUAL", "Fichaje manual (olvido)"
        # S141: la pulsación nueva de una corrección del supervisor
        # (ClockCorrection). Nunca la envía el móvil.
        CORRECTION = "CORRECTION", "Corrección del supervisor"

    company = models.ForeignKey(
        Company,
        on_delete=models.PROTECT,
        related_name="clock_events",
        verbose_name="Empresa",
    )
    company_user = models.ForeignKey(
        CompanyUser,
        on_delete=models.PROTECT,
        related_name="clock_events",
        verbose_name="Usuario que fichó",
    )
    person = models.ForeignKey(
        PersonIdentity,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="clock_events",
        verbose_name="Trabajador",
        help_text="Ficha de Personal del usuario en el momento de "
                  "fichar; vacía si el usuario aún no tenía ficha.",
    )
    kind = models.CharField(
        max_length=3,
        choices=Kind.choices,
        verbose_name="Tipo",
    )
    client_id = models.CharField(
        max_length=40,
        unique=True,
        verbose_name="Identificador de la pulsación",
        help_text="Generado por el móvil; evita guardar dos veces la "
                  "misma pulsación.",
    )
    pressed_at = models.DateTimeField(
        verbose_name="Hora de la pulsación",
        help_text="Hora del móvil al pulsar.",
    )
    rounded_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Hora redondeada (parte)",
        help_text="La hora o media hora que usa el parte "
                  "(hr_calendar/clock_rounding.py). La pulsación real "
                  "queda en pressed_at.",
    )
    received_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Hora de llegada al servidor",
    )
    latitude = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True,
        verbose_name="Latitud",
    )
    longitude = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True,
        verbose_name="Longitud",
    )
    accuracy_m = models.PositiveIntegerField(
        null=True, blank=True,
        verbose_name="Precisión GPS (m)",
    )
    gps_error = models.CharField(
        max_length=120, blank=True,
        verbose_name="Motivo de la falta de GPS",
    )
    municipality = models.CharField(
        max_length=150, null=True, blank=True,
        verbose_name="Municipio",
        help_text=(
            "Municipio de las coordenadas (Google Geocoding, "
            "hr_calendar/clock_geocode.py). Vacío = sin resultado; "
            "nulo = todavía sin consultar."
        ),
    )
    sent_by = models.CharField(
        max_length=12,
        choices=SentBy.choices,
        default=SentBy.ONLINE,
        verbose_name="Cómo se envió",
    )
    user_agent = models.CharField(
        max_length=200, blank=True,
        verbose_name="Navegador",
    )
    # S144 (Miguel Ángel): desplazamiento con su propio vehículo; los
    # kilómetros se calculan al cerrar el tramo (OwnVehicleTrip).
    own_vehicle = models.BooleanField(
        default=False,
        verbose_name="Con su vehículo",
        help_text="Solo en un tramo de desplazamiento.",
    )
    # S143 (Miguel Ángel): en el fichaje por tipos, "No he parado para
    # comer". Sin esa casilla y sin pausa fichada, se descuenta una hora
    # de comida (y otra de cena si la jornada toca la hora de cenar).
    no_meal_break = models.BooleanField(
        default=False,
        verbose_name="No he parado para comer",
        help_text="Marcada por el trabajador en la jornada.",
    )
    # S149 (Miguel Ángel): "se le olvida picar la salida [...] tenía que
    # salir a las 19 y ha picado a las 20 [...] la opción de poner un
    # mensaje diciendo la hora real". La salida se guarda a la hora en
    # que se pulsó; esto es lo que dice el trabajador, y el supervisor lo
    # aplica (corrección) o no.
    claimed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Hora real indicada",
        help_text="Hora real de salida que indica el trabajador al "
                  "fichar tarde la salida.",
    )
    claim_note = models.CharField(
        max_length=255,
        blank=True,
        default="",
        verbose_name="Mensaje del trabajador",
    )
    clock_type = models.ForeignKey(
        "hr_calendar.ClockType",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="clock_events",
        verbose_name="Tipo de fichaje",
        help_text="S141: tipo del tramo que abre una entrada o un cambio "
                  "de tipo (secciones que fichan por tipos). Vacío en "
                  "las salidas y en quien ficha con el botón único.",
    )

    objects = ClockEventQuerySet.as_manager()

    class Meta:
        verbose_name = "Fichaje"
        verbose_name_plural = "Fichajes"
        ordering = ["-pressed_at"]
        indexes = [
            models.Index(
                fields=["company", "pressed_at"],
                name="clockevent_company_pressed",
            ),
            models.Index(
                fields=["company_user", "pressed_at"],
                name="clockevent_user_pressed",
            ),
        ]

    def save(self, *args, **kwargs):
        """
        rounded_at always follows pressed_at (clock_rounding).
        ---
        rounded_at sigue siempre a pressed_at (clock_rounding).
        """
        from hr_calendar.clock_rounding import round_pressed_at

        # S141: una pulsación ya guardada solo admite sus campos
        # derivados.
        if not self._state.adding:
            update_fields = kwargs.get("update_fields")
            if update_fields is None or (
                    set(update_fields) - CLOCK_EVENT_DERIVED_FIELDS):
                raise ImmutableClockRecord(
                    "Los fichajes no se modifican; se corrigen con "
                    "ClockCorrection."
                )
            return super().save(*args, **kwargs)
        if self.pressed_at is not None:
            self.rounded_at = round_pressed_at(self.pressed_at, self.kind)
            update_fields = kwargs.get("update_fields")
            if update_fields is not None and "pressed_at" in update_fields:
                kwargs["update_fields"] = set(update_fields) | {"rounded_at"}
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ImmutableClockRecord(
            "Los fichajes no se borran; se anulan con ClockCorrection."
        )

    def __str__(self) -> str:
        return (
            f"{self.company_user} — {self.get_kind_display()} "
            f"{self.pressed_at:%d/%m/%Y %H:%M}"
        )

    @property
    def delay_seconds(self) -> int:
        """
        Seconds between the press and its arrival at the server.
        ---
        Segundos entre la pulsación y su llegada al servidor.
        """
        return round((self.received_at - self.pressed_at).total_seconds())


class ClockReminder(models.Model):
    """
    A WhatsApp reminder sent because a clock press is missing (H24,
    S141): the IN a quarter of an hour after the scheduled start, or
    the OUT a quarter of an hour after the scheduled end. At most one
    per user, day and kind -- the row is what stops it being sent
    twice, and the proof that it was sent.

    ---

    Recordatorio por WhatsApp de un fichaje que falta (H24, S141): la
    entrada un cuarto de hora después de la hora de entrada del
    horario, o la salida un cuarto de hora después de la de salida.
    Como mucho uno por usuario, día y tipo: la fila es lo que impide
    mandarlo dos veces y la prueba de que se mandó.
    """

    class Kind(models.TextChoices):
        IN = "IN", "Entrada"
        OUT = "OUT", "Salida"

    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="clock_reminders",
        verbose_name="Empresa",
    )
    company_user = models.ForeignKey(
        CompanyUser,
        on_delete=models.CASCADE,
        related_name="clock_reminders",
        verbose_name="Trabajador",
    )
    day = models.DateField(verbose_name="Día")
    kind = models.CharField(
        max_length=3,
        choices=Kind.choices,
        verbose_name="Fichaje que falta",
    )
    scheduled_time = models.TimeField(
        verbose_name="Hora del horario",
        help_text="Hora de entrada o de salida del horario del "
                  "trabajador ese día.",
    )
    phone = models.CharField(max_length=20, verbose_name="Móvil")
    message_sid = models.CharField(
        max_length=64, blank=True,
        verbose_name="Mensaje de Twilio",
    )
    sent_as_text = models.BooleanField(
        default=False,
        verbose_name="Enviado como texto",
        help_text="Dentro de la ventana de 24 horas sale como texto "
                  "libre; fuera, con la plantilla.",
    )
    sent_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Enviado",
    )
    # S143: which of the worker's reminders it is, as minutes from the
    # scheduled time ("-5", "0", "3", "30", "60", "120"... for every
    # hour). Empty: one of before S143 (one per day and kind).
    # Cuál de los avisos del trabajador es, en minutos respecto de la
    # hora del horario. Vacío: uno de antes de S143.
    slot = models.CharField(
        max_length=8,
        blank=True,
        default="",
        verbose_name="Aviso",
        help_text="Minutos respecto de la hora del horario (negativo, "
                  "antes).",
    )

    class Meta:
        verbose_name = "Recordatorio de fichaje"
        verbose_name_plural = "Recordatorios de fichaje"
        ordering = ["-sent_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["company_user", "day", "kind", "slot"],
                name="clockreminder_unique_user_day_kind_slot",
            ),
        ]

    def __str__(self) -> str:
        return (
            f"{self.company_user} — {self.get_kind_display()} "
            f"{self.day:%d/%m/%Y}"
        )


class ClockCorrectionQuerySet(models.QuerySet):
    """
    Corrections: append-only (H24, S141).
    ---
    Correcciones: solo se añaden; ni `update()` ni `delete()`.
    """

    def update(self, **kwargs):
        raise ImmutableClockRecord(
            "Las correcciones de fichaje no se modifican."
        )

    def delete(self):
        raise ImmutableClockRecord(
            "Las correcciones de fichaje no se borran."
        )


class ClockCorrection(models.Model):
    """
    A supervisor's correction of one press (H24, S141). The press is
    never touched: a change creates a new press (sent_by CORRECTION)
    that replaces it, and a cancellation leaves it out of the reports.
    Who, when, the old and new values and the mandatory reason stay
    here for good -- the history of every modification of the record
    (draft royal decree on digital time records: every correction
    leaves a trace and the original is kept). Corrections are not
    edited or deleted either; a correction of a correction corrects
    the new press.

    ---

    Corrección de una pulsación por un supervisor (H24, S141). La
    pulsación no se toca nunca: un cambio crea una pulsación nueva
    (sent_by CORRECTION) que la sustituye, y una anulación la deja
    fuera de los informes. Quién, cuándo, el valor anterior, el nuevo y
    el motivo (obligatorio) quedan aquí para siempre: el historial de
    cada modificación del registro (borrador del real decreto de
    registro digital: cada corrección deja rastro y se conserva el
    original). Tampoco se editan ni se borran; para corregir una
    corrección se corrige la pulsación nueva.
    """

    class Action(models.TextChoices):
        CHANGE = "CHANGE", "Cambio de hora o de tipo"
        CANCEL = "CANCEL", "Anulación"
        # S144 (Miguel Ángel): partir un tramo fichado entero como
        # presencia o desplazamiento; también una pulsación que falta.
        ADD = "ADD", "Fichaje añadido"

    # S144: vacío en un fichaje añadido (no corrige ninguna pulsación;
    # la nueva va en `replacement`).
    event = models.OneToOneField(
        ClockEvent,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="correction",
        verbose_name="Fichaje corregido",
    )
    action = models.CharField(
        max_length=6,
        choices=Action.choices,
        verbose_name="Corrección",
    )
    replacement = models.OneToOneField(
        ClockEvent,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="replaces",
        verbose_name="Fichaje que lo sustituye",
    )
    old_kind = models.CharField(
        max_length=3,
        choices=ClockEvent.Kind.choices,
        blank=True,
        verbose_name="Tipo anterior",
    )
    old_pressed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Hora anterior",
    )
    new_kind = models.CharField(
        max_length=3,
        choices=ClockEvent.Kind.choices,
        blank=True,
        verbose_name="Tipo nuevo",
    )
    new_pressed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Hora nueva",
    )
    old_clock_type = models.ForeignKey(
        "hr_calendar.ClockType",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
        verbose_name="Tipo de fichaje anterior",
    )
    new_clock_type = models.ForeignKey(
        "hr_calendar.ClockType",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
        verbose_name="Tipo de fichaje nuevo",
    )

    class Source(models.TextChoices):
        # S149 (Miguel Ángel): "en la corrección del fichaje, corregido
        # por IA con el usuario que corresponda"; la manual, por quien la
        # hizo.
        MANUAL = "MANUAL", "Manual"
        AI = "AI", "IA"
        # S153: corregido con el parte de trabajo del trabajador
        # (hr_calendar/parte_clock.py).
        PARTE = "PARTE", "Parte de trabajo"

    reason = models.TextField(verbose_name="Motivo")
    source = models.CharField(
        max_length=10,
        choices=Source.choices,
        default=Source.MANUAL,
        verbose_name="Origen",
        help_text="IA: la hizo el cotejo de albaranes, lanzado por "
                  "«Corregido por».",
    )
    corrected_by = models.ForeignKey(
        CompanyUser,
        on_delete=models.PROTECT,
        related_name="clock_corrections",
        verbose_name="Corregido por",
    )
    corrected_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Fecha de la corrección",
    )
    user_agent = models.CharField(
        max_length=200,
        blank=True,
        verbose_name="Navegador",
    )

    objects = ClockCorrectionQuerySet.as_manager()

    class Meta:
        verbose_name = "Corrección de fichaje"
        verbose_name_plural = "Correcciones de fichaje"
        ordering = ["-corrected_at"]
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(reason=""),
                name="clockcorrection_reason_required",
            ),
        ]

    def save(self, *args, **kwargs):
        """
        Only new corrections are saved.
        ---
        Solo se guardan correcciones nuevas: no se modifican.
        """
        if not self._state.adding:
            raise ImmutableClockRecord(
                "Las correcciones de fichaje no se modifican."
            )
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ImmutableClockRecord(
            "Las correcciones de fichaje no se borran."
        )

    def __str__(self) -> str:
        return (
            f"{self.get_action_display()} de "
            f"{self.event or self.replacement} por {self.corrected_by}"
        )


class ClockSettings(models.Model):
    """
    Company-wide clock-in settings, managed from the panel (H24, S141).

    ---

    Ajustes de fichaje de la empresa, desde el panel (H24, S141).
    `reminders_enabled` es el permiso general para enviar los
    recordatorios de fichaje olvidado: apagado hasta que un supervisor
    lo enciende en la pestaña Fichajes. Cuándo salen los avisos lo
    elige cada trabajador (S143, `WorkerClockSetting.in_reminders` y
    `out_reminders`).
    """

    company = models.OneToOneField(
        Company,
        on_delete=models.CASCADE,
        related_name="clock_settings",
        verbose_name="Empresa",
    )
    reminders_enabled = models.BooleanField(
        default=False,
        verbose_name="Enviar recordatorios de fichaje",
    )
    # S143 (Miguel Ángel): "un tope de horas configurable. Lo que pase
    # de ese tope de horas lo vamos a pasar a horas acumuladas [...] 7
    # horas por mes".
    DEFAULT_OVERTIME_CAP_MINUTES = 7 * 60
    overtime_monthly_cap_minutes = models.PositiveIntegerField(
        default=DEFAULT_OVERTIME_CAP_MINUTES,
        verbose_name="Tope de horas extra al mes (minutos)",
        help_text="Lo trabajado de más en un mes por encima de este tope "
                  "pasa a horas acumuladas.",
    )
    updated_by = models.ForeignKey(
        CompanyUser,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        verbose_name="Cambiado por",
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Último cambio",
    )

    class Meta:
        verbose_name = "Ajustes de fichaje"
        verbose_name_plural = "Ajustes de fichaje"

    def __str__(self) -> str:
        return f"Ajustes de fichaje de {self.company}"


class SectionClockSetting(models.Model):
    """
    Whether a section clocks in with the platform (H24, S141).

    ---

    Si una sección ficha con la plataforma (H24, S141). Miguel Ángel:
    hay secciones que fichan por otro sistema (Plataformas, por
    Prologic) y se quitan o se ponen según lo que digan los jefes. Sin
    fila, la sección ficha.
    """

    section = models.OneToOneField(
        "ivr_config.Section",
        on_delete=models.CASCADE,
        related_name="clock_setting",
        verbose_name="Sección",
    )
    clocks = models.BooleanField(
        default=True,
        verbose_name="Ficha con la plataforma",
    )
    # S141: Grúas y Asistencia fichan por tipos (trabajo efectivo,
    # desplazamiento, presencia, varios), como en Sesame. S144: sin
    # "Fichaje normal".
    uses_types = models.BooleanField(
        default=False,
        verbose_name="Ficha por tipos",
    )
    updated_by = models.ForeignKey(
        CompanyUser,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        verbose_name="Cambiado por",
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Último cambio",
    )

    class Meta:
        verbose_name = "Fichaje de una sección"
        verbose_name_plural = "Fichaje de las secciones"

    def __str__(self) -> str:
        return f"{self.section} — {'ficha' if self.clocks else 'no ficha'}"


class WorkerClockSetting(models.Model):
    """
    Clock-in settings of one worker (H24, S141).

    ---

    Ajustes de fichaje de un trabajador (H24, S141). `clocks`: está
    obligado a fichar (Miguel Ángel: un jefe de sección, o quien sea,
    puede no estar obligado). `reminders`: recibe los recordatorios de
    fichaje olvidado; el permiso se da a cada trabajador desde la
    pestaña Fichajes. Sin fila: ficha y no recibe recordatorios.
    `in_reminders` y `out_reminders` (S143): qué avisos quiere él, con
    casillas en su página de fichaje (Miguel Ángel: "que puedan
    configurar sus avisos a la entrada y a la salida"), como claves de
    IN_REMINDER_CHOICES y OUT_REMINDER_CHOICES separadas por comas.
    Vacío (None): los de por defecto; "" (cadena vacía): ninguno. Cada
    aviso sale solo si todavía no ha fichado.
    """

    # S143: entrada 5 minutos antes, a la hora y 3 minutos después;
    # salida a la hora, 3 minutos, media hora, una hora y cada hora
    # ("muchas veces tienen que echar horas extras").
    HOURLY = "h"
    IN_REMINDER_CHOICES = [
        ("-5", "5 minutos antes"),
        ("0", "A la hora en punto"),
        ("3", "3 minutos después"),
    ]
    OUT_REMINDER_CHOICES = [
        ("0", "A la hora en punto"),
        ("3", "3 minutos después"),
        ("30", "Media hora después"),
        ("60", "Una hora después"),
        (HOURLY, "Cada hora"),
    ]
    DEFAULT_IN_REMINDERS = ("-5",)
    DEFAULT_OUT_REMINDERS = ("0",)

    person = models.OneToOneField(
        PersonIdentity,
        on_delete=models.CASCADE,
        related_name="clock_setting",
        verbose_name="Trabajador",
    )
    clocks = models.BooleanField(
        default=True,
        verbose_name="Obligado a fichar",
    )
    # S143 (Miguel Ángel): "no quiero que el alta de los fichajes les
    # cuente desde hoy, sino desde mañana": desde qué día ficha. Antes,
    # ni avisos, ni fichajes desde el móvil. Vacío: desde ya.
    clocks_from = models.DateField(
        null=True,
        blank=True,
        verbose_name="Ficha desde",
        help_text="Primer día en que ficha y recibe avisos. Vacío: desde "
                  "ya.",
    )
    reminders = models.BooleanField(
        default=False,
        verbose_name="Recibe recordatorios",
    )
    in_reminders = models.CharField(
        max_length=40,
        null=True,
        blank=True,
        verbose_name="Avisos de entrada",
        help_text="Claves separadas por comas (-5, 0, 3). Vacío: los de "
                  "por defecto.",
    )
    out_reminders = models.CharField(
        max_length=40,
        null=True,
        blank=True,
        verbose_name="Avisos de salida",
        help_text="Claves separadas por comas (0, 3, 30, 60, h). Vacío: "
                  "los de por defecto.",
    )
    # S143 (Miguel Ángel): quien tiene horario abierto (fichaje por
    # tipos, en una obra durante una temporada) se pone su propio horario
    # para los avisos: tramos de entrada y salida (las pausas de comida o
    # cena quedan entre tramos), los días de la semana y hasta cuándo.
    # Solo sirve para los avisos; no se compara con la jornada.
    MAX_OWN_SHIFTS = 4
    own_schedule = models.CharField(
        max_length=60,
        blank=True,
        default="",
        verbose_name="Horario propio para los avisos",
        help_text="Tramos HH:MM-HH:MM separados por comas. Vacío: ninguno.",
    )
    own_schedule_days = models.CharField(
        max_length=20,
        blank=True,
        default="0,1,2,3,4",
        verbose_name="Días del horario propio",
        help_text="Días de la semana (0 lunes ... 6 domingo) separados por "
                  "comas.",
    )
    own_schedule_until = models.DateField(
        null=True,
        blank=True,
        verbose_name="Horario propio hasta",
        help_text="Último día en que vale. Vacío: sin fecha de fin.",
    )
    # S148 (Miguel Ángel): "poder cambiar el tipo que ficha [...] un solo
    # trabajador, hacerle una exclusión de lo que es su sección o su
    # grupo, para que él tenga un tipo de fichaje aparte". Vacío: como
    # su sección; "normal": botón único aunque su sección fiche por
    # tipos; "types": por tipos aunque su sección no.
    CLOCK_MODE_SECTION = ""
    CLOCK_MODE_NORMAL = "normal"
    CLOCK_MODE_TYPES = "types"
    CLOCK_MODE_CHOICES = [
        (CLOCK_MODE_SECTION, "Como su sección"),
        (CLOCK_MODE_NORMAL, "Fichaje normal"),
        (CLOCK_MODE_TYPES, "Por tipos"),
    ]
    clock_mode = models.CharField(
        max_length=10,
        blank=True,
        default=CLOCK_MODE_SECTION,
        choices=CLOCK_MODE_CHOICES,
        verbose_name="Tipo de fichaje",
        help_text="Vacío: como su sección.",
    )
    # S141 (Miguel Ángel): el horario va en el trabajador, no en su
    # usuario del panel: chóferes, gruistas y administrativos no tienen
    # (ni tendrán de momento) acceso al panel, solo al fichaje. Se pone
    # desde la pestaña Horarios de Documentación.
    workday_schedule = models.ForeignKey(
        "ivr_config.WorkdaySchedule",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="worker_settings",
        verbose_name="Horario de jornada",
    )
    updated_by = models.ForeignKey(
        CompanyUser,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        verbose_name="Cambiado por",
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Último cambio",
    )

    class Meta:
        verbose_name = "Fichaje de un trabajador"
        verbose_name_plural = "Fichaje de los trabajadores"

    def __str__(self) -> str:
        return f"{self.person} — {'ficha' if self.clocks else 'no ficha'}"

    @staticmethod
    def _keys(value, default):
        if value is None:
            return list(default)
        return [key for key in value.split(",") if key]

    def in_reminder_keys(self):
        """
        The IN reminders chosen (or the default ones).
        ---
        Los avisos de entrada elegidos (o los de por defecto).
        """
        return self._keys(self.in_reminders, self.DEFAULT_IN_REMINDERS)

    def out_reminder_keys(self):
        """
        The OUT reminders chosen (or the default ones).
        ---
        Los avisos de salida elegidos (o los de por defecto).
        """
        return self._keys(self.out_reminders, self.DEFAULT_OUT_REMINDERS)

    def own_shifts(self):
        """
        The worker's own shifts as [(start time, end time)], in order.
        ---
        Los tramos del horario propio (S143) como [(entrada, salida)],
        en orden; los que no se entienden se saltan.
        """
        shifts = []
        for item in (self.own_schedule or "").split(","):
            try:
                start, end = item.split("-")
                shifts.append((
                    datetime.datetime.strptime(start.strip(), "%H:%M").time(),
                    datetime.datetime.strptime(end.strip(), "%H:%M").time(),
                ))
            except ValueError:
                continue
        return shifts

    def own_days(self):
        return [int(d) for d in (self.own_schedule_days or "").split(",")
                if d.strip().isdigit()]

    def own_shifts_on(self, day):
        """
        The own shifts that apply on `day` ([] if none).
        ---
        Los tramos del horario propio que valen el día `day`: si ese día
        de la semana está marcado y no ha pasado la fecha de fin.
        """
        if self.own_schedule_until and day > self.own_schedule_until:
            return []
        if day.weekday() not in self.own_days():
            return []
        return self.own_shifts()


class ClockType(models.Model):
    """
    A clock-in type (H24, S141), as in Sesame: the worker of a section
    that clocks by types picks one when clocking in or when changing
    what they are doing. Managed from the Fichajes tab (create, rename,
    reorder, deactivate). `counts_as_work`: whether its time counts as
    working hours (Miguel Ángel: presencia and desplazamiento are shown
    apart and do not count).

    ---

    Tipo de fichaje (H24, S141), como en Sesame: quien ficha por tipos
    elige uno al entrar o al cambiar de lo que está haciendo. Se
    gestiona desde la pestaña Fichajes (crear, renombrar, ordenar,
    desactivar). `counts_as_work`: si su tiempo cuenta como horas de
    jornada (Miguel Ángel: presencia y desplazamiento se ven aparte y no
    cuentan). `is_default`: el que se usa cuando una entrada llega sin
    tipo ("Trabajo efectivo" desde S144: el "Fichaje normal" se retiró
    porque llevaba a confusión).
    """

    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="clock_types",
        verbose_name="Empresa",
    )
    name = models.CharField(max_length=60, verbose_name="Nombre")
    icon = models.CharField(
        max_length=40,
        default="bi-box-arrow-in-right",
        verbose_name="Icono",
        help_text="Nombre de un icono de Bootstrap Icons (bi-...).",
    )
    counts_as_work = models.BooleanField(
        default=True,
        verbose_name="Cuenta como jornada",
    )
    is_default = models.BooleanField(
        default=False,
        verbose_name="Tipo por defecto",
    )
    # S144: qué tipo es el desplazamiento (puede ser con vehículo propio
    # y cuenta kilómetros) y cuál la pausa para comer (comida o cena,
    # dietas).
    ROLE_TRAVEL = "travel"
    ROLE_MEAL = "meal"
    # S143 (convenio, art. 20 b y d): presencia (esperas, averías...) y
    # fuerza mayor no son trabajo efectivo para la jornada ni para las
    # horas extra, y se compensan con descanso, una hora por hora: su
    # tiempo va a la bolsa.
    ROLE_PRESENCE = "presence"
    ROLE_FORCE = "force"
    BAG_ROLES = (ROLE_PRESENCE, ROLE_FORCE)
    ROLE_CHOICES = [
        ("", "Normal"),
        (ROLE_TRAVEL, "Desplazamiento"),
        (ROLE_MEAL, "Pausa para comer"),
        (ROLE_PRESENCE, "Presencia (a la bolsa)"),
        (ROLE_FORCE, "Fuerza mayor (a la bolsa)"),
    ]
    role = models.CharField(
        max_length=10, blank=True, default="", choices=ROLE_CHOICES,
        verbose_name="Función",
    )
    is_active = models.BooleanField(default=True, verbose_name="Activo")
    order = models.PositiveSmallIntegerField(default=0, verbose_name="Orden")
    updated_by = models.ForeignKey(
        CompanyUser,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        verbose_name="Cambiado por",
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Último cambio",
    )

    class Meta:
        verbose_name = "Tipo de fichaje"
        verbose_name_plural = "Tipos de fichaje"
        ordering = ["order", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "name"],
                name="clocktype_unique_company_name",
            ),
        ]

    def __str__(self) -> str:
        return self.name


class OwnVehicleTrip(models.Model):
    """
    Kilometres of one travel stretch in the worker's own vehicle (S144).

    ---

    Kilómetros de un tramo de desplazamiento con el vehículo propio
    (H24, S144, Miguel Ángel: "que puedan indicar cuando el
    desplazamiento es propio, que cuente los kilómetros de forma
    automática"). Se calculan por carretera (Google Routes) entre el GPS
    de la pulsación que abre el tramo y el de la que lo cierra; si falta
    un GPS o falla la consulta, queda sin kilómetros y con el motivo. El
    supervisor los puede corregir (`source=manual`). Las pulsaciones no
    se tocan: son inmutables.
    """

    SOURCE_ROUTES = "routes"
    SOURCE_MANUAL = "manual"
    SOURCE_CHOICES = [
        (SOURCE_ROUTES, "Por carretera"),
        (SOURCE_MANUAL, "Corregido a mano"),
    ]

    start_event = models.OneToOneField(
        ClockEvent, on_delete=models.CASCADE,
        related_name="own_vehicle_trip", verbose_name="Inicio del tramo",
    )
    end_event = models.ForeignKey(
        ClockEvent, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="+", verbose_name="Fin del tramo",
    )
    km = models.DecimalField(
        max_digits=7, decimal_places=1, null=True, blank=True,
        verbose_name="Kilómetros",
    )
    source = models.CharField(
        max_length=10, choices=SOURCE_CHOICES, default=SOURCE_ROUTES,
        verbose_name="Origen",
    )
    error = models.CharField(
        max_length=200, blank=True, default="",
        verbose_name="Por qué no hay kilómetros",
    )
    corrected_by = models.ForeignKey(
        CompanyUser, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="+", verbose_name="Corregido por",
    )
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Cambio")

    class Meta:
        verbose_name = "Desplazamiento con vehículo propio"
        verbose_name_plural = "Desplazamientos con vehículo propio"

    def __str__(self) -> str:
        return "%s km (%s)" % (self.km, self.start_event_id)


class ClockDayReview(models.Model):
    """
    A supervisor has seen a worker's clock-in day (S143).

    ---

    Día de fichajes de un trabajador visado por un supervisor (H24,
    S143, Miguel Ángel: "que tenga una casilla que marque visado y
    cuando estén visadas pasen a color amarillo"). Un día con alguna
    corrección cuenta como visado aunque no tenga fila.
    """

    company_user = models.ForeignKey(
        CompanyUser, on_delete=models.CASCADE,
        related_name="clock_day_reviews", verbose_name="Trabajador",
    )
    day = models.DateField(verbose_name="Día")
    reviewed_by = models.ForeignKey(
        CompanyUser, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="+", verbose_name="Visado por",
    )
    reviewed_at = models.DateTimeField(
        auto_now_add=True, verbose_name="Visado",
    )

    class Meta:
        verbose_name = "Día de fichajes visado"
        verbose_name_plural = "Días de fichajes visados"
        constraints = [
            models.UniqueConstraint(
                fields=("company_user", "day"),
                name="clockdayreview_unique_user_day",
            ),
        ]

    def __str__(self) -> str:
        return "%s %s" % (self.company_user_id, self.day)


class OvertimeAdjustment(models.Model):
    """
    A manual movement of a worker's overtime bag (S144).

    ---

    Movimiento a mano de la bolsa de horas extras de un trabajador (H24,
    S144): horas pagadas o compensadas con descanso (en negativo) o
    añadidas, con su motivo. La bolsa suma cada día lo trabajado por
    encima del horario (los días de menos no restan, Miguel Ángel) más
    estos movimientos.
    """

    company_user = models.ForeignKey(
        CompanyUser, on_delete=models.CASCADE,
        related_name="overtime_adjustments", verbose_name="Trabajador",
    )
    date = models.DateField(verbose_name="Fecha")
    minutes = models.IntegerField(
        verbose_name="Minutos",
        help_text="Negativo: horas pagadas o compensadas.",
    )
    reason = models.CharField(max_length=200, verbose_name="Motivo")
    # S143: las horas que se descuentan por unos días libres dados en
    # Vacaciones; se borra con el ajuste de vacaciones.
    vacation_adjustment = models.OneToOneField(
        "hr_calendar.VacationBalanceAdjustment", null=True, blank=True,
        on_delete=models.CASCADE, related_name="overtime_adjustment",
        verbose_name="Días libres en vacaciones",
    )
    created_by = models.ForeignKey(
        CompanyUser, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="+", verbose_name="Apuntado por",
    )
    created_at = models.DateTimeField(
        auto_now_add=True, verbose_name="Apuntado",
    )

    class Meta:
        verbose_name = "Movimiento de la bolsa de horas"
        verbose_name_plural = "Movimientos de la bolsa de horas"
        ordering = ["-date", "-pk"]

    def __str__(self) -> str:
        return "%+d min %s" % (self.minutes, self.date)


class WorkerRequest(models.Model):
    """
    A request a worker makes from "Mis solicitudes" (H24, S147).

    Vacation, personal-matters days and medical appointments become a
    real VacationPeriod or AbsencePeriod only when a supervisor approves
    them; document requests are answered by delivering a file; claims by
    a written answer. The worker sees every status and answer.
    ---
    Una petición que hace el trabajador desde "Mis solicitudes" (H24,
    S147, Miguel Ángel: "solicitan sus vacaciones, sus días de asuntos
    propios y los días que quieren ir al médico [...] también pueden
    solicitar los documentos que la empresa esté obligada a
    facilitarles"). Vacaciones, asuntos propios y médico solo se
    convierten en un VacationPeriod o AbsencePeriod de verdad cuando un
    supervisor los aprueba; un documento se contesta entregando el
    archivo; una reclamación, con una respuesta escrita. El trabajador ve
    el estado y la respuesta de todas.
    """

    class Kind(models.TextChoices):
        VACATION = "VACATION", "Vacaciones"
        PERSONAL = "PERSONAL", "Asuntos propios"
        MEDICAL = "MEDICAL", "Médico"
        DOCUMENT = "DOCUMENT", "Documento"
        CLAIM = "CLAIM", "Reclamación o consulta"

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pendiente"
        APPROVED = "APPROVED", "Aprobada"
        DENIED = "DENIED", "Denegada"
        DELIVERED = "DELIVERED", "Entregada"
        ANSWERED = "ANSWERED", "Respondida"
        CANCELLED = "CANCELLED", "Anulada"

    class ProofStatus(models.TextChoices):
        NONE = "NONE", "Sin justificante"
        RECEIVED = "RECEIVED", "Recibido"
        VALID = "VALID", "Validado"
        REJECTED = "REJECTED", "No válido"

    company = models.ForeignKey(
        Company, on_delete=models.CASCADE,
        related_name="worker_requests", verbose_name="Empresa",
    )
    person = models.ForeignKey(
        PersonIdentity, on_delete=models.CASCADE,
        related_name="worker_requests", verbose_name="Trabajador",
    )
    kind = models.CharField(
        max_length=10, choices=Kind.choices, verbose_name="Tipo",
    )
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.PENDING,
        verbose_name="Estado",
    )
    date_start = models.DateField(
        null=True, blank=True, verbose_name="Desde",
    )
    date_end = models.DateField(
        null=True, blank=True, verbose_name="Hasta",
    )
    time_from = models.TimeField(
        null=True, blank=True, verbose_name="Hora desde",
        help_text="Solo médico, si no es el día entero.",
    )
    time_to = models.TimeField(
        null=True, blank=True, verbose_name="Hora hasta",
    )
    document_code = models.CharField(
        max_length=20, blank=True, verbose_name="Documento pedido",
        help_text="Clave de hr_calendar.worker_requests.DOCUMENTS.",
    )
    period = models.CharField(
        max_length=120, blank=True, verbose_name="Periodo o detalle",
        help_text="Mes, año o lo que identifique el documento pedido.",
    )
    note = models.TextField(
        blank=True, verbose_name="Nota del trabajador",
    )
    response = models.TextField(
        blank=True, verbose_name="Respuesta de la empresa",
    )
    created_by = models.ForeignKey(
        CompanyUser, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="+", verbose_name="Pedida por",
    )
    created_at = models.DateTimeField(
        auto_now_add=True, verbose_name="Pedida",
    )
    resolved_by = models.ForeignKey(
        CompanyUser, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="+", verbose_name="Resuelta por",
    )
    resolved_at = models.DateTimeField(
        null=True, blank=True, verbose_name="Resuelta",
    )
    vacation_period = models.ForeignKey(
        VacationPeriod, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="+", verbose_name="Vacaciones creadas",
    )
    absence_period = models.ForeignKey(
        AbsencePeriod, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="+", verbose_name="Ausencia creada",
    )
    proof_status = models.CharField(
        max_length=10, choices=ProofStatus.choices,
        default=ProofStatus.NONE, verbose_name="Justificante",
    )
    proof_reviewed_by = models.ForeignKey(
        CompanyUser, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="+", verbose_name="Justificante revisado por",
    )
    proof_reviewed_at = models.DateTimeField(
        null=True, blank=True, verbose_name="Justificante revisado",
    )

    class Meta:
        verbose_name = "Solicitud de un trabajador"
        verbose_name_plural = "Solicitudes de los trabajadores"
        ordering = ["-created_at", "-pk"]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(date_start__isnull=True)
                    | models.Q(date_end__isnull=True)
                    | models.Q(date_end__gte=models.F("date_start"))
                ),
                name="workerrequest_date_end_gte_date_start",
            ),
        ]

    def __str__(self) -> str:
        return "%s — %s (%s)" % (
            self.person, self.get_kind_display(), self.get_status_display(),
        )


class WorkerRequestFile(models.Model):
    """
    A file of a WorkerRequest: the worker's proof or the delivery.
    ---
    Un archivo de una solicitud (S147): el justificante que sube el
    trabajador o el documento que le entrega la empresa. El archivo vive
    en la carpeta del trabajador como cualquier otro documento suyo
    (DocumentIndexEntry); aquí solo se enlaza.
    """

    class Role(models.TextChoices):
        PROOF = "PROOF", "Justificante"
        DELIVERY = "DELIVERY", "Entrega"

    request = models.ForeignKey(
        WorkerRequest, on_delete=models.CASCADE, related_name="files",
        verbose_name="Solicitud",
    )
    role = models.CharField(
        max_length=10, choices=Role.choices, verbose_name="Papel",
    )
    entry = models.ForeignKey(
        DocumentIndexEntry, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="+",
        verbose_name="Documento",
    )
    name = models.CharField(max_length=255, verbose_name="Nombre")
    uploaded_by = models.ForeignKey(
        CompanyUser, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="+", verbose_name="Subido por",
    )
    uploaded_at = models.DateTimeField(
        auto_now_add=True, verbose_name="Subido",
    )

    class Meta:
        verbose_name = "Archivo de una solicitud"
        verbose_name_plural = "Archivos de las solicitudes"
        ordering = ["uploaded_at", "pk"]

    def __str__(self) -> str:
        return "%s (%s)" % (self.name, self.get_role_display())


class PayslipBatch(models.Model):
    """
    A payslip delivery: the PDFs of a folder, read, reviewed and sent.
    ---
    Una entrega de nóminas (S149, Miguel Ángel): el supervisor elige una
    carpeta, se suben todos sus PDF, el sistema los lee en segundo plano
    (a quién es cada nómina y de qué mes), avisa por WhatsApp a quien la
    inició, este da el visto bueno al listado y se envían: cada nómina
    se archiva cifrada en la ficha de su trabajador (confidencial) y le
    llega por WhatsApp.
    """

    class Status(models.TextChoices):
        UPLOADING = "UPLOADING", "Subiendo"
        READING = "READING", "Leyendo"
        READY = "READY", "Para el visto bueno"
        SENDING = "SENDING", "Enviando"
        SENT = "SENT", "Enviada"
        CANCELLED = "CANCELLED", "Anulada"

    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name="+",
        verbose_name="Empresa",
    )
    created_by = models.ForeignKey(
        CompanyUser, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="+", verbose_name="Iniciada por",
    )
    created_at = models.DateTimeField(
        auto_now_add=True, verbose_name="Iniciada",
    )
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.UPLOADING,
        verbose_name="Estado",
    )
    folder_name = models.CharField(
        max_length=255, blank=True, default="", verbose_name="Carpeta",
    )
    read_at = models.DateTimeField(
        null=True, blank=True, verbose_name="Leída",
    )
    notify_whatsapp = models.BooleanField(
        default=True,
        verbose_name="Avisar por WhatsApp al terminar la lectura",
        help_text="S149: lo marca o no quien inicia la entrega.",
    )
    notified_at = models.DateTimeField(
        null=True, blank=True, verbose_name="Aviso de lectura enviado",
    )
    notify_error = models.CharField(
        max_length=255, blank=True, default="",
        verbose_name="Error del aviso de lectura",
    )
    approved_by = models.ForeignKey(
        CompanyUser, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="+", verbose_name="Visto bueno de",
    )
    approved_at = models.DateTimeField(
        null=True, blank=True, verbose_name="Visto bueno",
    )
    finished_at = models.DateTimeField(
        null=True, blank=True, verbose_name="Envío terminado",
    )

    class Meta:
        verbose_name = "Entrega de nóminas"
        verbose_name_plural = "Entregas de nóminas"
        ordering = ["-created_at", "-pk"]

    def __str__(self) -> str:
        return "Entrega de nóminas #%s (%s)" % (
            self.pk, self.get_status_display())


class PayslipBatchShare(models.Model):
    """
    A supervisor who may see, download and send one payslip batch.
    ---
    S153. A quién da acceso a una entrega quien la sube. Miguel Ángel:
    "Jerónimo en cada carga de carpeta será el que dé el acceso a esa
    carga para el supervisor correspondiente [...] la persona con el
    permiso suficiente recibirá una notificación [...] y podrá enviar
    las nóminas a los trabajadores [...] y de poder descargarlas". Con
    acceso: ve la entrega, sus nóminas (también ya archivadas en la
    ficha del trabajador, aunque sean confidenciales), las descarga y
    da el visto bueno y envía. Aviso por WhatsApp al tenerla lista.
    """

    batch = models.ForeignKey(
        PayslipBatch, on_delete=models.CASCADE, related_name="shares",
        verbose_name="Entrega",
    )
    company_user = models.ForeignKey(
        CompanyUser, on_delete=models.CASCADE,
        related_name="payslip_batch_shares", verbose_name="Usuario",
    )
    granted_by = models.ForeignKey(
        CompanyUser, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="+", verbose_name="Compartida por",
    )
    granted_at = models.DateTimeField(
        auto_now_add=True, verbose_name="Compartida",
    )
    notified_at = models.DateTimeField(
        null=True, blank=True, verbose_name="Avisado",
    )
    notify_error = models.CharField(
        max_length=255, blank=True, default="",
        verbose_name="Error del aviso",
    )

    class Meta:
        verbose_name = "Acceso a una entrega de nóminas"
        verbose_name_plural = "Accesos a las entregas de nóminas"
        ordering = ["pk"]
        constraints = [
            models.UniqueConstraint(
                fields=("batch", "company_user"),
                name="unique_payslip_share_per_user",
            ),
        ]

    def __str__(self) -> str:
        return "%s -> %s" % (self.batch, self.company_user)


class PayslipItem(models.Model):
    """
    One payslip of a delivery: pages of an uploaded PDF and its worker.
    ---
    Una nómina de una entrega (S149): las páginas de uno de los PDF
    subidos (un PDF puede traer las de varios trabajadores), el
    trabajador al que es (leído del DNI/NIE o puesto a mano), el mes y
    cómo ha ido el envío. El PDF subido se guarda cifrado hasta el
    envío, fuera de la carpeta del trabajador.
    """

    class Status(models.TextChoices):
        PENDING = "PENDING", "Por leer"
        READY = "READY", "Lista"
        UNMATCHED = "UNMATCHED", "Sin trabajador"
        EXCLUDED = "EXCLUDED", "Fuera de la entrega"
        SENT = "SENT", "Enviada"
        FILED = "FILED", "Archivada, sin WhatsApp"
        ERROR = "ERROR", "Error"

    class MatchSource(models.TextChoices):
        NONE = "", "—"
        DNI = "DNI", "DNI/NIE"
        MANUAL = "MANUAL", "A mano"

    batch = models.ForeignKey(
        PayslipBatch, on_delete=models.CASCADE, related_name="items",
        verbose_name="Entrega",
    )
    original_name = models.CharField(
        max_length=255, verbose_name="Archivo",
    )
    staged_path = models.CharField(
        max_length=255, blank=True, default="",
        # S153: la copia ya no se borra al enviar (no son efímeras).
        verbose_name="Copia cifrada del PDF subido",
    )
    page_from = models.PositiveSmallIntegerField(
        default=1, verbose_name="Desde la página",
    )
    page_to = models.PositiveSmallIntegerField(
        default=0, verbose_name="Hasta la página",
    )
    person = models.ForeignKey(
        PersonIdentity, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="+", verbose_name="Trabajador",
    )
    dni_found = models.CharField(
        max_length=12, blank=True, default="",
        verbose_name="DNI/NIE leído",
    )
    match_source = models.CharField(
        max_length=6, blank=True, default="", choices=MatchSource.choices,
        verbose_name="Asignada por",
    )
    period_start = models.DateField(
        null=True, blank=True, verbose_name="Periodo desde",
    )
    period_end = models.DateField(
        null=True, blank=True, verbose_name="Periodo hasta",
    )
    period_label = models.CharField(
        max_length=60, blank=True, default="", verbose_name="Mes",
    )
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.PENDING,
        verbose_name="Estado",
    )
    note = models.CharField(
        max_length=255, blank=True, default="", verbose_name="Nota",
    )
    entry = models.ForeignKey(
        DocumentIndexEntry, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="+",
        verbose_name="Documento archivado",
    )
    phone = models.CharField(
        max_length=32, blank=True, default="", verbose_name="Móvil",
    )
    message_sid = models.CharField(
        max_length=64, blank=True, default="", verbose_name="Mensaje",
    )
    sent_at = models.DateTimeField(
        null=True, blank=True, verbose_name="Enviada",
    )
    media_token = models.CharField(
        max_length=64, blank=True, default="", db_index=True,
        verbose_name="Enlace temporal para WhatsApp",
    )
    media_expires = models.DateTimeField(
        null=True, blank=True, verbose_name="El enlace caduca",
    )

    class Meta:
        verbose_name = "Nómina de una entrega"
        verbose_name_plural = "Nóminas de las entregas"
        ordering = ["pk"]

    def __str__(self) -> str:
        return "%s (págs. %s-%s)" % (self.original_name, self.page_from,
                                     self.page_to)


class AlbaranBatch(models.Model):
    """
    A folder of a worker's production delivery notes (S149).

    ---

    Carpeta de albaranes de producción de un trabajador (H24, S149,
    Miguel Ángel: "desde la ficha de fichajes de un trabajador, un botón
    para cargar una carpeta [...] los vamos a ir comparando con los
    fichajes"). Gemini lee cada albarán; con los de cada día se compara
    la jornada y se corrige por IA lo que pase de la tolerancia.
    """

    class Status(models.TextChoices):
        UPLOADING = "UPLOADING", "Subiendo"
        READING = "READING", "Leyendo"
        READY = "READY", "Comparada"
        CANCELLED = "CANCELLED", "Anulada"

    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name="albaran_batches",
        verbose_name="Empresa",
    )
    # S149 (Miguel Ángel, 16/11: "pasarlo a la lista de fichajes para
    # poder subir los albaranes de varias personas"): sin trabajador, la
    # carga es de varios y cada albarán va al suyo por el nombre leído.
    person = models.ForeignKey(
        "document_explorer.PersonIdentity", null=True, blank=True,
        on_delete=models.CASCADE,
        related_name="albaran_batches", verbose_name="Trabajador",
    )
    candidate_ids = models.JSONField(
        default=list, blank=True, verbose_name="Entre quiénes repartir",
        help_text="Carga de varios: los trabajadores marcados en la lista "
                  "(vacío: todos los que fichan por tipos).",
    )
    created_by = models.ForeignKey(
        CompanyUser, null=True, on_delete=models.SET_NULL,
        related_name="+", verbose_name="Cargada por",
    )
    created_at = models.DateTimeField(auto_now_add=True,
                                      verbose_name="Cargada")
    status = models.CharField(max_length=10, choices=Status.choices,
                              default=Status.UPLOADING,
                              verbose_name="Estado")
    folder_name = models.CharField(max_length=255, blank=True,
                                   verbose_name="Carpeta")
    read_at = models.DateTimeField(null=True, blank=True,
                                   verbose_name="Comparada")
    error = models.TextField(blank=True, verbose_name="Error")
    # S149 (16/11, carga cortada por un reinicio de Celery a mitad): la
    # lectura da señales de vida; si se para, se reanuda sola donde se
    # quedó (resume_stalled_albaran_batches), como mucho MAX_RESUMES
    # veces.
    heartbeat_at = models.DateTimeField(null=True, blank=True,
                                        verbose_name="Última señal")
    resumes = models.PositiveSmallIntegerField(default=0,
                                               verbose_name="Reanudaciones")

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Carga de albaranes"
        verbose_name_plural = "Cargas de albaranes"

    def __str__(self) -> str:
        return "Albaranes %s (%s)" % (self.pk, self.person_id)


class AlbaranSheet(models.Model):
    """
    One production delivery note read by Gemini (S149).

    ---

    Un albarán de producción leído por Gemini: un archivo de la carpeta
    puede traer varios (uno por fila). Las horas son las del parte de
    producción: salida de base, llegada al trabajo, salida del trabajo y
    llegada a base.
    """

    class Status(models.TextChoices):
        PENDING = "PENDING", "Por leer"
        READ = "READ", "Leído"
        UNREADABLE = "UNREADABLE", "Ilegible"
        ERROR = "ERROR", "Error"
        # S149: carga de varios en la que el nombre no es de nadie.
        NO_PERSON = "NO_PERSON", "Sin trabajador"

    batch = models.ForeignKey(AlbaranBatch, on_delete=models.CASCADE,
                              related_name="sheets", verbose_name="Carga")
    # S149: de quién es (en la carga de un trabajador, el suyo; en la de
    # varios, el del nombre leído).
    person = models.ForeignKey(
        "document_explorer.PersonIdentity", null=True, blank=True,
        on_delete=models.CASCADE, related_name="albaran_sheets",
        verbose_name="Trabajador",
    )
    original_name = models.CharField(max_length=255,
                                     verbose_name="Archivo")
    staged_path = models.CharField(max_length=255, blank=True,
                                   verbose_name="Copia guardada")
    position = models.PositiveSmallIntegerField(
        default=1, verbose_name="Albarán dentro del archivo")
    status = models.CharField(max_length=12, choices=Status.choices,
                              default=Status.PENDING,
                              verbose_name="Estado")
    number = models.CharField(max_length=40, blank=True,
                              verbose_name="Nº de albarán")
    day = models.DateField(null=True, blank=True, verbose_name="Fecha")
    operator_name = models.CharField(max_length=120, blank=True,
                                     verbose_name="Operario")
    machine = models.CharField(max_length=60, blank=True,
                               verbose_name="Máquina")
    observations = models.CharField(max_length=255, blank=True,
                                    verbose_name="Observaciones")
    base_out = models.TimeField(null=True, blank=True,
                                verbose_name="Salida de base")
    work_in = models.TimeField(null=True, blank=True,
                               verbose_name="Llegada al trabajo")
    work_out = models.TimeField(null=True, blank=True,
                                verbose_name="Salida del trabajo")
    base_in = models.TimeField(null=True, blank=True,
                               verbose_name="Llegada a base")
    name_mismatch = models.BooleanField(
        default=False, verbose_name="El nombre no es el del trabajador")
    raw = models.TextField(blank=True, verbose_name="Lectura de Gemini")
    # S153 (Miguel Ángel: "es necesario extraer los datos [...] una
    # copia digital exacta en base de datos"): todo lo que trae el
    # albarán, no solo las horas (hr_calendar/albaran_full.py), y dónde
    # está guardado en el cubo.
    full_data = models.JSONField(default=dict, blank=True,
                                 verbose_name="Datos completos")
    full_text = models.TextField(blank=True,
                                 verbose_name="Transcripción completa")
    full_read_at = models.DateTimeField(null=True, blank=True,
                                        verbose_name="Datos extraídos")
    bucket_blob = models.CharField(max_length=500, blank=True,
                                   verbose_name="Archivo en el cubo")
    note = models.CharField(max_length=255, blank=True,
                            verbose_name="Nota")

    class Meta:
        ordering = ["day", "base_out", "work_in", "pk"]
        verbose_name = "Albarán leído"
        verbose_name_plural = "Albaranes leídos"

    def __str__(self) -> str:
        return "%s %s" % (self.number or self.original_name, self.day)


class ClockDayAiCheck(models.Model):
    """
    A clock-in day compared by AI against its delivery notes (S149).

    ---

    Día de fichajes comparado por IA con sus albaranes (Miguel Ángel:
    "un previsado automático [...] se marca como comparado
    automáticamente por IA"). Queda quién lanzó la comparación, si hubo
    corrección por IA y qué se vio; el visado del supervisor sigue en
    ClockDayReview.
    """

    company_user = models.ForeignKey(
        CompanyUser, on_delete=models.CASCADE,
        related_name="clock_ai_checks", verbose_name="Trabajador",
    )
    day = models.DateField(verbose_name="Día")
    batch = models.ForeignKey(
        AlbaranBatch, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="day_checks", verbose_name="Carga de albaranes",
    )
    checked_by = models.ForeignKey(
        CompanyUser, null=True, on_delete=models.SET_NULL,
        related_name="+", verbose_name="Lanzado por",
    )
    checked_at = models.DateTimeField(auto_now=True,
                                      verbose_name="Comparado")
    corrected = models.BooleanField(default=False,
                                    verbose_name="Corregido por IA")
    albaranes = models.CharField(max_length=255, blank=True,
                                 verbose_name="Albaranes")
    summary = models.TextField(blank=True, verbose_name="Resultado")

    class Origin(models.TextChoices):
        # S153: el día también se compara con el parte de trabajo del
        # trabajador (hr_calendar/parte_clock.py).
        AI = "AI", "IA (albaranes)"
        PARTE = "PARTE", "Parte de trabajo"

    origin = models.CharField(max_length=10, choices=Origin.choices,
                              default=Origin.AI, verbose_name="Origen")

    class Meta:
        verbose_name = "Día comparado por IA"
        verbose_name_plural = "Días comparados por IA"
        constraints = [
            models.UniqueConstraint(
                fields=("company_user", "day"),
                name="clockdayaicheck_unique_user_day",
            ),
        ]

    def __str__(self) -> str:
        return "%s %s" % (self.company_user_id, self.day)
