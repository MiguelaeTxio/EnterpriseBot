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
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.db.models import Q, Case, When
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View
from django.views.generic import ListView

from fleet.models import MachineAsset
from ivr_config.models import CompanyUser
from panel.mixins import CompanyUserRequiredMixin, SupervisorAccessMixin
from spare_parts.models import SparePartEntry, StockMovement
from spare_parts.services import (
    StockAssignmentService,
    generate_internal_reference,
    register_salvaged_entry,
    register_uninventoried_warehouse_stock,
)
from work_order_processor.models import WorkOrderEntryLine

from .forms import QuickWarehouseIntakeForm, SalvageEntryForm, SparePartEntryCatalogForm

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


class SparePartEntryListView(SupervisorAccessMixin, ListView):
    """
    Registro maestro del catálogo de repuestos, para Administración --
    referencia, descripción, proveedor y precio de compra. Corregido
    2026-07-07 a petición de Miguel Ángel: esto y el "Almacén" de
    Mecánicos (SparePartWarehouseListView) son DOS entidades
    distintas, no la misma vista con dos etiquetas. Este catálogo es
    el registro general (quién lo vende, a qué precio) -- sin limbo,
    sin avisos de antigüedad, sin gestión de stock físico, eso es
    responsabilidad de los mecánicos en su propia vista de Almacén.
    Acceso restringido a ADMIN/SUPERVISOR -- los mecánicos no tienen
    por qué ver precios de compra ni datos de proveedor.
    ---
    Master catalog registry of spare parts, for Administración --
    reference, description, supplier and purchase price. Fixed
    2026-07-07 at Miguel Ángel's request: this and the mechanics'
    "Almacén" (SparePartWarehouseListView) are TWO distinct entities,
    not the same view with two labels. This catalog is the general
    registry (who sells it, at what price) -- no limbo, no age
    warnings, no physical stock management, that is the mechanics'
    responsibility in their own Almacén view. Access restricted to
    ADMIN/SUPERVISOR -- mechanics have no reason to see purchase
    prices or supplier data.
    """

    model = SparePartEntry
    template_name = 'workorder_spare_parts/spare_part_entry_list.html'
    context_object_name = 'entries'
    paginate_by = 30

    def get_queryset(self):
        company = self.request.user.company_user.company
        qs = SparePartEntry.objects.filter(company=company).select_related(
            'machine', 'supplier',
        )
        status = self.request.GET.get('status', '').strip()
        if status:
            qs = qs.filter(status=status)
        machine_pk = self.request.GET.get('machine', '').strip()
        if machine_pk:
            qs = qs.filter(machine_id=machine_pk)
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(
                Q(internal_reference__icontains=q)
                | Q(reference__icontains=q)
                | Q(description__icontains=q)
            )
        return qs.order_by('-pk')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        company_user = self.request.user.company_user
        company = company_user.company
        ctx['company_user'] = company_user
        ctx['active_nav'] = 'workorder_spare_parts_catalog'
        ctx['status_choices'] = SparePartEntry.STATUS_CHOICES
        ctx['selected_status'] = self.request.GET.get('status', '')
        ctx['selected_q'] = self.request.GET.get('q', '')
        ctx['selected_machine'] = self.request.GET.get('machine', '')
        ctx['machines'] = (
            MachineAsset.objects.filter(company=company, is_active=True)
            .order_by('code')
        )
        # SupervisorAccessMixin ya garantiza ADMIN/SUPERVISOR -- can_edit
        # siempre True aquí, se mantiene la variable en la plantilla por
        # si en el futuro se abre a otro rol de solo lectura.
        ctx['can_edit'] = True
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
        entry.internal_reference = generate_internal_reference(entry.company)
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


# =============================================================================
# Almacén (Mecánicos) -- H10 Paso 5/6, corregido 2026-07-07
# =============================================================================

class SparePartWarehouseListView(CatalogReadAccessMixin, View):
    """
    Vista operativa del almacén para Mecánicos -- entidad distinta del
    catálogo de Administración (corregido 2026-07-07 a petición de
    Miguel Ángel, que señaló que había quedado la misma vista con dos
    etiquetas cuando en realidad son dos cosas diferentes: aquí NO hay
    proveedor ni precio de compra, y SÍ hay gestión de stock físico y
    del limbo de pre-asignación, porque son los mecánicos quienes
    saben si un repuesto reservado para una máquina se va a colocar o
    ya está descartado). Un único listado con filtro por estado/
    máquina: las filas PRE_ASSIGNED muestran el aviso de antigüedad
    del limbo (anexo H10, sección 3.2 -- verde &lt;2 semanas, azul-info
    1 mes, naranja 3 meses, rojo 6+ meses) y el botón "Devolver a
    almacén"; las filas WAREHOUSE permiten ajustar la cantidad/nivel
    directamente (SparePartStockAdjustView).

    Acceso: ADMIN, SUPERVISOR, WORKSHOP, WORKSHOPBOSS (mismo permiso
    de lectura ya abierto en 2bb5c81 -- son los mecánicos quienes
    usan esta pantalla día a día).

    GET /panel/repuestos/almacen/

    ---

    Operational warehouse view for Mechanics -- a distinct entity from
    the Administración catalog (fixed 2026-07-07 at Miguel Ángel's
    request, who pointed out it had ended up as the same view with two
    labels when they are actually two different things: no supplier or
    purchase price here, and yes physical stock and pre-assignment
    limbo management, because mechanics are the ones who know whether
    a part reserved for a machine will actually be fitted or is
    already discarded). A single list with status/machine filter:
    PRE_ASSIGNED rows show the limbo age warning (annex H10, section
    3.2 -- green &lt;2 weeks, info-blue 1 month, orange 3 months, red
    6+ months) and the "Devolver a almacén" button; WAREHOUSE rows
    allow adjusting quantity/level directly
    (SparePartStockAdjustView).

    Access: ADMIN, SUPERVISOR, WORKSHOP, WORKSHOPBOSS (same read
    permission already opened in 2bb5c81 -- mechanics are the ones
    using this screen day to day).

    GET /panel/repuestos/almacen/
    """

    template_name = 'workorder_spare_parts/spare_part_warehouse_list.html'

    # Umbrales de antigüedad del limbo -- anexo H10 sección 3.2, literal.
    # Limbo age thresholds -- annex H10 section 3.2, literal.
    _AGE_YELLOW_DAYS = 14   # >= 2 semanas
    _AGE_ORANGE_DAYS = 30   # >= 1 mes
    _AGE_RED_DAYS = 90      # >= 3 meses
    # NOTA: el anexo tambien menciona "rojo (6 meses o mas)" como un
    # cuarto escalon, pero solo describe 4 colores para 3 umbrales
    # explicitos (2 semanas/1 mes/3 meses) -- interpretado como que
    # "rojo" cubre todo lo que supere los 3 meses (incluido 6+), sin
    # un quinto color propio para 6 meses. Asuncion no bloqueante, a
    # confirmar con Miguel Angel si se querian 4 umbrales reales.
    # NOTE: the annex also mentions "red (6 months or more)" as a
    # fourth step, but only describes 4 colours for 3 explicit
    # thresholds (2 weeks/1 month/3 months) -- interpreted as "red"
    # covering everything past 3 months (including 6+), without a
    # fifth colour of its own. Non-blocking assumption, to confirm
    # with Miguel Ángel if 4 real thresholds were wanted.

    def get(self, request):
        from django.utils.timezone import now as _tz_now

        company = request.user.company_user.company
        qs = (
            SparePartEntry.objects.filter(company=company)
            .select_related('machine', 'breakdown_ticket')
        )
        status = request.GET.get('status', '').strip()
        if status:
            qs = qs.filter(status=status)
        machine_pk = request.GET.get('machine', '').strip()
        if machine_pk:
            qs = qs.filter(machine_id=machine_pk)
        # Pre-asignados primero (por antigüedad, los más viejos arriba
        # para que salten a la vista), el resto por pk descendente.
        # Pre-assigned first (by age, oldest on top so they stand
        # out), the rest by descending pk.
        entries = list(qs.order_by(
            Case(
                When(status=SparePartEntry.STATUS_PRE_ASSIGNED, then=0),
                default=1,
            ),
            'pre_assigned_at', '-pk',
        ))

        _now = _tz_now()
        rows = []
        for entry in entries:
            age_days = None
            age_class = None
            if (
                entry.status == SparePartEntry.STATUS_PRE_ASSIGNED
                and entry.pre_assigned_at
            ):
                age_days = (_now - entry.pre_assigned_at).days
                if age_days >= self._AGE_RED_DAYS:
                    age_class = 'danger'
                elif age_days >= self._AGE_ORANGE_DAYS:
                    age_class = 'warning'
                elif age_days >= self._AGE_YELLOW_DAYS:
                    age_class = 'info'
                else:
                    age_class = 'success'
            rows.append({
                'entry': entry, 'age_days': age_days, 'age_class': age_class,
            })

        machines = (
            MachineAsset.objects.filter(company=company, is_active=True)
            .order_by('code')
        )

        return render(request, self.template_name, {
            'company_user': request.user.company_user,
            'active_nav': 'workorder_spare_parts_warehouse',
            'rows': rows,
            'machines': machines,
            'status_choices': SparePartEntry.STATUS_CHOICES,
            'selected_status': status,
            'selected_machine': machine_pk,
            'level_choices': StockAssignmentService.LEVEL_CHOICES,
        })


class SparePartReturnToWarehouseView(CatalogReadAccessMixin, View):
    """
    Ejecuta la transición "Devolver a almacén" del anexo H10, sección
    3.2: status -> WAREHOUSE, limpia machine/breakdown_ticket/
    pre_assigned_at, registra StockMovement RETURN_TO_WAREHOUSE.
    Corregido 2026-07-07: acceso ampliado de ADMIN/SUPERVISOR a
    CatalogReadAccessMixin (incluye WORKSHOP/WORKSHOPBOSS) -- son los
    mecánicos quienes saben si un repuesto en el limbo se va a colocar
    o ya está descartado, y deben poder devolverlo ellos mismos, sin
    depender de un ADMIN.

    URL: POST /panel/repuestos/almacen/<pk>/devolver/

    ---

    Executes the "Devolver a almacén" transition from annex H10,
    section 3.2: status -> WAREHOUSE, clears machine/breakdown_ticket/
    pre_assigned_at, records StockMovement RETURN_TO_WAREHOUSE. Fixed
    2026-07-07: access widened from ADMIN/SUPERVISOR to
    CatalogReadAccessMixin (includes WORKSHOP/WORKSHOPBOSS) --
    mechanics are the ones who know whether a part in limbo will
    actually be fitted or is already discarded, and should be able to
    return it themselves, without depending on an ADMIN.

    URL: POST /panel/repuestos/almacen/<pk>/devolver/
    """

    def post(self, request, pk):
        company = request.user.company_user.company
        entry = get_object_or_404(
            SparePartEntry,
            pk=pk,
            company=company,
            status=SparePartEntry.STATUS_PRE_ASSIGNED,
        )

        entry.status = SparePartEntry.STATUS_WAREHOUSE
        entry.machine = None
        entry.breakdown_ticket = None
        entry.pre_assigned_at = None
        entry.save(update_fields=[
            'status', 'machine', 'breakdown_ticket', 'pre_assigned_at',
        ])

        StockMovement.objects.create(
            spare_part_entry=entry,
            movement_type=StockMovement.MOVEMENT_RETURN_TO_WAREHOUSE,
            quantity=(
                entry.stock_quantity if not entry.is_uncountable else 0
            ),
            created_by=request.user.company_user,
            notes='Devuelto a almacén desde el limbo de pre-asignación.',
        )

        messages.success(
            request,
            f"'{entry.description}' devuelto a almacén correctamente.",
        )
        return redirect('workorder_spare_parts:warehouse_list')


class SparePartStockAdjustView(CatalogReadAccessMixin, View):
    """
    Ajuste directo de stock (cantidad o nivel) para una SparePartEntry
    en status=WAREHOUSE, ejecutado por los propios mecánicos -- a
    petición de Miguel Ángel (2026-07-07): "el inventario lo van a
    gestionar los propios mecánicos". Genera un StockMovement ADJUST
    para trazabilidad, mismo patrón que el ajuste ya existente al
    editar el catálogo desde Administración (SparePartEntryUpdateView),
    pero accesible aquí sin pasar por el formulario completo de
    catálogo (que incluye referencia/proveedor/precio, campos que los
    mecánicos no tocan).

    URL: POST /panel/repuestos/almacen/<pk>/ajustar/

    ---

    Direct stock adjustment (quantity or level) for a SparePartEntry
    in status=WAREHOUSE, executed by the mechanics themselves -- at
    Miguel Ángel's request (2026-07-07): "the mechanics themselves
    will manage the inventory". Records a StockMovement ADJUST for
    traceability, same pattern as the adjustment already made when
    editing the catalog from Administración
    (SparePartEntryUpdateView), but reachable here without going
    through the full catalog form (which includes
    reference/supplier/price, fields mechanics don't touch).

    URL: POST /panel/repuestos/almacen/<pk>/ajustar/
    """

    def post(self, request, pk):
        company = request.user.company_user.company
        entry = get_object_or_404(
            SparePartEntry,
            pk=pk,
            company=company,
            status=SparePartEntry.STATUS_WAREHOUSE,
        )

        if entry.is_uncountable:
            new_level = request.POST.get('stock_level', '').strip().upper()
            if new_level not in StockAssignmentService.LEVEL_CHOICES:
                messages.error(request, 'Nivel de stock no válido.')
                return redirect('workorder_spare_parts:warehouse_list')
            entry.stock_level = new_level
            entry.save(update_fields=['stock_level'])
            StockMovement.objects.create(
                spare_part_entry=entry,
                movement_type=StockMovement.MOVEMENT_ADJUST,
                quantity=0,
                level_after=new_level,
                machine=entry.machine,
                created_by=request.user.company_user,
                notes='Ajuste de nivel de stock desde el almacén (mecánico).',
            )
        else:
            raw_qty = request.POST.get('stock_quantity', '').strip()
            try:
                new_qty = Decimal(raw_qty)
            except (InvalidOperation, ValueError):
                messages.error(request, 'Cantidad no válida.')
                return redirect('workorder_spare_parts:warehouse_list')
            delta = new_qty - (entry.stock_quantity or Decimal('0'))
            entry.stock_quantity = new_qty
            entry.save(update_fields=['stock_quantity'])
            StockMovement.objects.create(
                spare_part_entry=entry,
                movement_type=StockMovement.MOVEMENT_ADJUST,
                quantity=delta,
                machine=entry.machine,
                created_by=request.user.company_user,
                notes='Ajuste de cantidad de stock desde el almacén (mecánico).',
            )

        messages.success(
            request, f"Stock de '{entry.description}' actualizado.",
        )
        return redirect('workorder_spare_parts:warehouse_list')


class SparePartWarehouseSearchView(CatalogReadAccessMixin, View):
    """
    HTMX endpoint: searches the digital warehouse (StockAssignmentService
    Caso A, paso 1 de la sección 3.5) scoped to the entry_line's company,
    for use from within the work order form/confirm templates (H10 Paso 4,
    bloque 2/4). Returns an HTML fragment with matching entries, or an
    empty-state fragment.
    ---
    Endpoint HTMX: busca en el almacén digital (Caso A de
    StockAssignmentService, paso 1 de la sección 3.5) acotado a la
    empresa de la entry_line, para usarse desde dentro de las plantillas
    del formulario de parte (H10 Paso 4, bloque 2/4). Devuelve un
    fragmento HTML con los resultados, o un fragmento de estado vacío.
    """

    template_name = 'workorder_spare_parts/_warehouse_search_results.html'

    def get(self, request, entry_line_pk):
        entry_line = get_object_or_404(
            WorkOrderEntryLine,
            pk=entry_line_pk,
            entry__work_order__company=request.user.company_user.company,
        )
        query = request.GET.get('q', '')
        results = StockAssignmentService.search_warehouse(
            company=request.user.company_user.company,
            query=query,
        )
        return render(request, self.template_name, {
            'entry_line': entry_line,
            'results': results,
            'query': query,
        })


class SparePartConsumeFromWarehouseView(CatalogReadAccessMixin, View):
    """
    HTMX endpoint: executes StockAssignmentService.consume_from_warehouse
    (Caso A) for a given SparePartEntry against a given WorkOrderEntryLine.
    machine and breakdown_ticket are resolved from the entry_line itself,
    never from client input. Returns a confirmation fragment on success,
    or the search results fragment with an inline error banner on
    ValueError (insufficient stock, wrong entry status, etc.).
    ---
    Endpoint HTMX: ejecuta StockAssignmentService.consume_from_warehouse
    (Caso A) para un SparePartEntry dado contra una WorkOrderEntryLine
    dada. machine y breakdown_ticket se resuelven desde la propia
    entry_line, nunca desde la entrada del cliente. Devuelve un
    fragmento de confirmación si tiene éxito, o el fragmento de
    resultados de búsqueda con un banner de error inline ante
    ValueError (stock insuficiente, estado incorrecto de la entrada,
    etc.).
    """

    results_template_name = 'workorder_spare_parts/_warehouse_search_results.html'
    confirm_template_name = 'workorder_spare_parts/_consumption_confirmed.html'

    def post(self, request, entry_line_pk, entry_pk):
        company = request.user.company_user.company
        entry_line = get_object_or_404(
            WorkOrderEntryLine,
            pk=entry_line_pk,
            entry__work_order__company=company,
        )
        entry = get_object_or_404(SparePartEntry, pk=entry_pk, company=company)

        quantity_raw = request.POST.get('quantity_used', '').strip()
        new_level = request.POST.get('new_level', '').strip() or None
        notes = request.POST.get('notes', '').strip()

        quantity_used = None
        if quantity_raw:
            try:
                quantity_used = Decimal(quantity_raw)
            except InvalidOperation:
                quantity_used = None

        try:
            spare_part_line = StockAssignmentService.consume_from_warehouse(
                entry=entry,
                entry_line=entry_line,
                machine=entry_line.machine_asset,
                breakdown_ticket=entry_line.breakdown_ticket,
                created_by=request.user.company_user,
                quantity_used=quantity_used,
                new_level=new_level,
                notes=notes,
            )
        except ValueError as exc:
            results = StockAssignmentService.search_warehouse(
                company=company, query=entry.description,
            )
            return render(request, self.results_template_name, {
                'entry_line': entry_line,
                'results': results,
                'query': entry.description,
                'error': str(exc),
            })

        return render(request, self.confirm_template_name, {
            'entry_line': entry_line,
            'spare_part_line': spare_part_line,
            'entry': entry,
        })


class SparePartPreAssignedListView(CatalogReadAccessMixin, View):
    """
    HTMX endpoint: lists pre-assigned entries (Caso B, sección 3.3/3.5)
    for the entry_line's breakdown_ticket if it has one, otherwise for
    its machine_asset. Auto-loaded when the consumption widget renders
    (hx-trigger="load"), no search input needed -- the limbo listing
    is always scoped to a specific machine/ticket, never free-text.
    ---
    Endpoint HTMX: lista los repuestos pre-asignados (Caso B, sección
    3.3/3.5) para el breakdown_ticket de la entry_line si lo tiene, o
    si no para su machine_asset. Se carga automáticamente al
    renderizar el widget de consumo (hx-trigger="load"), sin campo de
    búsqueda -- el listado del limbo siempre está acotado a una
    máquina/ticket concreta, nunca es texto libre.
    """

    template_name = 'workorder_spare_parts/_pre_assigned_results.html'

    def get(self, request, entry_line_pk):
        entry_line = get_object_or_404(
            WorkOrderEntryLine,
            pk=entry_line_pk,
            entry__work_order__company=request.user.company_user.company,
        )
        if entry_line.breakdown_ticket is not None:
            results = StockAssignmentService.list_pre_assigned(
                breakdown_ticket=entry_line.breakdown_ticket,
            )
        elif entry_line.machine_asset is not None:
            results = StockAssignmentService.list_pre_assigned(
                machine=entry_line.machine_asset,
            )
        else:
            results = SparePartEntry.objects.none()
        return render(request, self.template_name, {
            'entry_line': entry_line,
            'results': results,
        })


class SparePartConsumePreAssignedView(CatalogReadAccessMixin, View):
    """
    HTMX endpoint: executes StockAssignmentService.consume_pre_assigned
    (Caso B) for a given SparePartEntry against a given
    WorkOrderEntryLine. No quantity/level input needed -- the whole
    reserved amount is consumed at once (section 3.4 punto 1).
    ---
    Endpoint HTMX: ejecuta StockAssignmentService.consume_pre_assigned
    (Caso B) para un SparePartEntry dado contra una WorkOrderEntryLine
    dada. No hace falta cantidad/nivel -- se consume toda la reserva
    de golpe (sección 3.4 punto 1).
    """

    results_template_name = 'workorder_spare_parts/_pre_assigned_results.html'
    confirm_template_name = 'workorder_spare_parts/_consumption_confirmed.html'

    def post(self, request, entry_line_pk, entry_pk):
        company = request.user.company_user.company
        entry_line = get_object_or_404(
            WorkOrderEntryLine,
            pk=entry_line_pk,
            entry__work_order__company=company,
        )
        entry = get_object_or_404(SparePartEntry, pk=entry_pk, company=company)
        notes = request.POST.get('notes', '').strip()

        try:
            spare_part_line = StockAssignmentService.consume_pre_assigned(
                entry=entry, entry_line=entry_line,
                created_by=request.user.company_user, notes=notes,
            )
        except ValueError as exc:
            if entry_line.breakdown_ticket is not None:
                results = StockAssignmentService.list_pre_assigned(
                    breakdown_ticket=entry_line.breakdown_ticket,
                )
            else:
                results = StockAssignmentService.list_pre_assigned(
                    machine=entry_line.machine_asset,
                )
            return render(request, self.results_template_name, {
                'entry_line': entry_line, 'results': results, 'error': str(exc),
            })

        return render(request, self.confirm_template_name, {
            'entry_line': entry_line,
            'spare_part_line': spare_part_line,
            'entry': entry,
        })


class SparePartRegisterNewAndConsumeView(CatalogReadAccessMixin, View):
    """
    HTMX endpoint: GET renders the ad-hoc registration form (Caso C),
    POST executes StockAssignmentService.register_new_and_consume --
    organic digitisation of a spare part never seen before, straight
    from the work order form. Only used when the part is not in the
    warehouse (Caso A) nor pre-assigned (Caso B).
    ---
    Endpoint HTMX: GET renderiza el formulario de alta ad-hoc (Caso C),
    POST ejecuta StockAssignmentService.register_new_and_consume --
    digitalización orgánica de un repuesto nunca visto, directamente
    desde el formulario de parte. Solo se usa cuando la pieza no está
    en almacén (Caso A) ni pre-asignada (Caso B).
    """

    form_template_name = 'workorder_spare_parts/_register_new_form.html'
    confirm_template_name = 'workorder_spare_parts/_consumption_confirmed.html'

    def get(self, request, entry_line_pk):
        entry_line = get_object_or_404(
            WorkOrderEntryLine,
            pk=entry_line_pk,
            entry__work_order__company=request.user.company_user.company,
        )
        return render(request, self.form_template_name, {'entry_line': entry_line})

    def post(self, request, entry_line_pk):
        company = request.user.company_user.company
        entry_line = get_object_or_404(
            WorkOrderEntryLine,
            pk=entry_line_pk,
            entry__work_order__company=company,
        )

        description = request.POST.get('description', '').strip()
        reference = request.POST.get('reference', '').strip()
        is_uncountable = request.POST.get('is_uncountable') == 'on'
        notes = request.POST.get('notes', '').strip()

        def _to_decimal(raw):
            raw = (raw or '').strip()
            if not raw:
                return None
            try:
                return Decimal(raw)
            except InvalidOperation:
                return None

        stock_quantity_remaining = _to_decimal(request.POST.get('stock_quantity_remaining'))
        stock_level_remaining = request.POST.get('stock_level_remaining', '').strip() or None
        quantity_used = _to_decimal(request.POST.get('quantity_used'))

        try:
            spare_part_line = StockAssignmentService.register_new_and_consume(
                company=company,
                entry_line=entry_line,
                machine=entry_line.machine_asset,
                breakdown_ticket=entry_line.breakdown_ticket,
                created_by=request.user.company_user,
                description=description,
                reference=reference,
                is_uncountable=is_uncountable,
                stock_quantity_remaining=stock_quantity_remaining,
                stock_level_remaining=stock_level_remaining,
                quantity_used=quantity_used,
                notes=notes,
            )
        except ValueError as exc:
            return render(request, self.form_template_name, {
                'entry_line': entry_line, 'error': str(exc),
            })

        return render(request, self.confirm_template_name, {
            'entry_line': entry_line,
            'spare_part_line': spare_part_line,
            'entry': spare_part_line.spare_part_entry,
        })


# =============================================================================
# TaskTicketResolutionView -- H10 Paso 4-bis, punto 1 (revisado en S007)
# =============================================================================

# Solo para mostrar el numero en el fragmento sin importar la constante
# interna de chat.ticket_resolution en cada peticion -- valor identico,
# duplicado deliberado y minimo para no acoplar la vista al modulo de
# chat mas de lo necesario (ya se importa resolve_ticket_for_machine
# bajo demanda).
_REOPEN_WINDOW_HOURS_DISPLAY = 72


class TaskTicketResolutionView(CatalogReadAccessMixin, View):
    """
    Ampliado 2026-07-07 a petición de Miguel Ángel: además de resolver
    el ticket, este mismo endpoint devuelve también los SparePartEntry
    PRE_ASSIGNED anclados solo a la máquina (sin ticket) -- si el
    centro de gasto ya tiene repuestos reservados (p. ej. de un
    albarán confirmado antes de que existiera ninguna avería), se
    muestran con checkbox para que el mecánico marque cuáles se han
    consumido de verdad en esta tarea. Se materializan al guardar
    (ver panel/views_operator.py, WorkOrderEntryFormView.post()) vía
    StockAssignmentService.consume_pre_assigned(), sin tocar ese
    método existente.

    ---
    HTMX endpoint: resolves the breakdown-ticket-per-machine question
    for a single work-order-form block (a "tarea") BEFORE it is saved
    -- there is no WorkOrderEntryLine yet at this point (Vía A,
    creación directa), only a machine code the mechanic just picked
    from the asset autocomplete. Uses
    chat.ticket_resolution.resolve_ticket_for_machine() (read-only preview,
    Paso 4-bis punto 1, revisado en S007: PAUSED cuenta como abierto,
    con 1+ candidatos siempre hay que confirmar) -- never creates or
    touches any ticket here, that only happens at save time inside
    get_or_create_ticket_for_machine() under its own mutex.

    Replaces the old free-choice `ticket_pk` dropdown (H17) scoped to
    every open/paused ticket of the whole company -- confirmed by
    Miguel Ángel (2026-07-07): una vez el mecánico fija el centro de
    gasto de la tarea, el ticket se resuelve automáticamente (o se
    pregunta, si hay ambigüedad), nunca se elige libremente de una
    lista de toda la empresa.

    GET params:
      code       -- fleet.MachineAsset.code, required. If it doesn't
                     resolve to an active machine of this company
                     (e.g. PERSONAL, EMPRESA_* pseudo-assets, or a
                     code not yet matched), renders nothing (empty
                     fragment) -- those blocks never carry a ticket.
      block_idx  -- the work-order-form block index (`entrada.idx`),
                     required, used to build unique field names
                     (`entrada_{block_idx}_ticket_*`) matching the
                     rest of the form.

    Returns an HTML fragment: a notice (CREATE), a Sí/No question
    (ASK_REOPEN), or a short-list + "avería nueva" choice (CHOOSE) --
    see workorder_spare_parts/_ticket_resolution.html.
    ---

    Endpoint HTMX: resuelve la pregunta de ticket de avería por
    máquina para un bloque del formulario de parte (una "tarea")
    ANTES de guardarse -- todavía no existe ningún
    WorkOrderEntryLine (Vía A, creación directa), solo un código de
    máquina que el mecánico acaba de elegir del autocompletado de
    activos. Usa chat.ticket_resolution.resolve_ticket_for_machine() (vista
    previa de solo lectura, Paso 4-bis punto 1, revisado en S007:
    PAUSED cuenta como abierto, con 1+ candidatos siempre hay que
    confirmar) -- nunca crea ni toca ningún ticket aquí, eso solo
    ocurre al guardar dentro de get_or_create_ticket_for_machine(),
    bajo su propio mutex.

    Sustituye el desplegable de elección libre `ticket_pk` (H17)
    acotado a todos los tickets abiertos/pausados de la empresa --
    confirmado por Miguel Ángel (2026-07-07): una vez el mecánico fija
    el centro de gasto de la tarea, el ticket se resuelve
    automáticamente (o se pregunta, si hay ambigüedad), nunca se elige
    libremente de una lista de toda la empresa.

    Parámetros GET:
      code       -- fleet.MachineAsset.code, obligatorio. Si no
                     resuelve a una máquina activa de esta empresa
                     (p. ej. pseudo-activos PERSONAL, EMPRESA_*, o un
                     código todavía sin coincidencia), no renderiza
                     nada (fragmento vacío) -- esos bloques nunca
                     llevan ticket.
      block_idx  -- el índice de bloque del formulario de parte
                     (`entrada.idx`), obligatorio, se usa para
                     construir nombres de campo únicos
                     (`entrada_{block_idx}_ticket_*`) iguales al resto
                     del formulario.

    Devuelve un fragmento HTML: un aviso (CREATE), una pregunta Sí/No
    (ASK_REOPEN), o una lista corta + opción "avería nueva" (CHOOSE) --
    ver workorder_spare_parts/_ticket_resolution.html.
    """

    template_name = 'workorder_spare_parts/_ticket_resolution.html'

    def get(self, request):
        from chat.ticket_resolution import resolve_ticket_for_machine
        from work_order_processor.management.commands.seed_personal_asset import (
            PERSONAL_ASSET_CODE,
        )
        from work_order_processor.management.commands.seed_empresa_assets import (
            EMPRESA_ASSETS,
        )

        code = request.GET.get('code', '').strip()
        block_idx = request.GET.get('block_idx', '').strip()

        empresa_codes = {a['code'].upper() for a in EMPRESA_ASSETS}
        if (
            not code or not block_idx
            or code.upper() == PERSONAL_ASSET_CODE.upper()
            or code.upper() in empresa_codes
        ):
            # PERSONAL y EMPRESA_* son pseudo-activos (ausencias,
            # bloques administrativos) -- nunca llevan ticket de
            # avería, aunque sean MachineAsset reales en catálogo.
            return render(request, self.template_name, {'machine': None})

        machine = MachineAsset.objects.filter(
            company=request.user.company_user.company,
            code=code,
            is_active=True,
        ).first()

        if machine is None:
            # Código sin coincidencia todavía (autocompletado a medio
            # escribir) -- ningún ticket que resolver por ahora.
            return render(request, self.template_name, {'machine': None})

        resolution = resolve_ticket_for_machine(machine)

        from spare_parts.services import StockAssignmentService
        pre_assigned_parts = list(
            StockAssignmentService.list_pre_assigned(machine=machine)
        )

        return render(request, self.template_name, {
            'machine': machine,
            'block_idx': block_idx,
            'resolution': resolution,
            'reopen_window_hours': _REOPEN_WINDOW_HOURS_DISPLAY,
            'pre_assigned_parts': pre_assigned_parts,
        })


# =============================================================================
# H10 Paso 7 -- Alta de repuestos por canibalización (anexo, sección 3.6)
# =============================================================================

class SparePartSalvageOriginLinesView(CatalogReadAccessMixin, View):
    """
    HTMX endpoint: búsqueda libre de partes de trabajo recientes de
    una máquina donante, para el selector opcional
    `origin_work_order_entry_line` del alta por canibalización (anexo
    H10, sección 3.6, punto 3). Nunca obligatorio -- una pieza puede
    haberse retirado hace tiempo sin parte asociado en el sistema.

    GET params:
      origin_machine -- pk de fleet.MachineAsset (donante), obligatorio
                         para devolver resultados.
      origin_line_q  -- texto libre opcional, filtra por
                         fault_description/repair_notes.

    ---

    HTMX endpoint: free-text search of recent work-order lines for a
    donor machine, for the optional `origin_work_order_entry_line`
    selector of the cannibalisation intake (annex H10, section 3.6,
    point 3). Never mandatory -- a part may have been removed long
    ago with no associated record in the system.
    """

    template_name = 'workorder_spare_parts/_salvage_origin_lines_results.html'

    def get(self, request):
        company = request.user.company_user.company
        machine_pk = request.GET.get('origin_machine', '').strip()
        query = request.GET.get('origin_line_q', '').strip()

        if not machine_pk:
            return render(request, self.template_name, {
                'results': [], 'searched': False,
            })

        qs = WorkOrderEntryLine.objects.filter(
            machine_asset_id=machine_pk,
            entry__work_order__company=company,
        ).select_related('entry')
        if query:
            qs = qs.filter(
                Q(fault_description__icontains=query)
                | Q(repair_notes__icontains=query)
            )
        results = qs.order_by('-entry__work_date', '-pk')[:20]

        return render(request, self.template_name, {
            'results': results, 'searched': True,
        })


class SparePartSalvageCreateView(CatalogReadAccessMixin, View):
    """
    Alta manual de un repuesto recuperado por canibalización (H10
    Paso 7, anexo sección 3.6). Siempre iniciada desde aquí (nunca
    disparada automáticamente desde el parte de trabajo -- principio
    rector de separación total, ya validado en confirm_delivery_note()
    y en el diseño Paso 4-bis). Delega toda la lógica de creación y
    resolución de destino (WAREHOUSE vs PRE_ASSIGNED + ticket) en
    spare_parts.services.register_salvaged_entry().

    Acceso: mismo permiso que el Almacén (ADMIN/SUPERVISOR/WORKSHOP/
    WORKSHOPBOSS) -- son los mecánicos quienes retiran piezas
    reaprovechables y dan de alta el circuito, igual que gestionan el
    resto del almacén desde S007.

    ASUNCIÓN (a confirmar con Miguel Ángel): el anexo describe esto
    como "modal de alta manual", pero se implementa aquí como página
    dedicada, siguiendo el mismo patrón que el resto de altas
    manuales del módulo (SparePartEntryCreateView, SupplierCreateView)
    -- ninguna de ellas usa un modal real, y este formulario tiene
    lógica dinámica (búsqueda HTMX de parte de origen, aparición
    condicional de la máquina receptora) que encaja mejor en una
    página propia que en un modal embebido. Si Miguel Ángel prefiere
    un modal real sobre spare_part_warehouse_list.html, es un cambio
    de plantilla sin tocar la vista ni el servicio.

    ---

    Manual creation of a spare part recovered via cannibalisation
    (H10 Paso 7, annex section 3.6). Always initiated from here
    (never automatically triggered from the work order -- guiding
    principle of total separation, already validated in
    confirm_delivery_note() and in the Paso 4-bis design). Delegates
    all creation and destination-resolution logic (WAREHOUSE vs
    PRE_ASSIGNED + ticket) to
    spare_parts.services.register_salvaged_entry().

    Access: same permission as the Almacén (ADMIN/SUPERVISOR/WORKSHOP/
    WORKSHOPBOSS) -- mechanics are the ones removing reusable parts
    and registering the intake, same as they manage the rest of the
    warehouse since S007.

    ASSUMPTION (to confirm with Miguel Ángel): the annex describes
    this as a "manual creation modal", but it is implemented here as
    a dedicated page, following the same pattern as the rest of the
    module's manual intakes (SparePartEntryCreateView,
    SupplierCreateView) -- none of them use a real modal, and this
    form has dynamic logic (HTMX search of the origin part,
    conditional appearance of the receiving machine) that fits a
    dedicated page better than an embedded modal. If Miguel Ángel
    prefers a real modal over spare_part_warehouse_list.html, it is a
    template-only change, no view or service changes needed.
    """

    template_name = 'workorder_spare_parts/spare_part_salvage_form.html'

    def _get_form(self, request, data=None):
        return SalvageEntryForm(data, company=request.user.company_user.company)

    def get(self, request):
        return render(request, self.template_name, {
            'company_user': request.user.company_user,
            'active_nav': 'workorder_spare_parts_warehouse',
            'form': self._get_form(request),
        })

    def post(self, request):
        form = self._get_form(request, request.POST)
        if not form.is_valid():
            return render(request, self.template_name, {
                'company_user': request.user.company_user,
                'active_nav': 'workorder_spare_parts_warehouse',
                'form': form,
            })

        cleaned = form.cleaned_data
        try:
            entry = register_salvaged_entry(
                company=request.user.company_user.company,
                created_by=request.user.company_user,
                description=cleaned['description'],
                origin_machine=cleaned['origin_machine'],
                destination=cleaned['destination'],
                is_uncountable=cleaned['is_uncountable'],
                stock_quantity=cleaned['stock_quantity'],
                stock_level=cleaned['stock_level'],
                origin_work_order_entry_line=cleaned['origin_work_order_entry_line'],
                destination_machine=cleaned['destination_machine'],
            )
        except ValueError as exc:
            messages.error(request, str(exc))
            return render(request, self.template_name, {
                'company_user': request.user.company_user,
                'active_nav': 'workorder_spare_parts_warehouse',
                'form': form,
            })

        messages.success(
            request,
            f"Repuesto '{entry.description}' [{entry.internal_reference}] "
            f"dado de alta por canibalización correctamente.",
        )
        return redirect('workorder_spare_parts:warehouse_list')


class SparePartQuickIntakeCreateView(CatalogReadAccessMixin, View):
    """
    Alta rápida en el almacén digital de un repuesto que un mecánico
    acaba de coger del almacén físico y que todavía no estaba
    inventariado -- gap señalado por Miguel Ángel (2026-07-07): "faltaba
    dar de alta repuestos por los mecánicos cuando van cogiendo del
    almacén y aún no se han inventariado".

    Sin proveedor conocido (se resuelve más adelante en cuanto llegue
    un albarán del mismo artículo, ver
    spare_parts.services.confirm_delivery_note()) y sin destino a
    máquina (el destino se decide después, con el consumo normal
    desde el almacén) -- delega toda la lógica en
    spare_parts.services.register_uninventoried_warehouse_stock().

    Acceso: mismo permiso que el resto del Almacén (ADMIN/SUPERVISOR/
    WORKSHOP/WORKSHOPBOSS) -- son los mecánicos quienes hacen este
    alta sobre la marcha, según lo confirmado por Miguel Ángel.

    ---

    Quick digital-warehouse intake of a spare part a mechanic just
    took off the physical shelf that was not inventoried yet -- gap
    flagged by Miguel Ángel (2026-07-07): "mechanics need a way to
    register spare parts when they pick them up from the warehouse
    and they haven't been inventoried yet".

    No known supplier (resolved later once a delivery note for the
    same article arrives, see
    spare_parts.services.confirm_delivery_note()) and no machine
    destination (decided afterwards through normal consumption from
    the warehouse) -- delegates all logic to
    spare_parts.services.register_uninventoried_warehouse_stock().

    Access: same permission as the rest of the Almacén (ADMIN/
    SUPERVISOR/WORKSHOP/WORKSHOPBOSS) -- mechanics are the ones doing
    this intake on the spot, per Miguel Ángel's confirmation.
    """

    template_name = 'workorder_spare_parts/spare_part_quick_intake_form.html'

    def get(self, request):
        return render(request, self.template_name, {
            'company_user': request.user.company_user,
            'active_nav': 'workorder_spare_parts_warehouse',
            'form': QuickWarehouseIntakeForm(),
        })

    def post(self, request):
        form = QuickWarehouseIntakeForm(request.POST)
        if not form.is_valid():
            return render(request, self.template_name, {
                'company_user': request.user.company_user,
                'active_nav': 'workorder_spare_parts_warehouse',
                'form': form,
            })

        cleaned = form.cleaned_data
        try:
            entry = register_uninventoried_warehouse_stock(
                company=request.user.company_user.company,
                created_by=request.user.company_user,
                description=cleaned['description'],
                is_uncountable=cleaned['is_uncountable'],
                stock_quantity=cleaned['stock_quantity'],
                stock_level=cleaned['stock_level'],
            )
        except ValueError as exc:
            messages.error(request, str(exc))
            return render(request, self.template_name, {
                'company_user': request.user.company_user,
                'active_nav': 'workorder_spare_parts_warehouse',
                'form': form,
            })

        messages.success(
            request,
            f"Repuesto '{entry.description}' [{entry.internal_reference}] "
            f"dado de alta en almacén, sin proveedor conocido todavía.",
        )
        return redirect('workorder_spare_parts:warehouse_list')
