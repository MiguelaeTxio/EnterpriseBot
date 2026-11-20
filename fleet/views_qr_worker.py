# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/fleet/views_qr_worker.py
"""
H23 (S154, invasora) -- QR sheet editor inside the clock-in app.

---

H23 (S154, invasora) -- editor de fichas QR dentro de la aplicación de
fichaje (/fichaje/qr/). Miguel Ángel: "un botón en la propia aplicación
de fichajes y una contraseña para acceder que no sea la del usuario [...]
eligen de un listado con casillero (sólo admite uno señalado a la vez)
el vehículo [...] y un botón para acceder a la información del vehículo
marcado". Entra el móvil de confianza del fichaje (queda quién sube
cada cosa) y, además, la contraseña del editor, que pone la oficina
desde la ficha QR del panel. Se edita lo mismo que en el panel:
observaciones, fotos y vídeos.
"""
import logging

from django.db.models import Q
from django.http import Http404
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from fleet import qr_sheet_service as qr
from fleet.models import MachineAsset, MachineQrMedia, MachineQrSheet

logger = logging.getLogger(__name__)


def _device_user(request):
    from hr_calendar.clockin import trusted_device_user

    return trusted_device_user(request)


def _gate(request):
    """
    (company_user, response): response is set when the page must stop.

    ---

    (usuario, respuesta): hay respuesta si el móvil no es de confianza
    o si falta la contraseña del editor.
    """
    company_user = _device_user(request)
    if company_user is None:
        return None, render(request, "fleet/qr_worker_list.html",
                            {"no_device": True})
    if not qr.editor_unlocked(request):
        return company_user, redirect("fleet_qr_worker_list")
    return company_user, None


@never_cache
@require_http_methods(["GET", "POST"])
def worker_list(request):
    """
    GET/POST: password, then the vehicle list (one choice).

    ---

    GET/POST: primero la contraseña del editor; después, la lista de
    vehículos activos con casilla de elección única y el botón para
    entrar en el marcado.
    """
    company_user = _device_user(request)
    if company_user is None:
        return render(request, "fleet/qr_worker_list.html",
                      {"no_device": True})
    company = company_user.company
    error = ""
    if request.method == "POST" and request.POST.get("action") == "unlock":
        ok, error = qr.unlock_editor(request, company,
                                     request.POST.get("password", ""))
        if ok:
            logger.info("# [qr_worker] editor abierto por %s",
                        company_user.user.username)
            return redirect("fleet_qr_worker_list")
    if request.method == "POST" and request.POST.get("action") == "open":
        if not qr.editor_unlocked(request):
            return redirect("fleet_qr_worker_list")
        pk = request.POST.get("machine") or ""
        if pk.isdigit():
            return redirect("fleet_qr_worker_vehicle", pk=int(pk))
        error = "Marca un vehículo."
    if not qr.editor_unlocked(request):
        return render(request, "fleet/qr_worker_list.html", {
            "locked": True,
            "error": error,
            "no_password": not qr.editor_password_set(company),
        })
    machines = MachineAsset.objects.filter(
        company=company, is_active=True).order_by("code").only(
        "pk", "code", "plate", "brand_model", "family")
    # Los vehículos que ya tienen algo en su ficha QR, para marcarlos.
    with_sheet = set(MachineQrSheet.objects.filter(
        machine__company=company,
    ).filter(
        ~Q(observations="") | Q(media__isnull=False),
    ).values_list("machine_id", flat=True))
    return render(request, "fleet/qr_worker_list.html", {
        "machines": machines,
        "with_sheet": with_sheet,
        "error": error,
    })


@never_cache
@require_http_methods(["GET", "POST"])
def worker_vehicle(request, pk):
    """
    GET/POST: the QR sheet of the chosen vehicle, editable.

    ---

    GET/POST: la ficha QR del vehículo elegido: observaciones, subir
    fotos y vídeos (cámara o galería) y quitarlos.
    """
    company_user, stop = _gate(request)
    if stop is not None:
        return stop
    machine = MachineAsset.objects.filter(
        pk=pk, company=company_user.company).first()
    if machine is None:
        raise Http404
    sheet = qr.sheet_for(machine)
    notice, error = "", ""
    if request.method == "POST":
        action = request.POST.get("action", "")
        if action == "notes":
            sheet.observations = request.POST.get("observations", "").strip()
            sheet.updated_by = company_user
            sheet.save(update_fields=["observations", "updated_by",
                                      "updated_at"])
            notice = "Observaciones guardadas."
        elif action == "upload":
            added = 0
            for upload in request.FILES.getlist("files"):
                try:
                    qr.add_media(sheet, upload,
                                 request.POST.get("caption", ""),
                                 company_user)
                    added += 1
                except qr.QrSheetError as exc:
                    error = str(exc)
            if added:
                sheet.updated_by = company_user
                sheet.save(update_fields=["updated_by", "updated_at"])
                notice = "Subidos: %d." % added
            elif not error:
                error = "Elige una foto o un vídeo."
        elif action == "delete":
            media = MachineQrMedia.objects.filter(
                sheet=sheet, pk=request.POST.get("media_id") or 0).first()
            if media is not None:
                qr.delete_media(media)
                notice = "Quitado."
        if notice and not error:
            return redirect("fleet_qr_worker_vehicle", pk=machine.pk)
    return render(request, "fleet/qr_worker_vehicle.html", {
        "machine": machine,
        "sheet": sheet,
        "media": qr.media_rows(sheet),
        "public_url": qr.public_url(request, sheet),
        "error": error,
        "max_photo_mb": qr.MAX_PHOTO_BYTES // (1024 * 1024),
        "max_video_mb": qr.MAX_VIDEO_BYTES // (1024 * 1024),
    })
