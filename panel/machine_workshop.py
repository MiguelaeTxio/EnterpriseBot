# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/machine_workshop.py
"""
H30 (S139, invasive session). Workshop management of a cost centre:
its work-order tasks, its breakdown tickets and the spare parts used,
with the totals of what the machine has cost.

---

H30 (S139, sesión invasora). Gestión del taller de un centro de gasto,
pedida por Miguel Ángel desde la sección Taller de la ficha de máquina
(punto 7 de S119): "saber los gastos que ha tenido la máquina, con
sumatorio y exportación a Excel, y que el detalle de cada parte sea el
detalle total de lo grabado". Aquí vive toda la lógica (plantillas
tontas): filas, filtros, orden múltiple (directriz 4.24), importes y el
documento de solo lectura de un parte.

Criterio de importe de un repuesto (el mismo en la lista, el documento
y el Excel): unidades x precio unitario grabado en la línea de repuesto
del parte; si la línea no lo tiene, el precio de compra grabado en el
artículo del almacén del que salió. Sin unidades o sin ningún precio
grabado, el repuesto no suma y se cuenta como "sin precio". En una
máquina solo suman los repuestos imputados a ella: los de sus tareas
cuyo vehículo es esta máquina o está en blanco.
"""
import datetime
from decimal import Decimal

from django.db.models import Prefetch, Q

from chat.models import BreakdownTicket
from ivr_config.models import CompanyUser
from work_order_processor.models import (
    SparePartLine,
    TipoTarea,
    WorkOrder,
    WorkOrderEntryLine,
)

MAX_SORT_KEYS = 4

# Roles that can open the spare-part and delivery-note pages (the same
# set as SupervisorAccessMixin) and the ticket page.
# Roles que pueden abrir la ficha de repuesto y la de albarán (los de
# SupervisorAccessMixin) y la del ticket (BreakdownTicketDetailView).
STOCK_ROLES = {
    CompanyUser.ROLE_ADMIN,
    CompanyUser.ROLE_SUPERVISOR,
    CompanyUser.ROLE_WORKSHOPBOSS,
}
TICKET_ROLES = STOCK_ROLES | {CompanyUser.ROLE_WORKSHOP}

TASK_FILTER_KEYS = (
    "search", "tipo", "worker", "ticket", "albaran", "date_from",
    "date_to", "sort",
)
# Filtro "Albarán" del listado de tareas (S139, Miguel Ángel: "filtros
# de partes que llevan albarán para que de una tacada saquemos todos").
ALBARAN_WITH = "with"
ALBARAN_WITHOUT = "without"
TICKET_FILTER_KEYS = ("search", "state", "date_from", "date_to", "sort")

# Columnas que cada usuario elige ver (S139, Miguel Ángel: "casilleros
# con las columnas que queremos que salgan"). (clave, etiqueta, si se
# suma en la fila de totales). Se guardan las ocultas, para que una
# columna nueva salga visible por defecto.
TASK_COLUMNS = (
    ("date", "Fecha", False),
    ("worker", "Mecánico", False),
    ("tipo", "Tipo", False),
    ("description", "Avería / tarea", False),
    ("schedule", "Horario", False),
    ("shift", "Jornada", False),
    ("ordinary", "H. ordinarias", True),
    ("extra", "H. extra", True),
    ("festive", "H. festivas", True),
    ("hours", "Horas", True),
    ("parts", "Repuestos", True),
    ("cost", "Importe", True),
    ("albaranes", "Albaranes", False),
    ("ticket", "Ticket", False),
)
TICKET_COLUMNS = (
    ("code", "Ticket", False),
    ("date", "Fecha", False),
    ("status", "Estado", False),
    ("urgency", "Urgencia", False),
    ("tipo", "Tipo", False),
    ("summary", "Avería", False),
    ("tasks", "Tareas", True),
    ("ordinary", "H. ordinarias", True),
    ("extra", "H. extra", True),
    ("festive", "H. festivas", True),
    ("hours", "Horas", True),
    ("cost", "Importe", True),
    ("closed", "Cerrada", False),
)


def column_choices(columns, hidden):
    """
    Columns of a list with whether the user shows them.

    ---

    Columnas de un listado con si el usuario las muestra (las ocultas
    vienen de su navegación guardada).
    """
    hidden = set(hidden or [])
    return [
        {"key": key, "label": label, "visible": key not in hidden}
        for key, label, _summed in columns
    ]

STATE_OPEN = "open"
STATE_CLOSED = "closed"

_DATE_MIN = datetime.date.min
_DATETIME_MIN = datetime.datetime.min.replace(tzinfo=datetime.timezone.utc)


# ---------------------------------------------------------------------------
# Common helpers / Utilidades comunes
# ---------------------------------------------------------------------------

def parse_sort(raw, sortable):
    """
    Parse "key,-key" (priority order) into [(key, descending)].

    ---

    Interpreta "clave,-clave" (orden de prioridad) como
    [(clave, descendente)], sin claves inválidas ni repetidas, máximo
    MAX_SORT_KEYS (directriz 4.24).
    """
    keys = []
    for token in (raw or "").split(","):
        token = token.strip()
        key = token.lstrip("-")
        if key in sortable and key not in [k for k, _d in keys]:
            keys.append((key, token.startswith("-")))
    return keys[:MAX_SORT_KEYS]


def sort_controls(raw, sortable):
    """
    Sort value of each header click, arrows and priorities.

    ---

    Para cada columna ordenable, el valor de "sort" de un clic en su
    cabecera, su flecha y su prioridad: el clic la promueve a criterio
    principal conservando las demás; en la principal invierte el
    sentido (directriz 4.24, mismo comportamiento que Centros de gasto).
    """
    keys = parse_sort(raw, sortable)
    active = [key for key, _desc in keys]
    cols = {}
    for key in sortable:
        if key in active:
            idx = active.index(key)
            desc = keys[idx][1]
            arrow = "down" if desc else "up"
            priority = idx + 1 if len(keys) > 1 else ""
            new = [(key, (not desc) if idx == 0 else desc)] + [
                (k, d) for k, d in keys if k != key
            ]
        else:
            arrow, priority = "", ""
            new = [(key, False)] + keys
        cols[key] = {
            "next": ",".join(
                ("-" if d else "") + k for k, d in new[:MAX_SORT_KEYS]
            ),
            "arrow": arrow,
            "priority": priority,
        }
    return {
        "sort_cols": cols,
        "sort_active": bool(keys),
        "current_sort": ",".join(("-" if d else "") + k for k, d in keys),
    }


def _sort_rows(rows, keys, sortable, default_order):
    """
    Stable sort by several keys, the first one the most important.

    ---

    Orden estable por varias claves, la primera la más importante. Sin
    orden elegido, el orden por defecto de cada listado.
    """
    for key, desc in reversed(list(keys or default_order)):
        rows.sort(key=sortable[key], reverse=desc)
    return rows


def parse_date(raw):
    """
    Date of a filter (YYYY-MM-DD), or None.

    ---

    Fecha de un filtro (AAAA-MM-DD), o None.
    """
    try:
        return datetime.date.fromisoformat((raw or "").strip())
    except ValueError:
        return None


def _words(text):
    """
    Lower-case words of a search box.

    ---

    Palabras en minúsculas de la caja de búsqueda: una fila coincide
    si contiene todas, en cualquier orden.
    """
    return [word for word in (text or "").lower().split() if word]


def _matches(words, haystack):
    """
    Whether every search word appears in the text of a row.

    ---

    Si todas las palabras buscadas aparecen en el texto de la fila.
    """
    return all(word in haystack for word in words)


def _user_name(company_user):
    """
    Display name of a CompanyUser, or "".

    ---

    Nombre visible de un CompanyUser, o "".
    """
    if company_user is None or company_user.user_id is None:
        return ""
    user = company_user.user
    return user.get_full_name() or user.username


def _money(value):
    """
    Round an amount to cents.

    ---

    Redondea un importe a céntimos.
    """
    return value.quantize(Decimal("0.01"))


# ---------------------------------------------------------------------------
# Spare parts / Repuestos
# ---------------------------------------------------------------------------

def _part_price(part):
    """
    Unit price recorded for a spare-part line, or None.

    ---

    Precio unitario grabado de una línea de repuesto: el de la propia
    línea o, si no lo tiene, el de compra del artículo del almacén del
    que salió. None si no hay ninguno grabado.
    """
    if part.unit_price is not None:
        return part.unit_price
    entry = part.spare_part_entry
    if entry is not None and entry.purchase_unit_price is not None:
        return entry.purchase_unit_price
    return None


def _part_delivery_notes(part):
    """
    Supplier delivery notes the spare part comes from.

    ---

    Albaranes de proveedor de los que depende el repuesto: el de la
    línea de albarán de origen del artículo y los de las líneas de
    albarán que lo crearon, sin repetir, por fecha.
    """
    entry = part.spare_part_entry
    if entry is None:
        return []
    notes = {}
    origin = entry.source_delivery_note_line
    if origin is not None:
        notes[origin.delivery_note.pk] = origin.delivery_note
    for line in entry.source_delivery_note_lines.all():
        notes[line.delivery_note.pk] = line.delivery_note
    return sorted(
        notes.values(),
        key=lambda note: (note.delivery_date or _DATE_MIN, note.pk),
    )


def delivery_note_label(note):
    """
    Short label of a delivery note.

    ---

    Etiqueta corta de un albarán: número, proveedor y fecha.
    """
    parts = [
        note.delivery_number or "Albarán #%d" % note.pk,
        note.supplier_name or (note.supplier.name if note.supplier else ""),
        note.delivery_date.strftime("%d/%m/%Y") if note.delivery_date else "",
    ]
    return " — ".join(part for part in parts if part)


class PartInfo:
    """
    One spare part used in a task, ready to show.

    ---

    Un repuesto gastado en una tarea, listo para pintar: datos
    grabados, importe, si cuenta para la máquina, enlace al artículo y
    albaranes de los que depende.
    """

    def __init__(self, part, machine_pk, can_open_stock):
        self.part = part
        self.reference = part.reference
        self.material = part.material
        self.quantity = part.quantity
        self.source_label = part.get_source_display()
        self.supplier = part.supplier
        self.vehicle = part.vehicle
        self.price = _part_price(part)
        self.amount = (
            _money(self.price * part.quantity)
            if self.price is not None and part.quantity is not None
            else None
        )
        self.counts_for_machine = (
            machine_pk is None
            or part.vehicle_id is None
            or part.vehicle_id == machine_pk
        )
        entry = part.spare_part_entry
        self.article_internal_reference = (
            entry.internal_reference if entry is not None else ""
        )
        self.article_pk = entry.pk if entry is not None else None
        self.can_open_stock = can_open_stock
        self.delivery_notes = [
            {"pk": note.pk, "label": delivery_note_label(note)}
            for note in _part_delivery_notes(part)
        ]

    @property
    def delivery_notes_text(self):
        """
        Delivery notes as one line of text (Excel).

        ---

        Albaranes en una sola línea de texto (para el Excel).
        """
        return "; ".join(note["label"] for note in self.delivery_notes)


def _parts_prefetch():
    """
    Prefetch of the spare parts of a task with their article and notes.

    ---

    Prefetch de los repuestos de una tarea con su artículo del almacén
    y los albaranes de los que dependen, en pocas consultas.
    """
    return Prefetch(
        "spare_parts",
        queryset=SparePartLine.objects.select_related(
            "vehicle",
            "spare_part_entry__source_delivery_note_line__delivery_note"
            "__supplier",
        ).prefetch_related(
            "spare_part_entry__source_delivery_note_lines__delivery_note"
            "__supplier",
        ).order_by("line_number"),
    )


def _task_notes_prefetch():
    """
    Prefetch of the delivery-note lines linked straight to a task.

    ---

    Prefetch de las líneas de albarán vinculadas directamente a la
    tarea, con su albarán y su proveedor.
    """
    return "delivery_note_lines__delivery_note__supplier"


def _parts_totals(parts):
    """
    Cost of the parts that count for the machine and how many lack it.

    ---

    Importe de los repuestos que cuentan para la máquina y cuántos de
    ellos no tienen precio grabado.
    """
    total = Decimal("0")
    unpriced = 0
    for info in parts:
        if not info.counts_for_machine:
            continue
        if info.amount is None:
            unpriced += 1
        else:
            total += info.amount
    return total, unpriced


# ---------------------------------------------------------------------------
# Tasks list / Listado de tareas de los partes
# ---------------------------------------------------------------------------

def shift_label(entry):
    """
    Shift type recorded in a parte, or "" if not recorded.

    ---

    Tipo de jornada grabado en el parte (H30, S139): "Intensiva",
    "Partida" o "" en los partes que no lo guardan (anteriores a S139,
    PDF o generados).
    """
    if entry.is_intensive_shift is None:
        return ""
    return "Intensiva" if entry.is_intensive_shift else "Partida"


def task_type_label(line):
    """
    Type of a task, with its automatic classification if recorded.

    ---

    Tipo de la tarea y, si está grabada, su clasificación (categoría y
    subcategoría de avería, o la categoría libre del resto).
    """
    label = line.get_tipo_tarea_display() if line.tipo_tarea else ""
    detail = ""
    if line.fault_category:
        detail = line.get_fault_category_display()
        if line.fault_subcategory:
            detail += " / " + line.get_fault_subcategory_display()
    elif line.task_category_free:
        detail = line.task_category_free
    return label, detail


class TaskRow:
    """
    One row of the tasks list: one block of a work order on the machine.

    ---

    Una fila del listado de tareas: un bloque de un parte de trabajo
    hecho sobre esta máquina. `key` identifica la fila en la selección.
    """

    def __init__(self, line, machine_pk, can_open_stock):
        entry = line.entry
        self.line = line
        self.entry = entry
        self.key = "l%d" % line.pk
        self.work_date = entry.work_date
        self.worker = entry.worker_name or ""
        self.tipo_label, self.tipo_detail = task_type_label(line)
        self.description = line.fault_description or ""
        self.repair = line.repair_notes or ""
        self.shift_label = shift_label(entry)
        self.hc = line.hc
        self.hf = line.hf
        self.hours = line.delta_hours
        # Reparto ordinarias / extra / festivas: lo rellena
        # apply_hour_split() con los datos del día completo del parte.
        self.ordinary_hours = Decimal("0")
        self.extra_hours = Decimal("0")
        self.festive_hours = Decimal("0")
        self.or_val = line.or_val
        ticket = line.breakdown_ticket
        self.ticket = ticket
        self.ticket_code = (
            (ticket.ticket_date_code or "#%d" % ticket.pk) if ticket else ""
        )
        self.parts = [
            PartInfo(part, machine_pk, can_open_stock)
            for part in line.spare_parts.all()
        ]
        self.parts_cost, self.parts_unpriced = _parts_totals(self.parts)
        self.parts_count = sum(
            1 for info in self.parts if info.counts_for_machine
        )
        self.delivery_notes = task_delivery_notes(line, self.parts)
        self.label = " — ".join(
            part for part in (
                self.work_date.strftime("%d/%m/%Y")
                if self.work_date else "",
                self.worker,
                self.description[:60],
            ) if part
        )
        self.haystack = " ".join([
            self.worker, self.description, self.repair, self.or_val,
            self.tipo_label, self.tipo_detail, self.ticket_code,
            " ".join(
                "%s %s %s" % (info.reference, info.material, info.supplier)
                for info in self.parts
            ),
            " ".join(note["label"] for note in self.delivery_notes),
        ]).lower()

    @property
    def delivery_notes_text(self):
        """
        Delivery notes of the task as one line of text (Excel).

        ---

        Albaranes de la tarea en una sola línea de texto (para el Excel).
        """
        return "; ".join(note["label"] for note in self.delivery_notes)


def task_delivery_notes(line, parts):
    """
    Supplier delivery notes of a task, without repeats, by date.

    ---

    Albaranes de proveedor que lleva una tarea, sin repetir: los
    vinculados directamente a la tarea (línea de albarán con esa línea
    de parte) y aquellos de los que dependen sus repuestos.
    """
    notes = {}
    for note_line in line.delivery_note_lines.all():
        note = note_line.delivery_note
        notes[note.pk] = (
            note.delivery_date or _DATE_MIN, delivery_note_label(note),
        )
    for info in parts:
        for note in _part_delivery_notes(info.part):
            notes[note.pk] = (
                note.delivery_date or _DATE_MIN, delivery_note_label(note),
            )
    return [
        {"pk": pk, "label": label}
        for pk, (_date, label) in sorted(
            notes.items(), key=lambda item: (item[1][0], item[0]),
        )
    ]


TASK_SORTABLE = {
    "date": lambda r: (r.work_date or _DATE_MIN, r.hc or datetime.time.min),
    "worker": lambda r: r.worker.lower(),
    "tipo": lambda r: r.tipo_label.lower(),
    "description": lambda r: r.description.lower(),
    "hours": lambda r: r.hours or Decimal("0"),
    "ordinary": lambda r: r.ordinary_hours,
    "extra": lambda r: r.extra_hours,
    "festive": lambda r: r.festive_hours,
    "shift": lambda r: r.shift_label,
    "parts": lambda r: r.parts_count,
    "cost": lambda r: r.parts_cost,
    "ticket": lambda r: r.ticket_code,
    "albaranes": lambda r: len(r.delivery_notes),
}
TASK_DEFAULT_ORDER = (("date", True),)


def machine_lines(machine):
    """
    Work-order blocks of a machine, the same set as its Workshop panel.

    ---

    Bloques de parte de una máquina: el mismo conjunto que cuenta la
    sección Taller de la ficha (con fecha de parte), para que los
    totales coincidan con los de la ficha.
    """
    return WorkOrderEntryLine.objects.filter(
        machine_asset=machine, entry__work_date__isnull=False,
    )


def build_task_rows(machine, params, can_open_stock, only_keys=None):
    """
    Rows of the tasks list with the filters and the order applied.

    ---

    Filas del listado de tareas con los filtros y el orden aplicados.
    Con `only_keys` (mostrar solo la selección) se ignoran los filtros.
    """
    lines = machine_lines(machine).select_related(
        "entry__work_order__uploaded_by__base", "breakdown_ticket",
    ).prefetch_related(_parts_prefetch(), _task_notes_prefetch())
    if only_keys is None:
        date_from = parse_date(params.get("date_from"))
        date_to = parse_date(params.get("date_to"))
        if date_from:
            lines = lines.filter(entry__work_date__gte=date_from)
        if date_to:
            lines = lines.filter(entry__work_date__lte=date_to)
        tipo = params.get("tipo") or ""
        if tipo == "none":
            lines = lines.filter(tipo_tarea="")
        elif tipo in TipoTarea.values:
            lines = lines.filter(tipo_tarea=tipo)
        worker = params.get("worker") or ""
        if worker:
            lines = lines.filter(entry__worker_name=worker)
        ticket = params.get("ticket") or ""
        if ticket == "none":
            lines = lines.filter(breakdown_ticket__isnull=True)
        elif ticket.isdigit():
            lines = lines.filter(breakdown_ticket_id=int(ticket))
    else:
        pks = [
            int(key[1:]) for key in only_keys
            if key[:1] == "l" and key[1:].isdigit()
        ]
        lines = lines.filter(pk__in=pks)

    rows = [TaskRow(line, machine.pk, can_open_stock) for line in lines]
    if only_keys is None:
        albaran = params.get("albaran") or ""
        if albaran == ALBARAN_WITH:
            rows = [row for row in rows if row.delivery_notes]
        elif albaran == ALBARAN_WITHOUT:
            rows = [row for row in rows if not row.delivery_notes]
    words = _words(params.get("search"))
    if words and only_keys is None:
        rows = [row for row in rows if _matches(words, row.haystack)]
    apply_hour_split(rows)
    return _sort_rows(
        rows, parse_sort(params.get("sort"), TASK_SORTABLE),
        TASK_SORTABLE, TASK_DEFAULT_ORDER,
    )


def apply_hour_split(rows):
    """
    Split the hours of each task into ordinary, overtime and festive.

    ---

    Reparte las horas de cada tarea en ordinarias, extra y festivas,
    con el mismo criterio que la exportación de partes ("H. Extra",
    work_order_processor/services.py) y festive.py (S133):
    - El día es el parte completo (todas sus tareas, de cualquier
      máquina), sin la hora fantasma de vacaciones.
    - Parte festivo (sábado, domingo o festivo de la base del
      trabajador): todas sus horas son festivas, ninguna extra.
    - Si no, son extra las que pasan de 8 en el día, repartidas entre
      sus tareas en proporción a las horas de cada una; el resto,
      ordinarias.
    """
    from django.db.models import Sum

    from work_order_processor.festive import STANDARD_DAY_HOURS, is_festive

    entry_ids = {row.entry.pk for row in rows}
    if not entry_ids:
        return rows
    day_hours = {
        item["entry_id"]: item["total"] or Decimal("0")
        for item in WorkOrderEntryLine.objects.filter(
            entry_id__in=entry_ids,
        ).exclude(vacation_period__isnull=False).values(
            "entry_id",
        ).annotate(total=Sum("delta_hours"))
    }
    festive_cache = {}
    for row in rows:
        hours = row.hours or Decimal("0")
        uploader = row.entry.work_order.uploaded_by
        cache_key = (row.work_date, uploader.pk if uploader else None)
        if cache_key not in festive_cache:
            festive_cache[cache_key] = is_festive(row.work_date, uploader)
        if festive_cache[cache_key]:
            row.festive_hours = hours
            continue
        day = day_hours.get(row.entry.pk, Decimal("0"))
        extra = Decimal("0")
        if day > STANDARD_DAY_HOURS:
            extra = (hours * (day - STANDARD_DAY_HOURS) / day).quantize(
                Decimal("0.01"),
            )
        row.extra_hours = extra
        row.ordinary_hours = hours - extra
    return rows


def task_totals(rows):
    """
    Totals of a set of task rows.

    ---

    Totales de un conjunto de filas: tareas, horas, repuestos, importe
    de repuestos y repuestos sin precio grabado.
    """
    hours = sum((row.hours or Decimal("0") for row in rows), Decimal("0"))
    cost = sum((row.parts_cost for row in rows), Decimal("0"))
    return {
        "count": len(rows),
        "hours": hours,
        "ordinary": sum(
            (row.ordinary_hours for row in rows), Decimal("0"),
        ),
        "extra": sum((row.extra_hours for row in rows), Decimal("0")),
        "festive": sum((row.festive_hours for row in rows), Decimal("0")),
        "parts": sum(row.parts_count for row in rows),
        "cost": _money(cost),
        "unpriced": sum(row.parts_unpriced for row in rows),
    }


def task_filter_options(machine):
    """
    Choices of the selects of the tasks list.

    ---

    Opciones de los desplegables del listado de tareas: mecánicos,
    tipos y averías que aparecen en los partes de esta máquina.
    """
    lines = machine_lines(machine)
    workers = sorted(
        name for name in lines.values_list(
            "entry__worker_name", flat=True,
        ).distinct() if name
    )
    ticket_ids = set(lines.exclude(
        breakdown_ticket__isnull=True,
    ).values_list("breakdown_ticket_id", flat=True))
    tickets = BreakdownTicket.objects.filter(
        Q(pk__in=ticket_ids) | Q(machine=machine),
    ).order_by("-created_at")
    return {
        "workers": workers,
        "tipos": TipoTarea.choices,
        "tickets": [
            {
                "pk": ticket.pk,
                "label": " — ".join(part for part in (
                    ticket.ticket_date_code or "#%d" % ticket.pk,
                    (ticket.fault_summary or "")[:50],
                ) if part),
            }
            for ticket in tickets
        ],
    }


def selected_task_rows(machine, keys, can_open_stock):
    """
    Task rows of the machine among the selected keys, by date.

    ---

    Filas de tareas de la máquina entre las seleccionadas, por fecha.
    """
    return build_task_rows(
        machine, {"sort": "date"}, can_open_stock, only_keys=set(keys),
    )


# ---------------------------------------------------------------------------
# Breakdown tickets list / Listado de averías
# ---------------------------------------------------------------------------

class TicketRow:
    """
    One row of the breakdowns list: a ticket of the machine.

    ---

    Una fila del listado de averías: un ticket de la máquina con sus
    partes (tareas vinculadas), horas y repuestos gastados.
    """

    def __init__(self, ticket, tasks):
        self.ticket = ticket
        self.key = "t%d" % ticket.pk
        self.code = ticket.ticket_date_code or "#%d" % ticket.pk
        self.created_at = ticket.created_at
        self.status_label = ticket.get_status_display()
        self.is_closed = ticket.status == BreakdownTicket.STATUS_CLOSED
        self.urgency_label = ticket.get_urgency_display()
        self.tipo_label = (
            ticket.get_tipo_tarea_display() if ticket.tipo_tarea else ""
        )
        self.summary = ticket.fault_summary or ""
        self.assigned = _user_name(ticket.assigned_to)
        self.resolved_at = ticket.resolved_at
        self.tasks = list(tasks)
        self.tasks.sort(
            key=lambda row: (
                row.work_date or _DATE_MIN, row.hc or datetime.time.min,
            ),
        )
        totals = task_totals(self.tasks)
        self.task_count = totals["count"]
        self.hours = totals["hours"]
        self.ordinary_hours = totals["ordinary"]
        self.extra_hours = totals["extra"]
        self.festive_hours = totals["festive"]
        self.parts_count = totals["parts"]
        self.parts_cost = totals["cost"]
        self.parts_unpriced = totals["unpriced"]
        self.label = " — ".join(
            part for part in (self.code, self.summary[:60]) if part
        )
        self.haystack = " ".join([
            self.code, self.summary, ticket.notes or "",
            ticket.machine_raw or "", self.assigned, self.status_label,
            self.tipo_label, " ".join(row.haystack for row in self.tasks),
        ]).lower()


TICKET_SORTABLE = {
    "code": lambda r: r.code,
    "date": lambda r: r.created_at or _DATETIME_MIN,
    "status": lambda r: r.status_label.lower(),
    "urgency": lambda r: r.urgency_label.lower(),
    "tipo": lambda r: r.tipo_label.lower(),
    "summary": lambda r: r.summary.lower(),
    "tasks": lambda r: r.task_count,
    "hours": lambda r: r.hours,
    "ordinary": lambda r: r.ordinary_hours,
    "extra": lambda r: r.extra_hours,
    "festive": lambda r: r.festive_hours,
    "cost": lambda r: r.parts_cost,
    "closed": lambda r: r.resolved_at or _DATETIME_MIN,
}
TICKET_DEFAULT_ORDER = (("date", True),)


def build_ticket_rows(machine, params, can_open_stock, only_keys=None):
    """
    Rows of the breakdowns list with the filters and the order applied.

    ---

    Filas del listado de averías con los filtros y el orden aplicados.
    `state`: "" abiertas y cerradas, "open", "closed", "none" ninguna
    (semántica literal de casilla). Las tareas que cuentan son las de
    esta máquina, como en el listado de tareas.
    """
    tickets = BreakdownTicket.objects.filter(machine=machine).select_related(
        "assigned_to__user",
    ).prefetch_related(Prefetch(
        "work_entry_lines",
        queryset=machine_lines(machine).select_related(
            "entry__work_order__uploaded_by__base", "breakdown_ticket",
        ).prefetch_related(_parts_prefetch(), _task_notes_prefetch()),
    ))
    state = params.get("state", "")
    if only_keys is None:
        date_from = parse_date(params.get("date_from"))
        date_to = parse_date(params.get("date_to"))
        if date_from:
            tickets = tickets.filter(created_at__date__gte=date_from)
        if date_to:
            tickets = tickets.filter(created_at__date__lte=date_to)
        if state == "none":
            return []
        if state == STATE_OPEN:
            tickets = tickets.exclude(status=BreakdownTicket.STATUS_CLOSED)
        elif state == STATE_CLOSED:
            tickets = tickets.filter(status=BreakdownTicket.STATUS_CLOSED)
    else:
        pks = [
            int(key[1:]) for key in only_keys
            if key[:1] == "t" and key[1:].isdigit()
        ]
        tickets = tickets.filter(pk__in=pks)

    tickets = list(tickets)
    tasks_by_ticket = {
        ticket.pk: [
            TaskRow(line, machine.pk, can_open_stock)
            for line in ticket.work_entry_lines.all()
        ]
        for ticket in tickets
    }
    apply_hour_split([
        task for tasks in tasks_by_ticket.values() for task in tasks
    ])
    rows = [TicketRow(ticket, tasks_by_ticket[ticket.pk])
            for ticket in tickets]
    words = _words(params.get("search"))
    if words and only_keys is None:
        rows = [row for row in rows if _matches(words, row.haystack)]
    return _sort_rows(
        rows, parse_sort(params.get("sort"), TICKET_SORTABLE),
        TICKET_SORTABLE, TICKET_DEFAULT_ORDER,
    )


def ticket_totals(rows):
    """
    Totals of a set of ticket rows.

    ---

    Totales de un conjunto de averías: averías, tareas, horas,
    repuestos, importe y repuestos sin precio.
    """
    return {
        "count": len(rows),
        "tasks": sum(row.task_count for row in rows),
        "hours": sum((row.hours for row in rows), Decimal("0")),
        "ordinary": sum(
            (row.ordinary_hours for row in rows), Decimal("0"),
        ),
        "extra": sum((row.extra_hours for row in rows), Decimal("0")),
        "festive": sum((row.festive_hours for row in rows), Decimal("0")),
        "parts": sum(row.parts_count for row in rows),
        "cost": _money(sum((row.parts_cost for row in rows), Decimal("0"))),
        "unpriced": sum(row.parts_unpriced for row in rows),
    }


# ---------------------------------------------------------------------------
# Read-only document of a work order day / Documento de un parte
# ---------------------------------------------------------------------------

def time_text(value):
    """
    "HH:MM" of a time, or "".

    ---

    "HH:MM" de una hora, o "".
    """
    return value.strftime("%H:%M") if value else ""


def _service_info(line):
    """
    Services (oil and filters) recorded on a task, one per engine.

    ---

    Revisiones (aceite y filtros) grabadas en la tarea, una por motor
    (S137: las A con dos motores llevan la del camión y la de la grúa),
    solo con los datos que tienen y las etiquetas del formulario del
    mecánico. Lista vacía si la tarea no tiene revisión.
    """
    from fleet.work_order_service import FILTER_LABELS

    services = []
    for record in sorted(
        line.service_records.all(), key=lambda item: item.engine,
    ):
        services.append({
            "engine": record.get_engine_display(),
            "filters": [
                FILTER_LABELS.get(code, code)
                for code in record.filters_changed.split(",") if code
            ],
            "oil": (
                record.get_oil_type_display() if record.oil_type else ""
            ),
            "oil_litres": record.oil_litres,
            "next_hours": record.next_service_hours,
            "next_km": record.next_service_km,
            "notes": record.notes,
        })
    return services


def _photos(line):
    """
    Photos of a task with their URL resolved.

    ---

    Fotos de la tarea con su URL ya resuelta (la firmada de GCS o el
    enlace de Drive heredado), mismo criterio que el widget de fotos.
    """
    from panel.views_task_photos import _build_photo_entries

    result = []
    for item in _build_photo_entries(line.photos.all()):
        url = item["signed_url"] or item["photo"].drive_web_link
        if url:
            result.append({"url": url, "caption": item["photo"].caption})
    return result


def work_order_document(entry, machine, company_user):
    """
    Everything recorded in one work-order day, ready to show.

    ---

    Todo lo grabado en un parte (un día de un mecánico), listo para
    pintar como documento de solo lectura (Miguel Ángel, S139): "debe
    mostrar todo lo que hay grabado en el parte y nada de lo que no
    está grabado". Cada dato solo aparece si tiene valor; los sí/no
    solo aparecen cuando aplican. Las tareas de la máquina desde la
    que se abre van marcadas.
    """
    can_open_stock = company_user.role in STOCK_ROLES
    machine_pk = machine.pk if machine is not None else None
    lines = list(
        entry.lines.select_related(
            "machine_asset", "breakdown_ticket",
        ).prefetch_related(
            _parts_prefetch(), "photos", "service_records",
            "delivery_note_lines__delivery_note__supplier",
        ).order_by("line_number")
    )
    tasks = []
    total_hours = Decimal("0")
    total_cost = Decimal("0")
    total_unpriced = 0
    for line in lines:
        parts = [
            PartInfo(part, None, can_open_stock)
            for part in line.spare_parts.all()
        ]
        cost, unpriced = _parts_totals(parts)
        total_cost += cost
        total_unpriced += unpriced
        total_hours += line.delta_hours or Decimal("0")
        tipo_label, tipo_detail = task_type_label(line)
        readings = [
            (label, value) for label, value in (
                ("Km", line.odometer_reading),
                ("Horómetro motor (h)", line.engine_hours_reading),
                ("Horómetro grúa (h)", line.crane_hours_reading),
            ) if value is not None
        ]
        task_notes = {}
        for note_line in line.delivery_note_lines.all():
            note = note_line.delivery_note
            task_notes[note.pk] = {
                "pk": note.pk, "label": delivery_note_label(note),
            }
        tasks.append({
            "line": line,
            "number": line.line_number,
            "machine": line.machine_asset,
            "machine_text": line.machine_raw or line.machine_norm,
            "is_this_machine": (
                machine_pk is not None
                and line.machine_asset_id == machine_pk
            ),
            "hc": time_text(line.hc),
            "hf": time_text(line.hf),
            "hours": line.delta_hours,
            "or_val": line.or_val,
            "tipo_label": tipo_label,
            "tipo_detail": tipo_detail,
            "description": line.fault_description,
            "repair": line.repair_notes,
            "is_on_site": line.is_on_site,
            "readings": readings,
            "ticket": line.breakdown_ticket,
            "ticket_closed": line.ticket_closed,
            "services": _service_info(line),
            "parts": parts,
            "parts_cost": _money(cost),
            "parts_unpriced": unpriced,
            "delivery_notes": list(task_notes.values()),
            "photos": _photos(line),
        })

    starts = [line.hc for line in lines if line.hc]
    ends = [line.hf for line in lines if line.hf]
    work_order = entry.work_order
    gaps = []
    if work_order.source == WorkOrder.Source.DIGITAL:
        for gap in work_order.workday_gaps.select_related(
            "absence_category",
        ).order_by("gap_start"):
            gaps.append({
                "type": gap.get_gap_type_display(),
                "start": time_text(gap.gap_start),
                "end": time_text(gap.gap_end),
                "minutes": gap.duration_minutes,
                "category": (
                    gap.absence_category.label
                    if gap.absence_category_id else ""
                ),
                "note": gap.note,
            })
    lunch = ""
    if entry.lunch_break_start and entry.lunch_break_end:
        lunch = "%s — %s" % (
            time_text(entry.lunch_break_start),
            time_text(entry.lunch_break_end),
        )
    return {
        "entry": entry,
        "work_order": work_order,
        "worker": entry.worker_name,
        "work_date": entry.work_date,
        "uncertain_date": entry.uncertain_date,
        "is_pdf": work_order.source == WorkOrder.Source.PDF_UPLOAD,
        "pdf_name": (
            work_order.pdf_display_name
            if work_order.source == WorkOrder.Source.PDF_UPLOAD else ""
        ),
        "page_number": entry.page_number,
        "reviewed_by": (
            _user_name(work_order.reviewed_by) if work_order.reviewed
            else ""
        ),
        "reviewed_at": work_order.reviewed_at if work_order.reviewed
        else None,
        "start": time_text(min(starts)) if starts else "",
        "end": time_text(max(ends)) if ends else "",
        "lunch": lunch,
        "no_lunch_break": entry.no_lunch_break,
        "is_intensive_shift": entry.is_intensive_shift,
        "has_diet": entry.has_diet,
        "tasks": tasks,
        "gaps": gaps,
        "total_hours": total_hours,
        "total_cost": _money(total_cost),
        "total_unpriced": total_unpriced,
        "can_open_stock": can_open_stock,
        "can_open_ticket": company_user.role in TICKET_ROLES,
    }
