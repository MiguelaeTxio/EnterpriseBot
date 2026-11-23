# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/new_ui/views_payslips_nui.py
"""
Payslip deliveries in the new interface (Empresa › Nóminas).

---

Entrega de nóminas en la nueva interfaz (S163, 23/11), copiado de
panel/views_payslips.py: subir la carpeta de una entrega (se crea, se
suben sus PDF uno a uno y empieza la lectura), las acciones sobre la
entrega elegida en el filtro «Entrega» (visto bueno y enviar,
reintentar el WhatsApp, volver a avisar, anular, compartir con
supervisores) y sobre las nóminas marcadas (dejar fuera, volver a
meter, poner el trabajador, descargar). La lógica vive en
hr_calendar.payslip_delivery y el acceso en hr_calendar.payslip_access:
Jerónimo (y quien tiene `payslip_uploader`) sube; cada entrega la ven
quien la subió, los supervisores con los que la comparte y quien tiene
acceso a todas (Alejandro). Nadie más ve una nómina.
"""
import io
import re
import zipfile
from urllib.parse import quote

from django.db.models import Q
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.views import View

from document_explorer.models import PersonIdentity
from hr_calendar import payslip_access as access
from hr_calendar import payslip_delivery as pd
from hr_calendar.models import PayslipBatch, PayslipItem
from hr_calendar.worker_requests import person_label
from new_ui.mixins import SuperuserRequiredMixin


def _ok(message, **extra):
    return JsonResponse(dict({"ok": True, "message": message}, **extra))


def _error(message, status=400):
    return JsonResponse({"ok": False, "message": message,
                         "error": message}, status=status)


def can_upload(company_user):
    """True si sube entregas (`CompanyUser.payslip_uploader`)."""
    return bool(company_user is not None
                and getattr(company_user, "payslip_uploader", False))


def _candidates(company_user, batch=None):
    users = access.share_candidates(
        company_user.company,
        exclude=batch.created_by if batch is not None else company_user)
    for user in users:
        user.label = access.user_label(user)
    return users


def _chosen(request, company_user, batch=None):
    wanted = set(request.POST.getlist("share"))
    return [u for u in _candidates(company_user, batch)
            if str(u.pk) in wanted]


def _batch_of(request):
    """La entrega elegida en el filtro «Entrega» (x_nominas_entrega)."""
    raw = request.POST.get("x_nominas_entrega", "")
    if not raw.isdigit():
        return None
    return access.visible_batches(request.user.company_user).filter(
        pk=int(raw)).first()


def payslips_context(section, company_user):
    """Contexto de Empresa › Nóminas: subir y compartir."""
    if section != "doc" or company_user is None:
        return {}
    return {
        "psl_can_upload": can_upload(company_user),
        "psl_candidates": _candidates(company_user),
    }


class PayslipNuiCreateView(SuperuserRequiredMixin, View):
    """POST: entrega nueva («Subiendo») con el nombre de la carpeta."""

    def post(self, request):
        cu = request.user.company_user
        if not can_upload(cu):
            return _error("Tu usuario no sube nóminas.", 403)
        batch = PayslipBatch.objects.create(
            company=cu.company, created_by=cu,
            folder_name=request.POST.get("folder", "")[:255],
            notify_whatsapp=request.POST.get("notify") != "0")
        access.set_shares(batch, _chosen(request, cu), cu)
        return _ok("Entrega creada.", id=batch.pk)


class PayslipNuiUploadView(SuperuserRequiredMixin, View):
    """POST: uno de los PDF de la carpeta (cifrado hasta el envío)."""

    def post(self, request, pk):
        batch = access.visible_batches(request.user.company_user).filter(
            pk=pk).first()
        if batch is None:
            return _error("Esa entrega no existe.", 404)
        if batch.status != PayslipBatch.Status.UPLOADING:
            return _error("La entrega ya no admite archivos.")
        upload = request.FILES.get("file")
        if upload is None:
            return _error("Falta el archivo.")
        try:
            pd.stage_file(batch, upload.name, upload.read())
        except pd.PayslipError as exc:
            return _error(str(exc))
        return _ok("Subido.")


class PayslipNuiReadView(SuperuserRequiredMixin, View):
    """POST: ya están todos los PDF; empieza la lectura."""

    def post(self, request, pk):
        from hr_calendar.tasks import read_payslip_batch_task

        batch = access.visible_batches(request.user.company_user).filter(
            pk=pk).first()
        if batch is None:
            return _error("Esa entrega no existe.", 404)
        if batch.status != PayslipBatch.Status.UPLOADING:
            return _error("La entrega ya se está leyendo.")
        if not batch.items.exists():
            batch.delete()
            return _error("No se ha subido ningún PDF.")
        batch.status = PayslipBatch.Status.READING
        batch.save(update_fields=["status"])
        read_payslip_batch_task.delay(batch.pk)
        return _ok("Leyendo en segundo plano.", id=batch.pk)


def _find_person(company, text):
    """El trabajador por DNI exacto o por un nombre que solo case con uno."""
    text = (text or "").strip()
    if not text:
        return None, ""
    by_dni = PersonIdentity.objects.filter(company=company,
                                           dni__iexact=text).first()
    if by_dni is not None:
        return by_dni, ""
    qs = PersonIdentity.objects.filter(company=company)
    for word in text.split():
        qs = qs.filter(Q(given_name__icontains=word)
                       | Q(first_surname__icontains=word)
                       | Q(second_surname__icontains=word))
    found = list(qs[:3])
    if len(found) == 1:
        return found[0], ""
    if not found:
        return None, "No hay ningún trabajador con «%s»." % text
    return None, ("«%s» es más de un trabajador: escribe su DNI." % text)


class PayslipNuiActionView(SuperuserRequiredMixin, View):
    """
    POST `action`: sobre la entrega del filtro o las nóminas marcadas.
    """

    def post(self, request):
        from hr_calendar.tasks import (
            retry_payslip_whatsapp_task, send_payslip_batch_task,
        )

        cu = request.user.company_user
        visible = access.visible_batches(cu)
        action = request.POST.get("action", "")
        ids = [v for v in request.POST.getlist("selected") if v.isdigit()]
        items = list(PayslipItem.objects.filter(
            pk__in=ids, batch__in=visible).select_related("batch"))
        batch = _batch_of(request)
        if action in ("approve", "retry", "notify", "cancel", "share") and (
                batch is None):
            return _error("Elige la entrega en los filtros de Nóminas "
                          "(«Entrega»).")
        try:
            if action in ("exclude", "include"):
                if not items:
                    raise pd.PayslipError("Marca alguna nómina.")
                for item in items:
                    pd.set_excluded(item, action == "exclude")
                return _ok("%d nómina(s) %s." % (
                    len(items), "fuera de la entrega" if action == "exclude"
                    else "otra vez en la entrega"))
            if action == "assign":
                if len(items) != 1:
                    raise pd.PayslipError(
                        "Marca una sola nómina para ponerle el trabajador.")
                person, problem = _find_person(cu.company,
                                               request.POST.get("person"))
                if problem:
                    raise pd.PayslipError(problem)
                pd.assign(items[0], person)
                return _ok("Nómina asignada a %s." % person_label(person)
                           if person else "Nómina sin trabajador.")
            if action == "approve":
                pd.approve(batch, cu)
                send_payslip_batch_task.delay(batch.pk)
                return _ok("Visto bueno dado: se están archivando y "
                           "enviando las nóminas.")
            if action == "retry":
                retry_payslip_whatsapp_task.delay(batch.pk)
                return _ok("Reintentando el WhatsApp de las nóminas que no "
                           "salieron.")
            if action == "notify":
                if pd.notify_ready(batch):
                    return _ok("Aviso enviado.")
                return _error("No se ha podido avisar: %s"
                              % batch.notify_error)
            if action == "cancel":
                pd.cancel(batch)
                return _ok("Entrega anulada; sus copias se han borrado.")
            if action == "share":
                if not access.can_share(batch, cu):
                    raise pd.PayslipError(
                        "Solo quien subió la entrega puede cambiar el "
                        "acceso.")
                added, removed = access.set_shares(
                    batch, _chosen(request, cu, batch), cu)
                return _ok("Acceso guardado (%d nuevo(s), %d quitado(s))."
                           % (added, removed))
        except pd.PayslipError as exc:
            return _error(str(exc))
        return _error("Acción desconocida.")


def _download_name(item):
    parts = [person_label(item.person) if item.person else "Sin_trabajador",
             "Nomina", item.period_label or "", str(item.pk)]
    text = "_".join(part for part in parts if part)
    return re.sub(r"[^A-Za-z0-9]+", "_", pd._plain(text)).strip("_") + ".pdf"


def _item_bytes(item, company_user):
    from document_explorer.confidential import ConfidentialError, open_bytes

    if item.entry_id is not None:
        try:
            return open_bytes(item.entry, company_user)
        except ConfidentialError as exc:
            raise pd.PayslipError(str(exc)) from exc
    if not item.staged_path:
        raise pd.PayslipError("La nómina %s no tiene PDF guardado."
                              % item.pk)
    return pd.item_pdf(item)


class PayslipNuiDownloadView(SuperuserRequiredMixin, View):
    """POST: las nóminas marcadas, un PDF (una) o un ZIP (varias)."""

    def post(self, request):
        cu = request.user.company_user
        ids = [v for v in request.POST.getlist("selected") if v.isdigit()]
        items = list(PayslipItem.objects.filter(
            pk__in=ids, batch__in=access.visible_batches(cu),
        ).exclude(page_to=0).select_related(
            "batch", "entry", "person__company_user").order_by(
            "period_end", "person__first_surname", "pk"))
        if not items:
            return _error("No hay ninguna nómina marcada que se pueda "
                          "descargar.")
        try:
            if len(items) == 1:
                data = _item_bytes(items[0], cu)
                response = HttpResponse(data, content_type="application/pdf")
                name = _download_name(items[0])
            else:
                buffer = io.BytesIO()
                with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
                    for item in items:
                        zf.writestr(_download_name(item),
                                    _item_bytes(item, cu))
                response = HttpResponse(buffer.getvalue(),
                                        content_type="application/zip")
                name = "Nominas_%s.zip" % timezone.localdate().strftime(
                    "%Y%m%d")
        except pd.PayslipError as exc:
            return _error(str(exc))
        response["Content-Disposition"] = (
            'attachment; filename="%s"; filename*=UTF-8\'\'%s' % (
                name, quote(name)))
        response["Cache-Control"] = "private, no-store"
        return response
