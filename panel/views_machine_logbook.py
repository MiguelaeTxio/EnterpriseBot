# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/views_machine_logbook.py
"""
H23 (S154, invasora). Generate the crane logbook from the machine page.

---

H23 (S154, invasora). Genera el libro historial de una grúa A/H desde
su ficha (sección Taller) y lo guarda como su documento LIBRO_HISTORIAL
(fleet.logbook_service.generate_logbook). Miguel Ángel: "Cada libro
generado se guarda como documento el libro historial de esa máquina".
"""
import logging
from urllib.parse import urlencode

from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views import View

from fleet.logbook_service import (
    LogbookReadError, generate_logbook, is_logbook_machine,
)
from fleet.models import MachineAsset
from panel.mixins import CompanyUserRequiredMixin, FleetAccessMixin

logger = logging.getLogger(__name__)

# Mismos roles que editan la ficha (MachineDetailView.EDIT_ROLES).
LOGBOOK_ROLES = {"ADMIN", "ADMIN_SUPERVISOR", "DOCS_SUPERVISOR"}


class MachineLogbookGenerateView(CompanyUserRequiredMixin, View):
    """
    POST: generate and store the logbook of one A/H crane.

    ---

    POST: genera y guarda el libro historial de una grúa A/H y vuelve a
    la ficha, con el documento nuevo en "Libro historial y órdenes de
    mantenimiento".
    """

    def post(self, request, pk):
        if request.user.company_user.role not in LOGBOOK_ROLES:
            return HttpResponse(
                "No tienes permiso para generar el libro historial.",
                status=403,
            )
        machine = get_object_or_404(MachineAsset, pk=pk)
        if not is_logbook_machine(machine):
            return HttpResponse(
                "Solo las grúas móviles A y H llevan libro historial.",
                status=400,
            )
        try:
            entry = generate_logbook(machine, request.user.company_user)
        except LogbookReadError as exc:
            messages.error(request, str(exc))
        except Exception:  # noqa: BLE001 -- se registra y se avisa
            logger.exception(
                "# [MachineLogbookGenerateView] Error generando el libro "
                "de %s", machine.code,
            )
            messages.error(
                request,
                "No se pudo generar el libro historial. Inténtalo de "
                "nuevo y, si se repite, avisa al administrador.",
            )
        else:
            messages.success(
                request,
                "Libro historial generado y guardado: %s." % entry.name,
            )
        # S154: desde la pestaña Libros historial se vuelve a ella.
        next_url = request.POST.get("next") or ""
        if next_url.startswith("/panel/") and "//" not in next_url:
            return redirect(next_url)
        params = {}
        back_url = request.POST.get("back_url") or request.GET.get(
            "back_url")
        if back_url:
            params["back_url"] = back_url
        url = reverse("panel:documentation_machine_detail", args=[pk])
        if params:
            url = "%s?%s" % (url, urlencode(params))
        return redirect(url + "#collapseMachineWorkshop")


# ---------------------------------------------------------------------------
# Pestaña "Libros historial" del taller de la máquina (S154)
# ---------------------------------------------------------------------------

LOGBOOKS_TEMPLATE = "panel/machine_workshop/logbooks.html"
LOGBOOKS_TABLE_TEMPLATE = "panel/machine_workshop/_logbooks_table.html"
LOGBOOKS_KIND = "logbooks"


def _logbooks_context(request, machine):
    """
    Context of the logbooks table fragment.

    ---

    Contexto del fragmento de la tabla de libros: filas, totales de lo
    listado, filtros vigentes y controles de orden (plantillas tontas).
    """
    from panel import machine_workshop as workshop
    from panel import machine_workshop_logbooks as logbooks
    from panel.views_machine_workshop import _only_keys, _params

    params = _params(request, logbooks.LOGBOOK_FILTER_KEYS)
    only_keys = _only_keys(request)
    rows = logbooks.build_logbook_rows(machine, params, only_keys=only_keys)
    return {
        "machine": machine,
        "rows": rows,
        "totals": logbooks.logbook_totals(rows),
        "filters": params,
        "only_selected": only_keys is not None,
        "is_filtered": bool(
            any(params[key] for key in params if key != "sort")
            or only_keys is not None
        ),
        "table_url": reverse(
            "panel:machine_workshop_logbooks_table",
            kwargs={"pk": machine.pk},
        ),
        **workshop.sort_controls(params["sort"], logbooks.LOGBOOK_SORTABLE),
    }


def _logbooks_page_context(request, machine):
    """
    Page context: header tabs, columns, saved selection, permissions.

    ---

    Contexto de la página: pestañas de la cabecera, columnas visibles
    del usuario, selección guardada y permisos (botón de generar solo
    para grúas A/H y los roles que editan la ficha).
    """
    from panel import machine_workshop as workshop
    from panel import machine_workshop_logbooks as logbooks
    from panel.navigation_persistence import get_saved_state_key
    from panel.views_machine_workshop import _saved_selection, _screen_key

    screen_key = _screen_key(LOGBOOKS_KIND, machine)
    hidden = get_saved_state_key(
        request.user.company_user, screen_key, "hidden_columns", [],
    )
    hidden = [key for key in hidden if isinstance(key, str)] if isinstance(
        hidden, list) else []
    columns = workshop.column_choices(logbooks.LOGBOOK_COLUMNS, hidden)
    return {
        "columns": columns,
        "hidden_columns": [
            column["key"] for column in columns if not column["visible"]
        ],
        "machine": machine,
        "active_kind": LOGBOOKS_KIND,
        "machine_detail_url": reverse(
            "panel:documentation_machine_detail", kwargs={"pk": machine.pk},
        ),
        "screen_key": screen_key,
        "saved_selection": _saved_selection(
            request, LOGBOOKS_KIND, machine),
        "doc_types": logbooks.logbook_type_options(),
        "origins": logbooks.ORIGIN_CHOICES,
        "show_generate_button": (
            is_logbook_machine(machine)
            and request.user.company_user.role in LOGBOOK_ROLES
        ),
    }


class MachineWorkshopLogbooksView(FleetAccessMixin, View):
    """
    Logbooks tab of a machine's workshop.

    ---

    Pestaña "Libros historial" del taller de una máquina.
    """

    def get(self, request, pk):
        """
        Render the page with the saved filters.

        ---

        Pinta la página con los filtros guardados del usuario.
        """
        from panel import machine_workshop_logbooks as logbooks
        from panel.navigation_persistence import apply_list_navigation
        from panel.views_machine_workshop import _machine, _screen_key

        machine = _machine(request, pk)
        apply_list_navigation(
            request, _screen_key(LOGBOOKS_KIND, machine),
            logbooks.LOGBOOK_FILTER_KEYS,
        )
        return render(request, LOGBOOKS_TEMPLATE, {
            **_logbooks_page_context(request, machine),
            **_logbooks_context(request, machine),
        })


class MachineWorkshopLogbooksFragmentView(FleetAccessMixin, View):
    """
    Logbooks table fragment (filters, order, selection).

    ---

    Fragmento de la tabla de libros. Guarda filtros y orden por usuario.
    """

    def get(self, request, pk):
        """
        Return the table fragment.

        ---

        Devuelve el fragmento de tabla.
        """
        from panel import machine_workshop_logbooks as logbooks
        from panel.navigation_persistence import apply_list_navigation
        from panel.views_machine_workshop import _machine, _screen_key

        machine = _machine(request, pk)
        apply_list_navigation(
            request, _screen_key(LOGBOOKS_KIND, machine),
            logbooks.LOGBOOK_FILTER_KEYS,
        )
        return render(
            request, LOGBOOKS_TABLE_TEMPLATE,
            _logbooks_context(request, machine),
        )


class MachineWorkshopLogbooksZipView(FleetAccessMixin, View):
    """
    ZIP of the selected logbook documents.

    ---

    ZIP con los originales de los documentos seleccionados (POST
    selected=d<pk>), con el mismo constructor que la descarga de
    documentación de la ficha.
    """

    def post(self, request, pk):
        """
        Build and return the ZIP.

        ---

        Construye y devuelve el ZIP.
        """
        from panel import machine_workshop_logbooks as logbooks
        from panel.views_documentation_h30 import (
            _build_dossier_zip_response,
        )
        from panel.views_machine_workshop import _machine

        machine = _machine(request, pk)
        entries = logbooks.selected_entries(
            machine, request.POST.getlist("selected"),
        )
        if not entries:
            return HttpResponse(
                "No hay ningún documento seleccionado.", status=400,
            )
        return _build_dossier_zip_response(machine, entries)
