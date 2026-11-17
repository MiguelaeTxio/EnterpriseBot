# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/views_signatures.py
"""
S153. "Firmas" tab of the Documentation hub: stored company signatures
and the signed forms generated with them.

---

S153. Pestaña "Firmas" del hub de Documentación. Miguel Ángel: los
clientes envían varios documentos casi iguales (cambia la obra), vacíos
y sin firmar; se elige qué empresa nuestra hace el trabajo y con qué
firma, y con un botón salen todos rellenos y firmados. Las firmas quedan
guardadas (cifradas). Solo entra quien tiene
`CompanyUser.signature_access` ("solamente puede tener acceso Yolanda").
Lógica: document_explorer/signed_forms_service.py.
"""
import io
import json
import logging
import zipfile
from urllib.parse import quote

from django.http import HttpResponse, JsonResponse
from django.urls import reverse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

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
from panel.mixins import CompanyUserRequiredMixin

logger = logging.getLogger(__name__)

MAX_FORM_BYTES = 25 * 1024 * 1024
MAX_SIGNATURE_BYTES = 5 * 1024 * 1024


def can_use_signatures(company_user):
    """
    True if this user may see and use the company signatures.
    ---
    True si este usuario puede ver y usar las firmas de las empresas.
    """
    return bool(company_user is not None
                and getattr(company_user, "signature_access", False))


class SignatureAccessMixin(CompanyUserRequiredMixin):
    """
    Only users with signature access; the rest get a 403.
    ---
    Solo quien tiene acceso a las firmas; el resto recibe un 403 (la
    pestaña ni siquiera se le muestra).
    """

    def dispatch(self, request, *args, **kwargs):
        company_user = getattr(request.user, "company_user", None)
        if (request.user.is_authenticated
                and not can_use_signatures(company_user)):
            return HttpResponse("Acceso denegado: las firmas no son para "
                                "tu usuario.", status=403)
        return super().dispatch(request, *args, **kwargs)


class SignatureSaveView(SignatureAccessMixin, View):
    """
    POST: store a new signature for a company.
    ---
    POST: guarda una firma nueva de una empresa (empresa, nombre e
    imagen). JSON {ok} o {error}.
    """

    def post(self, request):
        profile = CompanyFiscalProfile.objects.filter(
            pk=request.POST.get("company") or 0).first()
        label = (request.POST.get("label") or "").strip()[:120]
        image = request.FILES.get("image")
        if profile is None:
            return JsonResponse({"error": "Elige la empresa."}, status=400)
        if not label:
            return JsonResponse({"error": "Escribe quién firma."},
                                status=400)
        if image is None:
            return JsonResponse({"error": "Elige la imagen de la firma."},
                                status=400)
        if image.size > MAX_SIGNATURE_BYTES:
            return JsonResponse({"error": "La imagen pasa de 5 MB."},
                                status=400)
        try:
            data = forms.store_signature(image.read())
        except (forms.SignedFormError, ConfidentialError) as exc:
            return JsonResponse({"error": str(exc)}, status=400)
        CompanySignature.objects.create(
            company=profile, label=label, image_encrypted=data,
            created_by=request.user.company_user)
        logger.info("# [FIRMAS] Firma '%s' de %s guardada por %s.", label,
                    profile.legal_name, request.user.username)
        return JsonResponse({"ok": True})


class SignatureDeleteView(SignatureAccessMixin, View):
    """
    POST: delete a stored signature.
    ---
    POST: borra una firma guardada. JSON {ok} o {error}.
    """

    def post(self, request, pk):
        signature = CompanySignature.objects.filter(pk=pk).first()
        if signature is None:
            return JsonResponse({"error": "Esa firma ya no existe."},
                                status=404)
        logger.info("# [FIRMAS] Firma '%s' de %s borrada por %s.",
                    signature.label, signature.company.legal_name,
                    request.user.username)
        signature.delete()
        return JsonResponse({"ok": True})


class SignatureImageView(SignatureAccessMixin, View):
    """
    GET: the PNG of a stored signature (preview).
    ---
    GET: la imagen de una firma guardada, para verla en la pestaña.
    """

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


class SignedFormsGenerateView(SignatureAccessMixin, View):
    """
    POST: fill and sign the uploaded forms; one PDF or a ZIP.
    ---
    POST: rellena y firma los PDF subidos con la empresa, la firma y,
    si el documento lo pide, el trabajador elegidos (por texto o, si no
    se puede, por Gemini). Devuelve el PDF (si es uno) o un ZIP, con la
    cabecera X-Signed-Notes (cómo se rellenó cada uno y sus avisos). Si
    alguno no se puede rellenar, no se genera nada y se dice cuál y por
    qué (JSON).
    """

    def post(self, request):
        profile = CompanyFiscalProfile.objects.filter(
            pk=request.POST.get("company") or 0).first()
        signature = CompanySignature.objects.filter(
            pk=request.POST.get("signature") or 0).first()
        files = request.FILES.getlist("documents")
        if profile is None:
            return JsonResponse({"error": "Elige la empresa."}, status=400)
        if signature is None or signature.company_id != profile.pk:
            return JsonResponse(
                {"error": "Elige una firma de esa empresa."}, status=400)
        if not files:
            return JsonResponse({"error": "Elige los PDF del cliente."},
                                status=400)
        try:
            png = forms.signature_png(signature)
        except ConfidentialError as exc:
            return JsonResponse({"error": str(exc)}, status=500)
        person = PersonIdentity.objects.filter(
            pk=request.POST.get("person") or 0).first()
        values = forms.form_values(profile, person)
        results, errors, names, notes, configs = [], [], set(), [], []
        for upload in files:
            if upload.size > MAX_FORM_BYTES:
                errors.append("%s: pasa de 25 MB" % upload.name)
                continue
            try:
                # S153: con certificado, un documento sin huecos que
                # rellenar se firma solo digitalmente.
                filled = forms.fill_form(
                    upload.read(), values, png,
                    allow_empty=bool(signature.certificate_cif
                                     or signature.certificate_alias))
            except forms.SignedFormError as exc:
                errors.append("%s: %s" % (upload.name, exc))
                continue
            data = filled.data
            notes.append({"file": upload.name, "method": filled.method,
                          "notes": filled.notes})
            name = forms.output_name(upload.name, profile)
            base, number = name[:-4], 2
            while name in names:
                name = "%s (%d).pdf" % (base, number)
                number += 1
            names.add(name)
            results.append((name, data))
            configs.append(forms.autofirma_config(data,
                                                  filled.signature_box))
        if errors:
            return JsonResponse({"error": "No se ha generado nada. "
                                          + "; ".join(errors)}, status=400)
        logger.info("# [FIRMAS] %d documento(s) firmados con '%s' (%s) por "
                    "%s.", len(results), signature.label,
                    profile.legal_name, request.user.username)
        if signature.certificate_cif or signature.certificate_alias:
            # S153: con certificado, a la cola del agente de firmas. Con
            # el CIF (agente v3), solo con un certificado vigente.
            try:
                job = agents.create_job(
                    signature, [(name, data, config) for (name, data),
                                config in zip(results, configs)],
                    notes, request.user.company_user,
                    all_pages=request.POST.get("all_pages") == "1",
                    person=person)
            except agents.NoValidCertificate as exc:
                return JsonResponse({"error": "No se ha generado nada. "
                                              + str(exc)}, status=400)
            return JsonResponse({
                "job": job.pk, "notes": notes,
                "status_url": reverse("panel:signed_job_status",
                                      args=[job.pk]),
            }, status=202)
        # S153: también queda en el listado de documentos firmados.
        agents.record_image_job(signature, results, notes,
                                request.user.company_user, person=person)
        response = _files_response(results)
        # Cómo se rellenó cada uno y qué pedía que no se ha puesto.
        response["X-Signed-Notes"] = quote(json.dumps(notes))
        return response


def _files_response(results):
    """
    One PDF as is, or several in a ZIP, as a download.
    ---
    Un PDF tal cual o varios en un ZIP, para descargar.
    """
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
    response["Content-Disposition"] = (
        "attachment; filename*=UTF-8''%s" % quote(name))
    return response


class SignedJobStatusView(SignatureAccessMixin, View):
    """
    GET: progress of a digital-signature job (JSON).
    ---
    GET: cómo va un lote de firma digital: estado, firmados, errores y,
    cuando termina, el enlace de descarga.
    """

    def get(self, request, pk):
        job = SignedFormJob.objects.filter(pk=pk).first()
        if job is None:
            return JsonResponse({"error": "Ese lote ya no existe."},
                                status=404)
        files = list(job.files.only("name", "status", "error"))
        done = [f for f in files if f.status == SignedFormFile.STATUS_DONE]
        return JsonResponse({
            "status": job.status,
            "total": len(files),
            "done": len(done),
            "errors": [f"{f.name}: {f.error}" for f in files
                       if f.status == SignedFormFile.STATUS_ERROR],
            "download_url": reverse("panel:signed_job_download",
                                    args=[job.pk]) if done else "",
            "cancel_url": reverse("panel:signed_job_cancel",
                                  args=[job.pk]),
        })


class SignedJobDownloadView(SignatureAccessMixin, View):
    """
    GET: the digitally signed PDFs of a job (PDF or ZIP).
    ---
    GET: los PDF ya firmados digitalmente de un lote (uno o un ZIP).
    """

    def get(self, request, pk):
        job = SignedFormJob.objects.filter(pk=pk).first()
        if job is None:
            return HttpResponse("Ese lote ya no existe.", status=404)
        files = job.files.filter(status=SignedFormFile.STATUS_DONE)
        try:
            results = [(f.name, agents.signed_pdf(f)) for f in files]
        except ConfidentialError as exc:
            return HttpResponse(str(exc), status=500)
        if not results:
            return HttpResponse("Todavía no hay ningún documento firmado.",
                                status=404)
        return _files_response(results)


class SigningAgentCreateView(SignatureAccessMixin, View):
    """
    POST: create a signing agent; returns its code once.
    ---
    POST: crea un agente de firmas y devuelve su código (solo esta vez;
    se pega en el agente al instalarlo).
    """

    def post(self, request):
        name = (request.POST.get("name") or "").strip()[:120] or (
            "Ordenador de firmas")
        agent, token = agents.create_agent(name, request.user.company_user)
        logger.info("# [FIRMAS] Agente '%s' (%s) creado por %s.", name,
                    agent.pk, request.user.username)
        return JsonResponse({"ok": True, "code": token})


class SigningAgentDeactivateView(SignatureAccessMixin, View):
    """
    POST: disable a signing agent (its code stops working).
    ---
    POST: da de baja un agente: su código deja de valer.
    """

    def post(self, request, pk):
        updated = SigningAgent.objects.filter(pk=pk).update(is_active=False)
        if not updated:
            return JsonResponse({"error": "Ese agente ya no existe."},
                                status=404)
        return JsonResponse({"ok": True})


class SignatureCertificateView(SignatureAccessMixin, View):
    """
    POST: choose the certificate (alias) a signature signs with.
    ---
    POST: elige el certificado digital (alias que ve el agente) con el
    que firma una firma guardada; vacío = solo imagen.
    """

    def post(self, request, pk):
        signature = CompanySignature.objects.filter(pk=pk).first()
        if signature is None:
            return JsonResponse({"error": "Esa firma ya no existe."},
                                status=404)
        # S153 (agente v3): se elige la empresa del certificado (CIF);
        # el alias suelto queda solo para el agente antiguo.
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
        return JsonResponse({"ok": True})


class SignatureAlertDismissView(SignatureAccessMixin, View):
    """
    POST: "No mostrar más" on a certificate alert.
    ---
    POST: «No mostrar más» en un aviso de certificado (CIF y situación);
    vuelve a salir si la situación cambia.
    """

    def post(self, request):
        cif = (request.POST.get("cif") or "").strip().upper()[:20]
        key = (request.POST.get("key") or "").strip()[:40]
        if not cif or not key:
            return JsonResponse({"error": "Falta el aviso."}, status=400)
        CertificateAlertDismissal.objects.get_or_create(
            cif=cif, alert_key=key,
            defaults={"dismissed_by": getattr(request.user,
                                              "company_user", None)})
        return JsonResponse({"ok": True})


# ---------------------------------------------------------------------------
# API del agente de firmas (sin sesión: Authorization: Bearer <código>).
# ---------------------------------------------------------------------------


class AgentApiMixin:
    """
    The agent identified by its code; 403 otherwise.
    ---
    Identifica al agente por su código; si no vale, 403.
    """

    def dispatch(self, request, *args, **kwargs):
        self.agent = agents.agent_for_request(request)
        if self.agent is None:
            return HttpResponse("Código de agente no válido.", status=403)
        return super().dispatch(request, *args, **kwargs)


@method_decorator(csrf_exempt, name="dispatch")
class AgentHeartbeatView(AgentApiMixin, View):
    """
    POST: the agent says hello (PC, certificates, AutoFirma, error).
    ---
    POST: latido del agente: ordenador, certificados que ve (JSON),
    versión de AutoFirma y último error.
    """

    def post(self, request):
        try:
            aliases = json.loads(request.POST.get("aliases") or "null")
        except ValueError:
            aliases = None
        if aliases is not None and not isinstance(aliases, list):
            aliases = None
        # S153 (agente v3): certificados con huella y fechas.
        try:
            certificates = json.loads(
                request.POST.get("certificates") or "null")
        except ValueError:
            certificates = None
        if certificates is not None and not isinstance(certificates, list):
            certificates = None
        agents.record_heartbeat(
            self.agent, request.POST.get("host", ""), aliases,
            request.POST.get("autofirma", ""), request.POST.get("error", ""),
            certificates)
        return JsonResponse({"ok": True, "name": self.agent.name})


@method_decorator(csrf_exempt, name="dispatch")
class SignedJobCancelView(SignatureAccessMixin, View):
    """
    POST: cancel a digital-signature job still in progress.
    ---
    POST: cancela un lote de firma digital que aún no ha terminado.
    """

    def post(self, request, pk):
        job = SignedFormJob.objects.filter(pk=pk).first()
        if job is None:
            return JsonResponse({"error": "Ese lote ya no existe."},
                                status=404)
        if not agents.cancel_job(job, request.user.company_user):
            return JsonResponse({"error": "Ese lote ya ha terminado."},
                                status=400)
        logger.info("# [FIRMAS] Lote %s cancelado por %s.", job.pk,
                    request.user.username)
        return JsonResponse({"ok": True})


class AgentPendingView(AgentApiMixin, View):
    """
    POST: next documents to sign.
    ---
    POST: los siguientes documentos a firmar (id, nombre, certificado y
    URL para bajarlos). Cuenta también como latido.
    """

    def post(self, request):
        agents.record_heartbeat(
            self.agent, request.POST.get("host", self.agent.host), None,
            request.POST.get("autofirma", self.agent.autofirma_version),
            request.POST.get("error", ""))
        files = agents.take_pending(self.agent)
        return JsonResponse({"files": [{
            "id": item.pk,
            "name": item.name,
            "alias": item.job.certificate_alias,
            "thumbprint": item.job.certificate_thumbprint,
            # S153: el agente v4 (firma nativa, con huella) lee la
            # configuración por líneas; AutoFirma la quiere con "\\n".
            "config": (item.signature_config.replace("\\n", "\n")
                       if item.job.certificate_thumbprint
                       else item.signature_config),
            "all_pages": item.job.all_pages,
            "download": reverse("panel:signing_agent_file",
                                args=[item.pk]),
            "result": reverse("panel:signing_agent_result",
                              args=[item.pk]),
        } for item in files]})


class AgentFileView(AgentApiMixin, View):
    """
    GET: the generated PDF of a document being signed.
    ---
    GET: el PDF generado de un documento que se está firmando.
    """

    def get(self, request, pk):
        item = SignedFormFile.objects.filter(
            pk=pk, status=SignedFormFile.STATUS_SIGNING).first()
        if item is None:
            return HttpResponse(status=404)
        return HttpResponse(agents.unsigned_pdf(item),
                            content_type="application/pdf")


@method_decorator(csrf_exempt, name="dispatch")
class AgentResultView(AgentApiMixin, View):
    """
    POST: the signed PDF (file "signed") or the error ("error").
    ---
    POST: el PDF firmado (archivo "signed") o el error ("error").
    """

    def post(self, request, pk):
        item = SignedFormFile.objects.select_related("job").filter(
            pk=pk, status=SignedFormFile.STATUS_SIGNING).first()
        if item is None:
            # S153: también si el lote se canceló mientras se firmaba.
            return JsonResponse({"error": "no está pendiente"}, status=404)
        upload = request.FILES.get("signed")
        if upload is not None:
            agents.finish_file(item, signed=upload.read())
        else:
            agents.finish_file(item, error=request.POST.get("error", ""))
        logger.info("# [FIRMAS] Agente %s: documento %s -> %s.",
                    self.agent.pk, item.pk, item.status)
        return JsonResponse({"ok": True, "status": item.status})
