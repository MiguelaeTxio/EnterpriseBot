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
import logging

from django.shortcuts import get_object_or_404, render
from django.views import View

from spare_parts.gcs_service import TASK_PHOTOS_BUCKET, generate_signed_url
from work_order_processor.models import TaskPhoto, WorkOrderEntryLine
from work_order_processor.tasks import upload_task_photo_to_drive

from .mixins import WorkOrderFormAccessMixin

logger = logging.getLogger(__name__)

_WIDGET_TEMPLATE = "panel/operator/_task_photo_widget.html"


def _get_line(request, line_pk):
    company = request.user.company_user.company
    return get_object_or_404(
        WorkOrderEntryLine,
        pk=line_pk,
        entry__work_order__company=company,
    )


def _build_photo_entries(photos) -> list[dict]:
    """
    Builds the widget's rendering context for a queryset of photos:
    one dict per photo with the photo itself plus its signed GCS URL
    already resolved (or None if not applicable) -- logic lives here,
    never in the template (project-wide directriz: "dumb templates").

    A photo with gcs_blob_name gets a signed URL generated on demand
    (S022 -- see spare_parts/gcs_service.py); a legacy photo with only
    drive_web_link (uploaded before the GCS migration) keeps using
    that link untouched, with no attempt to re-sign anything.

    ---

    Construye el contexto de renderizado del widget para un queryset
    de fotos: un diccionario por foto con la propia foto más su URL
    firmada de GCS ya resuelta (o None si no aplica) -- la lógica vive
    aquí, nunca en el template (directriz del proyecto: "plantillas
    tontas").

    Una foto con gcs_blob_name obtiene una URL firmada generada bajo
    demanda (S022 -- ver spare_parts/gcs_service.py); una foto legada
    con solo drive_web_link (subida antes de la migración a GCS) sigue
    usando ese enlace tal cual, sin intentar refirmar nada.
    """
    entries = []
    for photo in photos:
        signed_url = None
        if photo.gcs_blob_name:
            try:
                signed_url = generate_signed_url(
                    TASK_PHOTOS_BUCKET, photo.gcs_blob_name,
                )
            except Exception:
                logger.exception(
                    "# [views_task_photos] Fallo generando URL firmada "
                    "para TaskPhoto #%d (blob=%s).",
                    photo.pk, photo.gcs_blob_name,
                )
        entries.append({"photo": photo, "signed_url": signed_url})
    return entries


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
            "photo_entries": _build_photo_entries(line.photos.all()),
        })


class TaskPhotoUploadView(WorkOrderFormAccessMixin, View):
    """
    Handles the multipart upload of a single photo for a line. Creates
    the TaskPhoto with company/breakdown_ticket/machine_asset
    denormalised from the line at this exact moment, enqueues the GCS
    upload task (S022 -- see work_order_processor.tasks for the
    task name history), and re-renders the widget so the new
    thumbnail appears immediately (upload still pending in the
    background -- the widget shows a "subiendo..." state until
    gcs_blob_name is set).
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
            "photo_entries": _build_photo_entries(line.photos.all()),
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
            "photo_entries": _build_photo_entries(line.photos.all()),
        })
