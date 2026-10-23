# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/budgets/assistance_albaranes.py
"""
H37 (S133). List of the assistance albaranes (Services > Albaranes).

---

H37 (S133). Listado de albaranes de asistencia (Servicios > Albaranes),
con el formato de la directriz 4.24: filtros (abiertos y cerrados,
aseguradora, fechas, búsqueda), orden múltiple con prioridad y
selección. Una fila por albarán, más una por cada orden abierta que aún
no tiene ninguno, para que nada se pierda de vista (Miguel Ángel, S133:
"he cerrado uno y ya no se puede ver en ningún sitio").
"""
import datetime

from budgets.assistance_search import Query, row_phrases
from budgets.models import WorkOrderAssistance, WorkOrderAssistanceUnit

Unit = WorkOrderAssistanceUnit

STATE_OPEN = "open"
STATE_CLOSED = "closed"

# Sortable columns: key -> how to read the value of a row.
# Columnas ordenables: clave -> cómo se lee el valor de una fila.
SORTABLE = {
    "number": lambda r: r.number,
    "date": lambda r: r.service_date or datetime.date.min,
    "insurer": lambda r: r.insurer.lower(),
    "expediente": lambda r: r.expediente.lower(),
    "pickup": lambda r: r.pickup.lower(),
    "driver": lambda r: r.driver.lower(),
    "machine": lambda r: r.machine.lower(),
    "status": lambda r: r.status_label.lower(),
    "closed": lambda r: r.closed_at or datetime.datetime.min.replace(
        tzinfo=datetime.timezone.utc,
    ),
}
MAX_SORT_KEYS = 4
DEFAULT_ORDER = (("date", True), ("number", True))

FILTER_KEYS = (
    "search", "state", "insurer", "date_from", "date_to", "sort",
)


class AlbaranRow:
    """
    One row of the list: an albarán or an order without albarán.

    ---

    Una fila del listado: un albarán o una orden sin albarán todavía.
    `key` identifica la fila en la selección ("u<pk>" u "o<pk>").
    """

    def __init__(self, work_order, unit=None):
        self.work_order = work_order
        self.unit = unit
        self.key = "u%d" % unit.pk if unit else "o%d" % work_order.pk
        self.number = (
            unit.albaran_number if unit else work_order.work_order_number
        )
        self.service_date = work_order.service_date
        self.insurer = work_order.insurer.name if work_order.insurer else ""
        self.expediente = work_order.expediente or ""
        self.pickup = work_order.pickup_location or ""
        self.destination = work_order.destination or ""
        self.vehicle_plate = work_order.vehicle_plate or ""
        self.client_name = work_order.client_name or ""
        if unit is not None:
            user = unit.operator.user if unit.operator_id else None
            self.driver = (
                (user.get_full_name() or user.username) if user else ""
            )
            self.machine = unit.machine or ""
            self.status = unit.status
            self.status_label = unit.get_status_display()
            self.is_closed = unit.status in (
                Unit.STATUS_CLOSED_BASE, Unit.STATUS_CANCELLED,
            )
            self.closed_at = unit.base_closed_at
            self.estimated_km = unit.estimated_km
            self.estimated_fuel = unit.estimated_fuel_liters
        else:
            self.driver = ""
            self.machine = ""
            self.status = ""
            self.status_label = "Sin albarán"
            self.is_closed = False
            self.closed_at = None
            self.estimated_km = None
            self.estimated_fuel = None
        self.label = " — ".join(
            part for part in (self.number, self.insurer, self.expediente)
            if part
        )


def parse_sort(raw):
    """
    Parse "key,-key" (priority order) into [(key, descending)].

    ---

    Interpreta "clave,-clave" (orden de prioridad) como
    [(clave, descendente)], sin claves inválidas ni repetidas, máximo
    MAX_SORT_KEYS (directriz 4.24, mismo formato que Centros de gasto).
    """
    keys = []
    for token in (raw or "").split(","):
        token = token.strip()
        key = token.lstrip("-")
        if key in SORTABLE and key not in [k for k, _d in keys]:
            keys.append((key, token.startswith("-")))
    return keys[:MAX_SORT_KEYS]


def sort_controls(raw):
    """
    Sort value of each header click, arrows and priorities.

    ---

    Para cada columna ordenable, el valor de "sort" de un clic en su
    cabecera, su flecha y su prioridad: el clic la promueve a criterio
    principal conservando las demás; en la principal invierte el
    sentido. Resuelto aquí, nunca en la plantilla.
    """
    keys = parse_sort(raw)
    active = [key for key, _desc in keys]
    sort_next, sort_arrows, sort_priority = {}, {}, {}
    for key in SORTABLE:
        if key in active:
            idx = active.index(key)
            desc = keys[idx][1]
            sort_arrows[key] = "down" if desc else "up"
            sort_priority[key] = idx + 1 if len(keys) > 1 else ""
            new = [(key, (not desc) if idx == 0 else desc)] + [
                (k, d) for k, d in keys if k != key
            ]
        else:
            sort_arrows[key] = ""
            sort_priority[key] = ""
            new = [(key, False)] + keys
        sort_next[key] = ",".join(
            ("-" if d else "") + k for k, d in new[:MAX_SORT_KEYS]
        )
    return {
        "sort_cols": {
            key: {
                "next": sort_next[key],
                "arrow": sort_arrows[key],
                "priority": sort_priority[key],
            }
            for key in SORTABLE
        },
        "sort_next": sort_next,
        "sort_arrows": sort_arrows,
        "sort_priority": sort_priority,
        "sort_active": bool(keys),
        "current_sort": ",".join(("-" if d else "") + k for k, d in keys),
    }


def _sort_rows(rows, keys):
    """
    Stable sort by several keys, the first one the most important.

    ---

    Orden estable por varias claves, la primera la más importante. Sin
    orden elegido: de la fecha más reciente a la más antigua.
    """
    for key, desc in reversed(list(keys or DEFAULT_ORDER)):
        rows.sort(key=SORTABLE[key], reverse=desc)
    return rows


def _date(raw):
    """
    Date of a filter (YYYY-MM-DD), or None.

    ---

    Fecha de un filtro (AAAA-MM-DD), o None.
    """
    try:
        return datetime.date.fromisoformat((raw or "").strip())
    except ValueError:
        return None


def build_rows(company, params, only_keys=None):
    """
    Rows of the list with the filters and the order applied.

    ---

    Filas del listado con los filtros y el orden aplicados. `state`:
    "" abiertos y cerrados, "open", "closed", "none" ninguno (semántica
    literal de casilla, como Centros de gasto). Con `only_keys` (mostrar
    solo la selección) se ignoran estado, aseguradora y fechas.
    """
    orders = WorkOrderAssistance.objects.filter(
        company=company,
    ).select_related("insurer")
    date_from = _date(params.get("date_from"))
    date_to = _date(params.get("date_to"))
    insurer = (params.get("insurer") or "").strip()
    state = params.get("state", "")
    if only_keys is None:
        if date_from:
            orders = orders.filter(service_date__gte=date_from)
        if date_to:
            orders = orders.filter(service_date__lte=date_to)
        if insurer.isdigit():
            orders = orders.filter(insurer_id=int(insurer))
        if state == "none":
            return []

    units = Unit.objects.filter(
        work_order__in=orders,
    ).select_related("work_order__insurer", "operator__user")
    if (params.get("search") or "").strip():
        # Everything row_phrases reads, in a few queries.
        # Todo lo que lee row_phrases, en pocas consultas.
        units = units.select_related(
            "work_order__vehicle_type", "work_order__operator__user",
            "work_order__operator_2__user", "work_order__created_by__user",
            "work_order__base", "work_order__budget", "operator_2__user",
            "machine_asset", "departure_base", "arrival_base",
            "signed_received_by__user", "base_closed_by__user",
            "incidence__operator__user", "incidence__operator_2__user",
            "incidence__recorded_by__user", "signature",
        ).prefetch_related("helpers__user", "events__created_by__user")
    rows = [AlbaranRow(unit.work_order, unit) for unit in units]
    rows += [
        AlbaranRow(order) for order in orders.filter(
            units__isnull=True,
        ).exclude(status__in=(
            WorkOrderAssistance.STATUS_COMPLETED,
            WorkOrderAssistance.STATUS_INVOICED,
        ))
    ]

    if only_keys is not None:
        rows = [row for row in rows if row.key in only_keys]
    elif state == STATE_OPEN:
        rows = [row for row in rows if not row.is_closed]
    elif state == STATE_CLOSED:
        rows = [row for row in rows if row.is_closed]

    query = Query(params.get("search") or "")
    if query:
        # S134 (6.3.H): any stored datum of the albarán is searchable.
        # Cualquier dato guardado del albarán se puede buscar.
        rows = [
            row for row in rows
            if query.matches(row_phrases(row.work_order, row.unit))
        ]
    return _sort_rows(rows, parse_sort(params.get("sort")))


def selected_units(company, keys):
    """
    Albaranes of the company among the selected row keys.

    ---

    Albaranes de la empresa entre las filas seleccionadas (las órdenes
    sin albarán no tienen PDF ni exportación de albarán).
    """
    pks = [
        int(key[1:]) for key in keys
        if key[:1] == "u" and key[1:].isdigit()
    ]
    return Unit.objects.filter(
        pk__in=pks, work_order__company=company,
    ).select_related("work_order__insurer", "operator__user").order_by(
        "work_order__service_date", "work_order__work_order_number",
        "unit_number",
    )


# Albaranes whose part of the service is finished: signed on the phone,
# closed without signature or with the paper signature received.
# Albaranes cuya parte del servicio está terminada: firmados en el
# móvil, cerrados sin firma o con la firma en papel recibida.
DONE_STATUSES = (
    Unit.STATUS_COMPLETED,
    Unit.STATUS_CLOSED_UNSIGNED,
    Unit.STATUS_SIGNED_RECEIVED,
    Unit.STATUS_CLOSED_BASE,
)


def _sign_label(unit, signature):
    """
    How the signature of an albarán is described in the summary.

    ---

    Cómo se describe la firma de un albarán en el resumen.
    """
    if signature is not None and signature.signature_data:
        return "Firmado"
    if unit.status == Unit.STATUS_SIGNED_RECEIVED:
        return "Firma en papel recibida"
    if unit.unsigned_reason or unit.status == Unit.STATUS_CLOSED_UNSIGNED:
        return "Cerrado sin firma"
    if unit.status in DONE_STATUSES:
        return "Terminado sin firma"
    return "Pendiente de firma"


def summary_context(work_order):
    """
    Data of the summary albarán of an order.

    ---

    Datos del albarán resumen de la orden (Miguel Ángel, S133): una fila
    por albarán (conductor, ayudantes, máquina, km, horas y firma) con
    los totales, y la firma de cada uno. Se puede sacar en cualquier
    momento: es "parcial" mientras quede algún albarán sin terminar y
    "completo" cuando todos están firmados o cerrados.
    """
    from decimal import Decimal

    from django.core.exceptions import ObjectDoesNotExist

    units = work_order.units.select_related(
        "operator__user",
    ).prefetch_related("helpers__user").order_by("unit_number")
    rows = []
    totals = {"km": Decimal("0"), "rescue": Decimal("0"),
              "wait": Decimal("0")}
    for unit in units:
        try:
            signature = unit.signature
        except ObjectDoesNotExist:
            signature = None
        km = sum(
            (k for k in (unit.phase1_km, unit.phase2_km) if k is not None),
            Decimal("0"),
        )
        user = unit.operator.user if unit.operator_id else None
        rows.append({
            "number": unit.albaran_number,
            "driver": (
                (user.get_full_name() or user.username) if user else ""
            ),
            "helpers": ", ".join(unit.helper_names),
            "machine": unit.machine,
            "km": km or "",
            "rescue_hours": unit.rescue_hours or "",
            "wait_hours": unit.wait_hours or "",
            "sign_label": _sign_label(unit, signature),
            "signature_data": signature.signature_data if signature else "",
            "signed_at": signature.signed_at if signature else None,
            "signer_name": signature.signer_name if signature else "",
            "unsigned_reason": unit.unsigned_reason,
            "is_done": unit.status in DONE_STATUSES,
        })
        totals["km"] += km
        totals["rescue"] += unit.rescue_hours or 0
        totals["wait"] += unit.wait_hours or 0
    done = sum(1 for row in rows if row["is_done"])
    return {
        "rows": rows,
        "done_count": done,
        "is_complete": bool(rows) and done == len(rows),
        "total_km": totals["km"] or "",
        "total_rescue": totals["rescue"] or "",
        "total_wait": totals["wait"] or "",
    }
