# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/list_columns.py
"""
Configurable columns of the panel lists (S153).

---

Columnas configurables de los listados del panel (S153). Miguel Ángel:
"en el panel de filtrado y buscado podamos tener la opción de
configurar qué es lo que vamos a ver en el listado, qué columna vamos a
ver y tener plantillas, igual que en la exportación [...] trasladar lo
que tenemos en la exportación [...] a la vista propia del panel".

Cada pantalla usa el mismo catálogo que su exportación
(panel/screen_export_catalog.py) y las mismas plantillas
(ScreenExportTemplate). Lo que ve cada usuario se guarda en su
PanelNavigationState (pantalla "view_columns:<pantalla>"), como los
filtros. Las columnas `fixed` de la pantalla (p. ej. el código) salen
siempre las primeras. La plantilla "Vista del panel" de la exportación
es, desde ahora, lo que el usuario ve en el panel.
"""
import datetime
import json
from decimal import Decimal

from django.http import JsonResponse
from django.views import View

from panel.mixins import CompanyUserRequiredMixin
from panel.models import PanelNavigationState

STATE_PREFIX = "view_columns:"


def _state(company_user, screen):
    saved = (
        PanelNavigationState.objects
        .filter(company_user=company_user,
                screen_key=STATE_PREFIX + screen.key)
        .values_list("state", flat=True)
        .first()
    )
    return saved if isinstance(saved, dict) else {}


def view_keys(company_user, screen):
    """
    The column keys the user sees in the panel, fixed ones first.
    ---
    Las claves de las columnas que el usuario ve en el panel: las fijas
    de la pantalla y, detrás, las elegidas (o las de la tabla de
    siempre, `panel_columns`, si nunca ha elegido).
    """
    from panel.screen_exports import valid_keys

    fixed = [k for k in screen.fixed if k in screen.by_key]
    chosen = _state(company_user, screen).get("columns")
    if not isinstance(chosen, list) or not chosen:
        # Sin catálogo, [] = todas las de la tabla en su orden.
        chosen = screen.panel_columns
    rest = [k for k in valid_keys(screen, chosen) if k not in fixed]
    return fixed + rest


def _display(value):
    """
    A catalogue value as text for a plain panel cell.
    ---
    Un valor del catálogo como texto para una celda simple del panel.
    """
    if value is None or value == "":
        return ""
    if isinstance(value, bool):
        return "Sí" if value else "No"
    if isinstance(value, datetime.datetime):
        return value.strftime("%d/%m/%Y %H:%M")
    if isinstance(value, datetime.date):
        return value.strftime("%d/%m/%Y")
    if isinstance(value, (float, Decimal)):
        return ("%.2f" % value).rstrip("0").rstrip(".").replace(".", ",")
    return str(value)


def view_context(company_user, screen, rows, sort_controls=None,
                 rich=()):
    """
    Context for a configurable table: headers and the cells of each row.
    ---
    Contexto de una tabla configurable. `view_columns`: cabeceras (sin
    las fijas) con su orden de columna; en cada fila, `view_cells`: la
    clave y, para las columnas que no tienen celda propia en la
    plantilla de la pantalla (`rich`), el valor ya como texto. Solo se
    calculan los valores de las columnas visibles.
    """
    sort_controls = sort_controls or {}
    arrows = sort_controls.get("sort_arrows", {})
    priority = sort_controls.get("sort_priority", {})
    following = sort_controls.get("sort_next", {})
    keys = [k for k in view_keys(company_user, screen)
            if k not in screen.fixed]
    columns = [screen.by_key[k] for k in keys]
    headers = []
    for column in columns:
        sort = column.sort
        headers.append({
            "key": column.key,
            "label": column.short_label or column.label,
            "title": column.label,
            "css": column.css,
            "sort": sort,
            "sort_next": following.get(sort, "") if sort else "",
            "arrow": arrows.get(sort, "") if sort else "",
            "priority": priority.get(sort, "") if sort else "",
        })
    plain = [c for c in columns if c.key not in rich]
    for row in rows:
        values = {c.key: _display(c.getter(row)) for c in plain}
        row.view_cells = [
            {"key": c.key, "label": c.label, "css": c.css,
             "rich": c.key in rich, "value": values.get(c.key, "")}
            for c in columns
        ]
    return {"view_columns": headers}


class ViewColumnsSaveView(CompanyUserRequiredMixin, View):
    """
    POST (JSON) {screen, columns[], template}: the user's panel columns.
    ---
    POST (JSON): guarda las columnas que el usuario quiere ver en el
    listado de esa pantalla y la plantilla de la que salen (o ninguna).
    """

    def post(self, request):
        from panel.screen_exports import get_screen

        company_user = request.user.company_user
        try:
            data = json.loads(request.body or b"{}")
        except ValueError:
            return JsonResponse({"error": "Datos no válidos."}, status=400)
        screen = get_screen(data.get("screen"))
        from panel.screen_exports import valid_keys

        obj, _created = PanelNavigationState.objects.get_or_create(
            company_user=company_user,
            screen_key=STATE_PREFIX + screen.key,
            defaults={"state": {}},
        )
        state = obj.state if isinstance(obj.state, dict) else {}
        if "widths" in data:
            # S153: anchos de columna (arrastrando el borde de la
            # cabecera), en píxeles; sin anchos = los de siempre.
            widths = data.get("widths")
            state["widths"] = {
                k: int(v) for k, v in (
                    widths.items() if isinstance(widths, dict) else [])
                if valid_keys(screen, [k]) and isinstance(v, (int, float))
                and 30 <= v <= 1200
            }
        if "columns" in data:
            columns = [
                k for k in valid_keys(screen, data.get("columns") or [])
                if k not in screen.fixed]
            if not columns:
                return JsonResponse(
                    {"error": "Elige al menos una columna."}, status=400)
            template = data.get("template")
            state["columns"] = columns
            state["template"] = (
                template if isinstance(template, int) else None)
        obj.state = state
        obj.save(update_fields=["state", "updated_at"])
        return JsonResponse({"ok": True})


LAYOUT_PREFIX = "view_layout:"


class ViewLayoutSaveView(CompanyUserRequiredMixin, View):
    """
    POST (JSON) {key, split}: width of the list next to the selection.
    ---
    S153 (Miguel Ángel: "hacer crecer el panel de vista de selección y
    el panel de vista de listado para poder hacerlos uno más ancho que
    otro"). Guarda, por usuario y panel inferior (`key`, el id del
    panel), el porcentaje de ancho del listado; null = el de siempre.
    """

    def post(self, request):
        import re

        try:
            data = json.loads(request.body or b"{}")
        except ValueError:
            return JsonResponse({"error": "Datos no válidos."}, status=400)
        key = data.get("key") or ""
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", key):
            return JsonResponse({"error": "Panel no válido."}, status=400)
        obj, _created = PanelNavigationState.objects.get_or_create(
            company_user=request.user.company_user,
            screen_key=LAYOUT_PREFIX + key,
            defaults={"state": {}},
        )
        state = obj.state if isinstance(obj.state, dict) else {}
        if "split" in data:
            split = data.get("split")
            if split is not None and not (
                    isinstance(split, (int, float)) and 15 <= split <= 95):
                return JsonResponse(
                    {"error": "Ancho no válido."}, status=400)
            state["split"] = round(split, 1) if split else None
        if "top" in data:
            # S153: alto (px) del panel de arriba (filtros, grupos y
            # acciones); el listado ocupa el resto. null = automático.
            top = data.get("top")
            if top is not None and not (
                    isinstance(top, (int, float)) and 60 <= top <= 2000):
                return JsonResponse(
                    {"error": "Alto no válido."}, status=400)
            state["top"] = int(top) if top else None
        obj.state = state
        obj.save(update_fields=["state", "updated_at"])
        return JsonResponse({"ok": True})


def view_state(company_user, screen):
    """
    What the "Columnas" tab needs: current, standard and fixed columns.
    ---
    Lo que necesita la pestaña "Columnas": las columnas que se ven, las
    de siempre de la tabla, las fijas y la plantilla elegida.
    """
    state = _state(company_user, screen)
    return {
        "current": [k for k in view_keys(company_user, screen)
                    if k not in screen.fixed],
        "standard": [k for k in screen.panel_columns
                     if k not in screen.fixed],
        "fixed": list(screen.fixed),
        "template": state.get("template"),
        # S153: sin catálogo, las columnas las da la cabecera de la tabla.
        "dynamic": screen.dynamic,
    }


def export_panel_columns(company_user, export_id, standard):
    """
    The export columns of "Vista del panel": what the list shows now.
    ---
    S153: las columnas de la exportación de la plantilla "Vista del
    panel" = las que el usuario ve ahora en el listado de esa pantalla,
    en su orden (panel/view_screens.EXPORT_VIEWS). Si nunca ha elegido
    columnas, las de siempre (`standard`).
    """
    from panel.view_screens import EXPORT_VIEWS

    spec = EXPORT_VIEWS.get(export_id)
    if spec is None:
        return list(standard)
    saved = (
        PanelNavigationState.objects
        .filter(company_user=company_user,
                screen_key=STATE_PREFIX + spec["view"])
        .values_list("state", flat=True)
        .first()
    )
    chosen = saved.get("columns") if isinstance(saved, dict) else None
    if not isinstance(chosen, list) or not chosen:
        return list(standard)
    result = list(spec["fixed"])
    for key in chosen:
        for column in spec["map"].get(key, []):
            if column not in result:
                result.append(column)
    return result

