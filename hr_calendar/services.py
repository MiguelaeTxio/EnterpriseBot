# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/hr_calendar/services.py
"""
Automatic generation of the PERSONAL/VACATION ghost task (Hito 24, paso 1
de la hoja de ruta de continuación del anexo V24).

Triggered from VacationPeriod.save() (see hr_calendar/models.py) the first
time a period is created. Creates a standalone, self-contained WorkOrder
(source=GENERATED, status=DONE) with a single WorkOrderEntryLine tagged
machine_asset=PERSONAL / fault_description=<label of AbsenceCategory
VACATION>, delta_hours=1, on the last working day before
VacationPeriod.date_start.

Deliberately does NOT reuse the "already_exists" collision guard from
panel/views_workorders.py::AdminHistoryView.post (action=generate_absence_parts,
WorkerAbsence flow) -- that guard assumes the whole day is absence and must
be skipped if another WorkOrder already covers it. Here the ghost task is a
1-hour marker that coexists with whatever real work the operator logged on
that same day (it is the last working day BEFORE vacation, not a vacation
day itself), so a dedicated WorkOrder is always created regardless of what
else exists for that operator/date.

Does NOT create a WorkdayGap record either -- that mechanism exists to let
Gate 4 block a WorkOrder from being promoted PENDING_GAPS -> DONE. This
WorkOrder is created directly with status=DONE (same precedent as the
WorkerAbsence/GENERATED flow above), so Gate 4 never runs against it and
there is nothing to resolve.

"Last working day before date_start" reuses budgets.services._is_holiday
(weekend + Base.labor_calendar, already synced via sync_base_calendars,
H16/H18) against the operator's CompanyUser.base (H24/S018). If the
operator has no base assigned, _is_holiday falls back to weekend-only
detection (documented behaviour of the function itself).

Exclusion of the ghost hour from aggregate hour totals is NOT handled
here -- it lives at the three call sites that sum WorkOrderEntryLine.
delta_hours (work_order_processor/services.py::generate_work_order_excel,
work_order_processor/services.py::build_export_from_template,
analytics/views.py cost-share denominator), all of which now exclude any
line referenced by VacationPeriod.generated_entry_line
(`.exclude(vacation_period__isnull=False)`, using the reverse accessor of
that FK -- see VacationPeriod.generated_entry_line's related_name in
hr_calendar/models.py). Same commit, see ENTERPRISEBOT_ATTACHED_MILESTONE_V24.md
sección 5, pregunta 5.

---

Generación automática de la tarea fantasma PERSONAL/VACACIONES (Hito 24,
paso 1 de la hoja de ruta de continuación del anexo V24).

Se dispara desde VacationPeriod.save() (ver hr_calendar/models.py) la
primera vez que se crea un periodo. Crea un WorkOrder autocontenido e
independiente (source=GENERATED, status=DONE) con una única
WorkOrderEntryLine etiquetada machine_asset=PERSONAL /
fault_description=<label de la AbsenceCategory VACATION>, delta_hours=1,
en la última jornada laboral antes de VacationPeriod.date_start.

Deliberadamente NO reutiliza la guarda de colisión "already_exists" de
panel/views_workorders.py::AdminHistoryView.post (action=generate_absence_parts,
flujo WorkerAbsence) -- esa guarda asume que el día completo es ausencia y
debe omitirse si ya existe otro WorkOrder que lo cubra. Aquí la tarea
fantasma es un marcador de 1 hora que coexiste con el trabajo real que el
operario haya registrado ese mismo día (es la última jornada laboral ANTES
de las vacaciones, no un día de vacaciones en sí), así que siempre se crea
un WorkOrder dedicado, sin importar qué más exista para ese operario/fecha.

Tampoco crea ningún registro WorkdayGap -- ese mecanismo existe para que
Gate 4 pueda bloquear el paso de un WorkOrder de PENDING_GAPS a DONE. Este
WorkOrder se crea directamente con status=DONE (mismo precedente que el
flujo WorkerAbsence/GENERATED de arriba), así que Gate 4 nunca se ejecuta
sobre él y no hay nada que resolver.

La "última jornada laboral antes de date_start" reutiliza
budgets.services._is_holiday (fin de semana + Base.labor_calendar, ya
sincronizado vía sync_base_calendars, H16/H18) contra el CompanyUser.base
del operario (H24/S018). Si el operario no tiene base asignada,
_is_holiday recurre a detección de solo fin de semana (comportamiento ya
documentado en la propia función).

La exclusión de la hora fantasma de los cómputos agregados de horas NO se
gestiona aquí -- vive en los tres puntos de llamada que suman
WorkOrderEntryLine.delta_hours (work_order_processor/services.py::
generate_work_order_excel, work_order_processor/services.py::
build_export_from_template, denominador de coste de analytics/views.py),
todos los cuales ahora excluyen cualquier línea referenciada por
VacationPeriod.generated_entry_line (`.exclude(vacation_period__isnull=False)`,
vía el accesor inverso de esa FK -- ver el related_name de
VacationPeriod.generated_entry_line en hr_calendar/models.py). Mismo
commit, ver ENTERPRISEBOT_ATTACHED_MILESTONE_V24.md sección 5, pregunta 5.
"""
import logging
from datetime import timedelta
from decimal import Decimal

from django.db import transaction

logger = logging.getLogger(__name__)

# Reserved AbsenceCategory.code for the vacation ghost task -- see
# work_order_processor/management/commands/seed_absence_categories.py.
# Código reservado de AbsenceCategory.code para la tarea fantasma de
# vacaciones -- ver work_order_processor/management/commands/seed_absence_categories.py.
VACATION_ABSENCE_CODE = "VACATION"


def _last_working_day_before(target_date, base):
    """
    Walks backwards from target_date, skipping weekends and holidays in
    base.labor_calendar (via budgets.services._is_holiday), and returns the
    first working day found. Bounded to 60 days back as a safety net
    against a malformed/empty labor_calendar that could otherwise loop
    indefinitely.
    ---
    Retrocede desde target_date, saltando fines de semana y festivos de
    base.labor_calendar (vía budgets.services._is_holiday), y devuelve el
    primer día laborable encontrado. Acotado a 60 días hacia atrás como
    salvaguarda ante un labor_calendar malformado/vacío que de otro modo
    podría bucear indefinidamente.
    """
    from budgets.services import _is_holiday

    cursor = target_date - timedelta(days=1)
    for _ in range(60):
        if not _is_holiday(cursor, base):
            return cursor
        cursor -= timedelta(days=1)

    logger.warning(
        "# [hr_calendar/services] _last_working_day_before agotó 60 días "
        "retrocediendo desde %r sin encontrar día laborable (labor_calendar "
        "posiblemente malformado). Devolviendo %r sin más comprobación.",
        target_date, cursor,
    )
    return cursor


def register_vacation_period_from_line(
    entry_line, vacation_end_date, operator, company, created_by,
):
    """
    Real-world flow (S019 correction to the S018 design): the operator
    themselves adds the PERSONAL/VACATION line on their own last working
    day, via the normal daily digital work order form (the pre-existing
    H7/H10 PERSONAL-absence mechanism, panel/views_operator.py::
    _parse_entry_lines_from_post + the WorkdayGap creation blocks in
    WorkOrderEntryConfirmView and WorkOrderEntryFormView), indicating the
    end date of their vacation in a dedicated field. That real, operator-
    entered line is what should exist -- generate_vacation_task() above
    (creating a whole new standalone WorkOrder) is the wrong direction for
    this flow and is now scoped to the panel CRUD only (hr_calendar/views.py),
    which Miguel Ángel keeps as a secondary/administrative path, not the
    primary one.

    Creates the VacationPeriod with generated_entry_line already pointing
    at the real, just-persisted line -- so VacationPeriod.save()'s own
    auto-generation (see hr_calendar/models.py) is a no-op here
    (generated_entry_line_id is already set at creation time, no new
    WorkOrder gets created).

    date_start is the day after entry_line.entry.work_date (the day after
    the operator's own last working day) -- date_start itself is never
    asked of the operator, only date_end (per Miguel Ángel: "el periodo
    vacacional lo crea el operario cuando añade en un día una tarea de
    vacaciones de una hora, donde indica el final de su periodo
    vacacional").

    Idempotent per (operator, date_start) rather than per exact line pk:
    the operator's own daily form (panel/views_operator.py::
    WorkOrderEntryFormView, action=save_blocks) deletes and recreates
    every WorkOrderEntryLine on each intermediate re-save while the
    operator is still filling out the form (WorkdayGap gets recreated
    too), so the "same" vacation task can arrive here pointing at a
    different line pk each time the operator saves again before finally
    closing the day's part. Matching on (operator, date_start) instead --
    the last working day never changes for the same vacation task --
    means a re-save updates the existing VacationPeriod in place
    (refreshing date_end and re-pointing generated_entry_line at the
    latest line) instead of creating a duplicate.
    ---
    Idempotente por (operario, date_start) en vez de por pk de línea
    exacta: el propio parte diario del operario (panel/views_operator.py::
    WorkOrderEntryFormView, action=save_blocks) borra y recrea cada
    WorkOrderEntryLine en cada reguardado intermedio mientras el operario
    sigue rellenando el formulario (el WorkdayGap también se recrea), así
    que la "misma" tarea de vacaciones puede llegar aquí apuntando a un pk
    de línea distinto cada vez que el operario vuelve a guardar antes de
    cerrar definitivamente el parte del día. Emparejar por (operario,
    date_start) en vez de eso -- la última jornada laboral nunca cambia
    para la misma tarea de vacaciones -- hace que un reguardado actualice
    el VacationPeriod existente en su sitio (refrescando date_end y
    reapuntando generated_entry_line a la línea más reciente) en vez de
    crear un duplicado.
    """
    from hr_calendar.models import VacationPeriod

    work_date = entry_line.entry.work_date
    date_start = work_date + timedelta(days=1)
    if vacation_end_date < date_start:
        raise ValueError(
            f"La fecha de fin de vacaciones ({vacation_end_date}) no puede "
            f"ser anterior al día siguiente a la última jornada laboral "
            f"({date_start})."
        )

    existing = VacationPeriod.objects.filter(
        operator=operator, company=company, date_start=date_start,
    ).first()
    if existing is not None:
        _update_fields = []
        if existing.date_end != vacation_end_date:
            existing.date_end = vacation_end_date
            _update_fields.append("date_end")
        if existing.generated_entry_line_id != entry_line.pk:
            existing.generated_entry_line = entry_line
            _update_fields.append("generated_entry_line")
        if _update_fields:
            existing.save(update_fields=_update_fields)
            logger.info(
                "# [hr_calendar/services] VacationPeriod actualizado tras "
                "reguardado del operario. vacation_period_pk=%r "
                "line_pk=%r campos=%r",
                existing.pk, entry_line.pk, _update_fields,
            )
        return existing

    period = VacationPeriod.objects.create(
        company=company,
        operator=operator,
        created_by=created_by,
        date_start=date_start,
        date_end=vacation_end_date,
        generated_entry_line=entry_line,
    )
    logger.info(
        "# [hr_calendar/services] VacationPeriod registrado desde tarea "
        "real del operario. line_pk=%r operator=%r date_start=%r "
        "date_end=%r vacation_period_pk=%r",
        entry_line.pk, operator.pk, date_start, vacation_end_date, period.pk,
    )
    return period


def compute_calendar_days(operator, company, date_from, date_to):
    """
    Returns a dict {date: {"color": ..., "label": ...}} for every calendar
    date in [date_from, date_to] (inclusive), following the day
    color-coding rules closed in S018
    (ENTERPRISEBOT_ATTACHED_MILESTONE_V24.md sección 3.2):

      green      — day covered by a VacationPeriod.
      blue       — real task that day (a WorkOrderEntryLine with
                   machine_asset set and machine_asset.code != PERSONAL)
                   AND no resolved WorkdayGap that same day — full day.
      light_blue — same as blue but WITH a resolved WorkdayGap that day
                   (partial PERSONAL absence, e.g. missing 2-3h) —
                   incomplete day.
      orange     — no real task that day, but a PERSONAL absence line
                   with an AbsenceCategory other than VACATION covers it
                   (or a legacy WorkerAbsence-generated line with no
                   machine_asset at all -- same underlying meaning, see
                   note below).
      yellow     — public holiday (Base.labor_calendar via
                   budgets.services._is_holiday, weekday only -- weekends
                   are excluded from "yellow" on purpose, see note below).
      red        — working day (weekday, not a holiday) with none of the
                   above -- unexplained gap.
      None       — weekend with nothing recorded (not part of the 6-color
                   spec; rendered neutral).

    Note on weekday vs weekend: budgets.services._is_holiday() returns
    True for BOTH weekends and Base.labor_calendar entries (it exists for
    a different purpose, the NYF budget surcharge). Section 3.2 defines
    "yellow" as specifically "festivo" (a named holiday) and "red" as
    specifically "día laborable ... sin explicar" -- a weekend is neither
    of those on its own. Since _is_holiday(d, base) is only True for a
    weekday when d is genuinely listed in the calendar (weekends already
    satisfy the weekend branch of that function regardless of the
    calendar), checking `d.weekday() < 5 and _is_holiday(d, base)`
    isolates real holidays without re-implementing the calendar lookup.

    Note on the legacy WorkerAbsence/GENERATED mechanism (H7,
    panel/views_workorders.py::AdminHistoryView.post,
    action=generate_absence_parts): those lines have machine_asset=None
    (no PERSONAL asset, no AbsenceCategory FK at all) rather than going
    through the PERSONAL+AbsenceCategory mechanism this anexo builds on.
    They represent the same real-world fact (operator absent that day) so
    they are folded into "orange" here too -- excluded from "real task"
    (machine_asset is null, not "a machine_asset whose code differs from
    PERSONAL") and detected as an absence day in their own right.

    Priority when several conditions could apply to the same date
    (documented here since the anexo lists the six colors but does not
    state an explicit priority order for edge-case overlaps): vacation
    (green) first, then real task (blue/light_blue), then non-vacation
    absence (orange), then holiday (yellow), then unexplained working day
    (red).
    ---
    Devuelve un dict {date: {"color": ..., "label": ...}} para cada fecha
    de calendario en [date_from, date_to] (ambas inclusive), siguiendo las
    reglas de color por día cerradas en S018
    (ENTERPRISEBOT_ATTACHED_MILESTONE_V24.md sección 3.2). Ver docstring
    en inglés arriba para el detalle completo de cada color y las notas
    sobre fin de semana vs festivo, el mecanismo legado WorkerAbsence, y
    la prioridad aplicada cuando varias condiciones podrían coincidir en
    la misma fecha (vacaciones primero, luego tarea real, luego ausencia
    no vacacional, luego festivo, luego laborable sin explicar).
    """
    from budgets.services import _is_holiday
    from hr_calendar.models import VacationPeriod
    from work_order_processor.management.commands.seed_personal_asset import (
        PERSONAL_ASSET_CODE,
    )
    from work_order_processor.models import WorkdayGap, WorkOrderEntryLine

    real_task_dates = set(
        WorkOrderEntryLine.objects.filter(
            entry__work_order__company=company,
            entry__work_order__uploaded_by=operator,
            entry__work_date__range=(date_from, date_to),
            machine_asset__isnull=False,
        ).exclude(
            machine_asset__code=PERSONAL_ASSET_CODE,
        ).values_list("entry__work_date", flat=True).distinct()
    )

    gap_resolved_dates = set(
        WorkdayGap.objects.filter(
            work_order__company=company,
            work_order__uploaded_by=operator,
            work_order__entries__work_date__range=(date_from, date_to),
            resolved=True,
            gap_type=WorkdayGap.GapType.GAP,
        ).values_list(
            "work_order__entries__work_date", flat=True,
        ).distinct()
    )

    absence_non_vacation_dates = set(
        WorkOrderEntryLine.objects.filter(
            entry__work_order__company=company,
            entry__work_order__uploaded_by=operator,
            entry__work_date__range=(date_from, date_to),
            machine_asset__code=PERSONAL_ASSET_CODE,
            absence_category__isnull=False,
        ).exclude(
            absence_category__code=VACATION_ABSENCE_CODE,
        ).values_list("entry__work_date", flat=True).distinct()
    )
    absence_non_vacation_dates |= set(
        WorkOrderEntryLine.objects.filter(
            entry__work_order__company=company,
            entry__work_order__uploaded_by=operator,
            entry__work_date__range=(date_from, date_to),
            machine_asset__isnull=True,
        ).values_list("entry__work_date", flat=True).distinct()
    )
    # No cuentan como "tarea real" -- ver nota del mecanismo legado arriba.
    absence_non_vacation_dates -= real_task_dates

    vacation_dates = set()
    for vp in VacationPeriod.objects.filter(
        company=company, operator=operator,
        date_start__lte=date_to, date_end__gte=date_from,
    ):
        cursor = max(vp.date_start, date_from)
        vp_end = min(vp.date_end, date_to)
        while cursor <= vp_end:
            vacation_dates.add(cursor)
            cursor += timedelta(days=1)

    base = operator.base
    result = {}
    cursor = date_from
    while cursor <= date_to:
        if cursor in vacation_dates:
            result[cursor] = {"color": "green", "label": "Vacaciones"}
        elif cursor in real_task_dates:
            if cursor in gap_resolved_dates:
                result[cursor] = {
                    "color": "light_blue", "label": "Jornada incompleta",
                }
            else:
                result[cursor] = {
                    "color": "blue", "label": "Jornada completa",
                }
        elif cursor in absence_non_vacation_dates:
            result[cursor] = {"color": "orange", "label": "Ausencia"}
        elif cursor.weekday() < 5 and _is_holiday(cursor, base):
            result[cursor] = {"color": "yellow", "label": "Festivo"}
        elif cursor.weekday() < 5:
            result[cursor] = {"color": "red", "label": "Sin explicar"}
        else:
            result[cursor] = {"color": None, "label": "Fin de semana"}
        cursor += timedelta(days=1)
    return result


def resolve_period_group_for_calendar(company, group_pk=None):
    """
    Resolves which WorkPeriodGroup the calendar should display, following
    ENTERPRISEBOT_ATTACHED_MILESTONE_V24.md sección 3.3 (cerrada en S018):
    the calendar groups by WorkPeriodGroup instead of a hardcoded "21 al
    20" cycle or a bare natural month.

      - group_pk given -> that exact group (scoped to company), for
        prev/next navigation between periods.
      - group_pk not given -> the most recent WorkPeriodGroup with
        is_closed=False (the active one); if none is open, falls back to
        the single most recent WorkPeriodGroup overall (all closed).
      - No WorkPeriodGroup exists at all for the company -> returns None;
        the caller falls back to the current natural month (documented
        default behaviour in the anexo).

    Also returns prev_group_pk/next_group_pk (by start_date ordering) so
    the view can render "<- mes anterior" / "mes siguiente ->" navigation
    without the template needing to know about WorkPeriodGroup ordering.
    ---
    Resuelve qué WorkPeriodGroup debe mostrar el calendario, siguiendo
    ENTERPRISEBOT_ATTACHED_MILESTONE_V24.md sección 3.3 (cerrada en
    S018): el calendario se agrupa por WorkPeriodGroup en vez de un ciclo
    "21 al 20" hardcodeado o un mes natural a secas.

      - Si se da group_pk -> ese grupo exacto (acotado a la empresa),
        para la navegación anterior/siguiente entre periodos.
      - Si no se da group_pk -> el WorkPeriodGroup más reciente con
        is_closed=False (el activo); si ninguno está abierto, cae al
        WorkPeriodGroup más reciente en general (todos liquidados).
      - Si no existe ningún WorkPeriodGroup para la empresa -> devuelve
        None; el llamante cae al mes natural actual (comportamiento por
        defecto documentado en el anexo).

    También devuelve prev_group_pk/next_group_pk (por orden de
    start_date) para que la vista pueda renderizar la navegación
    "<- mes anterior" / "mes siguiente ->" sin que la plantilla necesite
    conocer el orden de WorkPeriodGroup.
    """
    from ivr_config.models import WorkPeriodGroup

    groups = list(
        WorkPeriodGroup.objects.filter(company=company).order_by("start_date")
    )
    if not groups:
        return None

    if group_pk is not None:
        group = next((g for g in groups if g.pk == group_pk), None)
        if group is None:
            group = groups[-1]
    else:
        open_groups = [g for g in groups if not g.is_closed]
        group = open_groups[-1] if open_groups else groups[-1]

    idx = groups.index(group)
    prev_group_pk = groups[idx - 1].pk if idx > 0 else None
    next_group_pk = groups[idx + 1].pk if idx < len(groups) - 1 else None

    return {
        "group": group,
        "prev_group_pk": prev_group_pk,
        "next_group_pk": next_group_pk,
    }
    """
    Creates the PERSONAL/VACATION ghost task for a newly-created
    VacationPeriod and points vacation_period.generated_entry_line at it.

    Idempotent: if vacation_period.generated_entry_line_id is already set,
    returns the existing line without creating anything new.

    Raises MachineAsset.DoesNotExist / AbsenceCategory.DoesNotExist if the
    PERSONAL cost centre or the VACATION category are missing for the
    company -- deliberately not swallowed, this is a genuine setup gap
    (seed_personal_asset / seed_absence_categories not run for this
    company) that must surface, not fail silently.
    ---
    Crea la tarea fantasma PERSONAL/VACACIONES para un VacationPeriod recién
    creado y apunta vacation_period.generated_entry_line a ella.

    Idempotente: si vacation_period.generated_entry_line_id ya está fijado,
    devuelve la línea existente sin crear nada nuevo.

    Lanza MachineAsset.DoesNotExist / AbsenceCategory.DoesNotExist si falta
    el centro de gasto PERSONAL o la categoría VACATION para la empresa --
    deliberadamente no se capturan, es un hueco real de configuración
    (seed_personal_asset / seed_absence_categories no ejecutados para esta
    empresa) que debe salir a la luz, no fallar en silencio.
    """
    from fleet.models import MachineAsset
    from ivr_config.models import AbsenceCategory
    from work_order_processor.management.commands.seed_personal_asset import (
        PERSONAL_ASSET_CODE,
    )
    from work_order_processor.models import (
        WorkOrder,
        WorkOrderEntry,
        WorkOrderEntryLine,
    )

    if vacation_period.generated_entry_line_id:
        return vacation_period.generated_entry_line

    operator = vacation_period.operator
    company = vacation_period.company

    personal_asset = MachineAsset.objects.get(
        company=company, code=PERSONAL_ASSET_CODE,
    )
    vacation_category = AbsenceCategory.objects.get(
        company=company, code=VACATION_ABSENCE_CODE,
    )

    work_day = _last_working_day_before(
        vacation_period.date_start, operator.base,
    )

    worker_name = (
        operator.user.get_full_name() or operator.user.username
    ).upper()
    synthetic_name = (
        f"VACACIONES_{work_day.strftime('%Y%m%d')}_"
        f"{operator.user.username.upper()}.pdf"
    )

    with transaction.atomic():
        work_order = WorkOrder.objects.create(
            company=company,
            uploaded_by=operator,
            generated_by=vacation_period.created_by,
            source=WorkOrder.Source.GENERATED,
            status=WorkOrder.Status.DONE,
        )
        work_order.source_pdf.name = synthetic_name
        work_order.save()

        entry = WorkOrderEntry.objects.create(
            work_order=work_order,
            page_number=1,
            worker_name=worker_name,
            work_date=work_day,
            uncertain_date=False,
            extraction_confidence=WorkOrderEntry.Confidence.HIGH,
            raw_gemini_response=None,
        )

        line = WorkOrderEntryLine.objects.create(
            entry=entry,
            line_number=1,
            machine_asset=personal_asset,
            machine_raw=PERSONAL_ASSET_CODE,
            machine_norm=PERSONAL_ASSET_CODE,
            fault_description=vacation_category.label,
            repair_notes=(
                f"Vacaciones hasta el {vacation_period.date_end:%d/%m/%Y}."
            ),
            hc=None,
            hf=None,
            or_val="",
            delta_hours=Decimal("1"),
            flags=[],
        )

        vacation_period.generated_entry_line = line
        vacation_period.save(update_fields=["generated_entry_line"])

    logger.info(
        "# [hr_calendar/services] Tarea fantasma de vacaciones generada. "
        "vacation_period_pk=%r operator=%r work_day=%r work_order_pk=%r "
        "entry_line_pk=%r",
        vacation_period.pk, operator.pk, work_day, work_order.pk, line.pk,
    )
    return line
