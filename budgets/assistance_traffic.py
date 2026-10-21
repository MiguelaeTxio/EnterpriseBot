# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/budgets/assistance_traffic.py
"""
H37 (S133). Traffic panel of the assistance service: who and what is
free, the open albaranes, and the assignment rules.

---

H37 (S133). Panel de tráfico del servicio de asistencia (fase 2 del
dossier de Pepe, anexo V37 sección 4.4): qué conductores y máquinas
están libres, los albaranes abiertos con su color, y las reglas de
asignación:

- Al albarán va siempre un equipo (conductor + máquina,
  `AssistanceCrew`), nunca un conductor o una máquina sueltos
  (Miguel Ángel, S133). El equipo se forma soltando un conductor sobre
  una máquina; soltar el conductor de un equipo sobre otro equipo los
  intercambia de máquina. Solo se cambian equipos libres o que
  regresan, nunca uno asignado o en servicio.
- No se asigna un equipo ocupado (con otro albarán asignado o en
  servicio), ni con el conductor de vacaciones, de baja o ausente hoy,
  ni con la máquina en taller (con una avería abierta). Los que
  regresan a base sí se pueden asignar (S133).
- Solo se asigna o se cambia la asignación de un albarán que no se ha
  enviado todavía (pendiente o con el aviso fallido).
- No se envía sin conductor y máquina.
- Cada asignación, cada retirada y cada cambio de estado guardan hora
  y usuario (`WorkOrderAssistanceUnitEvent`).

Un albarán ocupa a su conductor y su máquina hasta que el conductor lo
cierra en base desde la app (fase 4 del dossier, S133): mientras tanto
el albarán firmado sale en verde ("regresando").
"""
import datetime

from django.db import transaction
from django.db.models import Max, Q
from django.utils import timezone

from budgets.assistance_resources import (
    assistance_drivers,
    assistance_machines,
)
from budgets.models import (
    AssistanceCrew,
    DriverPosition,
    WorkOrderAssistance,
    WorkOrderAssistanceUnit,
    WorkOrderAssistanceUnitEvent,
)

Unit = WorkOrderAssistanceUnit
Event = WorkOrderAssistanceUnitEvent

# Orders whose albaranes are on the board.
# Órdenes cuyos albaranes salen en el panel.
OPEN_ORDER_STATUSES = (
    WorkOrderAssistance.STATUS_PENDING,
    WorkOrderAssistance.STATUS_IN_PROGRESS,
)
# Albaranes whose driver and machine can still be changed and sent.
# Albaranes a los que aún se les puede cambiar la asignación y enviar.
ASSIGNABLE_STATUSES = (Unit.STATUS_PENDING, Unit.STATUS_NOTIFY_FAILED)
IN_SERVICE_STATUSES = (
    Unit.STATUS_NOTIFY_SENDING,
    Unit.STATUS_NOTIFIED,
    Unit.STATUS_DOWNLOADED,
    Unit.STATUS_IN_PROGRESS,
)
RETURNING_STATUSES = (
    Unit.STATUS_COMPLETED,
    Unit.STATUS_CLOSED_UNSIGNED,
    Unit.STATUS_SIGNED_RECEIVED,
)

# Colours of the dossier (4.4): red created or pending, yellow sent or
# in service, green finished and signed (returning), blue scheduled,
# orange incidence. Grey (closed in base) arrives with phase 4.
# Colores del dossier: rojo creado o pendiente, amarillo enviado o en
# servicio, verde terminado y firmado (regresando), azul programado,
# naranja incidencia. El gris (cerrado en base) llega con la fase 4.
COLOUR_RED = "red"
COLOUR_YELLOW = "yellow"
COLOUR_GREEN = "green"
COLOUR_BLUE = "blue"
COLOUR_ORANGE = "orange"

# Resource states shown on the cards.
# Estados de los recursos que se ven en las tarjetas.
STATE_FREE = "free"
STATE_ASSIGNED = "assigned"
STATE_IN_SERVICE = "in_service"
STATE_RETURNING = "returning"
STATE_UNAVAILABLE = "unavailable"
STATE_WORKSHOP = "workshop"
STATE_LABELS = {
    STATE_FREE: "Libre",
    STATE_ASSIGNED: "Asignado",
    STATE_IN_SERVICE: "En servicio",
    STATE_RETURNING: "Regresando",
    STATE_WORKSHOP: "En taller",
}
STATE_ORDER = {
    STATE_FREE: 0,
    STATE_ASSIGNED: 1,
    STATE_IN_SERVICE: 2,
    STATE_RETURNING: 3,
    STATE_UNAVAILABLE: 4,
    STATE_WORKSHOP: 4,
}

# Drivers and machines that can be dragged onto an albarán. Returning
# ones too (Miguel Ángel, S133: the driver who has just finished a
# service near another one goes straight to it instead of returning).
# Conductores y máquinas que se pueden arrastrar a un albarán. También
# los que regresan (Miguel Ángel, S133: el conductor que acaba de
# terminar un servicio cerca de otro va directamente a él).
ASSIGNABLE_RESOURCE_STATES = (STATE_FREE, STATE_RETURNING)
# Crews that can be split or change driver: never one with an albarán
# assigned or in service (it would no longer match the albarán sent).
# Equipos que se pueden separar o cambiar de conductor: nunca uno con
# un albarán asignado o en servicio (dejaría de cuadrar con el albarán).
CREW_LOCKED_STATES = (STATE_ASSIGNED, STATE_IN_SERVICE)
# Crews out of base, shown on the map at the driver's position.
# Equipos fuera de base, en el mapa en la posición del conductor.
CREW_OUT_STATES = (STATE_IN_SERVICE, STATE_RETURNING)
# Older positions are not used: the crew goes to "no position".
# Posiciones más antiguas no se usan: el equipo sale "sin posición".
POSITION_MAX_AGE = datetime.timedelta(hours=12)
RESOURCE_PRIORITY = {
    STATE_IN_SERVICE: 0,
    STATE_ASSIGNED: 1,
    STATE_RETURNING: 2,
}

SORT_AVAILABILITY = "availability"
SORT_NAME = "name"
SORT_OPTIONS = (
    (SORT_AVAILABILITY, "Disponibilidad"),
    (SORT_NAME, "Nombre"),
)


class TrafficError(Exception):
    """
    An assignment or a sending that the rules do not allow.

    ---

    Asignación o envío que las reglas no permiten. El mensaje es el que
    se muestra en el panel.
    """


def _today():
    """
    Today's date in the local time zone.

    ---

    Fecha de hoy en la zona horaria local.
    """
    return timezone.localdate()


def board_units(company):
    """
    Albaranes on the board: the units of the open orders not closed in
    base yet.

    ---

    Albaranes del panel: las unidades de las órdenes abiertas que aún
    no se han cerrado en base. Al cerrarse en base (fase 4 del dossier)
    salen del panel y su conductor y su máquina quedan libres.
    """
    return Unit.objects.filter(
        work_order__company=company,
        work_order__status__in=OPEN_ORDER_STATUSES,
    ).exclude(
        status=Unit.STATUS_CLOSED_BASE,
    ).select_related(
        "work_order__insurer", "operator__user", "machine_asset",
    )


def unit_resource_state(unit):
    """
    State that an albarán gives to its driver and machine.

    ---

    Estado que un albarán da a su conductor y su máquina.
    """
    if unit.status in IN_SERVICE_STATUSES:
        return STATE_IN_SERVICE
    if unit.status in RETURNING_STATUSES:
        return STATE_RETURNING
    return STATE_ASSIGNED


def unit_colour(unit, today=None):
    """
    Dossier colour of an albarán.

    ---

    Color del dossier para un albarán.
    """
    if unit.status == Unit.STATUS_NOTIFY_FAILED:
        return COLOUR_ORANGE
    if unit.status in IN_SERVICE_STATUSES:
        return COLOUR_YELLOW
    if unit.status in RETURNING_STATUSES:
        return COLOUR_GREEN
    if unit.work_order.service_date > (today or _today()):
        return COLOUR_BLUE
    return COLOUR_RED


def _absences_today(company, today):
    """
    Person pks away today, with the reason.

    ---

    Personas (pk de PersonIdentity) que no están disponibles hoy, con
    el motivo: baja médica, vacaciones o ausencia.
    """
    from hr_calendar.models import (
        AbsencePeriod,
        MedicalLeavePeriod,
        VacationPeriod,
    )

    away = {}
    for person_id, category in AbsencePeriod.objects.filter(
        company=company, date_start__lte=today, date_end__gte=today,
    ).values_list("person_id", "category__label"):
        away[person_id] = category or "Ausente"
    for person_id in VacationPeriod.objects.filter(
        company=company, date_start__lte=today, date_end__gte=today,
    ).values_list("person_id", flat=True):
        away[person_id] = "Vacaciones"
    for person_id in MedicalLeavePeriod.objects.filter(
        Q(date_end__isnull=True) | Q(date_end__gte=today),
        date_start__lte=today,
    ).values_list("person_id", flat=True):
        away[person_id] = "Baja"
    return away


def _machines_in_workshop(company):
    """
    Pks of the machines with an open breakdown ticket.

    ---

    Máquinas (pk) con un ticket de avería sin cerrar: en taller.
    """
    from chat.models import BreakdownTicket

    return set(BreakdownTicket.objects.filter(
        company=company,
        machine__isnull=False,
    ).exclude(
        status=BreakdownTicket.STATUS_CLOSED,
    ).values_list("machine_id", flat=True))


def _driver_name(company_user):
    """
    Full name of a panel user, or his username.

    ---

    Nombre completo del usuario del panel, o su usuario.
    """
    user = company_user.user
    return user.get_full_name() or user.username


def _machine_label(machine):
    """
    Label of a machine on the albarán: internal code and plate.

    ---

    Etiqueta de la máquina en el albarán: código interno y matrícula.
    """
    return " ".join(part for part in (machine.code, machine.plate) if part)


def _resources(company, units, today):
    """
    Drivers and machines with their state and current albarán.

    ---

    Conductores y máquinas con su estado y su albarán actual.
    """
    # With several albaranes, the most active one gives the state: in
    # service, then assigned, then returning (S133: a returning driver
    # can already have the next service).
    # Con varios albaranes manda el más activo: en servicio, después
    # asignado y por último regresando (S133: un conductor que regresa
    # puede tener ya el siguiente servicio).
    driver_units = {}
    machine_units = {}
    for unit in units:
        for key, table in (
            (unit.operator_id, driver_units),
            (unit.machine_asset_id, machine_units),
        ):
            if not key:
                continue
            current = table.get(key)
            if current is None or (
                RESOURCE_PRIORITY[unit_resource_state(unit)]
                < RESOURCE_PRIORITY[unit_resource_state(current)]
            ):
                table[key] = unit

    drivers = list(assistance_drivers(company).select_related(
        "person_identity", "base",
    ))
    away = _absences_today(company, today)
    for driver in drivers:
        driver.display_name = _driver_name(driver)
        driver.current_unit = driver_units.get(driver.pk)
        driver.away_reason = ""
        person = getattr(driver, "person_identity", None)
        if driver.current_unit:
            driver.state = unit_resource_state(driver.current_unit)
        elif person is not None and person.pk in away:
            driver.state = STATE_UNAVAILABLE
            driver.away_reason = away[person.pk]
        else:
            driver.state = STATE_FREE
        driver.state_label = (
            driver.away_reason or STATE_LABELS[driver.state]
        )
        driver.is_assignable = driver.state in ASSIGNABLE_RESOURCE_STATES

    machines = list(assistance_machines(company))
    workshop = _machines_in_workshop(company)
    for machine in machines:
        machine.label = _machine_label(machine)
        machine.current_unit = machine_units.get(machine.pk)
        if machine.current_unit:
            machine.state = unit_resource_state(machine.current_unit)
        elif machine.pk in workshop:
            machine.state = STATE_WORKSHOP
        else:
            machine.state = STATE_FREE
        machine.state_label = STATE_LABELS[machine.state]
        machine.is_assignable = machine.state in ASSIGNABLE_RESOURCE_STATES
    return drivers, machines


def _crew_state(driver, machine):
    """
    State and current albarán of a crew.

    ---

    Estado y albarán actual de un equipo: manda el albarán más activo
    de su conductor o de su máquina; sin albarán, el conductor ausente
    o la máquina en taller; si no, libre.
    """
    units = [
        unit for unit in (driver.current_unit, machine.current_unit)
        if unit is not None
    ]
    if units:
        unit = min(units, key=lambda u: RESOURCE_PRIORITY[
            unit_resource_state(u)
        ])
        state = unit_resource_state(unit)
        return state, unit, STATE_LABELS[state]
    if driver.state == STATE_UNAVAILABLE:
        return STATE_UNAVAILABLE, None, driver.state_label
    if machine.state == STATE_WORKSHOP:
        return STATE_WORKSHOP, None, machine.state_label
    return STATE_FREE, None, STATE_LABELS[STATE_FREE]


def _crews(company, drivers, machines):
    """
    Crews of the company with their state, and the loose resources.

    ---

    Equipos de la empresa con su estado. Marca en cada conductor y
    máquina su equipo (`crew`, None si va suelto). Un equipo cuyo
    conductor o máquina ya no es de asistencia no sale: los dos quedan
    sueltos en el panel.
    """
    by_driver = {driver.pk: driver for driver in drivers}
    by_machine = {machine.pk: machine for machine in machines}
    for resource in (*drivers, *machines):
        resource.crew = None
    crews = []
    for crew in AssistanceCrew.objects.filter(company=company):
        driver = by_driver.get(crew.driver_id)
        machine = by_machine.get(crew.machine_id)
        if driver is None or machine is None:
            continue
        crew.driver_card = driver
        crew.machine_card = machine
        crew.state, crew.current_unit, crew.state_label = _crew_state(
            driver, machine,
        )
        crew.is_assignable = crew.state in ASSIGNABLE_RESOURCE_STATES
        crew.is_movable = crew.state not in CREW_LOCKED_STATES
        driver.crew = crew
        machine.crew = crew
        crews.append(crew)
    return crews


def _current(company, today=None):
    """
    Drivers, machines and crews as they are now.

    ---

    Conductores, máquinas y equipos con los datos del momento, para
    comprobar las reglas de cada acción.
    """
    today = today or _today()
    units = list(board_units(company))
    drivers, machines = _resources(company, units, today)
    crews = _crews(company, drivers, machines)
    return drivers, machines, crews


def build_board(company, category="", sort=SORT_AVAILABILITY):
    """
    Everything the traffic board shows.

    ---

    Todo lo que muestra el panel de tráfico: equipos, conductores y
    máquinas sueltos (filtrados por categoría de máquina) y albaranes
    abiertos, más las órdenes abiertas que aún no tienen ningún
    albarán.
    """
    today = _today()
    units = list(board_units(company).order_by(
        "work_order__service_date", "work_order__work_order_number",
        "unit_number",
    ))
    drivers, machines = _resources(company, units, today)
    crews = _crews(company, drivers, machines)

    categories = sorted({m.type_name for m in machines if m.type_name})
    if category:
        machines = [m for m in machines if m.type_name == category]
        crews = [c for c in crews if c.machine_card.type_name == category]
    loose_drivers = [d for d in drivers if d.crew is None]
    loose_machines = [m for m in machines if m.crew is None]
    if sort == SORT_NAME:
        loose_drivers.sort(key=lambda d: d.display_name.lower())
        loose_machines.sort(key=lambda m: m.code)
        crews.sort(key=lambda c: c.machine_card.code)
    else:
        loose_drivers.sort(key=lambda d: (
            STATE_ORDER[d.state], d.display_name.lower(),
        ))
        loose_machines.sort(key=lambda m: (STATE_ORDER[m.state], m.code))
        crews.sort(key=lambda c: (
            STATE_ORDER[c.state], c.machine_card.code,
        ))

    for unit in units:
        unit.colour = unit_colour(unit, today)
        unit.is_assignable = unit.status in ASSIGNABLE_STATUSES
        unit.can_send = unit.is_assignable and bool(
            unit.operator_id and unit.machine_asset_id
        )
        unit.driver_name = (
            _driver_name(unit.operator) if unit.operator_id else ""
        )

    empty_orders = list(WorkOrderAssistance.objects.filter(
        company=company,
        status__in=OPEN_ORDER_STATUSES,
        units__isnull=True,
    ).select_related("insurer").order_by(
        "service_date", "work_order_number",
    ))
    for work_order in empty_orders:
        work_order.colour = (
            COLOUR_BLUE if work_order.service_date > today else COLOUR_RED
        )

    return {
        "crews": crews,
        "drivers": loose_drivers,
        "machines": loose_machines,
        "units": units,
        "empty_orders": empty_orders,
        "categories": categories,
        "category": category,
        "sort": sort,
        "sort_options": SORT_OPTIONS,
        "open_count": len(units) + len(empty_orders),
        "free_crews": sum(1 for c in crews if c.is_assignable),
    }


def _create_unit(work_order, by):
    """
    New empty albarán of an order (next unit number).

    ---

    Albarán nuevo, vacío, de una orden (siguiente número de unidad).
    Bloquea la fila de la orden para que dos altas a la vez no cojan
    el mismo número.
    """
    WorkOrderAssistance.objects.select_for_update().get(pk=work_order.pk)
    last = work_order.units.aggregate(last=Max("unit_number"))["last"]
    unit = Unit.objects.create(
        work_order=work_order,
        unit_number=(last or 0) + 1,
    )
    Event.objects.create(
        unit=unit,
        kind=Event.KIND_CREATED,
        to_status=unit.status,
        detail="Albarán %s creado." % unit.albaran_number,
        created_by=by,
    )
    return unit


def create_unit(work_order, by, operator=None, machine=None,
                machine_text=""):
    """
    Create an albarán with its driver and machine (detail page).

    ---

    Crea un albarán con su conductor y su máquina, desde el detalle de
    la orden. `machine` es la máquina de la flota si el texto coincide
    con una; si no, solo se guarda el texto.
    """
    with transaction.atomic():
        unit = _create_unit(work_order, by)
        if operator is not None:
            _set_driver(unit, operator, by)
        if machine is not None:
            _set_machine(unit, machine, by)
        elif machine_text:
            unit.machine = machine_text[:100]
            unit.save(update_fields=["machine", "updated_at"])
    return unit


def machine_from_text(company, text):
    """
    Assistance machine whose label is the text, or None.

    ---

    Máquina de asistencia cuya etiqueta ("X11 9237LGN") o código es el
    texto, o None.
    """
    text = (text or "").strip().lower()
    if not text:
        return None
    for machine in assistance_machines(company):
        if text in (_machine_label(machine).lower(), machine.code.lower()):
            return machine
    return None


def _set_driver(unit, driver, by):
    """
    Put the driver on the albarán and record it.

    ---

    Pone el conductor en el albarán y lo registra.
    """
    if unit.operator_id == driver.pk:
        return
    if unit.operator_id:
        Event.objects.create(
            unit=unit, kind=Event.KIND_UNASSIGN, created_by=by,
            detail="Conductor retirado: %s." % _driver_name(unit.operator),
        )
    unit.operator = driver
    unit.save(update_fields=["operator", "updated_at"])
    Event.objects.create(
        unit=unit, kind=Event.KIND_ASSIGN, created_by=by,
        detail="Conductor asignado: %s." % _driver_name(driver),
    )


def _set_machine(unit, machine, by):
    """
    Put the machine on the albarán and record it.

    ---

    Pone la máquina en el albarán y lo registra.
    """
    if unit.machine_asset_id == machine.pk:
        return
    if unit.machine_asset_id or unit.machine:
        Event.objects.create(
            unit=unit, kind=Event.KIND_UNASSIGN, created_by=by,
            detail="Máquina retirada: %s." % unit.machine,
        )
    unit.machine_asset = machine
    unit.machine = _machine_label(machine)[:100]
    unit.save(update_fields=["machine_asset", "machine", "updated_at"])
    Event.objects.create(
        unit=unit, kind=Event.KIND_ASSIGN, created_by=by,
        detail="Máquina asignada: %s." % unit.machine,
    )


def _locked_unit(company, unit_pk):
    """
    Albarán of the company, locked for the change.

    ---

    Albarán de la empresa, bloqueado para el cambio.
    """
    unit = Unit.objects.select_for_update().select_related(
        "work_order", "operator__user", "machine_asset",
    ).filter(pk=unit_pk, work_order__company=company).first()
    if unit is None:
        raise TrafficError("Ese albarán ya no existe.")
    if unit.work_order.status not in OPEN_ORDER_STATUSES:
        raise TrafficError("La orden de ese albarán ya está cerrada.")
    if unit.status not in ASSIGNABLE_STATUSES:
        raise TrafficError(
            "El albarán %s ya está %s: no se le puede cambiar la "
            "asignación." % (
                unit.albaran_number, unit.get_status_display().lower(),
            )
        )
    return unit


def _crew_name(crew):
    """
    How a crew is named in the panel messages.

    ---

    Cómo se nombra un equipo en los mensajes del panel.
    """
    return "%s con %s" % (_driver_name(crew.driver), crew.machine.code)


def _lock_crews(company):
    """
    Lock the crews of the company for a change.

    ---

    Bloquea los equipos de la empresa para un cambio: dos personas
    moviendo a la vez no dejan un conductor en dos máquinas.
    """
    list(AssistanceCrew.objects.select_for_update().filter(
        company=company,
    ).values_list("pk", flat=True))


def _check_movable(crew):
    """
    Refuse changing a crew with an albarán assigned or in service.

    ---

    No deja cambiar un equipo con un albarán asignado o en servicio.
    """
    if not crew.is_movable:
        raise TrafficError(
            "El equipo %s está %s con el albarán %s: no se puede cambiar "
            "hasta que termine." % (
                _crew_name(crew), crew.state_label.lower(),
                crew.current_unit.albaran_number,
            )
        )


def pair(company, by, driver_pk, machine_pk):
    """
    Put a driver on a machine.

    ---

    Pone un conductor en una máquina. Si los dos iban en equipos
    distintos, se intercambian: el otro conductor se queda con la
    máquina que deja este (caso de Miguel Ángel, S133: la grúa de 10 t
    y la de 35 t que se cruzan volviendo). Si solo uno iba en equipo,
    su compañero queda suelto. Devuelve el mensaje para el panel.
    """
    with transaction.atomic():
        _lock_crews(company)
        drivers, machines, crews = _current(company)
        driver = next((d for d in drivers if d.pk == driver_pk), None)
        machine = next((m for m in machines if m.pk == machine_pk), None)
        if driver is None:
            raise TrafficError("Ese conductor ya no es de asistencia.")
        if machine is None:
            raise TrafficError("Esa máquina ya no es de asistencia.")
        crew_a = driver.crew
        crew_b = machine.crew
        if crew_a is not None and crew_a is crew_b:
            raise TrafficError("%s ya lleva la %s." % (
                driver.display_name, machine.code,
            ))
        for crew in (crew_a, crew_b):
            if crew is not None:
                _check_movable(crew)
        if crew_a is None and not driver.is_assignable:
            raise TrafficError("%s no está disponible: %s." % (
                driver.display_name, driver.state_label.lower(),
            ))
        if crew_b is None and not machine.is_assignable:
            raise TrafficError("La %s no está disponible: %s." % (
                machine.code, machine.state_label.lower(),
            ))

        AssistanceCrew.objects.filter(
            Q(driver=driver) | Q(machine=machine),
        ).delete()
        AssistanceCrew.objects.create(
            company=company, driver=driver, machine=machine, created_by=by,
        )
        if crew_a is not None and crew_b is not None:
            partner = crew_b.driver_card
            AssistanceCrew.objects.create(
                company=company, driver=partner,
                machine=crew_a.machine_card, created_by=by,
            )
            return "Cambio: %s pasa a la %s y %s a la %s." % (
                driver.display_name, machine.code,
                partner.display_name, crew_a.machine_card.code,
            )
        message = "%s lleva la %s." % (driver.display_name, machine.code)
        if crew_a is not None:
            message += " La %s queda sin conductor." % crew_a.machine_card.code
        if crew_b is not None:
            message += " %s queda sin máquina." % (
                crew_b.driver_card.display_name
            )
        return message


def separate(company, by, crew_pk):
    """
    Split a crew: driver and machine stay loose.

    ---

    Separa un equipo: conductor y máquina quedan sueltos.
    """
    with transaction.atomic():
        _lock_crews(company)
        _drivers, _machines, crews = _current(company)
        crew = next((c for c in crews if c.pk == crew_pk), None)
        if crew is None:
            raise TrafficError("Ese equipo ya no existe.")
        _check_movable(crew)
        name = _crew_name(crew)
        crew.delete()
    return "Equipo %s separado." % name


def assign(company, by, crew_pk, unit_pk=None, order_pk=None):
    """
    Assign a crew to an albarán (or to a new albarán of an order).

    ---

    Asigna un equipo (conductor y máquina juntos) a un albarán. Si se
    suelta sobre una orden, va a su primer albarán aún sin enviar y sin
    nadie asignado, o a uno nuevo. Comprueba las reglas con los datos
    del momento, no con lo que pintaba el panel. Devuelve el albarán.
    """
    with transaction.atomic():
        _lock_crews(company)
        _drivers, _machines, crews = _current(company)
        crew = next((c for c in crews if c.pk == crew_pk), None)
        if crew is None:
            raise TrafficError("Ese equipo ya no existe.")
        if not crew.is_assignable:
            detail = crew.state_label.lower()
            if crew.current_unit is not None:
                detail += " con el albarán %s" % (
                    crew.current_unit.albaran_number
                )
            raise TrafficError("El equipo %s no está libre: %s." % (
                _crew_name(crew), detail,
            ))
        driver = crew.driver_card
        machine = crew.machine_card

        if unit_pk:
            unit = _locked_unit(company, unit_pk)
        else:
            work_order = WorkOrderAssistance.objects.filter(
                pk=order_pk, company=company,
                status__in=OPEN_ORDER_STATUSES,
            ).first()
            if work_order is None:
                raise TrafficError("Esa orden ya no está abierta.")
            unit = work_order.units.select_for_update().filter(
                status__in=ASSIGNABLE_STATUSES,
                operator__isnull=True,
                machine_asset__isnull=True,
            ).order_by("unit_number").first()
            if unit is None:
                unit = _create_unit(work_order, by)

        # Returning (signed, back to base) does not block: the crew can
        # go straight to the next service.
        # Regresando no bloquea: el equipo puede ir directamente al
        # siguiente servicio.
        busy = board_units(company).filter(
            Q(operator=driver) | Q(machine_asset=machine),
        ).exclude(pk=unit.pk).exclude(
            status__in=RETURNING_STATUSES,
        ).first()
        if busy is not None:
            raise TrafficError("El equipo %s ya está en el albarán %s." % (
                _crew_name(crew), busy.albaran_number,
            ))
        _set_driver(unit, driver, by)
        _set_machine(unit, machine, by)
    return unit


def unassign(company, by, unit_pk):
    """
    Take the crew off an albarán not sent yet.

    ---

    Quita el equipo (conductor y máquina) de un albarán aún sin enviar.
    """
    with transaction.atomic():
        unit = _locked_unit(company, unit_pk)
        fields = []
        if unit.operator_id:
            Event.objects.create(
                unit=unit, kind=Event.KIND_UNASSIGN, created_by=by,
                detail="Conductor retirado: %s."
                % _driver_name(unit.operator),
            )
            unit.operator = None
            fields.append("operator")
        if unit.machine_asset_id or unit.machine:
            Event.objects.create(
                unit=unit, kind=Event.KIND_UNASSIGN, created_by=by,
                detail="Máquina retirada: %s." % unit.machine,
            )
            unit.machine_asset = None
            unit.machine = ""
            fields += ["machine_asset", "machine"]
        if fields:
            unit.save(update_fields=fields + ["updated_at"])
    return unit


def send(company, by, unit_pk, whatsapp_sender):
    """
    Send the albarán to its driver by WhatsApp.

    ---

    Envía el albarán a su conductor por WhatsApp (mismo aviso que el
    detalle de la orden, `send_operator_albaran_notification`). Sin
    conductor y máquina no se envía.
    """
    from whatsapp.services import send_operator_albaran_notification

    with transaction.atomic():
        unit = _locked_unit(company, unit_pk)
        if not unit.operator_id:
            raise TrafficError(
                "El albarán %s no tiene conductor." % unit.albaran_number
            )
        if not unit.machine_asset_id:
            raise TrafficError(
                "El albarán %s no tiene máquina." % unit.albaran_number
            )
    if not whatsapp_sender:
        raise TrafficError(
            "No se ha podido enviar: falta el número de WhatsApp de la "
            "plataforma."
        )
    if not send_operator_albaran_notification(unit.pk, whatsapp_sender,
                                              changed_by=by):
        raise TrafficError(
            "No se ha podido enviar el aviso por WhatsApp a %s. Revisa "
            "que tenga teléfono." % _driver_name(unit.operator)
        )
    return unit


def _point(latitude, longitude):
    """
    Coordinates as floats, or None.

    ---

    Coordenadas como números, o None si falta alguna.
    """
    if latitude is None or longitude is None:
        return None
    return {"lat": float(latitude), "lng": float(longitude)}


def _last_positions(drivers, now):
    """
    Last recent position of each driver.

    ---

    Última posición de cada conductor que no tenga más de
    `POSITION_MAX_AGE`.
    """
    positions = {}
    for position in DriverPosition.objects.filter(
        company_user__in=drivers,
        recorded_at__gte=now - POSITION_MAX_AGE,
    ).order_by("company_user_id", "-recorded_at"):
        positions.setdefault(position.company_user_id, position)
    return positions


def build_map(company):
    """
    Data of the traffic map.

    ---

    Datos del mapa de tráfico (Miguel Ángel, S133):
    - Equipos fuera (en servicio o regresando): en la última posición
      que mandó el móvil del conductor; sin posición reciente, en la
      lista "sin posición".
    - Equipos en base y conductores libres sin máquina: agrupados en
      la base del conductor, sin posición.
    - Recogidas de los albaranes abiertos: la dirección tal cual, la
      sitúa el mapa.
    Las máquinas sin conductor no salen.
    """
    now = timezone.now()
    today = timezone.localdate()
    units = list(board_units(company).order_by(
        "work_order__service_date", "work_order__work_order_number",
        "unit_number",
    ))
    drivers, machines = _resources(company, units, today)
    crews = _crews(company, drivers, machines)
    positions = _last_positions(
        [crew.driver_card for crew in crews if crew.state in CREW_OUT_STATES],
        now,
    )

    bases = {}

    def base_entry(driver):
        base = getattr(driver, "base", None)
        key = base.pk if base is not None else 0
        if key not in bases:
            bases[key] = {
                "name": base.name if base is not None else "Sin base",
                "point": (
                    _point(base.latitude, base.longitude)
                    if base is not None else None
                ),
                "crews": [],
                "drivers": [],
            }
        return bases[key]

    crews_out = []
    for crew in crews:
        entry = {
            "driver": crew.driver_card.display_name,
            "machine": crew.machine_card.code,
            "plate": crew.machine_card.plate,
            "state": crew.state,
            "state_label": crew.state_label,
            "albaran": (
                crew.current_unit.albaran_number
                if crew.current_unit is not None else ""
            ),
        }
        if crew.state in CREW_OUT_STATES:
            position = positions.get(crew.driver_id)
            if position is not None:
                entry["point"] = _point(position.latitude, position.longitude)
                entry["accuracy"] = position.accuracy_m
                entry["at"] = timezone.localtime(
                    position.recorded_at,
                ).strftime("%H:%M")
            crews_out.append(entry)
        else:
            base_entry(crew.driver_card)["crews"].append(entry)
    for driver in drivers:
        if driver.crew is None and driver.state == STATE_FREE:
            base_entry(driver)["drivers"].append(driver.display_name)

    services = []
    for unit in units:
        if unit.status in RETURNING_STATUSES:
            continue
        services.append({
            "label": unit.albaran_number,
            "address": unit.work_order.pickup_location,
            "colour": unit_colour(unit, today),
            "status": unit.get_status_display(),
            "driver": (
                _driver_name(unit.operator) if unit.operator_id else ""
            ),
        })
    for work_order in WorkOrderAssistance.objects.filter(
        company=company,
        status__in=OPEN_ORDER_STATUSES,
        units__isnull=True,
    ):
        services.append({
            "label": work_order.work_order_number,
            "address": work_order.pickup_location,
            "colour": (
                COLOUR_BLUE if work_order.service_date > today
                else COLOUR_RED
            ),
            "status": "Sin albarán",
            "driver": "",
        })

    return {
        "bases": [entry for entry in bases.values()],
        "crews_out": crews_out,
        "services": [s for s in services if s["address"]],
    }


def driver_is_out(company_user):
    """
    Whether the driver has an albarán in progress.

    ---

    Si el conductor tiene un albarán en curso (enviado, en servicio o
    regresando): solo entonces se guarda su posición.
    """
    return Unit.objects.filter(
        operator=company_user,
        status__in=IN_SERVICE_STATUSES + RETURNING_STATUSES,
        work_order__status__in=OPEN_ORDER_STATUSES,
    ).exists()
