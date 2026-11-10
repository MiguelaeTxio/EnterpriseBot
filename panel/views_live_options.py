# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/views_live_options.py
"""
Current options of the hub dropdowns, to refresh them without reloading.

---

Opciones vigentes de los desplegables del hub de Documentación, para
refrescarlos sin recargar la página (S148). Miguel Ángel: "cuando se
crean dossieres, circulares, o cualquier otro item, tienen que crearse y
estar disponibles al vuelo sin necesidad de recargar la página".

Cada desplegable lleva data-live-options="<clave>"; el hub vuelve a
pedir esta vista al cambiar de pestaña y al volver a la ventana, y
rehace las opciones conservando las fijas (valor vacío o data-fixed) y
lo elegido. Un tercer valor de la opción va a su data-item-ids (los EPIs
de cada lote). Mismos criterios que las vistas que pintan cada desplegable
(Personal y Centros de gasto). Los requisitos ya se refrescan solos
(eb:requirement-saved, S123).
"""
from django.db.models import Q
from django.http import JsonResponse
from django.views import View

from panel.mixins import CompanyUserRequiredMixin


class LiveOptionsView(CompanyUserRequiredMixin, View):
    """
    GET (JSON): {key: [[value, label], ...]} for every live dropdown.
    ---
    GET (JSON): las opciones de cada desplegable "al vuelo".
    """

    def get(self, request):
        from document_explorer.models import (
            DocumentTypeCatalog,
            EpiDeliveryBatchTemplate,
            PersonalDossierTemplate,
        )
        from worksites.models import Worksite

        company = request.user.company_user.company
        notifications = DocumentTypeCatalog.objects.filter(
            is_active=True, is_notification_template=True,
            requires_signature=False,
        ).exclude(content_html="").order_by("label")
        docuten = DocumentTypeCatalog.objects.filter(
            is_active=True, is_notification_template=True,
            requires_signature=True,
        ).filter(
            ~Q(content_html="")
            | Q(current_template__name__iendswith=".pdf")
        ).order_by("label")
        dossiers = company.dossier_templates.order_by("name")
        return JsonResponse({
            "notification_types": [
                [t.code, t.label] for t in notifications],
            "docuten_types": [[t.code, t.label] for t in docuten],
            "worksites": [
                [str(w.pk), w.name] for w in Worksite.objects.filter(
                    is_active=True).order_by("name")],
            "person_dossier_templates": [
                [str(t.pk), t.name] for t in dossiers.filter(
                    scope=PersonalDossierTemplate.SCOPE_PERSONAL)],
            "machine_dossier_templates": [
                [str(t.pk), t.name] for t in dossiers.filter(
                    scope=PersonalDossierTemplate.SCOPE_MACHINE)],
            # Lotes de EPIs: el tercer valor son sus EPIs (data-item-ids).
            "epi_batch_templates": [
                [str(t.pk), t.name, [item.pk for item in t.items.all()]]
                for t in EpiDeliveryBatchTemplate.objects.prefetch_related(
                    "items").order_by("name")],
        })
