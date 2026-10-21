# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/budgets/assistance_traffic.py
"""
H37 (S133). Traffic panel of the assistance service: who and what is
free, the open albaranes, and the assignment rules.

---

H37 (S133). Panel de tráfico del servicio de asistencia (fase 2 del
dossier de Pepe, anexo V37 sección 4.4): qué conductores y máquinas
están libres, los albaranes abiertos con su color, y las reglas de
asignación:

- No se asigna un conductor ni una máquina ocupados (con otro albarán
  abierto), ni un conductor de vacaciones, de baja o ausente hoy, ni
  una máquina en taller (con una avería abierta).
- Solo se asigna o se cambia la asignación de un albarán que no se ha
  enviado todavía (pendiente o con el aviso fallido).
- No se envía sin conductor y máquina.
- Cada asignación, cada retirada y cada cambio de estado guardan hora
  y usuario (`WorkOrderAssistanceUnitEvent`).

Un albarán ocupa a su conductor y su máquina hasta que el conductor lo
cierra en base desde la app (fase 4 del dossier, S133): mientras tanto
el albarán firmado sale en verde ("regresando").
"""
from django.db import transaction
from django.db.models import Max, Q
from django.utils import timezone

from budgets.assistance_resources import (
    assistance_drivers,
    assistance_machines,
)
from budgets.models import (
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
    driver_units = {}
    machine_units = {}
    for unit in units:
        if unit.operator_id:
            driver_units.setdefault(unit.operator_id, unit)
        if unit.machine_asset_id:
            machine_units.setdefault(unit.machine_asset_id, unit)

    drivers = list(assistance_drivers(company).select_related(
        "person_identity",
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
        driver.is_assignable = driver.state == STATE_FREE

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
        machine.is_assignable = machine.state == STATE_FREE
    return drivers, machines


def build_board(company, category="", sort=SORT_AVAILABILITY):
    """
    Everything the traffic board shows.

    ---

    Todo lo que muestra el panel de tráfico: conductores, máquinas
    (filtradas por categoría) y albaranes abiertos, más las órdenes
    abiertas que aún no tienen ningún albarán.
    """
    today = _today()
    units = list(board_units(company).order_by(
        "work_order__service_date", "work_order__work_order_number",
        "unit_number",
    ))
    drivers, machines = _resources(company, units, today)

    categories = sorted({m.type_name for m in machines if m.type_name})
    if category:
        machines = [m for m in machines if m.type_name == category]
    if sort == SORT_NAME:
        drivers.sort(key=lambda d: d.display_name.lower())
        machines.sort(key=lambda m: m.code)
    else:
        drivers.sort(key=lambda d: (
            STATE_ORDER[d.state], d.display_name.lower(),
        ))
        machines.sort(key=lambda m: (STATE_ORDER[m.state], m.code))

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
        "drivers": drivers,
        "machines": machines,
        "units": units,
        "empty_orders": empty_orders,
        "categories": categories,
        "category": category,
        "sort": sort,
        "sort_options": SORT_OPTIONS,
        "open_count": len(units) + len(empty_orders),
        "free_drivers": sum(1 for d in drivers if d.is_assignable),
        "free_machines": sum(1 for m in machines if m.is_assignable),
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


def assign(company, by, resource_kind, resource_pk, unit_pk=None,
           order_pk=None):
    """
    Assign a driver or a machine to an albarán (or to a new albarán
    of an order).

    ---

    Asigna un conductor o una máquina a un albarán. Si se suelta sobre
    una orden, va a su primer albarán sin ese hueco ocupado que aún no
    se ha enviado, o a uno nuevo. Comprueba que el recurso esté libre
    con los datos del momento, no con lo que pintaba el panel.
    Devuelve el albarán.
    """
    today = _today()
    with transaction.atomic():
        if resource_kind == "driver":
            resource = assistance_drivers(company).filter(
                pk=resource_pk,
            ).first()
            field = "operator"
        elif resource_kind == "machine":
            resource = assistance_machines(company).filter(
                pk=resource_pk,
            ).first()
            field = "machine_asset"
        else:
            raise TrafficError("No se sabe qué se ha soltado.")
        if resource is None:
            raise TrafficError("Ese recurso ya no es de asistencia.")

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
                **{"%s__isnull" % field: True}
            ).order_by("unit_number").first()
            if unit is None:
                unit = _create_unit(work_order, by)

        busy = board_units(company).filter(
            **{field: resource}
        ).exclude(pk=unit.pk).first()
        if busy is not None:
            raise TrafficError(
                "%s ya está en el albarán %s." % (
                    _resource_name(resource_kind, resource),
                    busy.albaran_number,
                )
            )
        if resource_kind == "driver":
            person = getattr(resource, "person_identity", None)
            reason = (
                _absences_today(company, today).get(person.pk)
                if person is not None else None
            )
            if reason:
                raise TrafficError("%s: %s hoy." % (
                    _driver_name(resource), reason.lower(),
                ))
            _set_driver(unit, resource, by)
        else:
            if resource.pk in _machines_in_workshop(company):
                raise TrafficError(
                    "La máquina %s está en taller (avería abierta)."
                    % resource.code
                )
            _set_machine(unit, resource, by)
    return unit


def _resource_name(resource_kind, resource):
    """
    How a resource is named in the panel messages.

    ---

    Cómo se nombra un recurso en los mensajes del panel.
    """
    if resource_kind == "driver":
        return _driver_name(resource)
    return "La máquina %s" % resource.code


def unassign(company, by, unit_pk, resource_kind):
    """
    Take the driver or the machine off an albarán not sent yet.

    ---

    Quita el conductor o la máquina de un albarán aún sin enviar.
    """
    with transaction.atomic():
        unit = _locked_unit(company, unit_pk)
        if resource_kind == "driver" and unit.operator_id:
            Event.objects.create(
                unit=unit, kind=Event.KIND_UNASSIGN, created_by=by,
                detail="Conductor retirado: %s."
                % _driver_name(unit.operator),
            )
            unit.operator = None
            unit.save(update_fields=["operator", "updated_at"])
        elif resource_kind == "machine" and (
            unit.machine_asset_id or unit.machine
        ):
            Event.objects.create(
                unit=unit, kind=Event.KIND_UNASSIGN, created_by=by,
                detail="Máquina retirada: %s." % unit.machine,
            )
            unit.machine_asset = None
            unit.machine = ""
            unit.save(update_fields=[
                "machine_asset", "machine", "updated_at",
            ])
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
