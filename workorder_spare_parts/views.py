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
from django.db.models import Count, IntegerField, Max, Q, Case, Sum, Value, When
from django.http import Http404, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
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
    Catálogo de repuestos, para Administración -- AGRUPADO por
    artículo real (internal_reference), no una fila por cada entrada
    de stock individual. Petición explícita de Miguel Ángel
    (S116-H10): "pensar en la organización del almacén [...] la
    ficha de cada repuesto" -- confirmado tras revisar la pantalla
    real: antes era una lista plana, una fila por SparePartEntry, sin
    agrupar ni mostrar nunca el historial de movimientos junto. La
    misma referencia interna puede tener varias SparePartEntry a lo
    largo del tiempo (una en almacén, otra ya consumida hace meses,
    etc.) -- aquí se agrupan en una sola fila por artículo, y el
    detalle de cada una (con su historial completo de movimientos)
    vive en SparePartArticleDetailView.

    Corregido 2026-07-07 a petición de Miguel Ángel: esto y el
    "Almacén" de Mecánicos (SparePartWarehouseListView) son DOS
    entidades distintas, no la misma vista con dos etiquetas. Este
    catálogo es el registro general (quién lo vende, a qué precio) --
    sin limbo, sin avisos de antigüedad, sin gestión de stock físico,
    eso es responsabilidad de los mecánicos en su propia vista de
    Almacén. Acceso restringido a ADMIN/SUPERVISOR -- los mecánicos
    no tienen por qué ver precios de compra ni datos de proveedor.
    ---
    Spare parts catalog, for Administración -- GROUPED by real
    article (internal_reference), not one row per individual stock
    entry. See above for the S116-H10 rationale.
    """

    template_name = 'workorder_spare_parts/spare_part_entry_list.html'
    context_object_name = 'articles'
    paginate_by = 30

    # S116-H10: mismo patron de orden multiple con prioridad que ya
    # se hizo en Albaranes y Almacen -- peticion explicita de Miguel
    # Angel ("deberiamos poder lo mismo ordenar, senalar casilleros,
    # etcetera"). Aqui SI sigue siendo una queryset real (agrupada con
    # .values()/.annotate(), no una lista de Python materializada
    # como en Almacen), asi que el orden multiple se aplica con
    # order_by() de Django, no con sort() de Python.
    _SORTABLE_FIELDS = {
        'ref': 'internal_reference',
        'descripcion': 'description',
        'stock': 'total_stock',
        'tipo': 'status_rank',
    }
    _MAX_SORT_KEYS = 4

    def _parse_sort_param(self, raw):
        keys = []
        seen = set()
        for token in raw.split(','):
            token = token.strip()
            if not token:
                continue
            desc = token.startswith('-')
            key = token.lstrip('-')
            if key in self._SORTABLE_FIELDS and key not in seen:
                keys.append((key, desc))
                seen.add(key)
        return keys

    def get_queryset(self):
        company = self.request.user.company_user.company
        qs = SparePartEntry.objects.filter(company=company)
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

        sort_param = self.request.GET.get('sort', '').strip()
        self._sort_keys = self._parse_sort_param(sort_param)
        if self._sort_keys:
            order_exprs = [
                ('-' if desc else '') + self._SORTABLE_FIELDS[key]
                for key, desc in self._sort_keys
            ]
        else:
            order_exprs = ['internal_reference']

        # S116-H10: agrupado por artículo -- descripción representativa
        # (la más reciente, vía Max(pk) implícito en el order_by de
        # abajo no aplica a Max(description) directamente, así que se
        # toma la de mayor pk con una subconsulta sería más exacto,
        # pero Max(description) alfabético es una aproximación
        # aceptable dado que la descripción rara vez cambia entre
        # entradas del mismo artículo -- a revisar si da problemas
        # reales). Stock total SOLO cuenta entradas en almacén
        # contables -- ni el limbo ni lo consumido es "stock
        # disponible" (mismo criterio que StockAssignmentService en
        # todo el módulo). entry_pk: dado el constraint real
        # unique_internal_reference_per_company, cada grupo tiene
        # SIEMPRE exactamente una SparePartEntry -- Max('id') la
        # recupera sin necesidad de otra consulta, para las acciones
        # (ficha, borrado) que operan por pk.
        return (
            qs.exclude(internal_reference='')
            .values('internal_reference')
            .annotate(
                description=Max('description'),
                minimum_stock=Max('minimum_stock'),
                entry_pk=Max('id'),
                has_movements=Count('movements', distinct=True),
                # S116-H10: petición explícita de Miguel Ángel -- "la
                # única columna que falta por ordenar" es la de
                # Entradas (tipo: limbo/almacén/consumido). Es la
                # columna original que ya usaba WAREHOUSE/PRE_ASSIGNED/
                # CONSUMED para las badges -- max_status aquí (un solo
                # valor real por grupo, dado el constraint) es la base
                # sobre la que status_rank (abajo, en el SEGUNDO
                # .annotate()) construye el orden de agrupación real.
                max_status=Max('status'),
                total_stock=Sum(
                    'stock_quantity',
                    filter=Q(status='WAREHOUSE', is_uncountable=False),
                ),
                warehouse_count=Count(
                    'id', filter=Q(status='WAREHOUSE'), distinct=True,
                ),
                pre_assigned_count=Count(
                    'id', filter=Q(status='PRE_ASSIGNED'), distinct=True,
                ),
                consumed_count=Count(
                    'id', filter=Q(status='CONSUMED'), distinct=True,
                ),
                entry_count=Count('id', distinct=True),
            )
            .annotate(
                # Rango de agrupación -- limbo primero (lo más urgente
                # de ver junto), luego almacén, luego consumido.
                status_rank=Case(
                    When(max_status='PRE_ASSIGNED', then=Value(0)),
                    When(max_status='WAREHOUSE', then=Value(1)),
                    When(max_status='CONSUMED', then=Value(2)),
                    default=Value(3),
                    output_field=IntegerField(),
                ),
            )
            .order_by(*order_exprs)
        )

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

        # S116-H10: enlaces/flecha/prioridad de cabecera, mismo patrón
        # que Albaranes/Almacén -- resuelto aquí (plantillas tontas),
        # preservando el resto de filtros y la página actual.
        sort_keys = getattr(self, '_sort_keys', [])
        active_keys = [k for k, _ in sort_keys]
        sort_urls = {}
        sort_arrows = {}
        sort_priority = {}
        for key in self._SORTABLE_FIELDS:
            if key in active_keys:
                idx = active_keys.index(key)
                _, desc = sort_keys[idx]
                sort_arrows[key] = '▼' if desc else '▲'
                sort_priority[key] = idx + 1 if len(sort_keys) > 1 else ''
                new_desc = (not desc) if idx == 0 else False
                new_keys = (
                    [(key, new_desc)]
                    + [(k, d) for k, d in sort_keys if k != key]
                )
            else:
                sort_arrows[key] = ''
                sort_priority[key] = ''
                new_keys = [(key, False)] + sort_keys
            new_keys = new_keys[:self._MAX_SORT_KEYS]
            new_sort_param = ','.join(
                (('-' if d else '') + k) for k, d in new_keys
            )
            params = self.request.GET.copy()
            params['sort'] = new_sort_param
            # S116-H10: cambiar de orden vuelve siempre a la página 1
            # -- quedarse en la página 3 de un listado que se acaba de
            # reordenar no tiene ningún sentido (mismo motivo por el
            # que Miguel Ángel señaló que cambiar de página perdía el
            # orden: aquí es el caso simétrico, cambiar el orden no
            # debe arrastrar una página que ya no corresponde).
            params.pop('page', None)
            sort_urls[key] = '?' + params.urlencode()

        clear_sort_params = self.request.GET.copy()
        clear_sort_params.pop('sort', None)
        clear_sort_params.pop('page', None)
        ctx['sort_urls'] = sort_urls
        ctx['sort_arrows'] = sort_arrows
        ctx['sort_priority'] = sort_priority
        ctx['sort_active'] = bool(sort_keys)
        ctx['current_sort'] = self.request.GET.get('sort', '')
        ctx['clear_sort_url'] = (
            '?' + clear_sort_params.urlencode() if clear_sort_params
            else '?'
        )

        # S116-H10: hallazgo real de Miguel Ángel -- "al cambiar de
        # página se pierden todos los ordenamientos [...] tiene
        # sentido solo si el número de entradas fuese inferior al
        # número de entradas permitidas por página". Los enlaces
        # "Anterior"/"Siguiente" solo llevaban page=N, perdiendo sort/
        # status/q/machine por el camino. Resueltos aquí, como el
        # resto de enlaces de esta vista (plantillas tontas).
        page_obj = ctx.get('page_obj')
        if page_obj is not None:
            if page_obj.has_previous():
                prev_params = self.request.GET.copy()
                prev_params['page'] = page_obj.previous_page_number()
                ctx['prev_page_url'] = '?' + prev_params.urlencode()
            if page_obj.has_next():
                next_params = self.request.GET.copy()
                next_params['page'] = page_obj.next_page_number()
                ctx['next_page_url'] = '?' + next_params.urlencode()
        return ctx


class SparePartArticleDetailView(SupervisorAccessMixin, View):
    """
    Ficha de artículo (S116-H10) -- petición explícita de Miguel
    Ángel: "pensar en la organización del almacén [...] de dónde
    vienen [las cosas]". Reúne, para una referencia interna dada,
    TODAS sus SparePartEntry a lo largo del tiempo (una en almacén
    hoy, otra ya consumida hace meses, etc. -- pueden ser varias) y
    el historial COMPLETO de StockMovement de todas ellas juntas, en
    un único sitio: de qué albarán vino cada una, a qué máquina/
    ticket se pre-asignó, en qué parte se consumió, y cualquier
    ajuste o devolución. Antes esta trazabilidad ya existía en BD
    pero repartida en tres pantallas distintas sin unir nunca.

    GET /panel/repuestos/catalogo/articulo/<internal_reference>/
    """

    template_name = 'workorder_spare_parts/spare_part_article_detail.html'

    def get(self, request, internal_reference):
        company = request.user.company_user.company
        entries = list(
            SparePartEntry.objects.filter(
                company=company, internal_reference=internal_reference,
            )
            .select_related('machine', 'breakdown_ticket', 'supplier')
            .prefetch_related('source_delivery_note_lines__delivery_note')
            .order_by('-pk')
        )
        if not entries:
            raise Http404(
                'No existe ningún repuesto con esa referencia interna.'
            )

        for entry in entries:
            origin_line = entry.source_delivery_note_lines.first()
            entry.origin_note = (
                origin_line.delivery_note if origin_line else None
            )

        movements = (
            StockMovement.objects.filter(spare_part_entry__in=entries)
            .select_related(
                'machine', 'breakdown_ticket', 'work_order_entry_line',
                'created_by__user',
            )
            .order_by('-created_at')
        )

        total_stock = sum(
            (e.stock_quantity or Decimal('0')) for e in entries
            if e.status == SparePartEntry.STATUS_WAREHOUSE
            and not e.is_uncountable
        )
        minimum_stock = entries[0].minimum_stock or Decimal('0')
        below_minimum = bool(
            minimum_stock and total_stock < minimum_stock
        )

        return render(request, self.template_name, {
            'company_user': request.user.company_user,
            'active_nav': 'workorder_spare_parts_catalog',
            'internal_reference': internal_reference,
            'description': entries[0].description,
            'entries': entries,
            'movements': movements,
            'total_stock': total_stock,
            'minimum_stock': minimum_stock,
            'below_minimum': below_minimum,
        })


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
        return redirect(
            'workorder_spare_parts:catalog_article_detail',
            entry.internal_reference,
        )


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
        # S116-H10: vuelve a la ficha del artículo (agrupado por
        # internal_reference), no al catálogo plano -- el catálogo ya
        # no lista entradas individuales, así que ese "de vuelta"
        # perdía el contexto de qué artículo se estaba editando.
        if entry.internal_reference:
            return redirect(
                'workorder_spare_parts:catalog_article_detail',
                entry.internal_reference,
            )
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
        internal_reference = entry.internal_reference
        if entry.movements.exists():
            messages.error(
                request,
                "No se puede eliminar: este repuesto ya tiene movimientos de "
                "stock registrados (afectaría al historial de analítica de costes).",
            )
            if internal_reference:
                return redirect(
                    'workorder_spare_parts:catalog_article_detail',
                    internal_reference,
                )
            return redirect('workorder_spare_parts:catalog_list')
        description = entry.description
        entry.delete()
        messages.success(request, f"Repuesto '{description}' eliminado correctamente.")
        # S116-H10: si era la última entrada de este artículo, la
        # ficha ya no existe (0 resultados) -- vuelve al catálogo en
        # ese caso, a la ficha si todavía quedan otras entradas.
        if internal_reference and SparePartEntry.objects.filter(
            company=request.user.company_user.company,
            internal_reference=internal_reference,
        ).exists():
            return redirect(
                'workorder_spare_parts:catalog_article_detail',
                internal_reference,
            )
        return redirect('workorder_spare_parts:catalog_list')


class SparePartEntryBulkDeleteView(SupervisorAccessMixin, View):
    """
    S116-H10: borra varios artículos del catálogo a la vez -- petición
    explícita de Miguel Ángel ("deberíamos poder lo mismo ordenar,
    señalar casilleros [...] las acciones que se pueden realizar").
    Misma regla de seguridad que SparePartEntryDeleteView: nunca borra
    uno que ya tenga movimientos de stock reales -- en vez de bloquear
    todo el lote por eso, lo omite en silencio y avisa cuántos se han
    saltado.
    """

    def post(self, request):
        company = request.user.company_user.company
        pks = request.POST.getlist('selected')
        if not pks:
            messages.warning(request, 'No has seleccionado ningún repuesto.')
            return redirect('workorder_spare_parts:catalog_list')

        qs = SparePartEntry.objects.filter(pk__in=pks, company=company)
        blocked_count = 0
        deleted_count = 0
        for entry in qs:
            if entry.movements.exists():
                blocked_count += 1
                continue
            entry.delete()
            deleted_count += 1

        if deleted_count:
            messages.success(
                request,
                f"{deleted_count} repuesto{'s' if deleted_count != 1 else ''} "
                f"eliminado{'s' if deleted_count != 1 else ''} correctamente.",
            )
        if blocked_count:
            messages.warning(
                request,
                f"{blocked_count} repuesto{'s' if blocked_count != 1 else ''} "
                f"no se {'han' if blocked_count != 1 else 'ha'} tocado -- ya "
                f"{'tenían' if blocked_count != 1 else 'tenía'} movimientos de "
                f"stock reales registrados.",
            )
        if not deleted_count and not blocked_count:
            messages.warning(
                request, 'Ningún repuesto seleccionado existía ya.',
            )
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

    # S116-H10: mismo patrón de orden múltiple con prioridad que
    # delivery_notes.DeliveryNoteAdminListView -- petición explícita
    # de Miguel Ángel ("pasar aquí todo lo que hemos hecho en el
    # anterior"). `rows` ya es una lista de Python materializada (no
    # una queryset -- cada fila mezcla el SparePartEntry con
    # age_days/age_class calculados), así que aquí se ordena en
    # Python, no con order_by() de Django: una función por columna
    # que extrae la clave de un `row` (el dict {'entry':...,
    # 'age_days':...}).
    _SORTABLE_FIELDS = {
        'ref': lambda row: (row['entry'].internal_reference or ''),
        'descripcion': lambda row: (row['entry'].description or '').lower(),
        'cantidad': lambda row: (
            Decimal('-1') if row['entry'].is_uncountable
            else (row['entry'].stock_quantity or Decimal('0'))
        ),
        'estado': lambda row: row['entry'].status,
        'maquina': lambda row: (
            row['entry'].machine.code if row['entry'].machine
            else (
                row['entry'].breakdown_ticket.ticket_date_code or ''
                if row['entry'].breakdown_ticket else ''
            )
        ),
        'antiguedad': lambda row: (
            row['age_days'] if row['age_days'] is not None else -1
        ),
    }
    _MAX_SORT_KEYS = 4

    def _parse_sort_param(self, raw):
        keys = []
        seen = set()
        for token in raw.split(','):
            token = token.strip()
            if not token:
                continue
            desc = token.startswith('-')
            key = token.lstrip('-')
            if key in self._SORTABLE_FIELDS and key not in seen:
                keys.append((key, desc))
                seen.add(key)
        return keys

    def get(self, request):
        from django.utils.timezone import now as _tz_now

        company = request.user.company_user.company
        qs = (
            SparePartEntry.objects.filter(company=company)
            .select_related('machine', 'breakdown_ticket')
            .prefetch_related('source_delivery_note_lines__delivery_note')
        )
        status = request.GET.get('status', '').strip()
        if status:
            qs = qs.filter(status=status)
        machine_pk = request.GET.get('machine', '').strip()
        if machine_pk:
            qs = qs.filter(machine_id=machine_pk)
        # Pre-asignados primero (por antigüedad, los más viejos arriba
        # para que salten a la vista), el resto por pk descendente --
        # este es el orden de partida antes de aplicar, si lo hay, el
        # orden explícito pedido por columna (ver más abajo).
        # Pre-assigned first (by age, oldest on top so they stand
        # out), the rest by descending pk -- this is the starting
        # order before applying, if any, the explicit per-column sort
        # requested (see below).
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
            # S116-H10: albarán de origen -- petición explícita de
            # Miguel Ángel ("poder verlos desde aquí mismo, el albarán
            # al que pertenecían"). El dato ya existía en BD
            # (DeliveryNoteLine.spare_part_entry), nunca se había
            # mostrado en ningún sitio -- un SparePartEntry solo tiene
            # UNA línea de origen real (se crea una vez, al confirmar
            # el albarán), así que .first() es seguro aquí.
            origin_line = entry.source_delivery_note_lines.first()
            rows.append({
                'entry': entry, 'age_days': age_days, 'age_class': age_class,
                'origin_note': (
                    origin_line.delivery_note if origin_line else None
                ),
            })

        sort_param = request.GET.get('sort', '').strip()
        sort_keys = self._parse_sort_param(sort_param)
        if sort_keys:
            # Truco de sort estable: aplicar de la prioridad más baja a
            # la más alta, para que el último sort() (la más alta
            # prioridad) sea el que de verdad manda.
            for key, desc in reversed(sort_keys):
                rows.sort(key=self._SORTABLE_FIELDS[key], reverse=desc)

        active_keys = [k for k, _ in sort_keys]
        sort_urls = {}
        sort_arrows = {}
        sort_priority = {}
        for key in self._SORTABLE_FIELDS:
            if key in active_keys:
                idx = active_keys.index(key)
                _, desc = sort_keys[idx]
                sort_arrows[key] = '▼' if desc else '▲'
                sort_priority[key] = idx + 1 if len(sort_keys) > 1 else ''
                new_desc = (not desc) if idx == 0 else False
                new_keys = (
                    [(key, new_desc)]
                    + [(k, d) for k, d in sort_keys if k != key]
                )
            else:
                sort_arrows[key] = ''
                sort_priority[key] = ''
                new_keys = [(key, False)] + sort_keys
            new_keys = new_keys[:self._MAX_SORT_KEYS]
            new_sort_param = ','.join(
                (('-' if d else '') + k) for k, d in new_keys
            )
            params = request.GET.copy()
            params['sort'] = new_sort_param
            sort_urls[key] = '?' + params.urlencode()

        clear_sort_params = request.GET.copy()
        clear_sort_params.pop('sort', None)
        clear_sort_url = (
            '?' + clear_sort_params.urlencode() if clear_sort_params
            else '?'
        )

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
            'sort_urls': sort_urls,
            'sort_arrows': sort_arrows,
            'sort_priority': sort_priority,
            'clear_sort_url': clear_sort_url,
            'sort_active': bool(sort_keys),
            'current_sort': sort_param,
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
        # S116-H10: soporte opcional de vuelta al origen -- petición
        # explícita de Miguel Ángel: desde "Albaranes" (delivery_notes)
        # ahora también se puede devolver un repuesto en limbo a
        # almacén, y debe volver a esa pantalla, no saltar siempre al
        # almacén general. Compatible hacia atrás: sin `next`, mismo
        # comportamiento de siempre.
        next_url = request.POST.get('next', '').strip()
        if next_url and url_has_allowed_host_and_scheme(
            next_url, allowed_hosts={request.get_host()},
        ):
            return redirect(next_url)
        return redirect('workorder_spare_parts:warehouse_list')


class SparePartBulkReturnToWarehouseView(CatalogReadAccessMixin, View):
    """
    S116-H10: devuelve a almacén varios repuestos en limbo a la vez --
    petición explícita de Miguel Ángel ("pasar aquí todo lo que hemos
    hecho en el anterior [Albaranes]": casillas + acción masiva).
    Misma transición exacta que SparePartReturnToWarehouseView,
    aplicada uno a uno a cada SparePartEntry seleccionada -- nunca
    toca uno que no esté en PRE_ASSIGNED (se omite en silencio, por si
    la lista cambió entre que se cargó la página y se envió el
    formulario).

    URL: POST /panel/repuestos/almacen/devolver-varios/
    """

    def post(self, request):
        company = request.user.company_user.company
        pks = request.POST.getlist('selected')
        if not pks:
            messages.warning(request, 'No has seleccionado ningún repuesto.')
            return redirect('workorder_spare_parts:warehouse_list')

        entries = SparePartEntry.objects.filter(
            pk__in=pks, company=company,
            status=SparePartEntry.STATUS_PRE_ASSIGNED,
        )
        count = 0
        for entry in entries:
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
                notes=(
                    'Devuelto a almacén desde el limbo de pre-asignación '
                    '(acción masiva).'
                ),
            )
            count += 1

        if count:
            messages.success(
                request,
                f"{count} repuesto{'s' if count != 1 else ''} "
                f"devuelto{'s' if count != 1 else ''} a almacén "
                f"correctamente.",
            )
        else:
            messages.warning(
                request,
                'Ningún repuesto seleccionado seguía en el limbo -- no '
                'se ha tocado nada.',
            )

        next_url = request.POST.get('next', '').strip()
        if next_url and url_has_allowed_host_and_scheme(
            next_url, allowed_hosts={request.get_host()},
        ):
            return redirect(next_url)
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

        # S116-H07: distinguir un ticket realmente ajeno de uno que el
        # propio mecánico acaba de crear/cerrar en OTRA tarea de este
        # MISMO parte -- confusión real reportada por Miguel Ángel: "no
        # tenemos conciencia de que parte es el que dice que hay un
        # ticket abierto". Si el candidato ya está enganchado a una
        # línea de este mismo work_order, se marca aquí para que la
        # plantilla lo dilucide con un mensaje claro y lo preseleccione
        # -- nunca oculta la elección, el mecánico sigue pudiendo
        # corregirla.
        work_order_pk = request.GET.get('work_order_pk', '').strip()
        same_parte_ticket_pk = None
        same_parte_line_number = None
        if work_order_pk and resolution.action in ('ASK_REOPEN', 'CHOOSE'):
            _candidates = (
                [resolution.ticket] if resolution.action == 'ASK_REOPEN'
                else list(resolution.candidates)
            )
            for _cand in _candidates:
                _same_line = _cand.work_entry_lines.filter(
                    entry__work_order_id=work_order_pk,
                ).order_by('line_number').first()
                if _same_line is not None:
                    same_parte_ticket_pk = _cand.pk
                    same_parte_line_number = _same_line.line_number
                    break

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
            'same_parte_ticket_pk': same_parte_ticket_pk,
            'same_parte_line_number': same_parte_line_number,
        })


class SparePartGlobalSearchView(CatalogReadAccessMixin, View):
    """
    HTMX endpoint: modal global "Añadir repuesto" (2026-07-23, a
    peticion de Miguel Angel). A diferencia de
    SparePartWarehouseSearchView (Caso A, solo WAREHOUSE de la propia
    tarea) y SparePartPreAssignedListView (Caso B, solo de una
    maquina/ticket concreto), este endpoint busca en TODA la empresa,
    combinando WAREHOUSE y PRE_ASSIGNED -- para poder rescatar del
    limbo un repuesto pre-asignado a una maquina que nunca lo consumio,
    o asignar uno de almacen sin maquina, desde cualquier tarea del
    parte, no solo la que coincide con su codigo de maquina. No esta
    ligado a ninguna WorkOrderEntryLine todavia (se usa tanto en
    creacion como en edicion, antes de guardar el parte) -- la
    materializacion real ocurre al guardar el formulario completo, ver
    panel/views_operator.py::_parse_entry_lines_from_post y
    WorkOrderEntryFormView.post().

    GET params:
      q -- texto de busqueda libre (ref. interna, ref. proveedor,
           descripcion). Vacio -> listado completo, ordenado
           alfabeticamente por descripcion.
    """

    template_name = 'workorder_spare_parts/_global_search_results.html'

    def get(self, request):
        from spare_parts.services import StockAssignmentService

        query = request.GET.get('q', '')
        results = StockAssignmentService.search_global(
            company=request.user.company_user.company,
            query=query,
        )
        return render(request, self.template_name, {
            'results': results,
            'query': query,
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


# =============================================================================
# Selector de material en el parte de trabajo (2026-07-07) -- gap senalado
# por Miguel Angel: al anadir un repuesto desde el propio parte, en vez de
# escribirlo libre, hay que escogerlo del almacen o darlo de alta por la
# via rapida, sin salir del formulario ni tener que guardar la tarea
# (que puede estar incompleta todavia). JSON, no HTML/HTMX -- el
# formulario de parte (panel/operator/form_entry.html) usa fetch()
# vanilla en todo su JS, no HTMX (ver form_entry_assets.js).
# =============================================================================

class SparePartMaterialSearchView(CatalogReadAccessMixin, View):
    """
    Endpoint JSON: busqueda libre en el almacen digital
    (status=WAREHOUSE) para el modal de seleccion de material del
    parte de trabajo. A diferencia de SparePartWarehouseSearchView
    (H10 Paso 4, fragmento HTML anclado a un entry_line_pk ya
    existente), este no necesita ningun entry_line -- se usa mientras
    se rellena el parte, antes de que exista en BD.

    GET params: q (texto, minimo 2 caracteres).
    Respuesta: {"results": [{"pk", "description", "internal_reference",
    "stock_label"}, ...]}

    ---

    JSON endpoint: free search in the digital warehouse
    (status=WAREHOUSE) for the work-order form's material picker
    modal. Unlike SparePartWarehouseSearchView (H10 Paso 4, HTML
    fragment anchored to an already-existing entry_line_pk), this
    needs no entry_line at all -- used while filling in the work
    order, before it exists in the DB.
    """

    def get(self, request):
        query = request.GET.get('q', '').strip()
        if len(query) < 2:
            return JsonResponse({'results': []})

        company = request.user.company_user.company
        results = StockAssignmentService.search_warehouse(company, query, limit=15)
        payload = []
        for entry in results:
            stock_label = (
                (entry.stock_level or '—') if entry.is_uncountable
                else str(entry.stock_quantity)
            )
            payload.append({
                'pk': entry.pk,
                'description': entry.description,
                'internal_reference': entry.internal_reference,
                'stock_label': stock_label,
            })
        return JsonResponse({'results': payload})


class SparePartMaterialQuickCreateView(CatalogReadAccessMixin, View):
    """
    Endpoint JSON: alta rápida en almacén desde el mismo modal de
    selección de material, sin salir del formulario de parte ni tener
    que guardar la tarea todavía -- mismo servicio que
    SparePartQuickIntakeCreateView
    (register_uninventoried_warehouse_stock()), pero responde en JSON
    en vez de redirigir, para uso desde fetch() en el modal.

    POST params: description, is_uncountable ('1' o vacío),
    stock_quantity, stock_level.
    Respuesta: {"pk", "description", "internal_reference"}, o
    {"error": "..."} con status 400.

    ---

    JSON endpoint: quick warehouse intake from the same material
    picker modal, without leaving the work-order form or having to
    save the task yet -- same service as SparePartQuickIntakeCreateView
    (register_uninventoried_warehouse_stock()), but responds in JSON
    instead of redirecting, for use from the modal's fetch() call.
    """

    def post(self, request):
        description = request.POST.get('description', '').strip()
        is_uncountable = request.POST.get('is_uncountable') == '1'
        stock_quantity_raw = request.POST.get('stock_quantity', '').strip()
        stock_level = request.POST.get('stock_level', '').strip() or None

        stock_quantity = None
        if stock_quantity_raw:
            try:
                stock_quantity = Decimal(stock_quantity_raw)
            except (InvalidOperation, ValueError):
                return JsonResponse({'error': 'Cantidad no válida.'}, status=400)

        try:
            entry = register_uninventoried_warehouse_stock(
                company=request.user.company_user.company,
                created_by=request.user.company_user,
                description=description,
                is_uncountable=is_uncountable,
                stock_quantity=stock_quantity,
                stock_level=stock_level,
            )
        except ValueError as exc:
            return JsonResponse({'error': str(exc)}, status=400)

        return JsonResponse({
            'pk': entry.pk,
            'description': entry.description,
            'internal_reference': entry.internal_reference,
        })
