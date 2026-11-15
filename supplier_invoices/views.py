# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/supplier_invoices/views.py
"""
Supplier invoices (Warehouse): list, reprocess and detail.

---

H28 (S151, sesión invasora). Almacén > Facturas de proveedor: las
facturas que el agente de facturas del PC de Ani sube al cubo, a
FACTURACION PROVEEDORES (carpeta propia, separada de cualquier otra;
nada de bandeja de entrada), con sus dos subcarpetas: "Facturas
nuevas" (las que entran y las que no se han podido procesar) y
"Facturas procesadas". Formato de la directriz 4.24: panel fijo
(subcarpetas, filtros y acciones) y lista con scroll propio, orden
múltiple, casillas, selección visible y navegación persistida por
usuario (4.15). Mismo acceso que Albaranes (`SupervisorAccessMixin`).
"""
import json

from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.views import View

from panel.mixins import SupervisorAccessMixin
from panel.navigation_persistence import (
    apply_list_navigation, get_saved_state_key,
)

from .invoice_service import requeue_invoices
from .models import SupplierInvoice

SCREEN_KEY = "warehouse_invoices"
FILTER_KEYS = ("folder", "search", "status", "sort")
MAX_ROWS = 500
FOLDER_NEW = "nuevas"
FOLDER_PROCESSED = "procesadas"
FOLDERS = (
    (FOLDER_NEW, "Facturas nuevas"),
    (FOLDER_PROCESSED, "Facturas procesadas"),
)

_SORT_VALUES = {
    "created": lambda i: i.created_at,
    "name": lambda i: i.original_name.upper(),
    "supplier": lambda i: i.supplier_name.upper() or None,
    "number": lambda i: i.invoice_number.upper() or None,
    "date": lambda i: i.invoice_date,
    "lines": lambda i: i.lines_count,
    "covered": lambda i: i.covered_count,
    "purchased": lambda i: i.purchased_count,
    "placed": lambda i: i.placed_count,
    "status": lambda i: i.get_status_display(),
}
_MAX_SORT_KEYS = 4
_COLUMNS = (
    ("created", "Subida"),
    ("name", "Archivo"),
    ("supplier", "Proveedor"),
    ("number", "Nº factura"),
    ("date", "Fecha"),
    ("lines", "Líneas"),
    ("covered", "Con albarán"),
    ("purchased", "Compradas"),
    ("placed", "Colocadas"),
    ("status", "Estado"),
)
_STATUS_BADGES = {
    SupplierInvoice.STATUS_PENDING: "text-bg-secondary",
    SupplierInvoice.STATUS_PROCESSING: "text-bg-info",
    SupplierInvoice.STATUS_PROCESSED: "text-bg-success",
    SupplierInvoice.STATUS_DUPLICATE: "text-bg-light border",
    SupplierInvoice.STATUS_NOT_INVOICE: "text-bg-warning",
    SupplierInvoice.STATUS_ERROR: "text-bg-danger",
}


def _parse_sort(raw):
    """
    "key,-key,..." -> [(key, descending)], valid unique keys only.

    ---

    "clave,-clave,..." -> [(clave, descendente)], solo claves válidas y
    sin repetir, como máximo _MAX_SORT_KEYS (formato S116/S117).
    """
    keys, seen = [], set()
    for token in (raw or "").split(","):
        token = token.strip()
        key = token.lstrip("-")
        if key in _SORT_VALUES and key not in seen:
            keys.append((key, token.startswith("-")))
            seen.add(key)
    return keys[:_MAX_SORT_KEYS]


def _sort_controls(raw):
    """
    Next "sort" value, arrow and priority of every column header.

    ---

    Valor de "sort" que envía cada cabecera, su flecha y su prioridad
    (4.24: clic promueve a principal, clic en la principal invierte).
    """
    sort_keys = _parse_sort(raw)
    active = [key for key, _desc in sort_keys]
    columns = []
    for key, label in _COLUMNS:
        if key in active:
            idx = active.index(key)
            desc = sort_keys[idx][1]
            arrow = "down" if desc else "up"
            priority = idx + 1 if len(sort_keys) > 1 else ""
            new_desc = (not desc) if idx == 0 else desc
            new_keys = [(key, new_desc)] + [
                (k, d) for k, d in sort_keys if k != key
            ]
        else:
            arrow, priority = "", ""
            new_keys = [(key, False)] + sort_keys
        columns.append({
            "key": key, "label": label, "arrow": arrow,
            "priority": priority,
            "next": ",".join(
                ("-" if d else "") + k for k, d in new_keys[:_MAX_SORT_KEYS]
            ),
        })
    return {
        "sort_columns": columns,
        "sort_active": bool(sort_keys),
        "current_sort": ",".join(
            ("-" if d else "") + k for k, d in sort_keys
        ),
    }


def _sort_rows(rows, sort_keys):
    """
    Stable multi-key sort (newest first by default); empties last.

    ---

    Orden estable por varias claves (por defecto, lo más reciente
    arriba); los vacíos siempre al final.
    """
    rows = sorted(rows, key=lambda i: (i.created_at, i.pk), reverse=True)
    for key, desc in reversed(sort_keys):
        getter = _SORT_VALUES[key]
        present = [i for i in rows if getter(i) is not None]
        missing = [i for i in rows if getter(i) is None]
        rows = sorted(present, key=getter, reverse=desc) + missing
    return rows


def _annotate(invoice):
    """
    Attach display data resolved in the view (dumb templates).

    ---

    Añade los datos que pinta la fila, resueltos aquí (plantillas
    tontas): color del estado y enlaces al detalle y al archivo.
    """
    invoice.status_badge = _STATUS_BADGES.get(
        invoice.status, "text-bg-secondary",
    )
    invoice.detail_url = reverse(
        "supplier_invoices:detail", args=[invoice.pk],
    )
    invoice.file_url = (
        reverse("panel:documentation_document_view", args=[invoice.entry_id])
        if invoice.entry_id else ""
    )
    invoice.is_open = invoice.status in SupplierInvoice.OPEN_STATUSES
    invoice.can_retry = (
        invoice.status in SupplierInvoice.RETRYABLE_STATUSES
    )
    return invoice


def _param(request, key, default=""):
    """
    Read from GET, falling back to the _f_ copy posted by actions.

    ---

    Lee de GET y, si no está, de la copia _f_ que envían las acciones.
    """
    return request.GET.get(key) or request.POST.get("_f_" + key, default)


def _folder_of(request):
    """
    Selected subfolder ("nuevas" by default).

    ---

    Subcarpeta elegida ("nuevas" si no hay ninguna).
    """
    folder = _param(request, "folder")
    return folder if folder in dict(FOLDERS) else FOLDER_NEW


def _list_context(request):
    """
    Context of the table fragment: filtered, annotated, sorted rows.

    ---

    Contexto del fragmento de tabla: facturas de la subcarpeta elegida,
    filtradas, anotadas y ordenadas, más los contadores de cada
    subcarpeta.
    """
    folder = _folder_of(request)
    search = _param(request, "search").strip()
    status = _param(request, "status")
    base = SupplierInvoice.objects.select_related("uploaded_by__user")
    done = SupplierInvoice.DONE_STATUSES
    folder_counts = {
        FOLDER_NEW: base.exclude(status__in=done).count(),
        FOLDER_PROCESSED: base.filter(status__in=done).count(),
    }
    qs = (
        base.filter(status__in=done) if folder == FOLDER_PROCESSED
        else base.exclude(status__in=done)
    ).order_by("-created_at", "-pk")
    if status in {code for code, _label in SupplierInvoice.STATUS_CHOICES}:
        qs = qs.filter(status=status)
    rows = [_annotate(invoice) for invoice in qs[:MAX_ROWS]]
    if search:
        needle = search.upper()
        rows = [
            i for i in rows
            if needle in " ".join((
                i.original_name, i.supplier_name, i.supplier_tax_id,
                i.invoice_number, i.reason,
            )).upper()
        ]
    if request.GET.get("only_selected") == "1":
        wanted = {
            pk for pk in request.GET.get("selected_ids", "").split(",")
            if pk.isdigit()
        }
        rows = [i for i in rows if str(i.pk) in wanted]
    rows = _sort_rows(rows, _parse_sort(_param(request, "sort")))
    return {
        "invoices": rows,
        "filter_folder": folder,
        "filter_search": search,
        "filter_status": status,
        "folders": [
            {"key": key, "label": label, "count": folder_counts[key],
             "active": key == folder}
            for key, label in FOLDERS
        ],
        "status_choices": SupplierInvoice.STATUS_CHOICES,
        "is_filtered": bool(search or status),
        "has_open": any(i.is_open for i in rows),
        **_sort_controls(_param(request, "sort")),
    }


class InvoicesPageView(SupervisorAccessMixin, View):
    """
    GET: Warehouse > Supplier invoices (fixed panel and list).

    ---

    GET: Almacén > Facturas de proveedor (panel fijo y lista).
    """

    def get(self, request):
        apply_list_navigation(request, SCREEN_KEY, FILTER_KEYS)
        saved_selection = get_saved_state_key(
            request.user.company_user, SCREEN_KEY, "selection", [],
        )
        if not isinstance(saved_selection, list):
            saved_selection = []
        return render(request, "supplier_invoices/invoice_list.html", {
            **_list_context(request),
            "screen_key": SCREEN_KEY,
            "saved_selection": saved_selection,
            "active_nav": "supplier_invoices",
        })


class InvoicesResultsView(SupervisorAccessMixin, View):
    """
    GET: only the table (subfolder, search, filter, sort), stored.

    ---

    GET: solo la tabla (subcarpeta, búsqueda, filtro, orden), guardada
    por usuario.
    """

    def get(self, request):
        apply_list_navigation(request, SCREEN_KEY, FILTER_KEYS)
        return render(
            request, "supplier_invoices/_table.html",
            _list_context(request),
        )


class InvoiceRetryView(SupervisorAccessMixin, View):
    """
    POST: process again the selected "not an invoice"/failed ones.

    ---

    POST: vuelve a procesar las facturas marcadas que salieron "no es
    una factura" o con error. Responde JSON con el resumen.
    """

    def post(self, request):
        try:
            payload = json.loads(request.body.decode("utf-8") or "{}")
        except (ValueError, UnicodeDecodeError):
            return JsonResponse(
                {"ok": False, "error": "Petición no válida."}, status=400,
            )
        ids = [
            int(pk) for pk in payload.get("selected") or []
            if str(pk).isdigit()
        ]
        if not ids:
            return JsonResponse(
                {"ok": False, "error": "No hay nada seleccionado."},
                status=400,
            )
        requeued, skipped = requeue_invoices(
            list(SupplierInvoice.objects.filter(pk__in=ids)),
            request.user.company_user,
        )
        message = "%d factura(s) en cola para procesar de nuevo." % requeued
        if skipped:
            message += (
                " %d saltada(s): solo se vuelven a procesar las que no "
                "eran una factura o dieron error." % skipped
            )
        return JsonResponse({"ok": True, "message": message})


class InvoiceDetailView(SupervisorAccessMixin, View):
    """
    GET: one invoice, its lines and the work orders it was placed in.

    ---

    GET: una factura, lo que se leyó de cada línea, su destino
    (albarán que la cubre, entrada en almacén) y las líneas de parte
    en las que se ha dado por colocada.
    """

    def get(self, request, pk):
        invoice = get_object_or_404(
            SupplierInvoice.objects.select_related(
                "supplier", "uploaded_by__user", "duplicate_of",
            ),
            pk=pk,
        )
        _annotate(invoice)
        lines = list(invoice.lines.select_related(
            "delivery_note_line__delivery_note", "spare_part_entry",
        ).prefetch_related(
            "placements__spare_part_line__entry_line__entry",
            "placements__spare_part_line__entry_line__machine_asset",
            "placements__spare_part_line__vehicle",
        ))
        for line in lines:
            note_line = line.delivery_note_line
            line.delivery_label = (
                "%s (%s)" % (
                    note_line.delivery_note.delivery_number or "s/n",
                    note_line.delivery_note.delivery_date.strftime(
                        "%d/%m/%Y",
                    ) if note_line.delivery_note.delivery_date else "s/f",
                )
                if note_line else ""
            )
            line.delivery_url = (
                reverse(
                    "delivery_notes:detail",
                    args=[note_line.delivery_note_id],
                )
                if note_line else ""
            )
            line.placement_rows = []
            for placement in line.placements.all():
                spare_line = placement.spare_part_line
                entry_line = spare_line.entry_line
                machine = spare_line.vehicle or entry_line.machine_asset
                line.placement_rows.append({
                    "date": entry_line.entry.work_date,
                    "worker": entry_line.entry.worker_name,
                    "machine": machine.code if machine else "",
                    "material": spare_line.material or spare_line.reference,
                    "quantity": placement.quantity,
                    "assumed": placement.quantity_assumed,
                    "match": placement.get_match_kind_display(),
                })
        return render(request, "supplier_invoices/detail.html", {
            "invoice": invoice,
            "lines": lines,
            "has_placements": any(line.placement_rows for line in lines),
            "uploaded_label": (
                invoice.uploaded_by.user.get_full_name()
                or invoice.uploaded_by.user.username
                if invoice.uploaded_by_id else "Agente de facturas"
            ),
            "active_nav": "supplier_invoices",
        })
