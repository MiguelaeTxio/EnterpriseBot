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

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.timezone import now
from django.views import View

from fleet.models import MachineAsset
from panel.mixins import CompanyUserRequiredMixin, SupervisorAccessMixin

from .forms import SupplierForm
from .gcs_service import DELIVERY_NOTES_BUCKET, generate_signed_url
from .models import DeliveryNote, DeliveryNoteLine, Supplier
from .services import (
    confirm_delivery_note,
    validate_document_assignment,
)
from .tasks import extract_delivery_note_data, upload_delivery_note_photo_to_drive

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
    POST: saves the uploaded file as a new DeliveryNote (status=
    PENDING, extraction not run yet) and enqueues
    extract_delivery_note_data() (tasks.py, S014-H10) to run Gemini
    Vision extraction in the background, then redirects immediately
    to DeliveryNoteDetailView -- the operator does not wait for
    Gemini. See DeliveryNoteDetailView for how the PENDING/ERROR
    states are shown while/if the background task hasn't finished.

    ---

    Gestiona la ingesta de albaranes de proveedor vía foto o PDF.

    GET: renderiza el formulario de subida.
    POST: guarda el archivo subido como un DeliveryNote nuevo (status=
    PENDING, extracción aún no ejecutada) y encola
    extract_delivery_note_data() (tasks.py, S014-H10) para que la
    extracción Gemini Vision corra en segundo plano, y redirige de
    inmediato a DeliveryNoteDetailView -- el operario no espera a
    Gemini. Ver DeliveryNoteDetailView para cómo se muestran los
    estados PENDING/ERROR mientras la tarea en segundo plano no ha
    terminado o si falla.
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

        # S014-H10, Bloque B punto 2: se guarda el archivo y se
        # devuelve la respuesta de inmediato -- la extracción Gemini
        # Vision (antes síncrona aquí mismo) se ejecuta en segundo
        # plano vía Celery, ver extract_delivery_note_data() en
        # tasks.py. status queda en 'PENDING' (valor por defecto del
        # campo) hasta que la tarea termine.
        delivery_note = DeliveryNote(
            company=company,
            source_type=source_type,
            processed_by=company_user,
        )
        if source_type == 'PDF':
            delivery_note.pdf_file = upload
        else:
            delivery_note.image = upload
        delivery_note.save()

        extract_delivery_note_data.delay(delivery_note.pk)

        messages.success(
            request,
            'Albarán subido correctamente. Gemini lo está procesando '
            'en segundo plano -- la página se actualiza sola cuando '
            'termine.',
        )
        return redirect('spare_parts:delivery_note_detail', pk=delivery_note.pk)


class DeliveryNoteDetailView(CompanyUserRequiredMixin, View):
    """
    Shows the extracted delivery note for confirmation. No manual
    correction of any field (S015-H10, first roadmap point, explicit
    decision by Miguel Ángel): the operator can only CONFIRM the
    extracted data matches the physical document, or REJECT and
    re-upload a clearer photo -- never edit a value by hand. This
    forces good photo quality (readable, well lit) instead of relying
    on manual fixes, and prevents any workaround of the machine/cost-
    centre-in-Observaciones rule via the review screen.

    GET: renders all header and line fields read-only, plus the
    result of validate_document_assignment() (services.py) -- if
    invalid, shows the precise rejection reason and only the
    "reject / re-upload" action is available; if valid, both
    "Confirmar" and "reject / re-upload" are available.
    POST: removed -- there is nothing left to save here. Confirming
    goes through DeliveryNoteConfirmView, rejecting through
    DeliveryNoteRejectView.

    ---

    Muestra el albarán extraído para su confirmación. Sin corrección
    manual de ningún campo (S015-H10, primer punto de la hoja de
    ruta, decisión explícita de Miguel Ángel): el operario solo puede
    CONFIRMAR que los datos extraídos coinciden con el documento
    físico, o RECHAZAR y volver a subir una foto más clara -- nunca
    corregir un valor a mano. Esto obliga a una buena calidad de foto
    (legible, bien iluminada) en vez de depender de arreglos
    manuales, y evita cualquier forma de sortear la norma del código
    de máquina/centro de gasto (u palabra clave de almacén) desde la
    propia pantalla de revisión.

    GET: renderiza todos los campos de cabecera y línea en solo
    lectura, más el resultado de validate_document_assignment()
    (services.py) -- si no es válido, muestra el motivo preciso de
    rechazo y solo está disponible la acción "rechazar/volver a
    subir"; si es válido, están disponibles tanto "Confirmar" como
    "rechazar/volver a subir".
    POST: eliminado -- ya no hay nada que guardar aquí. Confirmar
    pasa por DeliveryNoteConfirmView, rechazar por
    DeliveryNoteRejectView.
    """

    template_name = 'spare_parts/delivery_note_detail.html'

    def get(self, request, pk):
        company = request.user.company_user.company
        delivery_note = get_object_or_404(
            DeliveryNote, pk=pk, company=company,
        )

        is_valid, rejection_reason = True, None
        resolved_type, resolved_machine = None, None
        if delivery_note.status == 'PROCESSED':
            is_valid, rejection_reason, resolved_type, resolved_machine = (
                validate_document_assignment(delivery_note, company)
            )

        # S025: lista de máquinas/centros de gasto para el desplegable
        # de asignación manual -- solo se necesita cuando la
        # extracción automática falló y el albarán todavía no se ha
        # asignado a mano (si ya se asignó, manually_assigned=True y
        # is_valid ya no importa para decidir si mostrar el
        # formulario, ver plantilla).
        assignable_machines = None
        if not is_valid and not delivery_note.manually_assigned:
            assignable_machines = (
                MachineAsset.objects
                .filter(company=company)
                .order_by('code')
            )

        # URL de descarga resuelta aquí (S022, directriz de plantillas
        # tontas): gcs_blob_name -> URL firmada bajo demanda;
        # drive_web_link (legado) se usa tal cual. Fallback al archivo
        # LOCAL (S025, hallazgo real de Miguel Ángel: "hay algunos que
        # no puedo ver las fotos originales, su estado es procesado")
        # -- la subida a GCS solo ocurre al CONFIRMAR
        # (upload_delivery_note_photo_to_drive, spare_parts/tasks.py),
        # así que un albarán en PROCESSED que nunca llegó a
        # confirmarse (típicamente porque validate_document_assignment
        # lo bloqueó) sigue teniendo su archivo original en disco,
        # nunca en GCS -- sin este fallback, esa foto era invisible
        # para siempre desde esta pantalla pese a existir de verdad.
        # Mismo patrón ya usado en otras plantillas del proyecto
        # (panel/machine_history.html, _task_photo_widget.html:
        # {{ photo.image.url }}, MEDIA_URL ya configurado).
        download_url = None
        if delivery_note.gcs_blob_name:
            try:
                download_url = generate_signed_url(
                    DELIVERY_NOTES_BUCKET, delivery_note.gcs_blob_name,
                )
            except Exception:
                logger.exception(
                    '# [DeliveryNoteDetailView] Fallo generando URL '
                    'firmada para albarán #%d (blob=%s).',
                    delivery_note.pk, delivery_note.gcs_blob_name,
                )
        elif delivery_note.drive_web_link:
            download_url = delivery_note.drive_web_link
        elif delivery_note.image:
            download_url = delivery_note.image.url
        elif delivery_note.pdf_file:
            download_url = delivery_note.pdf_file.url

        return render(request, self.template_name, {
            'company_user': request.user.company_user,
            'active_nav': 'spare_parts_upload',
            'delivery_note': delivery_note,
            'lines': delivery_note.lines.all(),
            'recipient_resolved': bool(delivery_note.recipient_company_code),
            'is_valid': is_valid,
            'rejection_reason': rejection_reason,
            'resolved_type': resolved_type,
            'resolved_machine': resolved_machine,
            'download_url': download_url,
            'assignable_machines': assignable_machines,
        })


class DeliveryNoteManualAssignView(CompanyUserRequiredMixin, View):
    """
    POST: asigna a mano la máquina/centro de gasto (o "Almacén" sin
    diferenciar) de un albarán cuya extracción automática no encontró
    ningún código válido (S025, petición explícita de Miguel Ángel:
    "deberíamos de incluir esa corrección manual indicando que es una
    corrección manual, asignarla a la máquina, pero dejando constancia
    de que ha sido una asignación manual, porque estamos teniendo un
    problema grave con esto"). Revierte PARCIALMENTE la norma de S015
    ("no se admite corrección manual") -- la corrección ahora se
    admite, pero queda SIEMPRE marcada como manual
    (manually_assigned/manually_assigned_by/manually_assigned_at en
    DeliveryNote), nunca se confunde con una asignación automática
    real.

    Aplica el mismo assignment_type/machine elegido a TODAS las
    líneas del albarán (mismo criterio "un albarán, un destino" ya
    vigente desde S015 para la vía automática -- ver
    services.resolve_document_assignment()), para que
    confirm_delivery_note() (que lee assignment_type/machine ya
    fijados en cada línea, sin recalcular nada) funcione exactamente
    igual después de una asignación manual que después de una
    automática.

    Solo disponible mientras el albarán no se ha confirmado
    (status=PROCESSED) y no está ya asignado a mano -- una vez
    asignado a mano, el flujo normal de "Confirmar" queda disponible
    igual que si la extracción automática hubiera tenido éxito.
    """

    def post(self, request, pk):
        company = request.user.company_user.company
        delivery_note = get_object_or_404(
            DeliveryNote, pk=pk, company=company,
        )

        if delivery_note.status != 'PROCESSED':
            messages.error(
                request,
                'Solo se puede asignar a mano un albarán ya extraído '
                'y todavía sin confirmar.',
            )
            return redirect(
                'spare_parts:delivery_note_detail', pk=delivery_note.pk,
            )

        choice = request.POST.get('assignment_choice', '').strip()
        if not choice:
            messages.error(
                request, 'Selecciona una máquina, centro de gasto o '
                '"Almacén" antes de asignar.',
            )
            return redirect(
                'spare_parts:delivery_note_detail', pk=delivery_note.pk,
            )

        if choice == 'WAREHOUSE':
            assignment_type, machine = 'WAREHOUSE', None
        else:
            machine = MachineAsset.objects.filter(
                pk=choice, company=company,
            ).first()
            if machine is None:
                messages.error(
                    request,
                    'La máquina/centro de gasto seleccionado no es '
                    'válido.',
                )
                return redirect(
                    'spare_parts:delivery_note_detail', pk=delivery_note.pk,
                )
            assignment_type = 'MACHINE'

        DeliveryNoteLine.objects.filter(
            delivery_note=delivery_note,
        ).update(assignment_type=assignment_type, machine=machine)

        delivery_note.manually_assigned = True
        delivery_note.manually_assigned_by = request.user.company_user
        delivery_note.manually_assigned_at = now()
        delivery_note.save(update_fields=[
            'manually_assigned', 'manually_assigned_by',
            'manually_assigned_at',
        ])

        logger.info(
            '# [DeliveryNoteManualAssignView] Albarán #%d asignado a '
            'mano por %s -- %s (%s).',
            delivery_note.pk, request.user.company_user,
            assignment_type, machine.code if machine else 'Almacén',
        )
        messages.success(
            request,
            'Asignación manual guardada -- ya puedes confirmar el '
            'albarán. Queda registrado que esta asignación fue manual.',
        )
        return redirect(
            'spare_parts:delivery_note_detail', pk=delivery_note.pk,
        )


class DeliveryNoteConfirmView(CompanyUserRequiredMixin, View):
    """
    Executes the assignment circuit (annex H10, section 3.1, step 5)
    for a reviewed delivery note. POST only. On success, enqueues
    upload_delivery_note_photo_to_drive() (spare_parts/tasks.py,
    S014-H10, migrated to Google Cloud Storage in S022 -- task name
    kept unchanged, see spare_parts/gcs_service.py): the source
    photo/PDF is uploaded to GCS and then deleted from the server --
    extracted data stays in BD permanently, only the file is removed.

    ---

    Ejecuta el circuito de asignación (anexo H10, sección 3.1, paso
    5) para un albarán ya revisado. Solo POST. En caso de éxito,
    encola upload_delivery_note_photo_to_drive() (spare_parts/tasks.py,
    S014-H10, migrada a Google Cloud Storage en S022 -- nombre de
    tarea sin cambiar, ver spare_parts/gcs_service.py): la foto/PDF
    origen se sube a GCS y después se borra del servidor -- los datos
    extraídos se quedan en BD permanentemente, solo se elimina el
    archivo.
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

        # S014-H10, Bloque B punto 2: con la subida asíncrona no puede
        # confirmarse un albarán que Gemini aún no ha procesado
        # (PENDING) o cuya extracción falló (ERROR) -- no hay líneas
        # reales que asignar.
        if delivery_note.status in ('PENDING', 'ERROR'):
            messages.error(
                request,
                'Este albarán todavía no tiene datos extraídos -- no '
                'se puede confirmar.',
            )
            return redirect(
                'spare_parts:delivery_note_detail', pk=delivery_note.pk,
            )

        # S015-H10, primer punto de la hoja de ruta: no se puede
        # confirmar un albarán sin el código único de máquina/centro
        # de gasto obligatorio, o sin el fallback de palabra clave de
        # almacén (S020) -- resuelto por el prompt de extracción.
        # Defensa en profundidad -- la plantilla ya oculta el botón
        # "Confirmar" cuando esto falla, pero un POST directo (fuera
        # de la UI normal) debe rechazarse igualmente aquí.
        #
        # EXCEPCIÓN S025: si delivery_note.manually_assigned es True,
        # un operario ya asignó máquina/centro de gasto a mano
        # (DeliveryNoteManualAssignView) y las líneas ya tienen su
        # assignment_type/machine reales -- validate_document_
        # assignment() seguiría diciendo "inválido" porque
        # general_machine_code_raw sigue vacío a propósito (nunca se
        # reescribe con un valor manual, para no simular una
        # extracción automática que nunca ocurrió), así que se omite
        # ese bloqueo cuando la asignación ya es manual.
        if not delivery_note.manually_assigned:
            is_valid, rejection_reason, _, _ = validate_document_assignment(
                delivery_note, company,
            )
            if not is_valid:
                messages.error(request, rejection_reason)
                return redirect(
                    'spare_parts:delivery_note_detail', pk=delivery_note.pk,
                )

        if not delivery_note.recipient_company_code:
            messages.warning(
                request,
                'La empresa destinataria no se ha podido resolver '
                'automáticamente (CIF no reconocido). Revisa y '
                'corrige el CIF destinatario si es necesario -- la '
                'asignación se confirmará igualmente.',
            )

        counts = confirm_delivery_note(delivery_note, request.user.company_user)

        # S014-H10: tras confirmar, el archivo origen (foto/PDF) se sube
        # a Google Drive y se borra del servidor -- los datos extraídos
        # ya están persistidos en BD, es lo único que cuenta a partir de
        # aquí. Asíncrono para no bloquear la respuesta esperando a
        # Google.
        upload_delivery_note_photo_to_drive.delay(delivery_note.pk)

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


class DeliveryNoteRejectView(CompanyUserRequiredMixin, View):
    """
    Rejects a not-yet-confirmed delivery note (S015-H10, first
    roadmap point): since no manual correction is allowed, the only
    way to fix a wrong or incomplete extraction is to delete this
    attempt and upload a clearer photo from scratch. POST only.
    Deletes the DeliveryNote row (cascades to its DeliveryNoteLine
    rows) and its source file (image or PDF -- FileField.delete()
    removes it from storage; nothing has been created yet in
    SparePartEntry/StockMovement at this point, since the assignment
    circuit only runs on confirm). Never allowed for status=ASSIGNED
    -- that data is already real stock, not reachable from here.

    ---

    Rechaza un albarán aún sin confirmar (S015-H10, primer punto de
    la hoja de ruta): al no admitirse corrección manual, la única
    forma de arreglar una extracción incorrecta o incompleta es
    borrar este intento y subir una foto más clara desde cero. Solo
    POST. Borra la fila DeliveryNote (en cascada sus filas
    DeliveryNoteLine) y su archivo origen (imagen o PDF --
    FileField.delete() lo elimina del almacenamiento; en este punto
    todavía no se ha creado nada en SparePartEntry/StockMovement, ya
    que el circuito de asignación solo se ejecuta al confirmar).
    Nunca permitido para status=ASSIGNED -- esos datos ya son stock
    real, no alcanzable desde aquí.
    """

    def post(self, request, pk):
        company = request.user.company_user.company
        delivery_note = get_object_or_404(
            DeliveryNote, pk=pk, company=company,
        )

        if delivery_note.status == 'ASSIGNED':
            messages.error(
                request,
                'Este albarán ya ha sido confirmado y asignado -- no '
                'se puede rechazar.',
            )
            return redirect(
                'spare_parts:delivery_note_detail', pk=delivery_note.pk,
            )

        if delivery_note.image:
            delivery_note.image.delete(save=False)
        if delivery_note.pdf_file:
            delivery_note.pdf_file.delete(save=False)
        delivery_note.delete()

        messages.warning(
            request,
            'Albarán rechazado. Vuelve a fotografiarlo asegurándote '
            'de que se lea bien y de que el proveedor haya anotado el '
            'centro de gasto o la máquina de destino en Observaciones, '
            'delimitado con #, * o " en una línea, o mencionado como '
            'repuesto/stock/almacén si va a almacén general.',
        )
        return redirect('spare_parts:delivery_note_upload')


class DeliveryNoteRetryExtractionView(CompanyUserRequiredMixin, View):
    """
    Re-enqueues extract_delivery_note_data() for a DeliveryNote whose
    background extraction failed (status=ERROR). POST only. Resets
    status back to PENDING so the detail view shows the same
    "processing" state as a fresh upload while the retry runs.

    ---

    Vuelve a encolar extract_delivery_note_data() para un DeliveryNote
    cuya extracción en segundo plano falló (status=ERROR). Solo POST.
    Restaura status a PENDING para que la vista de detalle muestre el
    mismo estado "procesando" que una subida nueva mientras corre el
    reintento.
    """

    def post(self, request, pk):
        company = request.user.company_user.company
        delivery_note = get_object_or_404(
            DeliveryNote, pk=pk, company=company,
        )

        if delivery_note.status != 'ERROR':
            messages.error(
                request,
                'Solo se puede reintentar un albarán con extracción '
                'fallida.',
            )
            return redirect(
                'spare_parts:delivery_note_detail', pk=delivery_note.pk,
            )

        delivery_note.status = 'PENDING'
        delivery_note.save(update_fields=['status'])
        extract_delivery_note_data.delay(delivery_note.pk)

        messages.success(
            request,
            'Reintentando la extracción del albarán en segundo plano.',
        )
        return redirect(
            'spare_parts:delivery_note_detail', pk=delivery_note.pk,
        )


class SupplierListView(SupervisorAccessMixin, View):
    """
    Lists Supplier records for the current company, including
    SALVAGE-type (internal recycling) entries -- confirmed by Miguel
    Ángel (2026-07-06): recycling is modelled as another Supplier,
    not a separate mechanism.
    ---
    Lista los registros Supplier de la empresa actual, incluyendo los
    de tipo SALVAGE (reciclado interno) -- confirmado por Miguel
    Ángel (2026-07-06): el reciclado se modela como otro Supplier, no
    como un mecanismo aparte.
    """

    template_name = 'spare_parts/supplier_list.html'

    def get(self, request):
        company = request.user.company_user.company
        suppliers = Supplier.objects.filter(company=company)
        return render(request, self.template_name, {
            'company_user': request.user.company_user,
            'active_nav': 'suppliers',
            'suppliers': suppliers,
        })


class SupplierCreateView(SupervisorAccessMixin, View):
    """
    Manual creation of a Supplier record.
    ---
    Alta manual de un registro Supplier.
    """

    template_name = 'spare_parts/supplier_form.html'

    def get(self, request):
        return render(request, self.template_name, {
            'company_user': request.user.company_user,
            'active_nav': 'suppliers',
            'form': SupplierForm(),
            'action': 'Crear',
        })

    def post(self, request):
        form = SupplierForm(request.POST)
        if not form.is_valid():
            return render(request, self.template_name, {
                'company_user': request.user.company_user,
                'active_nav': 'suppliers',
                'form': form,
                'action': 'Crear',
            })
        supplier = form.save(commit=False)
        supplier.company = request.user.company_user.company
        supplier.save()
        messages.success(request, f"Proveedor '{supplier.name}' creado correctamente.")
        return redirect('spare_parts:supplier_list')


class SupplierUpdateView(SupervisorAccessMixin, View):
    """
    Edits an existing Supplier record.
    ---
    Edita un registro Supplier existente.
    """

    template_name = 'spare_parts/supplier_form.html'

    def get(self, request, pk):
        company = request.user.company_user.company
        supplier = get_object_or_404(Supplier, pk=pk, company=company)
        return render(request, self.template_name, {
            'company_user': request.user.company_user,
            'active_nav': 'suppliers',
            'form': SupplierForm(instance=supplier),
            'action': 'Editar',
            'supplier': supplier,
        })

    def post(self, request, pk):
        company = request.user.company_user.company
        supplier = get_object_or_404(Supplier, pk=pk, company=company)
        form = SupplierForm(request.POST, instance=supplier)
        if not form.is_valid():
            return render(request, self.template_name, {
                'company_user': request.user.company_user,
                'active_nav': 'suppliers',
                'form': form,
                'action': 'Editar',
                'supplier': supplier,
            })
        supplier = form.save()
        messages.success(request, f"Proveedor '{supplier.name}' actualizado correctamente.")
        return redirect('spare_parts:supplier_list')


class SupplierDeactivateView(SupervisorAccessMixin, View):
    """
    Sets is_active=False on a Supplier -- does not delete, preserves
    historical traceability of any SparePartEntry that references it.
    ---
    Establece is_active=False en un Supplier -- no elimina, preserva
    la trazabilidad histórica de cualquier SparePartEntry que lo
    referencie.
    """

    def post(self, request, pk):
        company = request.user.company_user.company
        supplier = get_object_or_404(Supplier, pk=pk, company=company)
        supplier.is_active = False
        supplier.save(update_fields=['is_active'])
        messages.success(request, f"Proveedor '{supplier.name}' desactivado.")
        return redirect('spare_parts:supplier_list')


class SupplierReactivateView(SupervisorAccessMixin, View):
    """
    Sets is_active=True on a Supplier. Counterpart to
    SupplierDeactivateView.
    ---
    Establece is_active=True en un Supplier. Contraparte de
    SupplierDeactivateView.
    """

    def post(self, request, pk):
        company = request.user.company_user.company
        supplier = get_object_or_404(Supplier, pk=pk, company=company)
        supplier.is_active = True
        supplier.save(update_fields=['is_active'])
        messages.success(request, f"Proveedor '{supplier.name}' reactivado.")
        return redirect('spare_parts:supplier_list')


class SupplierDeleteView(SupervisorAccessMixin, View):
    """
    Permanently deletes a Supplier only if it has no linked
    SparePartEntry records (referential integrity guard) --
    same pattern as MachineAssetDeleteView in fleet/views.py.
    ---
    Elimina permanentemente un Supplier solo si no tiene
    SparePartEntry vinculados (guarda de integridad referencial) --
    mismo patrón que MachineAssetDeleteView en fleet/views.py.
    """

    def post(self, request, pk):
        company = request.user.company_user.company
        supplier = get_object_or_404(Supplier, pk=pk, company=company)
        if supplier.spare_part_entries.exists():
            messages.error(
                request,
                f"No se puede eliminar '{supplier.name}': tiene repuestos "
                f"vinculados. Desactívalo en su lugar.",
            )
            return redirect('spare_parts:supplier_list')
        name = supplier.name
        supplier.delete()
        messages.success(request, f"Proveedor '{name}' eliminado correctamente.")
        return redirect('spare_parts:supplier_list')
