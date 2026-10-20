# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/fleet/service_plan_service.py
"""
H30 (S131). Service plan of the cost centres by hours and kilometres:
state of each configured service and the notices it produces.

---

H30 (S131). Revisiones por horas y kilómetros de los centros de gasto.
Miguel Ángel: "tenemos avisos de documentación de maquinaria y de
personal, pero no de revisiones por kilometraje y por horas".

Decidido con él (hoja de ruta S131):
- Revisión por horas: cada centro de gasto pasa la suya a las 800 horas
  o a las 1200 (Miguel Ángel, S131: "unas máquinas la pasan a las 800
  horas y otras máquinas la pasan a las 1200"), nunca las dos. Además,
  "Revisión cada N km".
- Revisiones hechas y lecturas de horas/km se introducen a mano, con
  fecha. Una revisión anotada con horas cuenta para la revisión por
  horas, y con km para la de km. Sin una revisión anterior anotada no
  hay aviso de esa revisión.
- Aviso predefinido "revisión vencida": la última lectura pasa de la
  revisión anterior más el intervalo. Aviso configurable: antelación en
  horas y en km (`MachineServiceAlertSettings`); sin antelación fijada,
  solo se avisa de vencidas -- nunca valores inventados por el modelo.

Cálculo siempre en vivo, sin guardar nada: el aviso desaparece en
cuanto se anota la revisión que lo resuelve.
"""
from dataclasses import dataclass

UNIT_HOURS = "h"
UNIT_KM = "km"

STATE_NO_RECORD = "NO_RECORD"
STATE_NO_READING = "NO_READING"
STATE_OK = "OK"
STATE_UPCOMING = "UPCOMING"
STATE_OVERDUE = "OVERDUE"

SERVICE_REQUIREMENT_NAME = "Revisiones por horas y km"


@dataclass(frozen=True)
class Schedule:
    """
    One kind of service of the plan.

    ---

    Una revisión del plan: clave, etiqueta, unidad y campo de valor
    de revisiones y lecturas (horas o km).
    """

    key: str
    label: str
    unit: str
    value_field: str


KEY_HOURS = "HOURS"
KEY_CRANE = "CRANE"
KEY_KM = "KM"
SCHEDULE_KM = Schedule(KEY_KM, "Revisión por kilómetros", UNIT_KM, "km")


def hours_schedule(interval):
    """
    Hours schedule of a machine ("Revisión de 800 horas").

    ---

    La revisión por horas de una máquina, con su intervalo en la
    etiqueta.
    """
    return Schedule(
        KEY_HOURS, "Revisión de %d horas" % interval, UNIT_HOURS, "hours",
    )


def crane_schedule(interval):
    """
    Crane-engine hours schedule ("Revisión grúa de 800 horas").

    ---

    La revisión del motor de la grúa, con sus propias horas (horómetro
    de grúa) y su propio aviso -- Miguel Ángel, S131: "las grúas deben
    de tener su propio aviso". Mismo intervalo que la de la máquina.
    """
    return Schedule(
        KEY_CRANE, "Revisión grúa de %d horas" % interval, UNIT_HOURS,
        "crane_hours",
    )


@dataclass
class ScheduleStatus:
    """
    State of one configured service of one machine.

    ---

    Estado de una revisión configurada de un centro de gasto.
    `due_value` es la lectura a la que toca (revisión anterior +
    intervalo); `remaining` lo que falta (negativo si ya se pasó).
    """

    schedule: Schedule
    interval: int
    state: str
    last_record: object = None
    last_value: int = None
    due_value: int = None
    reading: object = None
    current_value: int = None
    remaining: int = None
    status_text: str = ""
    # S131: revisión anotada solo con fecha (sin el valor de esta
    # revisión): no avisa, pero se dice qué falta.
    undated_value_record: object = None


def format_number(value):
    """
    Integer with dot thousands separator ("1.650").

    ---

    Entero con punto de miles ("1.650"), como se escribe en España.
    """
    return "{:,}".format(value).replace(",", ".")


def enabled_schedules(machine):
    """
    (schedule, interval) pairs configured on the machine.

    ---

    Revisiones configuradas en el centro de gasto, con su intervalo.
    """
    pairs = []
    if machine.service_hours_interval:
        interval = machine.service_hours_interval
        pairs.append((hours_schedule(interval), interval))
        # S131: con horómetro de grúa, la grúa tiene su propia revisión.
        if machine.has_crane_hours:
            pairs.append((crane_schedule(interval), interval))
    if machine.service_every_km:
        pairs.append((SCHEDULE_KM, machine.service_every_km))
    return pairs


def _latest_with_value(rows, value_field, date_field):
    """
    Latest row (by date, then id) whose value field is set.

    ---

    La fila más reciente (fecha y desempate por id) con el valor
    informado.
    """
    candidates = [
        row for row in rows if getattr(row, value_field) is not None
    ]
    if not candidates:
        return None
    return max(
        candidates, key=lambda row: (getattr(row, date_field), row.pk),
    )


def _status_text(status):
    """
    Readable one-line state of a service.

    ---

    Estado legible de una revisión, en una línea (plantillas tontas).
    """
    unit = status.schedule.unit
    if status.state == STATE_NO_RECORD:
        if status.undated_value_record is not None:
            what = {
                "hours": "horas anotadas: no avisa hasta anotarlas",
                "crane_hours": (
                    "horas de grúa anotadas: no avisa hasta anotarlas"
                ),
            }.get(
                status.schedule.value_field,
                "kilómetros anotados: no avisa hasta anotarlos",
            )
            return "Revisión del %s sin %s." % (
                status.undated_value_record.service_date.strftime(
                    "%d/%m/%Y",
                ),
                what,
            )
        return "Sin revisión anotada: no avisa hasta anotar la primera."
    due = "%s %s" % (format_number(status.due_value), unit)
    if status.state == STATE_NO_READING:
        return "Toca a %s. Sin lectura posterior a la revisión." % due
    current = "%s %s" % (format_number(status.current_value), unit)
    if status.state == STATE_OVERDUE:
        return "Vencida: lectura %s, tocaba a %s (pasada %s %s)." % (
            current, due, format_number(-status.remaining), unit,
        )
    return "Lectura %s, toca a %s (faltan %s %s)." % (
        current, due, format_number(status.remaining), unit,
    )


def schedule_statuses(machine, records, readings, advance_of_unit=None):
    """
    State of every configured service of one machine.

    ---

    Estado de cada revisión configurada de un centro de gasto:
    - NO_RECORD: no hay revisión anotada de ese tipo (no avisa).
    - NO_READING: no hay lectura en o después de la revisión.
    - OVERDUE: la última lectura pasa de revisión + intervalo.
    - UPCOMING: faltan como mucho la antelación configurada (si hay).
    - OK: el resto.
    `advance_of_unit` es {UNIT_HOURS: n, UNIT_KM: n} (valores None =
    sin antelación).
    """
    advance_of_unit = advance_of_unit or {}
    statuses = []
    for schedule, interval in enabled_schedules(machine):
        record = _latest_with_value(
            records, schedule.value_field, "service_date",
        )
        status = ScheduleStatus(schedule, interval, STATE_NO_RECORD)
        if record is None and records:
            status.undated_value_record = max(
                records, key=lambda row: (row.service_date, row.pk),
            )
        if record is not None:
            status.last_record = record
            status.last_value = getattr(record, schedule.value_field)
            status.due_value = status.last_value + interval
            reading = _latest_with_value(
                readings, schedule.value_field, "reading_date",
            )
            if reading is None or reading.reading_date < record.service_date:
                status.state = STATE_NO_READING
            else:
                status.reading = reading
                status.current_value = getattr(reading, schedule.value_field)
                status.remaining = status.due_value - status.current_value
                advance = advance_of_unit.get(schedule.unit)
                if status.current_value > status.due_value:
                    status.state = STATE_OVERDUE
                elif advance and status.remaining <= advance:
                    status.state = STATE_UPCOMING
                else:
                    status.state = STATE_OK
        status.status_text = _status_text(status)
        statuses.append(status)
    return statuses


def advance_by_company():
    """
    {company_id: {unit: advance}} from MachineServiceAlertSettings.

    ---

    Antelación configurada de cada empresa, por unidad.
    """
    from fleet.models import MachineServiceAlertSettings

    return {
        settings.company_id: {
            UNIT_HOURS: settings.hours_advance,
            UNIT_KM: settings.km_advance,
        }
        for settings in MachineServiceAlertSettings.objects.all()
    }


def compute_service_notices():
    """
    Pending service notices (overdue and upcoming) of active machines.

    ---

    Avisos de revisión pendientes (vencidas y próximas) de los centros
    de gasto activos con alguna revisión configurada. Mismo
    `DocumentNotice` que los de documentación, para que pasen por los
    mismos destinatarios y ámbito de cada supervisor (S131).
    """
    from django.db.models import Q

    from document_explorer.document_notice_service import (
        DOMAIN_MACHINE, KIND_EXPIRED, KIND_UPCOMING, DocumentNotice,
        _subject_label,
    )
    from fleet.models import (
        MachineAsset, MachineMeterReading, MachineServiceRecord,
    )

    machines = list(
        MachineAsset.objects.filter(is_active=True).filter(
            Q(service_hours_interval__isnull=False)
            | Q(service_every_km__isnull=False, service_every_km__gt=0),
        ),
    )
    if not machines:
        return []
    ids = [machine.pk for machine in machines]
    records_of, readings_of = {}, {}
    for record in MachineServiceRecord.objects.filter(machine_id__in=ids):
        records_of.setdefault(record.machine_id, []).append(record)
    for reading in MachineMeterReading.objects.filter(machine_id__in=ids):
        readings_of.setdefault(reading.machine_id, []).append(reading)
    advances = advance_by_company()

    notices = []
    for machine in machines:
        for status in schedule_statuses(
            machine, records_of.get(machine.pk, []),
            readings_of.get(machine.pk, []),
            advances.get(machine.company_id),
        ):
            if status.state not in (STATE_OVERDUE, STATE_UPCOMING):
                continue
            notice = DocumentNotice(
                domain=DOMAIN_MACHINE,
                subject_id=machine.pk,
                subject_label=_subject_label(machine, DOMAIN_MACHINE),
                requirement_name=SERVICE_REQUIREMENT_NAME,
                document_label=status.schedule.label,
                document_type_id=None,
                kind=(
                    KIND_EXPIRED if status.state == STATE_OVERDUE
                    else KIND_UPCOMING
                ),
                subject_company=machine.company_code or "",
                subject_family=machine.family or "",
                entry_id=status.last_record.pk,
                is_service=True,
                service_due="%s%s" % (status.due_value, status.schedule.unit),
                service_text=status.status_text,
            )
            notices.append(notice)
    return notices
