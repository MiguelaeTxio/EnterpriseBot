# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/new_ui/views_signatures_nui.py
"""
Company signatures in the new interface (Empresa › Firmas).

---

Firmas de empresa en la nueva interfaz (S163, 24/11), copia de
panel/views_signatures.py y panel/views_signatures_lists.py sin
depender de ellas: documentos firmados, firmas guardadas, certificados
y agentes; generar documentos firmados, guardar o borrar firmas, elegir
el certificado de cada firma, descargar y cancelar lotes, vincular un
ordenador y dar de baja agentes, y los avisos de certificado. Solo para
quien tiene `CompanyUser.signature_access` (como en la antigua). La
lógica está en document_explorer/signed_forms_service.py y
document_explorer/signing_agent_service.py.
"""
import io
import json
import logging
import zipfile
from urllib.parse import quote

from django.db import transaction
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views import View

from document_explorer import signed_forms_service as forms
from document_explorer import signing_agent_service as agents
from document_explorer.confidential import ConfidentialError
from document_explorer.models import (
    CertificateAlertDismissal,
    CompanyFiscalProfile,
    CompanySignature,
    PersonIdentity,
    SignedFormFile,
    SignedFormJob,
    SigningAgent,
)
from new_ui.mixins import SuperuserRequiredMixin

logger = logging.getLogger(__name__)

MAX_FORM_BYTES = 25 * 1024 * 1024
MAX_SIGNATURE_BYTES = 5 * 1024 * 1024
FIRMAS_TABS = ("firmas", "firmas_guardadas", "certificados",
               "agentes_firma")


def can_sign(company_user):
    """Solo quien tiene acceso a las firmas (como en la antigua)."""
    return bool(company_user is not None
                and getattr(company_user, "signature_access", False))


def _ok(message, **extra):
    return JsonResponse({"ok": True, "message": message, **extra})


def _error(message, status=400):
    return JsonResponse({"ok": False, "message": message}, status=status)


class SignatureMixin(SuperuserRequiredMixin):
    """Superusuario de la nueva interfaz y, además, acceso a las firmas."""

    def dispatch(self, request, *args, **kwargs):
        cu = getattr(request.user, "company_user", None)
        if request.user.is_authenticated and not can_sign(cu):
            return _error("Las firmas no son para tu usuario.", 403)
        return super().dispatch(request, *args, **kwargs)


def _ids(request):
    return [v for v in request.POST.getlist("selected") if v.isdigit()]


def _files_response(results, note=""):
    """Un PDF tal cual o varios en un ZIP, para descargar."""
    if len(results) == 1:
        name, data = results[0]
        response = HttpResponse(data, content_type="application/pdf")
    else:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for name, data in results:
                zf.writestr(name, data)
        response = HttpResponse(buffer.getvalue(),
                                content_type="application/zip")
        name = "Documentos firmados %s.zip" % timezone.localdate(
        ).strftime("%Y-%m-%d")
    ascii_name = name.encode("ascii", "replace").decode().replace("?", "_")
    response["Content-Disposition"] = (
        "attachment; filename=\"%s\"; filename*=UTF-8''%s"
        % (ascii_name, quote(name)))
    if note:
        response["X-Nui-Message"] = json.dumps(note)
    return response


# ------------------------------------------------------------- contexto
def cert_alerts():
    """Los avisos de certificado (caduca pronto o caducado) sin ocultar."""
    try:
        company_certs = agents.company_certificates()
    except Exception:  # noqa: BLE001 -- un aviso nunca tumba la página
        logger.exception("# [FIRMAS] No se pudieron leer los certificados")
        return []
    dismissed = set(CertificateAlertDismissal.objects.values_list(
        "cif", "alert_key"))
    return [e for e in company_certs if e["level"]
            and (e["cif"], e["alert_key"]) not in dismissed]


def signatures_context(section, company_user):
    """Contexto de las acciones de Empresa › Firmas."""
    if section != "doc" or not can_sign(company_user):
        return {}
    signatures = list(CompanySignature.objects.select_related(
        "company").order_by("company__legal_name", "label"))
    return {
        "sig_can": True,
        "sig_signatures": signatures,
        "sig_profiles": list(CompanyFiscalProfile.objects.order_by(
            "legal_name")),
        "sig_people": list(PersonIdentity.objects.filter(
            is_active_employee=True).order_by(
            "first_surname", "second_surname", "given_name").only(
            "pk", "first_surname", "second_surname", "given_name")),
        "sig_alerts": cert_alerts(),
    }


def render_certificates(request):
    """
    Empresa › Firmas › Certificados (no es un listado de la base).

    ---

    Los certificados digitales que ven los agentes, por empresa: cuál se
    usa al firmar, los vigentes y los caducados (como el listado
    «Certificados» de la antigua).
    """
    if not can_sign(request.user.company_user):
        return HttpResponse('<p class="p-2 text-muted small">Las firmas no '
                            'son para tu usuario.</p>')
    rows = []
    for entry in agents.company_certificates():
        for cert in entry["certs"]:
            if cert is entry["current"]:
                state, label = "current", "Se usa al firmar"
            elif cert["valid"]:
                state, label = "valid", "Vigente"
            else:
                state, label = "expired", "Caducado"
            rows.append({"entry": entry, "cert": cert, "state": state,
                         "state_label": label,
                         "warning": state == "current" and entry["level"]})
    rows.sort(key=lambda r: (r["entry"]["company"].lower(),
                             r["state"] != "current"))
    return render(request, "new_ui/_sig_certificates.html", {
        "rows": rows, "alerts": cert_alerts()})


# --------------------------------------------------------------- firmas
class SignatureSaveView(SignatureMixin, View):
    """POST: guarda una firma nueva (empresa, quién firma e imagen)."""

    def post(self, request):
        profile = CompanyFiscalProfile.objects.filter(
            pk=request.POST.get("company") or 0).first()
        label = (request.POST.get("label") or "").strip()[:120]
        image = request.FILES.get("image")
        if profile is None:
            return _error("Elige la empresa.")
        if not label:
            return _error("Escribe quién firma.")
        if image is None:
            return _error("Elige la imagen de la firma.")
        if image.size > MAX_SIGNATURE_BYTES:
            return _error("La imagen pasa de 5 MB.")
        try:
            data = forms.store_signature(image.read())
        except (forms.SignedFormError, ConfidentialError) as exc:
            return _error(str(exc))
        CompanySignature.objects.create(
            company=profile, label=label, image_encrypted=data,
            created_by=request.user.company_user)
        logger.info("# [FIRMAS] Firma '%s' de %s guardada por %s.", label,
                    profile.legal_name, request.user.username)
        return _ok("Firma de %s (%s) guardada." % (label,
                                                   profile.legal_name))


class SignatureImageView(SignatureMixin, View):
    """GET: la imagen de una firma guardada."""

    def get(self, request, pk):
        signature = CompanySignature.objects.filter(pk=pk).first()
        if signature is None:
            return HttpResponse(status=404)
        try:
            png = forms.signature_png(signature)
        except ConfidentialError as exc:
            return HttpResponse(str(exc), status=500)
        response = HttpResponse(png, content_type="image/png")
        response["Cache-Control"] = "no-store"
        return response


class SignatureSheetView(SignatureMixin, View):
    """
    GET: one stored signature in the viewer (image and certificate).

    ---

    GET: una firma guardada en el visor (al pulsar su fila): la imagen,
    con qué certificado digital firma (botones, sin desplegable) y
    borrarla.
    """

    def get(self, request, pk):
        signature = CompanySignature.objects.select_related(
            "company", "created_by__user").filter(pk=pk).first()
        if signature is None:
            return HttpResponse("Esa firma ya no existe.", status=404)
        company_certs = agents.company_certificates()
        active = list(SigningAgent.objects.filter(is_active=True))
        return render(request, "new_ui/_sig_signature.html", {
            "signature": signature,
            "company_certs": company_certs,
            "cert_entry": next((e for e in company_certs
                                if e["cif"] == signature.certificate_cif),
                               None),
            "agents_v3": any(a.certificates for a in active),
            "aliases": sorted({alias for a in active
                               for alias in a.aliases or []}),
        })


class SignatureCertificateView(SignatureMixin, View):
    """POST: con qué certificado firma una firma (vacío = solo imagen)."""

    def post(self, request, pk):
        signature = CompanySignature.objects.filter(pk=pk).first()
        if signature is None:
            return _error("Esa firma ya no existe.", 404)
        if "cif" in request.POST:
            signature.certificate_cif = (
                request.POST.get("cif") or "").strip().upper()[:20]
            signature.certificate_alias = ""
        else:
            signature.certificate_alias = (
                request.POST.get("alias") or "").strip()[:255]
            signature.certificate_cif = ""
        signature.save(update_fields=["certificate_alias",
                                      "certificate_cif"])
        if signature.certificate_cif or signature.certificate_alias:
            return _ok("%s firmará con el certificado digital elegido."
                       % signature.label)
        return _ok("%s firmará solo con la imagen." % signature.label)


class SignatureMassView(SignatureMixin, View):
    """POST: borra las firmas marcadas o da de baja los agentes marcados."""

    def post(self, request):
        what = request.POST.get("what", "")
        ids = _ids(request) or [v for v in [request.POST.get("pk", "")]
                                if v.isdigit()]
        if not ids:
            return _error("Marca primero.")
        if what == "delete_signatures":
            items = CompanySignature.objects.filter(pk__in=ids)
            done = items.count()
            logger.info("# [FIRMAS] %s borra %d firma(s): %s",
                        request.user.username, done,
                        ", ".join(s.label for s in items))
            items.delete()
            return _ok("%d firma(s) borrada(s)." % done)
        if what == "disable_agents":
            done = SigningAgent.objects.filter(pk__in=ids).update(
                is_active=False)
            return _ok("%d ordenador(es) dado(s) de baja: su código ya no "
                       "vale." % done)
        return _error("Acción no válida.")


# ----------------------------------------------------------- documentos
class SignedFormsGenerateView(SignatureMixin, View):
    """
    POST: fill and sign the client's PDFs; one PDF or a ZIP.

    ---

    POST: rellena y firma los PDF del cliente con la firma elegida (su
    empresa) y, si el documento lo pide, el trabajador. Con firma de
    imagen descarga el PDF o un ZIP; con certificado, va a la cola del
    agente de firmas y se sigue en Documentos firmados. Si alguno no se
    puede rellenar, no se genera nada y se dice cuál. Si Gemini está
    saturado, nada se pierde: queda un lote «Esperando a Gemini».
    """

    def post(self, request):
        signature = CompanySignature.objects.select_related(
            "company").filter(pk=request.POST.get("signature") or 0).first()
        files = request.FILES.getlist("documents")
        if signature is None:
            return _error("Elige la firma.")
        if not files:
            return _error("Elige los PDF del cliente.")
        profile = signature.company
        try:
            png = forms.signature_png(signature)
        except ConfidentialError as exc:
            return _error(str(exc), 500)
        person = _person_from(request.POST.get("person", ""))
        values = forms.form_values(profile, person)
        results, errors, names, notes, configs = [], [], set(), [], []
        originals, busy = [], False
        all_pages = request.POST.get("all_pages") == "1"
        for upload in files:
            if upload.size > MAX_FORM_BYTES:
                errors.append("%s: pasa de 25 MB" % upload.name)
                continue
            raw = upload.read()
            name = forms.output_name(upload.name, profile)
            base, number = name[:-4], 2
            while name in names:
                name = "%s (%d).pdf" % (base, number)
                number += 1
            names.add(name)
            originals.append((name, raw))
            if busy:
                continue
            try:
                filled = forms.fill_form(
                    raw, values, png,
                    allow_empty=agents.is_digital(signature))
            except forms.GeminiBusyError:
                busy = True
                continue
            except forms.SignedFormError as exc:
                errors.append("%s: %s" % (upload.name, exc))
                continue
            notes.append({"file": upload.name, "method": filled.method,
                          "notes": filled.notes})
            results.append((name, filled.data))
            configs.append(forms.autofirma_config(filled.data,
                                                  filled.signature_box))
        if errors:
            return _error("No se ha generado nada. " + "; ".join(errors))
        cu = request.user.company_user
        if busy:
            from document_explorer.tasks import fill_signed_job_task

            try:
                job = agents.create_waiting_job(
                    signature, originals, cu, all_pages=all_pages,
                    person=person)
            except agents.NoValidCertificate as exc:
                return _error("No se ha generado nada. " + str(exc))
            transaction.on_commit(lambda: fill_signed_job_task.delay(job.pk))
            return _ok("Gemini está saturado: los %d documento(s) esperan "
                       "en el lote #%d y se rellenan solos; síguelos en "
                       "Documentos firmados." % (len(originals), job.pk))
        logger.info("# [FIRMAS] %d documento(s) firmados con '%s' (%s) por "
                    "%s.", len(results), signature.label,
                    profile.legal_name, request.user.username)
        if agents.is_digital(signature):
            try:
                job = agents.create_job(
                    signature, [(name, data, config) for (name, data),
                                config in zip(results, configs)],
                    notes, cu, all_pages=all_pages, person=person)
            except agents.NoValidCertificate as exc:
                return _error("No se ha generado nada. " + str(exc))
            return _ok("%d documento(s) en la cola del agente de firmas "
                       "(lote #%d): se descargan en Documentos firmados "
                       "cuando estén firmados." % (len(results), job.pk))
        agents.record_image_job(signature, results, notes, cu,
                                person=person)
        return _files_response(results, "%d documento(s) firmado(s)."
                               % len(results))


def _person_from(text):
    """El trabajador escrito (como sale en la lista) o None."""
    text = (text or "").strip().lower()
    if not text:
        return None
    for person in PersonIdentity.objects.filter(
            is_active_employee=True).only(
            "pk", "first_surname", "second_surname", "given_name"):
        if person_label(person).lower() == text:
            return person
    return None


def person_label(person):
    surnames = " ".join(p for p in (person.first_surname,
                                    person.second_surname) if p)
    return ("%s, %s" % (surnames, person.given_name)).strip(", ")


class SignedFilesDownloadView(SignatureMixin, View):
    """POST: los documentos firmados marcados (uno o un ZIP)."""

    def post(self, request):
        files = SignedFormFile.objects.filter(
            pk__in=_ids(request), status=SignedFormFile.STATUS_DONE,
        ).order_by("pk")
        try:
            results, names = [], set()
            for item in files:
                name, number = item.name, 2
                while name in names:
                    name = "%s (%d).pdf" % (item.name[:-4], number)
                    number += 1
                names.add(name)
                results.append((name, agents.signed_pdf(item)))
        except ConfidentialError as exc:
            return _error(str(exc), 500)
        if not results:
            return _error("Ninguno de los marcados está firmado todavía.")
        return _files_response(results)


class SignedJobsCancelView(SignatureMixin, View):
    """POST: cancela los lotes (sin terminar) de los documentos marcados."""

    def post(self, request):
        jobs = SignedFormJob.objects.filter(
            files__pk__in=_ids(request)).distinct()
        done = 0
        for job in jobs:
            if agents.cancel_job(job, request.user.company_user):
                done += 1
                logger.info("# [FIRMAS] Lote %s cancelado por %s.", job.pk,
                            request.user.username)
        if not done:
            return _error("Ninguno de esos lotes se puede cancelar: ya han "
                          "terminado.")
        return _ok("%d lote(s) cancelado(s)." % done)


# --------------------------------------------------------------- agentes
class SigningAgentCreateView(SignatureMixin, View):
    """POST: vincula un ordenador: crea el agente y da su código."""

    def post(self, request):
        name = (request.POST.get("name") or "").strip()[:120] or (
            "Ordenador de firmas")
        agent, token = agents.create_agent(name, request.user.company_user)
        logger.info("# [FIRMAS] Agente '%s' (%s) creado por %s.", name,
                    agent.pk, request.user.username)
        return _ok("Código de vinculación de «%s» (solo se ve ahora; "
                   "pégalo en el agente al instalarlo): %s" % (name, token))


class CertificateAlertDismissView(SignatureMixin, View):
    """POST: «No mostrar más» en un aviso de certificado."""

    def post(self, request):
        cif = (request.POST.get("cif") or "").strip().upper()[:20]
        key = (request.POST.get("key") or "").strip()[:40]
        if not cif or not key:
            return _error("Falta el aviso.")
        CertificateAlertDismissal.objects.get_or_create(
            cif=cif, alert_key=key,
            defaults={"dismissed_by": request.user.company_user})
        return _ok("Ese aviso ya no sale (vuelve si cambia la situación).")
