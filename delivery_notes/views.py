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
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View

from panel.mixins import SupervisorAccessMixin
from spare_parts.models import DeliveryNote


class DeliveryNoteAdminListView(SupervisorAccessMixin, View):
    """
    Lists all DeliveryNote records for the current company, filterable
    by status, supplier name and recipient company code.
    ---
    Lista todos los DeliveryNote de la empresa actual, filtrable por
    estado, nombre de proveedor y código de empresa destinataria.
    """

    template_name = 'delivery_notes/list.html'

    def get(self, request):
        company = request.user.company_user.company
        status = request.GET.get('status', '').strip()
        supplier = request.GET.get('supplier', '').strip()
        recipient = request.GET.get('recipient', '').strip()

        notes = (
            DeliveryNote.objects
            .filter(company=company)
            .select_related('processed_by__user')
            .prefetch_related('lines')
        )
        if status:
            notes = notes.filter(status=status)
        if supplier:
            notes = notes.filter(supplier_name__icontains=supplier)
        if recipient:
            notes = notes.filter(recipient_company_code=recipient)

        recipient_codes = (
            DeliveryNote.objects
            .filter(company=company)
            .exclude(recipient_company_code='')
            .values_list('recipient_company_code', flat=True)
            .distinct()
            .order_by('recipient_company_code')
        )

        return render(request, self.template_name, {
            'company_user': request.user.company_user,
            'active_nav': 'delivery_notes_admin',
            'notes': notes,
            'status_choices': DeliveryNote.STATUS_CHOICES,
            'recipient_codes': recipient_codes,
            'filter_status': status,
            'filter_supplier': supplier,
            'filter_recipient': recipient,
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

        return render(request, self.template_name, {
            'company_user': request.user.company_user,
            'active_nav': 'delivery_notes_admin',
            'note': note,
            'lines': note.lines.all(),
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
