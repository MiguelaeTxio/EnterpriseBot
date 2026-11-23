# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/new_ui/screen_templates.py
"""
Column templates of the screen exports (the old interface's ones), new UI.

---

Plantillas de columnas de las exportaciones de pantalla en la nueva
interfaz (S163). Son las mismas que guarda la antigua
(panel.ScreenExportTemplate, por pantalla), así que las creadas allí
salen aquí y al revés; el código es propio. Pantallas: la hoja
«Jornadas» del registro de jornada («clock_days») y el informe del alta
en el fichaje («clock_onboarding»). El bloque común
(new_ui/_screen_tpl_block.html) las elige, guarda, modifica y borra.
"""
from django.http import JsonResponse
from django.shortcuts import render
from django.views import View

from new_ui.mixins import SuperuserRequiredMixin


def _screens():
    """{screen: [(key, label), ...]} of the screens with templates here."""
    from new_ui.clock_export import DAY_COLUMNS
    from new_ui.views_onboarding import COLUMNS

    return {
        "clock_days": [(c[0], c[1]) for c in DAY_COLUMNS],
        "clock_onboarding": [(c[0], c[1]) for c in COLUMNS],
    }


def _model():
    from panel.models import ScreenExportTemplate

    return ScreenExportTemplate


def _is_admin(company_user):
    return company_user.role in company_user.ADMIN_ROLES


def templates_for(company_user, screen):
    """
    The user's own templates of a screen and the company's global ones.

    ---

    Las plantillas propias de la pantalla y las globales de la empresa,
    con si se pueden modificar.
    """
    keys = {k for k, _label in _screens()[screen]}
    rows = _model().objects.filter(company=company_user.company,
                                   screen=screen)
    own = list(rows.filter(company_user=company_user, is_global=False)
               .order_by("-is_default", "name"))
    shared = list(rows.filter(is_global=True).order_by("name"))
    return [{
        "pk": t.pk, "name": t.name, "is_global": t.is_global,
        "is_default": t.is_default,
        "columns": [k for k in (t.columns or []) if k in keys],
        "editable": _is_admin(company_user) if t.is_global else True,
    } for t in own + shared]


def chosen_keys(request, screen, default_keys=None):
    """
    The marked column keys, in the chosen template's order if it fits.

    ---

    Las columnas marcadas, en el orden de la plantilla elegida si la
    hay, si no en el de siempre; sin ninguna marcada, `default_keys` (o
    todas).
    """
    order_all = [k for k, _label in _screens()[screen]]
    keys = [k for k in request.POST.getlist("columns") if k in order_all]
    if not keys:
        return list(default_keys or order_all)
    template = _model().objects.filter(
        pk=request.POST.get("template_pk") or 0,
        company=request.user.company_user.company, screen=screen).first()
    if template is not None:
        order = [k for k in (template.columns or []) if k in keys]
        return order + [k for k in keys if k not in order]
    return [k for k in order_all if k in keys]


def _screen(request):
    screen = request.POST.get("screen") or request.GET.get("screen") or ""
    return screen if screen in _screens() else None


def _editable(company_user, screen, pk):
    template = _model().objects.filter(
        pk=pk or 0, company=company_user.company, screen=screen).first()
    if template is None:
        return None
    if template.is_global:
        return template if _is_admin(company_user) else None
    return (template if template.company_user_id == company_user.pk
            else None)


def _json(ok, message):
    return JsonResponse({"ok": ok, "message": message},
                        status=200 if ok else 400)


class ScreenTemplateBlockView(SuperuserRequiredMixin, View):
    """
    GET ?screen=&panel=: the templates and columns block of a screen.

    ---

    GET: el bloque de plantillas y columnas de una pantalla (la de por
    defecto ya marcada; sin ninguna, `panel`: las de la vista del
    panel, o todas).
    """

    def get(self, request):
        screen = _screen(request)
        if screen is None:
            return JsonResponse({"error": "Pantalla desconocida."},
                                status=400)
        columns = _screens()[screen]
        templates = templates_for(request.user.company_user, screen)
        default = next((t for t in templates if t["is_default"]), None)
        panel = [k for k in (request.GET.get("panel") or "").split(",")
                 if k]
        checked = set(default["columns"] if default
                      else panel or [k for k, _l in columns])
        key = "".join(c for c in request.GET.get("key", "") if c.isalnum())
        return render(request, "new_ui/_screen_tpl_block.html", {
            "screen": screen,
            "radio_name": "nui_tpl_%s_%s" % (screen, key),
            "templates": templates,
            "default_pk": default["pk"] if default else "",
            "columns": [(k, label, k in checked) for k, label in columns],
            "panel_keys": ",".join(panel or [k for k, _l in columns]),
            "can_global": _is_admin(request.user.company_user),
        })


class ScreenTemplateSaveView(SuperuserRequiredMixin, View):
    """
    POST: save the marked columns as a template (new or the chosen one).

    ---

    POST: guarda las columnas marcadas como plantilla: nueva con el
    nombre escrito, o sobre la elegida («Modificar la elegida»).
    """

    def post(self, request):
        screen = _screen(request)
        if screen is None:
            return _json(False, "Pantalla desconocida.")
        cu = request.user.company_user
        valid = {k for k, _l in _screens()[screen]}
        name = (request.POST.get("name") or "").strip()[:100]
        keys = [k for k in request.POST.getlist("columns") if k in valid]
        if not keys:
            return _json(False, "Marca al menos una columna.")
        if request.POST.get("overwrite") == "1":
            template = _editable(cu, screen,
                                 request.POST.get("template_pk"))
            if template is None:
                return _json(False, "Elige una plantilla que puedas "
                             "modificar.")
            name = name or template.name
        else:
            if not name:
                return _json(False, "Escribe el nombre de la plantilla.")
            is_global = request.POST.get("is_global") == "1" and _is_admin(cu)
            template = _model()(
                company=cu.company, screen=screen, is_global=is_global,
                company_user=None if is_global else cu)
        same = _model().objects.filter(
            company=cu.company, screen=screen, name__iexact=name,
            is_global=template.is_global)
        if not template.is_global:
            same = same.filter(company_user=cu)
        if same.exclude(pk=template.pk).exists():
            return _json(False, "Ya hay una plantilla con ese nombre.")
        template.name = name
        template.columns = keys
        template.is_default = (request.POST.get("is_default") == "1"
                               and not template.is_global)
        template.save()
        if template.is_default:
            _model().objects.filter(
                company=cu.company, screen=screen, company_user=cu,
                is_global=False).exclude(pk=template.pk).update(
                is_default=False)
        return _json(True, "Plantilla «%s» guardada." % name)


class ScreenTemplateDeleteView(SuperuserRequiredMixin, View):
    """POST `template_pk`: delete a template the user may edit."""

    def post(self, request):
        screen = _screen(request)
        template = _editable(request.user.company_user, screen,
                             request.POST.get("template_pk")) if screen else None
        if template is None:
            return _json(False, "Elige una plantilla que puedas borrar.")
        name = template.name
        template.delete()
        return _json(True, "Plantilla «%s» borrada." % name)
