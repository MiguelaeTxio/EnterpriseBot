# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/screen_exports.py
"""
Export templates for the panel screens without their own (S148).

---

Plantillas de exportación de las pantallas del panel que no tenían
modelo propio (S148). Miguel Ángel: "tener plantillas que sirvan
también para las tres exportaciones, la impresión, el PDF y el Excel,
siguiendo la misma filosofía que tenemos de plantilla para poder
reutilizarla. Y una plantilla por defecto, que es la de la vista del
propio panel".

Cada pantalla se declara con `Screen` (clave, catálogo de columnas y
las columnas de su tabla en el panel) en panel/screen_export_catalog.py.
Las plantillas propias y globales viven en panel.ScreenExportTemplate;
la "Vista del panel" es fija (panel/export_templates.py). Las vistas de
aquí sirven al modal común panel/_screen_export_modal.html, y cada
exportación pide sus columnas con `columns_for(request, screen)`: la
plantilla de `template_pk` o, sin ella, la por defecto del usuario.
"""
import json
from dataclasses import dataclass, field

from django.http import Http404, JsonResponse
from django.views import View

from ivr_config.models import CompanyUser
from panel.export_templates import (
    PANEL_TEMPLATE_ID, find_template, panel_template, with_panel_template,
)
from panel.mixins import CompanyUserRequiredMixin


@dataclass
class Column:
    """
    One exportable column.
    ---
    Una columna exportable: clave, cabecera, ancho, getter (recibe la
    fila), formato de número de Excel y si se suma en la fila de total.
    """

    key: str
    label: str
    width: int
    getter: object
    number_format: str = None
    summed: bool = False


@dataclass
class Screen:
    """
    An exportable screen.
    ---
    Una pantalla exportable: su clave, su nombre, el catálogo de
    columnas y las de su tabla en el panel ("Vista del panel").
    """

    key: str
    label: str
    columns: tuple
    panel_columns: list
    by_key: dict = field(default_factory=dict)

    def __post_init__(self):
        self.by_key = {column.key: column for column in self.columns}


SCREENS = {}


def register(screen):
    """
    Adds a screen to the registry.
    ---
    Da de alta una pantalla en el registro.
    """
    SCREENS[screen.key] = screen
    return screen


def get_screen(key):
    """
    The screen of `key` (404 if unknown).
    ---
    La pantalla de `key` (404 si no existe).
    """
    import panel.screen_export_catalog  # noqa: F401  (registra)

    screen = SCREENS.get(key or "")
    if screen is None:
        raise Http404("Pantalla de exportación desconocida.")
    return screen


def _model():
    from panel.models import ScreenExportTemplate

    return ScreenExportTemplate


def _is_admin(company_user):
    return company_user.role in CompanyUser.ADMIN_ROLES


def visible_templates(company_user, screen):
    """
    The user's own templates of the screen and the company's global ones.
    ---
    Las plantillas propias de la pantalla y las globales de la empresa.
    """
    templates = _model().objects.filter(
        company=company_user.company, screen=screen.key)
    own = templates.filter(company_user=company_user, is_global=False)
    shared = templates.filter(is_global=True)
    return list(own.order_by("-is_default", "name")) + list(
        shared.order_by("name"))


def _as_dict(template, company_user, screen):
    return {
        "id": template.pk,
        "name": template.name,
        "is_global": template.is_global,
        "is_default": template.is_default,
        "columns": [k for k in template.columns if k in screen.by_key],
        "editable": (
            _is_admin(company_user) if template.is_global
            else template.company_user_id == company_user.pk),
    }


def _editable_template(company_user, pk):
    template = _model().objects.filter(
        pk=pk, company=company_user.company).first()
    if template is None:
        return None
    if template.is_global:
        return template if _is_admin(company_user) else None
    return template if template.company_user_id == company_user.pk else None


def columns_for(request, screen):
    """
    The columns to export: those of `template_pk` or the default ones.
    ---
    Las columnas a exportar: las de la plantilla `template_pk` (GET o
    POST) o, sin ella (enlaces directos), la plantilla por defecto del
    usuario o la "Vista del panel". None si la plantilla no es suya.
    """
    company_user = request.user.company_user
    templates = visible_templates(company_user, screen)
    raw = request.GET.get("template_pk") or request.POST.get("template_pk")
    if raw in (None, ""):
        template = next(
            (t for t in templates
             if t.is_default and not t.is_global), None,
        ) or panel_template(screen.panel_columns)
    else:
        template = find_template(raw, templates, screen.panel_columns)
    if template is None:
        return None
    return [screen.by_key[k] for k in template.columns
            if k in screen.by_key]


def write_sheet(sheet, columns, rows, total_label=None):
    """
    Header, rows and (optionally) a total row on an openpyxl sheet.
    ---
    Escribe en la hoja la cabecera (negrita, fija), una fila por
    elemento con los getters de `columns`, los anchos y formatos y, con
    `total_label`, una fila de total que suma las columnas `summed`.
    """
    from openpyxl.styles import Font
    from openpyxl.utils import get_column_letter

    sheet.append([column.label for column in columns])
    for cell in sheet[1]:
        cell.font = Font(bold=True)
    sheet.freeze_panes = "A2"
    sums = [0 if column.summed else None for column in columns]
    count = 0
    for row in rows:
        values = [column.getter(row) for column in columns]
        sheet.append(values)
        count += 1
        for index, value in enumerate(values):
            if sums[index] is not None and isinstance(value, (int, float)):
                sums[index] += value
    for index, column in enumerate(columns, start=1):
        letter = get_column_letter(index)
        sheet.column_dimensions[letter].width = column.width
        if column.number_format:
            for cell in sheet[letter][1:]:
                cell.number_format = column.number_format
    if total_label and any(s is not None for s in sums):
        total = [round(s, 2) if s is not None else None for s in sums]
        if total[0] is None:
            total[0] = "%s (%d)" % (total_label, count)
        sheet.append(total)
        for cell in sheet[sheet.max_row]:
            cell.font = Font(bold=True)
    return count


class ScreenExportTemplateListView(CompanyUserRequiredMixin, View):
    """
    GET ?screen=: the templates of the screen and its column catalogue.
    ---
    GET ?screen=: las plantillas de la pantalla (con la "Vista del
    panel" delante) y su catálogo de columnas.
    """

    def get(self, request):
        company_user = request.user.company_user
        screen = get_screen(request.GET.get("screen"))
        return JsonResponse({
            "templates": with_panel_template(
                [_as_dict(t, company_user, screen)
                 for t in visible_templates(company_user, screen)],
                screen.panel_columns),
            "columns": [{"key": c.key, "label": c.label}
                        for c in screen.columns],
            "is_admin": _is_admin(company_user),
        })


class ScreenExportTemplateSaveView(CompanyUserRequiredMixin, View):
    """
    POST (JSON) {id?, screen, name, columns[], is_default, is_global}.
    ---
    POST (JSON): crea (sin id) o actualiza (con id) una plantilla.
    """

    def post(self, request):
        company_user = request.user.company_user
        try:
            data = json.loads(request.body or b"{}")
        except ValueError:
            return JsonResponse({"error": "Datos no válidos."}, status=400)
        screen = get_screen(data.get("screen"))
        name = (data.get("name") or "").strip()[:100]
        columns = [k for k in (data.get("columns") or [])
                   if k in screen.by_key]
        if not name:
            return JsonResponse({"error": "Falta el nombre."}, status=400)
        if not columns:
            return JsonResponse(
                {"error": "Elige al menos una columna."}, status=400)
        pk = data.get("id")
        if pk and int(pk) != PANEL_TEMPLATE_ID:
            template = _editable_template(company_user, pk)
            if template is None or template.screen != screen.key:
                return JsonResponse(
                    {"error": "No puedes modificar esta plantilla."},
                    status=403)
        else:
            is_global = bool(data.get("is_global")) and _is_admin(
                company_user)
            template = _model()(
                company=company_user.company, screen=screen.key,
                is_global=is_global,
                company_user=None if is_global else company_user)
        same_name = _model().objects.filter(
            company=company_user.company, screen=screen.key,
            name__iexact=name, is_global=template.is_global)
        if not template.is_global:
            same_name = same_name.filter(company_user=company_user)
        if same_name.exclude(pk=template.pk).exists():
            return JsonResponse(
                {"error": "Ya hay una plantilla con ese nombre."},
                status=400)
        template.name = name
        template.columns = columns
        template.is_default = (
            bool(data.get("is_default")) and not template.is_global)
        template.save()
        return JsonResponse({"ok": True, "id": template.pk})


class ScreenExportTemplateDeleteView(CompanyUserRequiredMixin, View):
    """
    POST: deletes a template the user may edit.
    ---
    POST: borra una plantilla que el usuario puede editar.
    """

    def post(self, request, pk):
        template = _editable_template(request.user.company_user, pk)
        if template is None:
            return JsonResponse(
                {"error": "No puedes borrar esta plantilla."}, status=403)
        template.delete()
        return JsonResponse({"ok": True})
