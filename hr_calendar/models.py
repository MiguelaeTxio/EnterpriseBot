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
from django.db import models

from ivr_config.models import Company, CompanyUser


class VacationPeriod(models.Model):
    """
    A registered vacation period for a CompanyUser. Source of truth for
    the HR calendar's green days and for the automatic PERSONAL/
    VACATION task generated on the last working day before date_start.
    ---
    Un periodo de vacaciones registrado para un CompanyUser. Fuente de
    verdad de los días verdes del calendario de RRHH y de la tarea
    automática PERSONAL/VACACIONES generada en la última jornada
    laboral antes de date_start.
    """

    # ------------------------------------------------------------------
    # Relations / Relaciones
    # ------------------------------------------------------------------
    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="vacation_periods",
        verbose_name="Empresa",
        help_text="Empresa a la que pertenece este periodo, "
                  "denormalizada desde operator.company en el momento "
                  "de creación (mismo patrón que MachineDocument/"
                  "TaskPhoto).",
    )
    operator = models.ForeignKey(
        CompanyUser,
        on_delete=models.CASCADE,
        related_name="vacation_periods",
        verbose_name="Operario/chófer",
        help_text="CompanyUser al que pertenecen estas vacaciones. "
                  "Abierto a cualquier rol -- hoy en la práctica solo "
                  "WORKSHOP/DRIVER lo usan, sin restricción a nivel de "
                  "modelo (decisión explícita de Miguel Ángel, S018).",
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
                check=models.Q(date_end__gte=models.F("date_start")),
                name="vacationperiod_date_end_gte_date_start",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.operator} — {self.date_start:%d/%m/%Y} a {self.date_end:%d/%m/%Y}"

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
        """
        from django.db import transaction

        is_new = self._state.adding
        with transaction.atomic():
            super().save(*args, **kwargs)
            if is_new and self.generated_entry_line_id is None:
                from hr_calendar.services import generate_vacation_task
                generate_vacation_task(self)
