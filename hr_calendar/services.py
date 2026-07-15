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


def generate_vacation_task(vacation_period):
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
