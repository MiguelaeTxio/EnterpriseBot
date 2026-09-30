# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/views_worksites.py
"""
H31 (S115). CRUD mínimo de Obras -- listado + alta simple (primer
alcance, ver deuda técnica 4.23 del documento maestro para el diseño
completo previsto: cliente real, coordenadas...). Suficiente para que
"Generar documento" y el envío de circulares por WhatsApp tengan obras
reales entre las que elegir hoy mismo. H30 (S126): borrado, pedido por
Miguel Ángel.
"""
from django.contrib import messages
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views import View

from panel.mixins import AdminRoleRequiredMixin
from worksites.models import Worksite


class WorksiteListView(AdminRoleRequiredMixin, View):
    """
    GET: listado de obras + formulario de alta simple.
    POST: da de alta una obra nueva.

    ---

    GET: worksite listing + simple creation form.
    POST: creates a new worksite.
    """

    template_name = "panel/worksites/worksite_list.html"

    def get(self, request):
        worksites = Worksite.objects.all().select_related(
            "managing_company",
        ).annotate(n_circulars=Count("document_acknowledgments"))
        return render(request, self.template_name, {
            "worksites": worksites,
            "active_nav": "worksites",
        })

    def post(self, request):
        name = request.POST.get("name", "").strip()
        if not name:
            messages.error(request, "Falta el nombre de la obra.")
            return redirect(reverse("panel:worksites_list"))

        worksite = Worksite.objects.create(
            name=name,
            client_name=request.POST.get("client_name", "").strip(),
            address=request.POST.get("address", "").strip(),
        )
        # Código autogenerado a partir del pk real, nunca a mano por el
        # usuario de turno -- Miguel Ángel, verbatim: "si es un código de
        # referencia, lo suyo es que lo vayamos generando conforme se van
        # dando de alta las obras y no un código generado al tuntún".
        worksite.code = "OBRA-%04d" % worksite.pk
        worksite.save(update_fields=["code"])

        messages.success(request, "Obra «%s» dada de alta con código %s." % (name, worksite.code))
        return redirect(reverse("panel:worksites_list"))


class WorksiteDeleteView(AdminRoleRequiredMixin, View):
    """
    POST: delete one worksite.

    ---

    POST: elimina una obra (H30, S126, pedido por Miguel Ángel). Las
    circulares ya enviadas que la tuvieran se conservan, sin obra
    (`DocumentAcknowledgment.worksite` es SET_NULL); la pantalla avisa
    de cuántas son antes de confirmar.
    """

    def post(self, request, pk):
        worksite = get_object_or_404(Worksite, pk=pk)
        label = "%s (%s)" % (worksite.name, worksite.code)
        linked = worksite.document_acknowledgments.count()
        worksite.delete()
        message = "Obra %s eliminada." % label
        if linked:
            message += " %d circular(es) enviada(s) quedan sin obra." % linked
        messages.success(request, message)
        return redirect(reverse("panel:worksites_list"))
