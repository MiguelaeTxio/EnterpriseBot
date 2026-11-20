# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/views_machine_qr.py
"""
H23 (S154, invasora) -- panel page of a cost centre's QR sheet.

---

H23 (S154, invasora) -- botón "QR" de la ficha del centro de gasto: qué
verá el trabajador al leer el QR con el móvil. Miguel Ángel: "un botón
que sea el QR, donde nos permita meter un vídeo, una fotografía,
observaciones [...] el QR va a hacer referencia al sitio web donde
vamos a mostrar toda la información". Aquí se escriben las
observaciones, se suben y quitan fotos y vídeos, se ve la página tal
cual y se descarga el QR para imprimirlo. Lo ve quien entra en la
flota; lo edita quien edita la ficha y el jefe de taller.
"""
import logging

from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View

from fleet import qr_sheet_service as qr
from fleet.models import MachineAsset, MachineQrMedia
from panel.mixins import FleetAccessMixin

logger = logging.getLogger(__name__)

EDIT_ROLES = {"ADMIN", "ADMIN_SUPERVISOR", "DOCS_SUPERVISOR",
              "WORKSHOPBOSS"}
# Quién pone la contraseña del editor QR del fichaje.
PASSWORD_ROLES = {"ADMIN", "ADMIN_SUPERVISOR", "DOCS_SUPERVISOR"}


def _machine(request, pk):
    return get_object_or_404(
        MachineAsset, pk=pk, company=request.user.company_user.company)


def _can_edit(request):
    return request.user.company_user.role in EDIT_ROLES


class MachineQrSheetView(FleetAccessMixin, View):
    """
    GET: the QR sheet editor. POST: save notes, add or remove media.

    ---

    GET: la ficha QR del centro de gasto (QR, enlace, observaciones,
    fotos y vídeos). POST (action): "notes" guarda las observaciones,
    "upload" sube fotos y vídeos, "delete" quita uno.
    """

    template_name = "panel/machine_qr/sheet.html"

    def get(self, request, pk):
        machine = _machine(request, pk)
        sheet = qr.sheet_for(machine)
        url = qr.public_url(request, sheet)
        return render(request, self.template_name, {
            "machine": machine,
            "sheet": sheet,
            "public_url": url,
            "qr_svg": qr.qr_image(url, "svg", scale=6),
            "media": qr.media_rows(sheet),
            "specs": qr.spec_rows(machine),
            "service_lines": qr.service_lines(machine),
            "can_edit": _can_edit(request),
            "max_photo_mb": qr.MAX_PHOTO_BYTES // (1024 * 1024),
            "max_video_mb": qr.MAX_VIDEO_BYTES // (1024 * 1024),
            "can_set_password": (
                request.user.company_user.role in PASSWORD_ROLES),
            "editor_password_set": qr.editor_password_set(machine.company),
            "min_password_length": qr.MIN_PASSWORD_LENGTH,
        })

    def post(self, request, pk):
        machine = _machine(request, pk)
        if not _can_edit(request):
            return HttpResponse("No puedes editar la ficha QR.", status=403)
        sheet = qr.sheet_for(machine)
        company_user = request.user.company_user
        action = request.POST.get("action", "")
        if action == "notes":
            sheet.observations = request.POST.get("observations", "").strip()
            sheet.updated_by = company_user
            sheet.save(update_fields=["observations", "updated_by",
                                      "updated_at"])
            messages.success(request, "Observaciones guardadas.")
        elif action == "upload":
            caption = request.POST.get("caption", "")
            files = request.FILES.getlist("files")
            if not files:
                messages.error(request, "Elige al menos una foto o vídeo.")
            added = 0
            for upload in files:
                try:
                    qr.add_media(sheet, upload, caption, company_user)
                    added += 1
                except qr.QrSheetError as exc:
                    messages.error(request, str(exc))
            if added:
                sheet.updated_by = company_user
                sheet.save(update_fields=["updated_by", "updated_at"])
                messages.success(request, "Subidos: %d." % added)
        elif action == "caption":
            media = get_object_or_404(MachineQrMedia, sheet=sheet,
                                      pk=request.POST.get("media_id") or 0)
            media.caption = request.POST.get("caption", "").strip()[:300]
            media.save(update_fields=["caption"])
            messages.success(request, "Descripción guardada.")
        elif action == "editor_password":
            if company_user.role not in PASSWORD_ROLES:
                return HttpResponse("No puedes cambiar esta contraseña.",
                                    status=403)
            try:
                qr.set_editor_password(machine.company,
                                       request.POST.get("password", ""),
                                       company_user)
            except qr.QrSheetError as exc:
                messages.error(request, str(exc))
            else:
                messages.success(
                    request,
                    "Contraseña del editor QR del fichaje guardada.")
        elif action == "delete":
            media = get_object_or_404(MachineQrMedia, sheet=sheet,
                                      pk=request.POST.get("media_id") or 0)
            qr.delete_media(media)
            messages.success(request, "Quitado.")
        return redirect("panel:machine_qr_sheet", pk=machine.pk)


class MachineQrImageView(FleetAccessMixin, View):
    """
    GET: the QR code as PNG, to print.

    ---

    GET: el código QR en PNG, para imprimirlo y pegarlo en el vehículo
    (nombre del archivo: QR_<código>.png).
    """

    def get(self, request, pk):
        machine = _machine(request, pk)
        sheet = qr.sheet_for(machine)
        data = qr.qr_image(qr.public_url(request, sheet), "png", scale=20)
        response = HttpResponse(data, content_type="image/png")
        response["Content-Disposition"] = (
            'attachment; filename="QR_%s.png"' % machine.code)
        return response
