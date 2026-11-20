# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/crane_albaranes/views_worker.py
"""
The worker side of the crane albaranes, inside the clock-in app (H11,
S162).

---

El lado del gruista, dentro de la aplicación de fichaje (/fichaje/):
sus albaranes del día, el albarán que le llega por WhatsApp (el enlace
lleva su llave) y uno nuevo desde cero. Las horas salen de sus fichajes;
él completa lo que falte, firma y firma el cliente en la pantalla. Al
firmar se genera el PDF, se guarda en el cubo y se envía al cliente.
"""
import datetime
import logging
from decimal import Decimal, InvalidOperation

from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from crane_albaranes.models import CraneAlbaran
from crane_albaranes.services import (
    create_albaran,
    fill_from_clock,
    finish_signed,
    pdf_bytes,
    pdf_name,
    person_label,
)
from crane_albaranes.views_panel import save_albaran_form

logger = logging.getLogger(__name__)

# Lo que el gruista puede tocar (la oficina fija obra, gruista y empresa
# emisora; la máquina sí la puede cambiar si llevó otra).
WORKER_FIELDS = (
    "machine", "tonnage", "helpers", "work_done", "hours_worked", "trips",
    "km", "base_out", "work_in", "work_out", "base_in", "observations",
    "order_number", "work_place", "work_locality",
    "vehicle_on_site", "vehicle_on_site_present", "continues_previous",
    "continues_previous_present",
    "goods_load_company", "goods_load_place", "goods_load_tractor",
    "goods_load_trailer", "goods_unload_company", "goods_unload_place",
    "goods_unload_tractor", "goods_unload_trailer", "goods_unload_date",
    "goods_owner_company",
)


def _device_person(request):
    """
    The worker of this trusted device (clock-in key), or None.
    ---
    El trabajador del dispositivo de confianza (la llave del fichaje).
    """
    from hr_calendar.clockin import _person_of, trusted_device_user

    company_user = trusted_device_user(request)
    if company_user is None:
        return None, None
    return company_user, _person_of(company_user)


def _by_token(token):
    albaran = CraneAlbaran.objects.filter(token=token).select_related(
        "worksite", "machine", "person", "issuer", "client").first()
    if albaran is None or albaran.status == CraneAlbaran.Status.CANCELLED:
        raise Http404
    return albaran


def _machines(company):
    from fleet.models import MachineAsset

    return MachineAsset.objects.filter(
        company=company, is_active=True).order_by("code").only(
        "pk", "code", "plate", "brand_model", "type_name")


@never_cache
@require_GET
def worker_list(request):
    """
    GET: the worker's albaranes (pending first) and "new albarán".
    ---
    GET: los albaranes del gruista: los pendientes de hoy y anteriores,
    y los firmados de los últimos días; y el botón de uno nuevo.
    """
    from worksites.models import Worksite

    company_user, person = _device_person(request)
    if person is None:
        return render(request, "crane_albaranes/worker_list.html",
                      {"no_device": True})
    today = timezone.localdate()
    mine = CraneAlbaran.objects.filter(person=person).exclude(
        status=CraneAlbaran.Status.CANCELLED).select_related(
        "worksite", "machine")
    pending = [a for a in mine.filter(signed_at__isnull=True)
               .order_by("day", "planned_time")]
    signed = list(mine.filter(
        signed_at__isnull=False,
        day__gte=today - datetime.timedelta(days=7)).order_by("-day"))
    return render(request, "crane_albaranes/worker_list.html", {
        "person": person, "name": person_label(person),
        "pending": pending, "signed": signed, "today": today,
        "worksites": Worksite.objects.filter(is_active=True).order_by(
            "name"),
        "machines": _machines(company_user.company),
    })


@never_cache
@require_POST
def worker_new(request):
    """
    POST: a new albarán made by the worker from scratch.
    ---
    POST: albarán nuevo hecho por el gruista desde cero (obra y máquina);
    lleva al albarán para rellenarlo.
    """
    from fleet.models import MachineAsset
    from worksites.models import Worksite

    company_user, person = _device_person(request)
    if person is None:
        return redirect("crane_albaranes:worker_list")
    site = Worksite.objects.filter(pk=request.POST.get("worksite") or 0,
                                   is_active=True).first()
    machine = MachineAsset.objects.filter(
        company=company_user.company,
        pk=request.POST.get("machine") or 0).first()
    if site is None:
        return redirect("crane_albaranes:worker_list")
    albaran = create_albaran(
        company_user.company, day=timezone.localdate(), worksite=site,
        machine=machine, person=person,
        origin=CraneAlbaran.ORIGIN_WORKER, created_by=company_user)
    return redirect("crane_albaranes:worker_albaran", token=albaran.token)


@never_cache
@require_GET
def worker_albaran(request, token):
    """
    GET: the albarán to fill and sign.
    ---
    GET: el albarán para rellenar y firmar. La primera vez queda
    "Abierto" y se rellenan las horas que falten con los fichajes.
    """
    albaran = _by_token(token)
    if albaran.can_edit:
        changed = fill_from_clock(albaran)
        if albaran.opened_at is None:
            albaran.opened_at = timezone.now()
            if albaran.status in (CraneAlbaran.Status.PREPARED,
                                  CraneAlbaran.Status.SENT,
                                  CraneAlbaran.Status.SEND_FAILED):
                albaran.status = CraneAlbaran.Status.OPENED
            changed.append("opened_at")
        if changed:
            albaran.save()
    return render(request, "crane_albaranes/worker_albaran.html", {
        "a": albaran, "operator": person_label(albaran.person),
        "machines": _machines(albaran.company),
        "goods": albaran.goods or {},
    })


@never_cache
@require_POST
def worker_save(request, token):
    """
    POST: save what the worker filled in.
    ---
    POST: guarda lo que ha rellenado el gruista (sin firmar todavía).
    """
    albaran = _by_token(token)
    if not albaran.can_edit:
        return JsonResponse({"error": "Este albarán ya está firmado."},
                            status=400)
    data = {k: v for k, v in request.POST.items() if k in WORKER_FIELDS}
    save_albaran_form(albaran, data, albaran.company)
    albaran.save()
    return JsonResponse({"ok": True})


@never_cache
@require_POST
def worker_clock(request, token):
    """
    POST: take the times again from today's clock events.
    ---
    POST: vuelve a sacar las horas de los fichajes del día (pisa las
    escritas). JSON con las horas.
    """
    albaran = _by_token(token)
    if not albaran.can_edit:
        return JsonResponse({"error": "Este albarán ya está firmado."},
                            status=400)
    changed = fill_from_clock(albaran, overwrite=True)
    if not changed:
        return JsonResponse({"error": "Todavía no hay fichajes de ese día."},
                            status=400)
    albaran.save()

    def hhmm(value):
        return value.strftime("%H:%M") if value else ""

    return JsonResponse({
        "base_out": hhmm(albaran.base_out), "work_in": hhmm(albaran.work_in),
        "work_out": hhmm(albaran.work_out), "base_in": hhmm(albaran.base_in),
        "hours_worked": str(albaran.hours_worked or ""),
    })


def _coordinate(raw, limit):
    try:
        value = Decimal(str(raw))
    except (InvalidOperation, TypeError):
        return None
    if abs(value) > limit:
        return None
    return value.quantize(Decimal("0.000001"))


@never_cache
@require_POST
def worker_sign(request, token):
    """
    POST: both signatures; then PDF, bucket and delivery to the client.
    ---
    POST: firma del operario y del cliente (nombre, D.N.I. y firma en la
    pantalla). Se guarda lo rellenado, queda firmado (ya no se edita) y
    se genera el PDF, se guarda en el cubo y se envía al cliente. JSON
    con el resultado de la entrega.
    """
    albaran = _by_token(token)
    if not albaran.can_edit:
        return JsonResponse({"error": "Este albarán ya está firmado."},
                            status=400)
    client_signature = request.POST.get("client_signature", "")
    operator_signature = request.POST.get("operator_signature", "")
    signer = (request.POST.get("signer_name") or "").strip()
    if not client_signature.startswith("data:image/png;base64,"):
        return JsonResponse({"error": "Falta la firma del cliente."},
                            status=400)
    if not operator_signature.startswith("data:image/png;base64,"):
        return JsonResponse({"error": "Falta tu firma."}, status=400)
    if not signer:
        return JsonResponse({"error": "Falta el nombre de quien firma."},
                            status=400)
    data = {k: v for k, v in request.POST.items() if k in WORKER_FIELDS}
    save_albaran_form(albaran, data, albaran.company)
    albaran.client_signature = client_signature
    albaran.operator_signature = operator_signature
    albaran.signer_name = signer[:120]
    albaran.signer_dni = (request.POST.get("signer_dni") or "").strip()[:20]
    albaran.sign_latitude = _coordinate(request.POST.get("lat"), 90)
    albaran.sign_longitude = _coordinate(request.POST.get("lon"), 180)
    albaran.signed_at = timezone.now()
    albaran.status = CraneAlbaran.Status.SIGNED
    albaran.save()
    delivered = finish_signed(albaran)
    logger.info("# [ALBARÁN GRÚA] %s firmado por %s; entrega: %s",
                albaran.number, signer,
                albaran.delivered_to or albaran.delivery_error)
    return JsonResponse({
        "ok": True, "delivered": delivered,
        "delivered_to": albaran.delivered_to,
        "delivery_error": albaran.delivery_error,
        "status": albaran.get_status_display(),
    })


@never_cache
@require_GET
def worker_pdf(request, token):
    """
    GET: the albarán as PDF.
    ---
    GET: el albarán en PDF.
    """
    albaran = _by_token(token)
    response = HttpResponse(pdf_bytes(albaran),
                            content_type="application/pdf")
    response["Content-Disposition"] = 'inline; filename="%s"' % (
        pdf_name(albaran))
    return response
