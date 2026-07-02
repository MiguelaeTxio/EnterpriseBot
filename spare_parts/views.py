# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/spare_parts/views.py
"""
Views for the spare parts and supplier delivery note module.
Implements the delivery note ingestion flow described in annex H10,
section 3.1: upload -> Gemini Vision extraction -> manual review ->
confirmation of the assignment circuit.

---

Vistas del módulo de albaranes de proveedores y repuestos. Implementa
el flujo de ingesta de albaranes descrito en el anexo H10, sección
3.1: subida -> extracción con Gemini Vision -> revisión manual ->
confirmación del circuito de asignación.
"""
import logging
from datetime import date

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View

from panel.mixins import CompanyUserRequiredMixin

from .models import DeliveryNote, DeliveryNoteLine
from .services import (
    GeminiVisionExtractionService,
    confirm_delivery_note,
    parse_decimal,
    resolve_line_assignment,
)

logger = logging.getLogger(__name__)

# Accepted upload extensions and their DeliveryNote.source_type.
# Extensiones de subida aceptadas y su DeliveryNote.source_type.
_ALLOWED_EXTENSIONS = {
    '.pdf': 'PDF',
    '.jpg': 'PHOTO',
    '.jpeg': 'PHOTO',
    '.png': 'PHOTO',
    '.webp': 'PHOTO',
}


class DeliveryNoteUploadView(CompanyUserRequiredMixin, View):
    """
    Handles supplier delivery note ingestion via photo or PDF.

    GET: renders the upload form.
    POST: saves the uploaded file as a new DeliveryNote, invokes
    GeminiVisionExtractionService to extract structured data, creates
    a DeliveryNoteLine per extracted line item with a first-pass
    assignment suggestion (resolve_line_assignment), and redirects to
    DeliveryNoteDetailView for review.

    ---

    Gestiona la ingesta de albaranes de proveedor vía foto o PDF.

    GET: renderiza el formulario de subida.
    POST: guarda el archivo subido como un DeliveryNote nuevo, invoca
    GeminiVisionExtractionService para extraer los datos
    estructurados, crea una DeliveryNoteLine por cada línea extraída
    con una sugerencia de asignación de primera pasada
    (resolve_line_assignment), y redirige a DeliveryNoteDetailView
    para su revisión.
    """

    template_name = 'spare_parts/delivery_note_upload.html'

    def get(self, request):
        return render(request, self.template_name, {
            'company_user': request.user.company_user,
            'active_nav': 'spare_parts_upload',
        })

    def post(self, request):
        company_user = request.user.company_user
        company = company_user.company

        upload = request.FILES.get('delivery_note_file')
        if upload is None:
            messages.error(
                request,
                'Debes seleccionar una foto o un PDF del albarán.',
            )
            return render(request, self.template_name, {
                'company_user': company_user,
                'active_nav': 'spare_parts_upload',
            })

        extension = (
            '.' + upload.name.rsplit('.', 1)[-1].lower()
            if '.' in upload.name else ''
        )
        source_type = _ALLOWED_EXTENSIONS.get(extension)
        if source_type is None:
            messages.error(
                request,
                f'Formato de archivo no soportado '
                f'({extension or "sin extensión"}). '
                f'Formatos válidos: PDF, JPG, PNG, WEBP.',
            )
            return render(request, self.template_name, {
                'company_user': company_user,
                'active_nav': 'spare_parts_upload',
            })

        delivery_note = DeliveryNote(company=company, source_type=source_type)
        if source_type == 'PDF':
            delivery_note.pdf_file = upload
        else:
            delivery_note.image = upload
        delivery_note.save()

        file_path = (
            delivery_note.pdf_file.path
            if source_type == 'PDF' else delivery_note.image.path
        )

        try:
            extraction = GeminiVisionExtractionService().extract(file_path)
        except Exception:
            logger.exception(
                '# Fallo en la extracción Gemini Vision del albarán %s.',
                delivery_note.pk,
            )
            delivery_note.delete()
            messages.error(
                request,
                'No se ha podido extraer la información del albarán. '
                'Comprueba que la foto/PDF sea legible e inténtalo de '
                'nuevo.',
            )
            return render(request, self.template_name, {
                'company_user': company_user,
                'active_nav': 'spare_parts_upload',
            })

        delivery_note.supplier_name = extraction.supplier_name or ''
        delivery_note.supplier_tax_id = extraction.supplier_tax_id or ''
        delivery_note.delivery_number = extraction.delivery_number or ''
        if extraction.delivery_date:
            try:
                delivery_note.delivery_date = date.fromisoformat(
                    extraction.delivery_date
                )
            except ValueError:
                delivery_note.delivery_date = None
        delivery_note.extraction_raw = extraction.model_dump()
        delivery_note.status = 'PROCESSED'
        delivery_note.processed_by = company_user
        delivery_note.save()

        for line_data in extraction.lines:
            assignment_type, machine = resolve_line_assignment(
                line_data.machine_code_raw, company,
            )
            DeliveryNoteLine.objects.create(
                delivery_note=delivery_note,
                line_number=line_data.line_number,
                reference=line_data.reference or '',
                description=line_data.description,
                quantity=parse_decimal(line_data.quantity) or 0,
                unit_price=parse_decimal(line_data.unit_price),
                total_price=parse_decimal(line_data.total_price),
                machine_code_raw=line_data.machine_code_raw or '',
                assignment_type=assignment_type,
                machine=machine,
            )

        messages.success(
            request,
            f'Albarán extraído correctamente: {len(extraction.lines)} '
            f'línea(s). Revisa los datos antes de confirmar la '
            f'asignación.',
        )
        return redirect('spare_parts:delivery_note_detail', pk=delivery_note.pk)


class DeliveryNoteDetailView(CompanyUserRequiredMixin, View):
    """
    Shows the extracted delivery note for manual review and
    correction before confirming the assignment circuit.

    GET: renders all header and line fields as editable.
    POST: saves corrections. If a line's machine_code_raw changed,
    re-runs resolve_line_assignment on it. Does not execute the
    assignment circuit -- that is DeliveryNoteConfirmView's job.

    ---

    Muestra el albarán extraído para revisión y corrección manual
    antes de confirmar el circuito de asignación.

    GET: renderiza todos los campos de cabecera y línea como
    editables.
    POST: guarda las correcciones. Si el machine_code_raw de una
    línea cambió, vuelve a ejecutar resolve_line_assignment sobre
    ella. No ejecuta el circuito de asignación -- esa es tarea de
    DeliveryNoteConfirmView.
    """

    template_name = 'spare_parts/delivery_note_detail.html'

    def get(self, request, pk):
        company = request.user.company_user.company
        delivery_note = get_object_or_404(
            DeliveryNote, pk=pk, company=company,
        )
        return render(request, self.template_name, {
            'company_user': request.user.company_user,
            'active_nav': 'spare_parts_upload',
            'delivery_note': delivery_note,
            'lines': delivery_note.lines.all(),
        })

    def post(self, request, pk):
        company = request.user.company_user.company
        delivery_note = get_object_or_404(
            DeliveryNote, pk=pk, company=company,
        )

        if delivery_note.status == 'ASSIGNED':
            messages.error(
                request,
                'Este albarán ya ha sido confirmado y asignado.',
            )
            return redirect(
                'spare_parts:delivery_note_detail', pk=delivery_note.pk,
            )

        delivery_note.supplier_name = request.POST.get(
            'supplier_name', '',
        ).strip()
        delivery_note.supplier_tax_id = request.POST.get(
            'supplier_tax_id', '',
        ).strip()
        delivery_note.delivery_number = request.POST.get(
            'delivery_number', '',
        ).strip()
        delivery_date_raw = request.POST.get('delivery_date', '').strip()
        if delivery_date_raw:
            try:
                delivery_note.delivery_date = date.fromisoformat(
                    delivery_date_raw
                )
            except ValueError:
                pass
        delivery_note.save()

        for line in delivery_note.lines.all():
            prefix = f'line_{line.pk}_'
            new_raw_code = request.POST.get(
                f'{prefix}machine_code_raw', '',
            ).strip()
            code_changed = new_raw_code != (line.machine_code_raw or '')

            line.reference = request.POST.get(
                f'{prefix}reference', '',
            ).strip()
            line.description = request.POST.get(
                f'{prefix}description', line.description,
            ).strip()
            line.quantity = parse_decimal(
                request.POST.get(f'{prefix}quantity')
            ) or 0
            line.unit_price = parse_decimal(
                request.POST.get(f'{prefix}unit_price')
            )
            line.total_price = parse_decimal(
                request.POST.get(f'{prefix}total_price')
            )
            line.machine_code_raw = new_raw_code

            manual_assignment = request.POST.get(f'{prefix}assignment_type')
            if code_changed or not manual_assignment:
                assignment_type, machine = resolve_line_assignment(
                    new_raw_code, company,
                )
                line.assignment_type = assignment_type
                line.machine = machine
            elif manual_assignment == 'WAREHOUSE':
                line.assignment_type = 'WAREHOUSE'
                line.machine = None
            elif manual_assignment == 'UNASSIGNED':
                line.assignment_type = 'UNASSIGNED'
                line.machine = None
            # 'MACHINE' manual value keeps the machine already
            # resolved on the line -- no machine picker in this pass
            # (deferred to a future session per Paso 5/6 of the
            # roadmap).
            # El valor manual 'MACHINE' conserva la máquina ya
            # resuelta en la línea -- sin selector de máquina en este
            # paso (diferido a una sesión futura según el Paso 5/6 de
            # la hoja de ruta).

            line.save()

        messages.success(request, 'Revisión guardada correctamente.')
        return redirect(
            'spare_parts:delivery_note_detail', pk=delivery_note.pk,
        )


class DeliveryNoteConfirmView(CompanyUserRequiredMixin, View):
    """
    Executes the assignment circuit (annex H10, section 3.1, step 5)
    for a reviewed delivery note. POST only.

    ---

    Ejecuta el circuito de asignación (anexo H10, sección 3.1, paso
    5) para un albarán ya revisado. Solo POST.
    """

    def post(self, request, pk):
        company = request.user.company_user.company
        delivery_note = get_object_or_404(
            DeliveryNote, pk=pk, company=company,
        )

        if delivery_note.status == 'ASSIGNED':
            messages.error(
                request,
                'Este albarán ya ha sido confirmado y asignado.',
            )
            return redirect(
                'spare_parts:delivery_note_detail', pk=delivery_note.pk,
            )

        counts = confirm_delivery_note(delivery_note, request.user.company_user)

        summary = (
            f'Asignación confirmada: {counts["warehouse"]} línea(s) a '
            f'almacén, {counts["pre_assigned"]} línea(s) '
            f'pre-asignada(s) a máquina/ticket.'
        )
        if counts['unassigned']:
            summary += (
                f' {counts["unassigned"]} línea(s) quedaron sin '
                f'asignar (código no reconocido) -- revísalas '
                f'manualmente.'
            )
            messages.warning(request, summary)
        else:
            messages.success(request, summary)

        return redirect(
            'spare_parts:delivery_note_detail', pk=delivery_note.pk,
        )
