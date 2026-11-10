# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/export_templates.py
"""
The built-in "Panel view" export template (S148).

---

La plantilla de exportación "Vista del panel" (S148). Miguel Ángel:
"tener plantillas que sirvan también para las tres exportaciones, la
impresión, el PDF y el Excel [...] Y una plantilla por defecto, que es
la de la vista del propio panel".

Cada pantalla con plantillas de exportación (Personal, Repostajes...)
ofrece, además de las suyas, esta plantilla fija con las mismas
columnas que enseña la tabla del panel, en su orden. No se guarda en la
base de datos (id 0), no se edita ni se borra, y se puede "Usar como
base" para una propia. Es la que sale elegida salvo que el usuario haya
marcado otra suya como "por defecto". Las plantillas valen para Excel,
PDF e Imprimir: el formato lo pone el botón (panel/export_formats.py).
"""
from types import SimpleNamespace

PANEL_TEMPLATE_ID = 0
PANEL_TEMPLATE_NAME = "Vista del panel"


def panel_template(columns):
    """
    The panel-view template as an object like the stored ones.
    ---
    La plantilla de la vista del panel con la forma de las guardadas.
    """
    return SimpleNamespace(
        pk=PANEL_TEMPLATE_ID, name=PANEL_TEMPLATE_NAME,
        columns=list(columns), is_global=False, is_default=False,
        company_user_id=None,
    )


def with_panel_template(dicts, columns, auto_names=()):
    """
    The template dicts with the panel view first and the default mark.

    `auto_names`: (name, columns) of templates the app created by
    itself as default before S148; they no longer count as the user's
    chosen default.
    ---
    Las plantillas (diccionarios para el modal) con la vista del panel
    delante. La vista del panel queda "por defecto" salvo que el
    usuario haya marcado otra suya; las que creó la aplicación sola
    como por defecto antes de S148 (`auto_names`, mismo nombre y mismas
    columnas) ya no cuentan como elegidas por él.
    """
    for item in dicts:
        if item["is_default"] and (
                item["name"], list(item["columns"])) in [
                (name, list(cols)) for name, cols in auto_names]:
            item["is_default"] = False
    own_default = any(item["is_default"] for item in dicts)
    panel = {
        "id": PANEL_TEMPLATE_ID,
        "name": PANEL_TEMPLATE_NAME,
        "is_global": False,
        "is_default": not own_default,
        "columns": list(columns),
        "editable": False,
        "builtin": True,
    }
    return [panel] + list(dicts)


def find_template(raw_pk, templates, columns):
    """
    The template asked for (`raw_pk` from the request), or None.
    ---
    La plantilla pedida: "0" es la vista del panel; si no, una de
    `templates` (las que el usuario puede usar).
    """
    raw_pk = str(raw_pk or "")
    if not raw_pk.isdigit():
        return None
    if int(raw_pk) == PANEL_TEMPLATE_ID:
        return panel_template(columns)
    return next(
        (item for item in templates if item.pk == int(raw_pk)), None)
