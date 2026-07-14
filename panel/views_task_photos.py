# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/views_task_photos.py
"""
Views for optional task photos attached to a WorkOrderEntryLine (H7,
session S016). HTMX endpoints used from
panel/templates/panel/operator/form_entry.html, mirroring the existing
ticket-resolution-{{ entrada.idx }} widget pattern (see
workorder_spare_parts.views.TaskTicketResolutionView).

  TaskPhotoWidgetView — GET, renders the upload form + existing photos
                        list for a given line.
  TaskPhotoUploadView — POST, creates a TaskPhoto from the uploaded file,
                        enqueues
                        work_order_processor.tasks.upload_task_photo_to_drive,
                        re-renders the widget.
  TaskPhotoDeleteView — POST, deletes a TaskPhoto, re-renders the widget.

Photos are optional on every WorkOrderEntryLine regardless of
tipo_tarea -- the widget only requires the line to already have a real
pk (i.e. the block has been saved at least once via "Guardar bloques" or
the parte is IN_PROGRESS), same precondition the ticket-resolution
widget already has for machine_asset.

All three views scope the WorkOrderEntryLine to
request.user.company_user.company -- same tenant isolation the rest of
the form enforces.

---

Vistas para las fotos opcionales de tarea adjuntas a un
WorkOrderEntryLine (H7, sesión S016). Endpoints HTMX usados desde
panel/templates/panel/operator/form_entry.html, replicando el patrón ya
existente del widget ticket-resolution-{{ entrada.idx }} (ver
workorder_spare_parts.views.TaskTicketResolutionView).

Las fotos son opcionales en cualquier WorkOrderEntryLine
independientemente de tipo_tarea -- el widget solo requiere que la
línea ya tenga un pk real (el bloque se ha guardado al menos una vez vía
"Guardar bloques", o el parte está IN_PROGRESS), misma precondición que
ya tiene el widget de resolución de ticket para machine_asset.

Las tres vistas acotan el WorkOrderEntryLine a
request.user.company_user.company -- mismo aislamiento por empresa que
aplica el resto del formulario.
"""
from django.shortcuts import get_object_or_404, render
from django.views import View

from work_order_processor.models import TaskPhoto, WorkOrderEntryLine
from work_order_processor.tasks import upload_task_photo_to_drive

from .mixins import WorkOrderFormAccessMixin

_WIDGET_TEMPLATE = "panel/operator/_task_photo_widget.html"


def _get_line(request, line_pk):
    company = request.user.company_user.company
    return get_object_or_404(
        WorkOrderEntryLine,
        pk=line_pk,
        entry__work_order__company=company,
    )


class TaskPhotoWidgetView(WorkOrderFormAccessMixin, View):
    """
    Renders the photo widget (upload form + thumbnails) for a single
    WorkOrderEntryLine. Loaded via hx-get, same load pattern as
    ticket-resolution-{{ entrada.idx }}.
    """

    def get(self, request, line_pk):
        line = _get_line(request, line_pk)
        return render(request, _WIDGET_TEMPLATE, {
            "line": line,
            "photos": line.photos.all(),
        })


class TaskPhotoUploadView(WorkOrderFormAccessMixin, View):
    """
    Handles the multipart upload of a single photo for a line. Creates
    the TaskPhoto with company/breakdown_ticket/machine_asset
    denormalised from the line at this exact moment, enqueues the Drive
    upload task, and re-renders the widget so the new thumbnail appears
    immediately (upload still pending in the background -- the widget
    shows a "subiendo..." state until drive_web_link is set).
    """

    def post(self, request, line_pk):
        line = _get_line(request, line_pk)
        image = request.FILES.get("image")
        if image:
            photo = TaskPhoto.objects.create(
                line=line,
                company=line.entry.work_order.company,
                breakdown_ticket=line.breakdown_ticket,
                machine_asset=line.machine_asset,
                uploaded_by=getattr(request.user, "company_user", None),
                image=image,
                caption=(request.POST.get("caption") or "").strip(),
            )
            upload_task_photo_to_drive.delay(photo.pk)
        return render(request, _WIDGET_TEMPLATE, {
            "line": line,
            "photos": line.photos.all(),
        })


class TaskPhotoDeleteView(WorkOrderFormAccessMixin, View):
    """
    Deletes a TaskPhoto. If already uploaded to Drive, the Drive file
    itself is left untouched (no automated Drive deletion wired here --
    acceptable for these low-stakes, purely illustrative photos; Miguel
    Ángel can remove it manually from Drive if needed). Re-renders the
    widget.
    """

    def post(self, request, line_pk, photo_pk):
        line = _get_line(request, line_pk)
        photo = get_object_or_404(TaskPhoto, pk=photo_pk, line=line)
        if photo.image:
            photo.image.delete(save=False)
        photo.delete()
        return render(request, _WIDGET_TEMPLATE, {
            "line": line,
            "photos": line.photos.all(),
        })
