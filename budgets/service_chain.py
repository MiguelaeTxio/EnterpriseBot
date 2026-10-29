# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/budgets/service_chain.py
"""
Services chained on the road (H37, S138).

Miguel Ángel: coming back from a finished service (A), the driver can be
given another one (B) and leave from where he is. A ends there and B
starts there. The km of A are the driver's, always (he writes them when
the client signs, with the return to base he has not driven yet). The
office must know the km billed and not driven: "a final de año, ¿cuántos
kilómetros nos hemos ahorrado que hemos facturado sin tener que hacerlos
al encadenar?". The client and the insurer only see the driver's km.

When B starts (its km and time at departure) while A is coming back
(finished, not closed in base), A gets:
- chained_to = B, the time and the odometer of the change (B's km at
  departure) and the point (the phone position then);
- Google's estimate of the return from that point to A's base, as
  support information;
- closed in base automatically (Miguel Ángel, S138: "1. (a)"), with a
  note, since its return to base will never happen.
Km billed and not driven = the driver's km of A minus the km driven
until the change (odometer): WorkOrderAssistanceUnit.chain_saved_km.

---

Servicios encadenados en ruta. Al salir B (km y hora de salida)
mientras A vuelve (terminado y sin cerrar en base), A se marca como
encadenado con B (hora, km del cuentakilómetros y punto del cambio), se
estima con Google su vuelta a base desde ahí (información de apoyo) y
se cierra en base solo, con una nota. Los km cobrados sin hacer son los
km del chófer menos los hechos hasta el cambio.
"""
import datetime
import logging
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)

# The phone position of the change: the nearest to the time of the
# change within this margin.
# Posición del cambio: la más cercana a la hora del cambio dentro de
# este margen.
POINT_MARGIN = datetime.timedelta(minutes=30)


def returning_unit(unit):
    """
    The albarán the driver was coming back from when `unit` started.

    ---

    El albarán del que volvía el conductor cuando salió `unit`:
    terminado (firmado o cerrado sin firma) antes de la salida, sin
    cerrar en base, del mismo conductor. El más reciente; None si no hay.
    """
    from budgets.assistance_traffic import (
        MAX_RETURN, RETURNING_STATUSES, _work_end,
    )
    from budgets.models import WorkOrderAssistanceUnit as Unit

    if not unit.operator_id or unit.started_at is None:
        return None
    candidates = []
    for other in Unit.objects.select_for_update().filter(
        operator_id=unit.operator_id,
        status__in=RETURNING_STATUSES,
        base_closed_at__isnull=True,
    ).exclude(pk=unit.pk):
        end = _work_end(other)
        if end is None or end > unit.started_at:
            continue
        if unit.started_at - end > MAX_RETURN:
            continue
        candidates.append((end, other))
    if not candidates:
        return None
    return max(candidates, key=lambda pair: pair[0])[1]


def chain_on_start(unit, by):
    """
    Chain on the road the albarán the driver comes back from, if any.

    ---

    Si el conductor volvía de otro albarán al salir a `unit`, lo marca
    como encadenado en ruta con `unit` y lo cierra en base. Va dentro de
    la transacción de la salida; la estimación de Google, tras el commit.
    Si la salida se corrige (se repite), actualiza el ya encadenado.
    Devuelve el albarán encadenado o None.
    """
    from budgets.models import (
        WorkOrderAssistanceUnit as Unit,
        WorkOrderAssistanceUnitEvent as Event,
    )

    previous = Unit.objects.select_for_update().filter(
        chained_to=unit,
    ).first() or returning_unit(unit)
    if previous is None:
        # S140: closed on the road before leaving to this one: it is
        # chained now (the point and the estimate were taken then).
        # Cerrado en ruta antes de salir a este: se encadena ahora (el
        # punto y la estimación se tomaron al cerrarlo).
        closed = closed_in_route_unit(unit)
        if closed is not None:
            closed.chained_to = unit
            closed.chain_odometer = unit.km_start
            closed.save(update_fields=[
                "chained_to", "chain_odometer", "updated_at",
            ])
        return closed
    if previous.closed_in_route:
        # Departure corrected: only the odometer follows it.
        # Salida corregida: solo cambia el cuentakilómetros.
        previous.chain_odometer = unit.km_start
        previous.save(update_fields=["chain_odometer", "updated_at"])
        return previous
    first_time = previous.chained_to_id is None
    previous.chained_to = unit
    previous.chain_at = unit.started_at
    previous.chain_odometer = unit.km_start
    fields = ["chained_to", "chain_at", "chain_odometer", "updated_at"]
    if first_time:
        status = previous.status
        previous.status = Unit.STATUS_CLOSED_BASE
        previous.base_closed_at = timezone.now()
        previous.base_closed_by = by
        previous.arrival_base = _base_of(previous)
        fields += [
            "status", "base_closed_at", "base_closed_by", "arrival_base",
        ]
    previous.save(update_fields=fields)
    if first_time:
        Event.status_change(
            previous, status, previous.status, by=by,
            detail=(
                "Encadenado en ruta con %s: sale a ese servicio con %s km "
                "sin volver a base." % (unit.albaran_number, unit.km_start)
            ),
        )
    previous_pk = previous.pk
    transaction.on_commit(lambda: estimate_return(previous_pk))
    return previous


def closed_in_route_unit(unit):
    """
    The albarán closed on the road before `unit` left, or None.

    ---

    El albarán que el conductor cerró en ruta antes de salir a `unit`,
    aún sin encadenar y dentro de MAX_RETURN (S140).
    """
    from budgets.assistance_traffic import MAX_RETURN
    from budgets.models import WorkOrderAssistanceUnit as Unit

    if not unit.operator_id or unit.started_at is None:
        return None
    return Unit.objects.select_for_update().filter(
        operator_id=unit.operator_id,
        closed_in_route=True,
        chained_to__isnull=True,
        chain_at__lte=unit.started_at,
        chain_at__gte=unit.started_at - MAX_RETURN,
    ).exclude(pk=unit.pk).order_by("-chain_at").first()


def _base_of(unit):
    """
    Base the albarán would have come back to.

    ---

    Base a la que habría vuelto el albarán: la de salida, la del
    conductor o la de la orden.
    """
    if unit.departure_base_id:
        return unit.departure_base
    base = getattr(unit.operator, "base", None) if unit.operator_id else None
    return base or unit.work_order.base


def _change_point(unit):
    """
    Phone position at the time of the change, as (lat, lng), or None.

    ---

    Posición del móvil a la hora del cambio (la más cercana dentro de
    POINT_MARGIN), o None.
    """
    from budgets.models import DriverPosition

    if unit.chain_at is None or not unit.operator_id:
        return None
    nearby = DriverPosition.objects.filter(
        company_user_id=unit.operator_id,
        recorded_at__gte=unit.chain_at - POINT_MARGIN,
        recorded_at__lte=unit.chain_at + POINT_MARGIN,
    )
    best = min(
        nearby, key=lambda p: abs((p.recorded_at - unit.chain_at)),
        default=None,
    )
    if best is None:
        return None
    return best.latitude, best.longitude


def estimate_return(unit_pk):
    """
    Google's estimate of the return to base not driven; never raises.

    ---

    Estimación de Google de la vuelta a base que no se hizo: del punto
    del cambio (o, sin posición, del destino del servicio) a la base.
    Información de apoyo; nunca lanza excepciones.
    """
    from budgets.models import WorkOrderAssistanceUnit as Unit
    from budgets.service_eta import EtaError, Router, base_point
    from budgets.service_geocode import eta_point

    unit = Unit.objects.select_related(
        "work_order", "arrival_base", "operator",
    ).filter(pk=unit_pk).first()
    if unit is None or (
        unit.chained_to_id is None and not unit.closed_in_route
    ):
        return
    try:
        # S140: closed on the road, the point is the one of the phone.
        # Cerrado en ruta, el punto es el que mandó el móvil.
        point = (
            (unit.chain_latitude, unit.chain_longitude)
            if unit.chain_latitude is not None
            and unit.chain_longitude is not None
            else _change_point(unit)
        )
        changes = {}
        if point is not None:
            origin = {
                "lat": float(point[0]), "lng": float(point[1]),
                "label": "punto del encadenamiento",
            }
            changes["chain_latitude"], changes["chain_longitude"] = point
        else:
            origin = eta_point(unit.work_order, "destination")
        base = base_point(unit.arrival_base or _base_of(unit))
        if base is not None and (origin.get("lat") or origin.get("address")):
            try:
                seconds, meters = Router().leg(origin, base)
            except EtaError as exc:
                logger.warning("# [ENCADENADO] %s: %s", unit.pk, exc)
            else:
                changes["chain_return_km_est"] = (
                    Decimal(meters) / 1000
                ).quantize(Decimal("0.1"))
                changes["chain_return_minutes_est"] = round(seconds / 60)
        if changes:
            Unit.objects.filter(pk=unit.pk).update(**changes)
    except Exception:  # noqa: BLE001 -- solo información de apoyo
        logger.exception("# [ENCADENADO] Sin estimación para %s.", unit_pk)
