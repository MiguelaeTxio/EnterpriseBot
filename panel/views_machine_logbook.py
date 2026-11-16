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
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views import View

from fleet.logbook_service import (
    LogbookReadError, generate_logbook, is_logbook_machine,
)
from fleet.models import MachineAsset
from panel.mixins import CompanyUserRequiredMixin

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
        params = {}
        back_url = request.POST.get("back_url") or request.GET.get(
            "back_url")
        if back_url:
            params["back_url"] = back_url
        url = reverse("panel:documentation_machine_detail", args=[pk])
        if params:
            url = "%s?%s" % (url, urlencode(params))
        return redirect(url + "#collapseMachineWorkshop")
