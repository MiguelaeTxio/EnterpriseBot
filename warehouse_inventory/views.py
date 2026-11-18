# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/warehouse_inventory/views.py
"""
Photo-based warehouse inventory (Warehouse): capture and differences.

---

H10 (S151, sesión invasora). Almacén > Inventario por fotos. Solo para
Miguel Ángel de momento (superusuario, `SuperuserRequiredMixin`):

- Captura (pensada para el móvil): se abre un recuento, se escribe la
  ubicación y se hacen fotos; cada una se sube al momento y se lee en
  segundo plano.
- Diferencias (formato de la directriz 4.24): lo que no cuadra con el
  almacén digital, con orden múltiple, casillas y selección; Miguel
  Ángel confirma (ajusta el stock) o descarta cada una.
"""
import json

from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views import View

from panel.mixins import SuperuserRequiredMixin
from panel.navigation_persistence import (
    apply_list_navigation, get_saved_state_key,
)

from .inventory_service import (
    InventoryUploadError, close_count, location_for, open_count,
    register_photo, reopen_count, resolve_differences, start_count,
)
from .models import (
    InventoryCount, InventoryDifference, InventoryLocation, InventoryPhoto,
)

SCREEN_KEY = "warehouse_inventory_differences"
FILTER_KEYS = ("search", "kind", "status", "sort")
RECENT_PHOTOS = 60

_STATUS_BADGES = {
    InventoryPhoto.STATUS_PENDING: "text-bg-secondary",
    InventoryPhoto.STATUS_PROCESSING: "text-bg-info",
    InventoryPhoto.STATUS_DONE: "text-bg-success",
    InventoryPhoto.STATUS_ERROR: "text-bg-danger",
}
_DIFF_BADGES = {
    InventoryDifference.STATUS_PENDING: "text-bg-warning",
    InventoryDifference.STATUS_APPLIED: "text-bg-success",
    InventoryDifference.STATUS_DISCARDED: "text-bg-light border",
}
_KIND_BADGES = {
    InventoryDifference.KIND_NEW: "text-bg-primary",
    InventoryDifference.KIND_QUANTITY: "text-bg-warning",
    InventoryDifference.KIND_NOT_SEEN: "text-bg-danger",
}

_ACTION_TEXTS = {
    InventoryDifference.KIND_NEW: (
        "Al confirmar: alta en el almacén con lo contado."
    ),
    InventoryDifference.KIND_QUANTITY: (
        "Al confirmar: el stock pasa a lo contado."
    ),
    InventoryDifference.KIND_NOT_SEEN: (
        "Al confirmar: el stock pasa a cero (o a vacío si es incontable)."
    ),
}

_SORT_VALUES = {
    "kind": lambda d: d.get_kind_display(),
    "reference": lambda d: d.reference.upper() or None,
    "description": lambda d: d.description.upper(),
    "locations": lambda d: d.locations.upper() or None,
    "counted": lambda d: d.counted_quantity,
    "system": lambda d: d.system_quantity,
    "status": lambda d: d.get_status_display(),
}
_MAX_SORT_KEYS = 4
_COLUMNS = (
    ("kind", "Tipo"),
    ("reference", "Referencia"),
    ("description", "Descripción"),
    ("locations", "Ubicación"),
    ("counted", "Contado"),
    ("system", "En el sistema"),
    ("status", "Estado"),
)


def _number(value):
    """
    Decimal -> short text without useless decimals ("" if None).

    ---

    Decimal -> texto corto, sin decimales inútiles ("" si no hay).
    """
    if value is None:
        return ""
    return ("%f" % value).rstrip("0").rstrip(".")


# ---------------------------------------------------------------------
# Captura
# ---------------------------------------------------------------------

def _photo_rows(count):
    """
    Last photos of a stocktake with their items, resolved for display.

    ---

    Últimas fotos del recuento con lo leído en cada una, resueltas aquí
    (plantillas tontas).
    """
    photos = list(
        count.photos.select_related("location")
        .prefetch_related("items__spare_part_entry")[:RECENT_PHOTOS]
    )
    for photo in photos:
        photo.badge = _STATUS_BADGES.get(photo.status, "text-bg-secondary")
        photo.is_open = photo.status in InventoryPhoto.OPEN_STATUSES
        photo.file_url = (
            reverse("panel:documentation_document_view", args=[photo.entry_id])
            if photo.entry_id else ""
        )
        photo.item_rows = [
            {
                "label": " · ".join(
                    part for part in (
                        item.reference, item.brand, item.description,
                    ) if part
                ),
                "quantity": _number(item.quantity) or "?",
                "estimate": item.quantity_is_estimate,
                "source": item.get_source_display(),
                "matched": item.spare_part_entry_id is not None,
                "match": item.get_match_kind_display(),
            }
            for item in photo.items.all()
        ]
    return photos


def _pending_differences(count):
    return count.differences.filter(
        status=InventoryDifference.STATUS_PENDING,
    ).count()


class InventoryHomeView(SuperuserRequiredMixin, View):
    """
    GET: capture screen (open stocktake) and past stocktakes.

    ---

    GET: pantalla de captura del recuento abierto (o el botón para
    empezar uno) y los recuentos anteriores.
    """

    def get(self, request):
        company = request.user.company_user.company
        current = open_count(company)
        past = list(
            InventoryCount.objects.filter(
                company=company, closed_at__isnull=False,
            )[:20]
        )
        for count in past:
            count.pending = _pending_differences(count)
            count.photo_total = count.photos.count()
        context = {
            "count": current,
            "past_counts": past,
            "locations": InventoryLocation.objects.filter(company=company),
            "active_nav": "warehouse_inventory",
        }
        if current is not None:
            photos = _photo_rows(current)
            context.update({
                "photos": photos,
                "has_open": any(p.is_open for p in photos),
                "photo_total": current.photos.count(),
                "pending": _pending_differences(current),
            })
        return render(request, "warehouse_inventory/home.html", context)


class InventoryStartView(SuperuserRequiredMixin, View):
    """
    POST: open a stocktake.

    ---

    POST: empieza un recuento (si ya hay uno abierto, sigue con ese).
    """

    def post(self, request):
        start_count(request.user.company_user)
        return redirect("warehouse_inventory:home")


class InventoryUploadView(SuperuserRequiredMixin, View):
    """
    POST: one photo of the open stocktake (multipart). JSON reply.

    ---

    POST: una foto del recuento abierto con su ubicación. Responde JSON.
    """

    def post(self, request):
        company_user = request.user.company_user
        count = open_count(company_user.company)
        if count is None:
            return JsonResponse(
                {"ok": False, "error": "No hay ningún recuento abierto."},
                status=400,
            )
        upload = request.FILES.get("photo")
        if upload is None:
            return JsonResponse(
                {"ok": False, "error": "No ha llegado ninguna foto."},
                status=400,
            )
        try:
            location = location_for(
                company_user.company, request.POST.get("location"),
            )
            photo = register_photo(
                count, location, upload.read(), upload.name, company_user,
            )
        except InventoryUploadError as exc:
            return JsonResponse({"ok": False, "error": str(exc)}, status=400)
        return JsonResponse({
            "ok": True,
            "message": "Foto %s subida (%s)." % (photo.pk, location.name),
        })


class InventoryPhotosView(SuperuserRequiredMixin, View):
    """
    GET: photo list fragment of a stocktake (polled while reading).

    ---

    GET: fragmento con las fotos del recuento y lo leído en cada una (se
    refresca mientras queda alguna por leer).
    """

    def get(self, request, pk):
        count = get_object_or_404(
            InventoryCount, pk=pk,
            company=request.user.company_user.company,
        )
        photos = _photo_rows(count)
        return render(request, "warehouse_inventory/_photos.html", {
            "count": count,
            "photos": photos,
            "has_open": any(p.is_open for p in photos),
            "photo_total": count.photos.count(),
            "pending": _pending_differences(count),
        })


class InventoryCloseView(SuperuserRequiredMixin, View):
    """
    POST: close the stocktake and go to its differences.

    ---

    POST: cierra el recuento (aparece lo que no se ha visto) y lleva a
    sus diferencias.
    """

    def post(self, request, pk):
        count = get_object_or_404(
            InventoryCount, pk=pk,
            company=request.user.company_user.company,
        )
        if count.photos.filter(
            status__in=InventoryPhoto.OPEN_STATUSES,
        ).exists():
            messages.error(
                request,
                "Todavía hay fotos leyéndose: espera a que terminen para "
                "cerrar el recuento.",
            )
            return redirect("warehouse_inventory:home")
        close_count(count)
        messages.success(
            request,
            "Recuento cerrado. Revisa las diferencias: nada cambia en el "
            "almacén hasta que las confirmes.",
        )
        return redirect("warehouse_inventory:differences", pk=count.pk)


class InventoryReopenView(SuperuserRequiredMixin, View):
    """
    POST: reopen a stocktake closed too early.

    ---

    POST: reabre un recuento cerrado antes de tiempo y vuelve a las
    fotos para seguir.
    """

    def post(self, request, pk):
        count = get_object_or_404(
            InventoryCount, pk=pk,
            company=request.user.company_user.company,
        )
        if reopen_count(count):
            messages.success(
                request,
                "Recuento reabierto: sigue haciendo fotos y ciérralo cuando "
                "hayas pasado por todos los almacenes.",
            )
            return redirect("warehouse_inventory:home")
        messages.error(
            request,
            "Hay otro recuento abierto: ciérralo antes de reabrir este.",
        )
        return redirect("warehouse_inventory:differences", pk=count.pk)


# ---------------------------------------------------------------------
# Diferencias (directriz 4.24)
# ---------------------------------------------------------------------

def _parse_sort(raw):
    """
    "key,-key,..." -> [(key, descending)], valid unique keys only.

    ---

    "clave,-clave,..." -> [(clave, descendente)], solo claves válidas y
    sin repetir, como máximo _MAX_SORT_KEYS.
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

    Valor de "sort" de cada cabecera, su flecha y su prioridad (4.24:
    clic promueve a principal, clic en la principal invierte).
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
    Stable multi-key sort; empties last.

    ---

    Orden estable por varias claves (por defecto, tipo y descripción);
    los vacíos siempre al final.
    """
    rows = sorted(rows, key=lambda d: (d.kind, d.description.upper()))
    for key, desc in reversed(sort_keys):
        getter = _SORT_VALUES[key]
        present = [d for d in rows if getter(d) is not None]
        missing = [d for d in rows if getter(d) is None]
        rows = sorted(present, key=getter, reverse=desc) + missing
    return rows


def _param(request, key, default=""):
    return request.GET.get(key) or request.POST.get("_f_" + key, default)


def _differences_context(request, count):
    """
    Context of the differences table: filtered, annotated, sorted.

    ---

    Contexto de la tabla de diferencias: filtradas, anotadas y
    ordenadas.
    """
    search = _param(request, "search").strip()
    kind = _param(request, "kind")
    status = _param(request, "status")
    qs = count.differences.select_related("spare_part_entry")
    if kind in dict(InventoryDifference.KIND_CHOICES):
        qs = qs.filter(kind=kind)
    if status in dict(InventoryDifference.STATUS_CHOICES):
        qs = qs.filter(status=status)
    rows = list(qs)
    if search:
        needle = search.upper()
        rows = [
            d for d in rows
            if needle in " ".join((
                d.reference, d.description, d.locations,
            )).upper()
        ]
    if request.GET.get("only_selected") == "1":
        wanted = {
            pk for pk in request.GET.get("selected_ids", "").split(",")
            if pk.isdigit()
        }
        rows = [d for d in rows if str(d.pk) in wanted]
    for diff in rows:
        diff.kind_badge = _KIND_BADGES.get(diff.kind, "text-bg-secondary")
        diff.status_badge = _DIFF_BADGES.get(diff.status, "text-bg-secondary")
        diff.counted_text = _number(diff.counted_quantity) or "?"
        diff.system_text = (
            _number(diff.system_quantity)
            if diff.system_quantity is not None
            else ("incontable" if diff.spare_part_entry_id else "—")
        )
        diff.is_pending = diff.status == InventoryDifference.STATUS_PENDING
        diff.action_text = _ACTION_TEXTS[diff.kind]
    rows = _sort_rows(rows, _parse_sort(_param(request, "sort")))
    return {
        "count": count,
        "differences": rows,
        "filter_search": search,
        "filter_kind": kind,
        "filter_status": status,
        "kind_choices": InventoryDifference.KIND_CHOICES,
        "status_choices": InventoryDifference.STATUS_CHOICES,
        "is_filtered": bool(search or kind or status),
        **_sort_controls(_param(request, "sort")),
    }


def _count_for(request, pk):
    return get_object_or_404(
        InventoryCount, pk=pk, company=request.user.company_user.company,
    )


class DifferencesPageView(SuperuserRequiredMixin, View):
    """
    GET: differences of a stocktake (fixed panel and list).

    ---

    GET: diferencias de un recuento (panel fijo y lista).
    """

    def get(self, request, pk):
        count = _count_for(request, pk)
        apply_list_navigation(request, SCREEN_KEY, FILTER_KEYS)
        saved_selection = get_saved_state_key(
            request.user.company_user, SCREEN_KEY, "selection", [],
        )
        if not isinstance(saved_selection, list):
            saved_selection = []
        return render(request, "warehouse_inventory/differences.html", {
            **_differences_context(request, count),
            "screen_key": SCREEN_KEY,
            "saved_selection": saved_selection,
            "active_nav": "warehouse_inventory",
        })


class DifferencesResultsView(SuperuserRequiredMixin, View):
    """
    GET: only the differences table (search, filters, sort), stored.

    ---

    GET: solo la tabla de diferencias (búsqueda, filtros, orden),
    guardada por usuario.
    """

    def get(self, request, pk):
        count = _count_for(request, pk)
        apply_list_navigation(request, SCREEN_KEY, FILTER_KEYS)
        return render(
            request, "warehouse_inventory/_differences_table.html",
            _differences_context(request, count),
        )


class DifferencesResolveView(SuperuserRequiredMixin, View):
    """
    POST: confirm or discard the selected differences. JSON reply.

    ---

    POST: confirma (ajusta el stock) o descarta las diferencias marcadas.
    Responde JSON con el resumen.
    """

    def post(self, request, pk):
        _count_for(request, pk)
        try:
            payload = json.loads(request.body.decode("utf-8") or "{}")
        except (ValueError, UnicodeDecodeError):
            return JsonResponse(
                {"ok": False, "error": "Petición no válida."}, status=400,
            )
        ids = [
            int(value) for value in payload.get("selected") or []
            if str(value).isdigit()
        ]
        action = payload.get("action")
        if not ids or action not in ("apply", "discard"):
            return JsonResponse(
                {"ok": False, "error": "No hay nada seleccionado."},
                status=400,
            )
        done, warnings = resolve_differences(
            ids, request.user.company_user, apply=action == "apply",
        )
        message = "%d diferencia(s) %s." % (
            done, "confirmadas y aplicadas al almacén"
            if action == "apply" else "descartadas",
        )
        if warnings:
            message += " No se pudo: " + "; ".join(warnings[:5])
        return JsonResponse({"ok": True, "message": message})
