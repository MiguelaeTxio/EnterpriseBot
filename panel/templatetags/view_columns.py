# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/templatetags/view_columns.py
"""
Template tag with the columns the user sees in a panel list (S153).
---
Etiqueta con las columnas que el usuario ve en un listado del panel
(S153): las que pinta la pestaña "Columnas" al cargar la página, antes
de abrirla, para colocar la tabla sin esperar a ninguna petición.
"""
import json

from django import template

register = template.Library()


@register.simple_tag(takes_context=True)
def view_columns_json(context, screen_key):
    """
    JSON list of the column keys the user chose for `screen_key`.
    ---
    Lista JSON de las columnas elegidas ([] = las de siempre).
    """
    from panel.list_columns import STATE_PREFIX
    from panel.models import PanelNavigationState

    request = context.get("request")
    company_user = getattr(getattr(request, "user", None),
                           "company_user", None)
    if company_user is None:
        return "[]"
    state = (
        PanelNavigationState.objects
        .filter(company_user=company_user,
                screen_key=STATE_PREFIX + screen_key)
        .values_list("state", flat=True)
        .first()
    )
    columns = state.get("columns") if isinstance(state, dict) else None
    return json.dumps(columns if isinstance(columns, list) else [])


def _saved(context, screen_key):
    from panel.models import PanelNavigationState

    request = context.get("request")
    company_user = getattr(getattr(request, "user", None),
                           "company_user", None)
    if company_user is None:
        return {}
    state = (
        PanelNavigationState.objects
        .filter(company_user=company_user, screen_key=screen_key)
        .values_list("state", flat=True)
        .first()
    )
    return state if isinstance(state, dict) else {}


@register.simple_tag(takes_context=True)
def view_widths_json(context, screen_key):
    """
    JSON {column: px} of the widths the user set in a list.
    ---
    S153: los anchos de columna que el usuario ha puesto ({} = ninguno).
    """
    from panel.list_columns import STATE_PREFIX

    widths = _saved(context, STATE_PREFIX + screen_key).get("widths")
    return json.dumps(widths if isinstance(widths, dict) else {})


@register.simple_tag(takes_context=True)
def view_layout_split(context, key):
    """
    Saved width (%) of the list next to the selection, or "".
    ---
    S153: el ancho guardado (%) del listado junto a la selección.
    """
    from panel.list_columns import LAYOUT_PREFIX

    split = _saved(context, LAYOUT_PREFIX + key).get("split")
    return split if isinstance(split, (int, float)) else ""


@register.simple_tag(takes_context=True)
def view_layout_top(context, key):
    """
    Saved height (px) of the top panel of a list, or "".
    ---
    S153: el alto guardado (px) del panel de arriba de un listado.
    """
    from panel.list_columns import LAYOUT_PREFIX

    top = _saved(context, LAYOUT_PREFIX + key).get("top")
    return top if isinstance(top, (int, float)) else ""
