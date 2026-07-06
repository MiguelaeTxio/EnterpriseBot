# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/workorder_spare_parts/views.py
"""
CRUD views for the SparePartEntry catalog, outside the delivery-note
circuit. Confirmed by Miguel Ángel (2026-07-06) as a condición sine
qua non before integrating spare-part consumption into the work order
form (H10 Paso 4): without an editable catalog there is nowhere to
fix an entry created ad-hoc from the digital work order.

Every create/update that changes stock_quantity leaves an audit trail
via StockMovement ADJUST, same convention as the rest of the H10
circuit (spare_parts.services). Deletion is only allowed for entries
with zero linked StockMovement records -- a genuine catalog mistake
with nothing consumed yet -- to protect the H9 cost-analytics module,
which crosses labour with spare-part consumption history.

---

Vistas CRUD del catálogo de SparePartEntry, fuera del circuito de
albaranes. Confirmado por Miguel Ángel (2026-07-06) como condición
sine qua non antes de integrar el consumo de repuestos en el parte de
trabajo (H10 Paso 4): sin catálogo editable no hay dónde corregir una
entrada creada ad-hoc desde el parte digital.

Toda alta/edición que cambie stock_quantity deja rastro vía
StockMovement ADJUST, misma convención que el resto del circuito H10
(spare_parts.services). El borrado solo se permite para entradas sin
ningún StockMovement vinculado -- un error de catálogo genuino sin
nada consumido todavía -- para proteger el módulo de analítica de
costes (H9), que cruza mano de obra con historial de consumo de
repuestos.
"""
import logging

from django.contrib import messages
from django.db.models import Q
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View
from django.views.generic import ListView

from fleet.models import MachineAsset
from ivr_config.models import CompanyUser
from panel.mixins import CompanyUserRequiredMixin, SupervisorAccessMixin
from spare_parts.models import SparePartEntry, StockMovement

from .forms import SparePartEntryCatalogForm

logger = logging.getLogger(__name__)


class CatalogReadAccessMixin(CompanyUserRequiredMixin):
    """
    Read access to the spare part catalog for ADMIN, SUPERVISOR,
    WORKSHOP and WORKSHOPBOSS -- confirmed by Miguel Ángel (2026-07-06):
    the mechanics are the ones who will actually use the catalog once
    the consumption endpoints (Paso 4, next block) replace the
    free-text entry in the work order form. Create/edit/delete stay
    restricted to SupervisorAccessMixin (ADMIN/SUPERVISOR) below --
    only the listing is opened up.

    Not reusing panel.mixins.WorkshopRequiredMixin as-is because it
    excludes SUPERVISOR, and not widening it here to avoid touching a
    shared mixin used across the whole panel app for an app-local need.
    ---
    Acceso de lectura al catálogo de repuestos para ADMIN, SUPERVISOR,
    WORKSHOP y WORKSHOPBOSS -- confirmado por Miguel Ángel
    (2026-07-06): los mecánicos son quienes realmente van a usar el
    catálogo en cuanto los endpoints de consumo (Paso 4, siguiente
    bloque) sustituyan la entrada de texto libre del formulario de
    parte. Crear/editar/eliminar siguen restringidos a
    SupervisorAccessMixin (ADMIN/SUPERVISOR) más abajo -- solo se abre
    el listado.
    """

    _allowed_roles = {
        CompanyUser.ROLE_ADMIN,
        CompanyUser.ROLE_SUPERVISOR,
        CompanyUser.ROLE_WORKSHOP,
        CompanyUser.ROLE_WORKSHOPBOSS,
    }

    def dispatch(self, request, *args, **kwargs):
        response = super().dispatch(request, *args, **kwargs)
        if not request.user.is_authenticated:
            return response
        company_user = getattr(request.user, "company_user", None)
        if company_user is None:
            return response
        if company_user.role not in self._allowed_roles:
            return HttpResponseForbidden(
                "Acceso denegado. Esta sección requiere rol de "
                "Administrador, Supervisor, Operario o Jefe de taller."
            )
        return response


class SparePartEntryListView(CatalogReadAccessMixin, ListView):
    """
    Lists the SparePartEntry catalog for the current company, with
    optional filtering by status and free-text search over
    reference/description.
    ---
    Lista el catálogo de SparePartEntry de la empresa actual, con
    filtro opcional por estado y búsqueda libre sobre
    referencia/descripción.
    """

    model = SparePartEntry
    template_name = 'workorder_spare_parts/spare_part_entry_list.html'
    context_object_name = 'entries'
    paginate_by = 30

    def get_queryset(self):
        company = self.request.user.company_user.company
        qs = SparePartEntry.objects.filter(company=company).select_related('machine')
        status = self.request.GET.get('status', '').strip()
        if status:
            qs = qs.filter(status=status)
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(Q(reference__icontains=q) | Q(description__icontains=q))
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        company_user = self.request.user.company_user
        ctx['company_user'] = company_user
        ctx['active_nav'] = 'workorder_spare_parts_catalog'
        ctx['status_choices'] = SparePartEntry.STATUS_CHOICES
        ctx['selected_status'] = self.request.GET.get('status', '')
        ctx['selected_q'] = self.request.GET.get('q', '')
        ctx['can_edit'] = company_user.role in {
            CompanyUser.ROLE_ADMIN, CompanyUser.ROLE_SUPERVISOR,
        }
        return ctx


class SparePartEntryCreateView(SupervisorAccessMixin, View):
    """
    Manual ad-hoc creation of a SparePartEntry catalog record, outside
    the delivery-note and salvage circuits. origin_type is fixed to
    SUPPLIER with empty supplier fields, same convention documented in
    StockAssignmentService's Caso C docstring (no better category
    exists yet in the model for a manual catalog entry).
    ---
    Alta manual ad-hoc de un registro de catálogo SparePartEntry,
    fuera de los circuitos de albarán y canibalización. origin_type se
    fija a SUPPLIER con campos de proveedor vacíos, misma convención
    documentada en el docstring del Caso C de StockAssignmentService.
    """

    template_name = 'workorder_spare_parts/spare_part_entry_form.html'

    def _get_form(self, request, data=None):
        form = SparePartEntryCatalogForm(data)
        form.fields['machine'].queryset = MachineAsset.objects.filter(
            company=request.user.company_user.company,
        ).order_by('code')
        return form

    def get(self, request):
        return render(request, self.template_name, {
            'company_user': request.user.company_user,
            'active_nav': 'workorder_spare_parts_catalog',
            'form': self._get_form(request),
            'action': 'Crear',
        })

    def post(self, request):
        form = self._get_form(request, request.POST)
        if not form.is_valid():
            return render(request, self.template_name, {
                'company_user': request.user.company_user,
                'active_nav': 'workorder_spare_parts_catalog',
                'form': form,
                'action': 'Crear',
            })
        entry = form.save(commit=False)
        entry.company = request.user.company_user.company
        entry.origin_type = SparePartEntry.ORIGIN_SUPPLIER
        entry.save()
        if entry.stock_quantity:
            StockMovement.objects.create(
                spare_part_entry=entry,
                movement_type=StockMovement.MOVEMENT_ADJUST,
                quantity=entry.stock_quantity,
                level_after=entry.stock_level,
                machine=entry.machine,
                notes='Alta manual desde el catálogo (fuera del circuito de albaranes).',
                created_by=request.user.company_user,
            )
        messages.success(request, f"Repuesto '{entry.description}' creado correctamente.")
        return redirect('workorder_spare_parts:catalog_list')


class SparePartEntryUpdateView(SupervisorAccessMixin, View):
    """
    Edits an existing SparePartEntry catalog record. If
    stock_quantity changes, records the delta as a StockMovement
    ADJUST for audit purposes.
    ---
    Edita un registro de catálogo SparePartEntry existente. Si
    stock_quantity cambia, registra la diferencia como un
    StockMovement ADJUST a efectos de auditoría.
    """

    template_name = 'workorder_spare_parts/spare_part_entry_form.html'

    def _get_entry(self, request, pk):
        return get_object_or_404(
            SparePartEntry, pk=pk, company=request.user.company_user.company,
        )

    def _get_form(self, request, entry, data=None):
        form = SparePartEntryCatalogForm(data, instance=entry)
        form.fields['machine'].queryset = MachineAsset.objects.filter(
            company=request.user.company_user.company,
        ).order_by('code')
        return form

    def get(self, request, pk):
        entry = self._get_entry(request, pk)
        return render(request, self.template_name, {
            'company_user': request.user.company_user,
            'active_nav': 'workorder_spare_parts_catalog',
            'form': self._get_form(request, entry),
            'action': 'Editar',
            'entry': entry,
        })

    def post(self, request, pk):
        entry = self._get_entry(request, pk)
        previous_quantity = entry.stock_quantity
        form = self._get_form(request, entry, request.POST)
        if not form.is_valid():
            return render(request, self.template_name, {
                'company_user': request.user.company_user,
                'active_nav': 'workorder_spare_parts_catalog',
                'form': form,
                'action': 'Editar',
                'entry': entry,
            })
        entry = form.save()
        delta = entry.stock_quantity - previous_quantity
        if delta:
            StockMovement.objects.create(
                spare_part_entry=entry,
                movement_type=StockMovement.MOVEMENT_ADJUST,
                quantity=delta,
                level_after=entry.stock_level,
                machine=entry.machine,
                notes='Corrección manual de stock desde el catálogo.',
                created_by=request.user.company_user,
            )
        messages.success(request, f"Repuesto '{entry.description}' actualizado correctamente.")
        return redirect('workorder_spare_parts:catalog_list')


class SparePartEntryDeleteView(SupervisorAccessMixin, View):
    """
    Deletes a SparePartEntry catalog record. Only allowed when it has
    zero linked StockMovement records -- protects H9 cost-analytics
    history from silently losing consumption data.
    ---
    Elimina un registro de catálogo SparePartEntry. Solo permitido
    cuando no tiene ningún StockMovement vinculado -- protege el
    historial de analítica de costes (H9) frente a pérdida silenciosa
    de datos de consumo.
    """

    template_name = 'workorder_spare_parts/spare_part_entry_confirm_delete.html'

    def get(self, request, pk):
        entry = get_object_or_404(
            SparePartEntry, pk=pk, company=request.user.company_user.company,
        )
        has_movements = entry.movements.exists()
        return render(request, self.template_name, {
            'company_user': request.user.company_user,
            'active_nav': 'workorder_spare_parts_catalog',
            'entry': entry,
            'has_movements': has_movements,
        })

    def post(self, request, pk):
        entry = get_object_or_404(
            SparePartEntry, pk=pk, company=request.user.company_user.company,
        )
        if entry.movements.exists():
            messages.error(
                request,
                "No se puede eliminar: este repuesto ya tiene movimientos de "
                "stock registrados (afectaría al historial de analítica de costes).",
            )
            return redirect('workorder_spare_parts:catalog_list')
        description = entry.description
        entry.delete()
        messages.success(request, f"Repuesto '{description}' eliminado correctamente.")
        return redirect('workorder_spare_parts:catalog_list')
