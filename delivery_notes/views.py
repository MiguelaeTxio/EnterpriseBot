# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/delivery_notes/views.py
"""
Admin CRUD views for supplier delivery notes (H10, gap flagged by
Miguel Ángel 2026-07-08).

Scope deliberately bounded by an existing safety invariant already in
spare_parts.views.DeliveryNoteDetailView: a DeliveryNote with
status=ASSIGNED has already materialised real StockMovement/
SparePartEntry records (warehouse stock, pre-assignments) -- editing
its lines here would silently desync those records from the delivery
note. So:

  - List  : all delivery notes, any status, filterable.
  - Detail: read-only for ASSIGNED notes (audit trail); for
    PENDING/PROCESSED notes, redirects to the existing
    spare_parts:delivery_note_detail edit view (already handles
    correction pre-confirmation -- no duplicated logic here).
  - Delete: only allowed for notes that are NOT ASSIGNED (nothing to
    desync yet). ASSIGNED notes are never deletable from here --
    reversing their stock effects is a separate, bigger decision not
    requested yet.

---

Vistas CRUD de administración de albaranes de proveedor (H10, gap
señalado por Miguel Ángel 2026-07-08).

Alcance delimitado deliberadamente por un invariante de seguridad ya
existente en spare_parts.views.DeliveryNoteDetailView: un DeliveryNote
con status=ASSIGNED ya ha materializado StockMovement/SparePartEntry
reales (stock de almacén, pre-asignaciones) -- editar sus líneas aquí
desincronizaría esos registros del albarán en silencio. Por tanto:

  - Listado: todos los albaranes, cualquier estado, filtrable.
  - Detalle: solo lectura para albaranes ASSIGNED (traza de auditoría);
    para PENDING/PROCESSED, redirige a la vista de edición ya
    existente spare_parts:delivery_note_detail (ya gestiona la
    corrección pre-confirmación -- sin lógica duplicada aquí).
  - Borrado: solo permitido para albaranes que NO estén ASSIGNED (nada
    que desincronizar todavía). Los ASSIGNED nunca son borrables desde
    aquí -- revertir sus efectos de stock es una decisión aparte y
    mayor, no solicitada todavía.
"""
import logging

from django.contrib import messages
from django.db.models import Case, Count, F, IntegerField, Q, Value, When
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View

from panel.mixins import SupervisorAccessMixin
from spare_parts.gcs_service import DELIVERY_NOTES_BUCKET, generate_signed_url
from spare_parts.models import DeliveryNote

logger = logging.getLogger(__name__)


class DeliveryNoteAdminListView(SupervisorAccessMixin, View):
    """
    Lists all DeliveryNote records for the current company, filterable
    by status, supplier name and recipient company code. Each row also
    carries its assignment progress (LIMBO/PARTIAL/FULL), computed via
    DeliveryNote.assignment_progress() -- how much of the note's
    MACHINE-type lines have left the pre-assignment limbo. Resolved
    here, not in the template (dumb templates directive) -- see
    status_badge_class precedent in panel/views_workorders.py (S012).
    ---
    Lista todos los DeliveryNote de la empresa actual, filtrable por
    estado, nombre de proveedor y código de empresa destinataria. Cada
    fila lleva también su progreso de asignación (LIMBO/PARTIAL/FULL),
    calculado con DeliveryNote.assignment_progress() -- cuánto de sus
    líneas MACHINE ya salió del limbo de pre-asignación. Resuelto aquí,
    no en la plantilla (directriz de plantillas tontas) -- ver
    precedente status_badge_class en panel/views_workorders.py (S012).
    """

    template_name = 'delivery_notes/list.html'

    _PROGRESS_BADGE = {
        'LIMBO': 'bg-danger',
        'PARTIAL': 'bg-warning text-dark',
        'FULL': 'bg-success',
    }
    _PROGRESS_LABEL = {
        'LIMBO': 'En limbo',
        'PARTIAL': 'Parcialmente asignado',
        'FULL': 'Totalmente asignado',
    }

    # S116-H10: columnas ordenables desde la cabecera de la tabla,
    # petición explícita de Miguel Ángel ("debemos poder ordenar por
    # columna para gestionar un poco esto"). Clave = nombre corto que
    # sale en el enlace ?sort=; valor = campo real de DeliveryNote.
    # 'lineas' y 'asignacion' quedan fuera a propósito -- son un
    # recuento y un cálculo en Python (assignment_progress()), no un
    # campo de BD, y ordenar por ellos exigiría anotar la consulta;
    # no se ha hecho todavía.
    # S116-H10: columnas ordenables desde la cabecera de la tabla,
    # petición explícita de Miguel Ángel ("debemos poder ordenar por
    # columna [...] falta la columna de asignación y la de revisado
    # por, la del número de líneas"). 'lineas' y 'asignacion' se
    # resuelven con anotaciones (num_lines_annotated/progress_rank,
    # ver get()) porque no son un campo real de DeliveryNote --
    # 'revisado' ordena por processed_by__user__username, el único
    # campo de nombre siempre poblado (first_name/last_name pueden
    # estar vacíos).
    _SORTABLE_FIELDS = {
        'fecha': 'delivery_date',
        'proveedor': 'supplier_name',
        'numero': 'delivery_number',
        'destinatario': 'recipient_company_code',
        'estado': 'status',
        'revisado': 'processed_by__user__username',
        'lineas': 'num_lines_annotated',
        'asignacion': 'progress_rank',
    }
    _DEFAULT_SORT = '-fecha'

    def get(self, request):
        company = request.user.company_user.company
        status = request.GET.get('status', '').strip()
        supplier = request.GET.get('supplier', '').strip()
        recipient = request.GET.get('recipient', '').strip()

        sort = request.GET.get('sort', self._DEFAULT_SORT).strip()
        sort_key = sort.lstrip('-')
        if sort_key not in self._SORTABLE_FIELDS:
            sort = self._DEFAULT_SORT
            sort_key = sort.lstrip('-')
        db_field = self._SORTABLE_FIELDS[sort_key]
        order_expr = ('-' + db_field) if sort.startswith('-') else db_field

        notes = (
            DeliveryNote.objects
            .filter(company=company)
            .select_related('processed_by__user', 'supplier')
            .prefetch_related('lines', 'lines__spare_part_entry')
            .annotate(
                num_lines_annotated=Count('lines', distinct=True),
                _total_machine=Count(
                    'lines',
                    filter=Q(
                        lines__assignment_type='MACHINE',
                        lines__spare_part_entry__isnull=False,
                    ),
                    distinct=True,
                ),
                _assigned_machine=Count(
                    'lines',
                    filter=Q(
                        lines__assignment_type='MACHINE',
                        lines__spare_part_entry__isnull=False,
                    ) & ~Q(lines__spare_part_entry__status='PRE_ASSIGNED'),
                    distinct=True,
                ),
            )
            .annotate(
                # S116-H10: rango numérico para poder ordenar por
                # 'Asignación' -- 0=En limbo, 1=Parcial, 2=Total,
                # 3=nada que rastrear (sin líneas MACHINE confirmadas).
                # Mismo criterio que DeliveryNote.assignment_progress().
                progress_rank=Case(
                    When(_total_machine=0, then=Value(3)),
                    When(_assigned_machine=0, then=Value(0)),
                    When(
                        _assigned_machine=F('_total_machine'),
                        then=Value(2),
                    ),
                    default=Value(1),
                    output_field=IntegerField(),
                ),
            )
            .order_by(order_expr)
        )
        if status:
            notes = notes.filter(status=status)
        if supplier:
            notes = notes.filter(
                Q(supplier__name__icontains=supplier)
                | Q(supplier_name__icontains=supplier)
            )
        if recipient:
            notes = notes.filter(recipient_company_code=recipient)

        # Progreso de asignación resuelto aquí (no en la plantilla) y
        # anotado directamente sobre cada instancia -- son atributos
        # calculados, no campos de BD, así que no chocan con nada.
        for note in notes:
            state, assigned, total = note.assignment_progress()
            note.progress_state = state
            note.progress_badge_class = self._PROGRESS_BADGE.get(state, '')
            note.progress_label = self._PROGRESS_LABEL.get(state, '')
            note.progress_assigned = assigned
            note.progress_total = total
            # URL de descarga resuelta aquí (S022, misma directriz de
            # plantillas tontas): gcs_blob_name -> URL firmada bajo
            # demanda; drive_web_link (legado) se usa tal cual.
            note.download_url = None
            if note.gcs_blob_name:
                try:
                    note.download_url = generate_signed_url(
                        DELIVERY_NOTES_BUCKET, note.gcs_blob_name,
                    )
                except Exception:
                    logger.exception(
                        '# [DeliveryNoteAdminListView] Fallo generando '
                        'URL firmada para albarán #%d (blob=%s).',
                        note.pk, note.gcs_blob_name,
                    )
            elif note.drive_web_link:
                note.download_url = note.drive_web_link

        recipient_codes = (
            DeliveryNote.objects
            .filter(company=company)
            .exclude(recipient_company_code='')
            .values_list('recipient_company_code', flat=True)
            .distinct()
            .order_by('recipient_company_code')
        )

        # S116-H10: enlace y flecha de cada cabecera ordenable,
        # resueltos aquí (directriz de plantillas tontas, misma que ya
        # sigue esta vista para progress_badge_class/download_url) --
        # nunca en el propio template. Preserva el resto de filtros al
        # cambiar de orden.
        sort_urls = {}
        sort_arrows = {}
        for key in self._SORTABLE_FIELDS :
            if sort_key == key :
                next_sort = ("" if sort .startswith ("-")else "-")+key 
                sort_arrows [key ]="▲" if not sort .startswith ("-")else "▼"
            else :
                next_sort =key 
                sort_arrows [key ]=""
            params =request .GET .copy ()
            params ["sort"]=next_sort 
            sort_urls [key ]="?"+params .urlencode ()

        return render(request, self.template_name, {
            'company_user': request.user.company_user,
            'active_nav': 'delivery_notes_admin',
            'notes': notes,
            'status_choices': DeliveryNote.STATUS_CHOICES,
            'recipient_codes': recipient_codes,
            'filter_status': status,
            'filter_supplier': supplier,
            'filter_recipient': recipient,
            'sort_urls': sort_urls,
            'sort_arrows': sort_arrows,
            'current_sort': sort,
        })


class DeliveryNoteAdminDetailView(SupervisorAccessMixin, View):
    """
    Read-only detail for an ASSIGNED delivery note (audit trail).
    Non-ASSIGNED notes redirect to the existing pre-confirmation edit
    view in spare_parts -- editing logic is not duplicated here.
    ---
    Detalle de solo lectura para un albarán ASSIGNED (traza de
    auditoría). Los albaranes no-ASSIGNED redirigen a la vista de
    edición pre-confirmación ya existente en spare_parts -- la lógica
    de edición no se duplica aquí.
    """

    template_name = 'delivery_notes/detail.html'

    def get(self, request, pk):
        company = request.user.company_user.company
        note = get_object_or_404(DeliveryNote, pk=pk, company=company)

        if note.status != 'ASSIGNED':
            return redirect(
                'spare_parts:delivery_note_detail', pk=note.pk,
            )

        # S116-H10: petición explícita de Miguel Ángel -- "ver los que
        # están en el limbo, ver por qué no están asignados, si la
        # máquina a la que se habían asignado o preasignado se ha
        # terminado la avería o no". Resuelto aquí (directriz de
        # plantillas tontas), nunca en el template: para cada línea
        # con un SparePartEntry vinculado, su estado real (en limbo /
        # consumido / almacén) y, si sigue en limbo y está ligado a un
        # ticket, el estado actual de ese ticket.
        lines = list(
            note.lines.select_related(
                'spare_part_entry', 'spare_part_entry__breakdown_ticket',
                'machine',
            )
        )
        for line in lines:
            entry = line.spare_part_entry
            line.entry_status = entry.status if entry else None
            line.entry_status_label = (
                entry.get_status_display() if entry else None
            )
            line.ticket = (
                entry.breakdown_ticket
                if entry and entry.status == 'PRE_ASSIGNED'
                else None
            )

        return render(request, self.template_name, {
            'company_user': request.user.company_user,
            'active_nav': 'delivery_notes_admin',
            'note': note,
            'lines': lines,
        })


class DeliveryNoteAdminDeleteView(SupervisorAccessMixin, View):
    """
    Deletes a DeliveryNote (cascades to its DeliveryNoteLine rows).
    Blocked for status=ASSIGNED -- see module docstring.
    ---
    Elimina un DeliveryNote (encadena el borrado de sus
    DeliveryNoteLine). Bloqueado para status=ASSIGNED -- ver docstring
    del módulo.
    """

    def post(self, request, pk):
        company = request.user.company_user.company
        note = get_object_or_404(DeliveryNote, pk=pk, company=company)

        if note.status == 'ASSIGNED':
            messages.error(
                request,
                'Este albarán ya está confirmado y asignado -- no se '
                'puede eliminar desde aquí porque ya ha generado '
                'movimientos de stock reales. Contacta con el '
                'desarrollador si de verdad hace falta revertirlo.',
            )
            return redirect('delivery_notes:detail', pk=note.pk)

        note.delete()
        messages.success(request, 'Albarán eliminado correctamente.')
        return redirect('delivery_notes:list')


class DeliveryNoteAdminBulkDeleteView(SupervisorAccessMixin, View):
    """
    Bulk-deletes several DeliveryNote at once -- petición explícita de
    Miguel Ángel: "una vez que están vistos los que erróneos [...] si
    hay 50, no tener que estar borrando de uno en uno".

    Misma regla de seguridad que DeliveryNoteAdminDeleteView: nunca
    borra uno con status=ASSIGNED (ya generó movimientos de stock
    reales) -- en vez de bloquear todo el lote por eso, lo omite
    silenciosamente y avisa cuántos se han saltado, para no impedir
    borrar los demás.
    ---
    Borra varios DeliveryNote a la vez -- ver arriba.
    """

    def post(self, request):
        company = request.user.company_user.company
        pks = request.POST.getlist('selected')
        if not pks:
            messages.warning(request, 'No has seleccionado ningún albarán.')
            return redirect('delivery_notes:list')

        qs = DeliveryNote.objects.filter(pk__in=pks, company=company)
        assigned_count = qs.filter(status='ASSIGNED').count()
        deletable = qs.exclude(status='ASSIGNED')
        deleted_count = deletable.count()
        deletable.delete()

        if deleted_count:
            messages.success(
                request,
                f"{deleted_count} albarán"
                f"{'es' if deleted_count != 1 else ''} eliminado"
                f"{'s' if deleted_count != 1 else ''} correctamente.",
            )
        if assigned_count:
            messages.warning(
                request,
                f"{assigned_count} albarán"
                f"{'es' if assigned_count != 1 else ''} ya "
                f"{'estaban' if assigned_count != 1 else 'estaba'} "
                f"asignado{'s' if assigned_count != 1 else ''} y no "
                f"se {'han' if assigned_count != 1 else 'ha'} tocado "
                f"-- ya generó movimientos de stock reales.",
            )
        if not deleted_count and not assigned_count:
            messages.warning(
                request, 'Ningún albarán seleccionado existía ya.',
            )

        return redirect('delivery_notes:list')
