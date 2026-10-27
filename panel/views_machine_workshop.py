# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/views_machine_workshop.py
"""
H30 (S139, invasive session). Workshop management screens of a cost
centre, reached from the "Taller" section of its machine file: the
work-order tasks done on it, its breakdown tickets, and the read-only
document of a work order.

---

H30 (S139, sesión invasora). Pantallas de gestión del taller de un
centro de gasto, a las que se llega desde la sección Taller de su
ficha (botones "Gestión" y "Averías"):

- Tareas de los partes hechas sobre la máquina y averías (tickets),
  con el formato de la directriz 4.24 (panel fijo con filtros y
  acciones, lista con scroll propio, orden múltiple, casillas, visor de
  selección, pantalla completa, Excel de la selección) y el sumatorio
  de horas e importe de repuestos de lo listado.
- "Ver el parte": documento de solo lectura con todo lo grabado en el
  parte y nada más (no la vista de edición).

Acceso: los roles de Centros de gasto (FleetAccessMixin). Filtros,
orden y selección se guardan por usuario y por máquina (directriz
4.15). La lógica vive en panel/machine_workshop.py.
"""
import io

from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone
from django.views import View

from fleet.models import MachineAsset
from panel import machine_workshop as workshop
from panel.mixins import FleetAccessMixin
from work_order_processor.models import WorkOrderEntry

TASKS_TEMPLATE = "panel/machine_workshop/tasks.html"
TASKS_TABLE_TEMPLATE = "panel/machine_workshop/_tasks_table.html"
TICKETS_TEMPLATE = "panel/machine_workshop/tickets.html"
TICKETS_TABLE_TEMPLATE = "panel/machine_workshop/_tickets_table.html"
DOCUMENT_TEMPLATE = "panel/machine_workshop/document.html"

XLSX_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)


def _machine(request, pk):
    """
    Machine of the user's company, or 404.

    ---

    Máquina de la empresa del usuario, o 404.
    """
    return get_object_or_404(
        MachineAsset, pk=pk, company=request.user.company_user.company,
    )


def _screen_key(kind, machine):
    """
    Navigation key of a list of one machine.

    ---

    Clave de navegación de un listado de una máquina: los filtros y la
    selección de cada máquina se guardan aparte (directriz 4.15).
    """
    return "machine_workshop_%s_%d" % (kind, machine.pk)


def _params(request, keys):
    """
    Filters of a list: GET first, then POST (_f_ prefix).

    ---

    Filtros de un listado: los de GET y, en las acciones por POST, los
    vigentes con el prefijo _f_ (mismo criterio que Centros de gasto).
    """
    return {
        key: request.GET.get(key) or request.POST.get("_f_" + key, "")
        for key in keys
    }


def _only_keys(request):
    """
    Keys of "show only the current selection", or None.

    ---

    Claves de "Mostrar solo la selección actual", o None si no está
    marcada.
    """
    if request.GET.get("only_selected") != "1":
        return None
    return {
        key for key in request.GET.get("selected_ids", "").split(",") if key
    }


def _can_open_stock(request):
    """
    Whether the user can open spare-part and delivery-note pages.

    ---

    Si el usuario puede abrir las fichas de repuesto y de albarán.
    """
    return request.user.company_user.role in workshop.STOCK_ROLES


def _saved_selection(request, kind, machine):
    """
    Saved row selection of a list of one machine.

    ---

    Selección de filas guardada de un listado de una máquina.
    """
    from panel.navigation_persistence import get_saved_state_key

    saved = get_saved_state_key(
        request.user.company_user, _screen_key(kind, machine),
        "selection", [],
    )
    return saved if isinstance(saved, list) else []


def _page_context(request, machine, kind):
    """
    Common context of both list pages.

    ---

    Contexto común de las dos páginas: máquina, pestaña activa, URL de
    la ficha (destino de "Volver" sin historial), permisos y columnas
    visibles del usuario (todas se pintan; las ocultas las esconde una
    regla CSS, así el fragmento no depende de la elección).
    """
    from panel.navigation_persistence import get_saved_state_key

    hidden = get_saved_state_key(
        request.user.company_user, _screen_key(kind, machine),
        "hidden_columns", [],
    )
    hidden = [key for key in hidden if isinstance(key, str)] if isinstance(
        hidden, list) else []
    columns = workshop.column_choices(
        workshop.TASK_COLUMNS if kind == "tasks"
        else workshop.TICKET_COLUMNS,
        hidden,
    )
    return {
        "columns": columns,
        "hidden_columns": [
            column["key"] for column in columns if not column["visible"]
        ],
        "machine": machine,
        "active_kind": kind,
        "machine_detail_url": reverse(
            "panel:documentation_machine_detail", kwargs={"pk": machine.pk},
        ),
        "screen_key": _screen_key(kind, machine),
        "saved_selection": _saved_selection(request, kind, machine),
        "can_open_stock": _can_open_stock(request),
        "can_open_ticket": (
            request.user.company_user.role in workshop.TICKET_ROLES
        ),
    }


def _xlsx_response(workbook, name):
    """
    HTTP download of a workbook.

    ---

    Descarga HTTP de un libro Excel.
    """
    buffer = io.BytesIO()
    workbook.save(buffer)
    response = HttpResponse(buffer.getvalue(), content_type=XLSX_CONTENT_TYPE)
    response["Content-Disposition"] = 'attachment; filename="%s_%s.xlsx"' % (
        name, timezone.localtime().strftime("%Y%m%d_%H%M"),
    )
    return response


def _sheet(workbook, title, columns, first=False):
    """
    New sheet with a bold header row.

    ---

    Hoja nueva con la fila de cabecera en negrita.
    """
    from openpyxl.styles import Font

    sheet = workbook.active if first else workbook.create_sheet()
    sheet.title = title
    sheet.append(list(columns))
    for cell in sheet[1]:
        cell.font = Font(bold=True)
    sheet.freeze_panes = "A2"
    return sheet


def _number(value):
    """
    Float for Excel, or None.

    ---

    Número para el Excel, o None.
    """
    return float(value) if value is not None else None


def _append_total(sheet, values):
    """
    Bold total row at the end of a sheet.

    ---

    Fila de total en negrita al final de una hoja.
    """
    from openpyxl.styles import Font

    sheet.append(values)
    for cell in sheet[sheet.max_row]:
        cell.font = Font(bold=True)


TASK_COLUMNS = (
    "Fecha", "Mecánico", "Tipo", "Clasificación", "Avería / tarea",
    "Reparación", "H.C.", "H.F.", "Jornada", "Horas ordinarias",
    "Horas extra",
    "Horas festivas", "Horas", "O.R.", "Ticket", "Repuestos",
    "Importe repuestos (€)", "Repuestos sin precio", "Albaranes",
)
PART_COLUMNS = (
    "Fecha", "Mecánico", "Ticket", "Referencia", "Material", "Unidades",
    "Precio unitario (€)", "Importe (€)", "Procedencia", "Proveedor",
    "Albaranes",
)


def _write_tasks(workbook, rows, first=True):
    """
    TAREAS and REPUESTOS sheets of a set of task rows.

    ---

    Hojas TAREAS y REPUESTOS de un conjunto de tareas, con su fila de
    total (mismo criterio de importe que la pantalla).
    """
    tasks = _sheet(workbook, "TAREAS", TASK_COLUMNS, first=first)
    parts = _sheet(workbook, "REPUESTOS", PART_COLUMNS)
    for row in rows:
        tasks.append([
            row.work_date, row.worker, row.tipo_label, row.tipo_detail,
            row.description, row.repair, workshop.time_text(row.hc),
            workshop.time_text(row.hf), row.shift_label,
            _number(row.ordinary_hours),
            _number(row.extra_hours), _number(row.festive_hours),
            _number(row.hours), row.or_val,
            row.ticket_code, row.parts_count, _number(row.parts_cost),
            row.parts_unpriced or None, row.delivery_notes_text,
        ])
        for info in row.parts:
            if not info.counts_for_machine:
                continue
            parts.append([
                row.work_date, row.worker, row.ticket_code, info.reference,
                info.material, _number(info.quantity), _number(info.price),
                _number(info.amount), info.source_label, info.supplier,
                info.delivery_notes_text,
            ])
    totals = workshop.task_totals(rows)
    _append_total(tasks, [
        "TOTAL", "", "", "", "%d tareas" % totals["count"], "", "", "", "",
        _number(totals["ordinary"]), _number(totals["extra"]),
        _number(totals["festive"]), _number(totals["hours"]), "", "",
        totals["parts"],
        _number(totals["cost"]), totals["unpriced"] or None,
    ])
    _append_total(parts, [
        "TOTAL", "", "", "", "", "", "", _number(totals["cost"]),
    ])
    for sheet in (tasks, parts):
        for cell in sheet["A"][1:]:
            cell.number_format = "DD/MM/YYYY"


# ---------------------------------------------------------------------------
# Tasks / Tareas de los partes
# ---------------------------------------------------------------------------

def _tasks_context(request, machine):
    """
    Context of the tasks table fragment.

    ---

    Contexto del fragmento de la tabla de tareas: filas, totales de lo
    listado, filtros vigentes y controles de orden (plantillas tontas).
    """
    params = _params(request, workshop.TASK_FILTER_KEYS)
    only_keys = _only_keys(request)
    rows = workshop.build_task_rows(
        machine, params, _can_open_stock(request), only_keys=only_keys,
    )
    return {
        "machine": machine,
        "rows": rows,
        "totals": workshop.task_totals(rows),
        "filters": params,
        "only_selected": only_keys is not None,
        "is_filtered": bool(
            any(params[key] for key in params if key != "sort")
            or only_keys is not None
        ),
        "table_url": reverse(
            "panel:machine_workshop_tasks_table", kwargs={"pk": machine.pk},
        ),
        "can_open_ticket": (
            request.user.company_user.role in workshop.TICKET_ROLES
        ),
        "can_open_stock": _can_open_stock(request),
        **workshop.sort_controls(params["sort"], workshop.TASK_SORTABLE),
    }


class MachineWorkshopTasksView(FleetAccessMixin, View):
    """
    Management page of the work-order tasks done on a machine.

    ---

    Página "Gestión" de los partes de una máquina: cada tarea de parte
    hecha sobre ella, con horas, repuestos e importe, sumatorio de lo
    listado y Excel de la selección.
    """

    def get(self, request, pk):
        """
        Render the page with the saved filters.

        ---

        Pinta la página con los filtros guardados del usuario.
        """
        from panel.navigation_persistence import apply_list_navigation

        machine = _machine(request, pk)
        apply_list_navigation(
            request, _screen_key("tasks", machine),
            workshop.TASK_FILTER_KEYS,
        )
        return render(request, TASKS_TEMPLATE, {
            **_page_context(request, machine, "tasks"),
            **_tasks_context(request, machine),
            **workshop.task_filter_options(machine),
            "all_totals": workshop.task_totals(
                workshop.build_task_rows(machine, {}, False),
            ),
        })


class MachineWorkshopTasksFragmentView(FleetAccessMixin, View):
    """
    Tasks table fragment (filters, order, selection).

    ---

    Fragmento de la tabla de tareas, para filtros, orden y "mostrar
    solo la selección". Guarda filtros y orden por usuario.
    """

    def get(self, request, pk):
        """
        Return the table fragment.

        ---

        Devuelve el fragmento de tabla.
        """
        from panel.navigation_persistence import apply_list_navigation

        machine = _machine(request, pk)
        apply_list_navigation(
            request, _screen_key("tasks", machine),
            workshop.TASK_FILTER_KEYS,
        )
        return render(
            request, TASKS_TABLE_TEMPLATE, _tasks_context(request, machine),
        )


class MachineWorkshopTasksExportView(FleetAccessMixin, View):
    """
    Excel of the selected tasks.

    ---

    Excel de las tareas seleccionadas (POST selected=l<pk>): hoja
    TAREAS y hoja REPUESTOS, cada una con su total.
    """

    def post(self, request, pk):
        """
        Build and return the workbook.

        ---

        Construye y devuelve el libro.
        """
        from openpyxl import Workbook

        machine = _machine(request, pk)
        rows = workshop.selected_task_rows(
            machine, request.POST.getlist("selected"),
            _can_open_stock(request),
        )
        if not rows:
            return HttpResponse(
                "No hay ninguna tarea seleccionada.", status=400,
            )
        workbook = Workbook()
        _write_tasks(workbook, rows)
        return _xlsx_response(workbook, "partes_%s" % machine.code)


# ---------------------------------------------------------------------------
# Breakdown tickets / Averías
# ---------------------------------------------------------------------------

def _tickets_context(request, machine):
    """
    Context of the breakdowns table fragment.

    ---

    Contexto del fragmento de la tabla de averías.
    """
    params = _params(request, workshop.TICKET_FILTER_KEYS)
    only_keys = _only_keys(request)
    rows = workshop.build_ticket_rows(
        machine, params, _can_open_stock(request), only_keys=only_keys,
    )
    return {
        "machine": machine,
        "rows": rows,
        "totals": workshop.ticket_totals(rows),
        "filters": params,
        "only_selected": only_keys is not None,
        "is_filtered": bool(
            any(params[key] for key in params if key != "sort")
            or only_keys is not None
        ),
        "can_open_ticket": (
            request.user.company_user.role in workshop.TICKET_ROLES
        ),
        "table_url": reverse(
            "panel:machine_workshop_tickets_table",
            kwargs={"pk": machine.pk},
        ),
        **workshop.sort_controls(params["sort"], workshop.TICKET_SORTABLE),
    }


class MachineWorkshopTicketsView(FleetAccessMixin, View):
    """
    Breakdowns page of a machine.

    ---

    Página "Averías" de una máquina: sus tickets de avería, con los
    partes que los atendieron, horas, repuestos gastados e importe.
    """

    def get(self, request, pk):
        """
        Render the page with the saved filters.

        ---

        Pinta la página con los filtros guardados del usuario.
        """
        from panel.navigation_persistence import apply_list_navigation

        machine = _machine(request, pk)
        apply_list_navigation(
            request, _screen_key("tickets", machine),
            workshop.TICKET_FILTER_KEYS,
        )
        return render(request, TICKETS_TEMPLATE, {
            **_page_context(request, machine, "tickets"),
            **_tickets_context(request, machine),
        })


class MachineWorkshopTicketsFragmentView(FleetAccessMixin, View):
    """
    Breakdowns table fragment (filters, order, selection).

    ---

    Fragmento de la tabla de averías. Guarda filtros y orden por
    usuario.
    """

    def get(self, request, pk):
        """
        Return the table fragment.

        ---

        Devuelve el fragmento de tabla.
        """
        from panel.navigation_persistence import apply_list_navigation

        machine = _machine(request, pk)
        apply_list_navigation(
            request, _screen_key("tickets", machine),
            workshop.TICKET_FILTER_KEYS,
        )
        return render(
            request, TICKETS_TABLE_TEMPLATE,
            _tickets_context(request, machine),
        )


TICKET_COLUMNS = (
    "Ticket", "Fecha", "Estado", "Urgencia", "Tipo", "Avería",
    "Asignado a", "Cerrado", "Tareas", "Horas ordinarias", "Horas extra",
    "Horas festivas", "Horas", "Repuestos",
    "Importe repuestos (€)", "Repuestos sin precio",
)


class MachineWorkshopTicketsExportView(FleetAccessMixin, View):
    """
    Excel of the selected breakdown tickets.

    ---

    Excel de las averías seleccionadas (POST selected=t<pk>): hoja
    AVERIAS y, de sus partes, hojas TAREAS y REPUESTOS.
    """

    def post(self, request, pk):
        """
        Build and return the workbook.

        ---

        Construye y devuelve el libro.
        """
        from openpyxl import Workbook

        machine = _machine(request, pk)
        rows = workshop.build_ticket_rows(
            machine, {"sort": "date"}, _can_open_stock(request),
            only_keys=set(request.POST.getlist("selected")),
        )
        if not rows:
            return HttpResponse(
                "No hay ninguna avería seleccionada.", status=400,
            )
        workbook = Workbook()
        sheet = _sheet(workbook, "AVERIAS", TICKET_COLUMNS, first=True)
        tasks = []
        for row in rows:
            sheet.append([
                row.code,
                timezone.localtime(row.created_at).replace(tzinfo=None)
                if row.created_at else None,
                row.status_label, row.urgency_label, row.tipo_label,
                row.summary, row.assigned,
                timezone.localtime(row.resolved_at).replace(tzinfo=None)
                if row.resolved_at else None,
                row.task_count, _number(row.ordinary_hours),
                _number(row.extra_hours), _number(row.festive_hours),
                _number(row.hours), row.parts_count,
                _number(row.parts_cost), row.parts_unpriced or None,
            ])
            tasks.extend(row.tasks)
        totals = workshop.ticket_totals(rows)
        _append_total(sheet, [
            "TOTAL", "", "", "", "", "%d averías" % totals["count"], "", "",
            totals["tasks"], _number(totals["ordinary"]),
            _number(totals["extra"]), _number(totals["festive"]),
            _number(totals["hours"]), totals["parts"],
            _number(totals["cost"]), totals["unpriced"] or None,
        ])
        for column in ("B", "H"):
            for cell in sheet[column][1:]:
                cell.number_format = "DD/MM/YYYY HH:MM"
        _write_tasks(workbook, tasks, first=False)
        return _xlsx_response(workbook, "averias_%s" % machine.code)


# ---------------------------------------------------------------------------
# Read-only document of a work order / Documento del parte
# ---------------------------------------------------------------------------

class WorkOrderDocumentView(FleetAccessMixin, View):
    """
    Read-only document of one work-order day.

    ---

    "Ver el parte" (S139): el parte presentado como documento, solo
    con lo grabado (horas, horario, pausa, dieta, cada tarea con sus
    horas, lecturas, revisión, repuestos con enlace a su artículo y a
    sus albaranes, fotos y justificaciones de jornada). No es la vista
    de edición. `?maquina=<pk>` marca las tareas de esa máquina.
    """

    def get(self, request, entry_pk):
        """
        Render the document.

        ---

        Pinta el documento.
        """
        company_user = request.user.company_user
        entry = get_object_or_404(
            WorkOrderEntry.objects.select_related(
                "work_order__reviewed_by__user",
            ),
            pk=entry_pk, work_order__company=company_user.company,
        )
        machine = None
        machine_raw = request.GET.get("maquina", "")
        if machine_raw.isdigit():
            machine = MachineAsset.objects.filter(
                pk=int(machine_raw), company=company_user.company,
            ).first()
        return render(request, DOCUMENT_TEMPLATE, {
            **workshop.work_order_document(entry, machine, company_user),
            "machine": machine,
            "fallback_back_url": (
                reverse(
                    "panel:machine_workshop_tasks",
                    kwargs={"pk": machine.pk},
                ) if machine is not None
                else reverse("panel:documentation_hub")
            ),
        })
