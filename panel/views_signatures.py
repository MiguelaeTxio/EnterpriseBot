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
from django.shortcuts import render
from django.utils import timezone
from django.views import View

from document_explorer import signed_forms_service as forms
from document_explorer.confidential import ConfidentialError
from document_explorer.models import (
    CompanyFiscalProfile,
    CompanySignature,
    PersonIdentity,
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


def _pane_context():
    profiles = list(CompanyFiscalProfile.objects.order_by("legal_name"))
    signatures = list(CompanySignature.objects.select_related(
        "company", "created_by__user"))
    people = PersonIdentity.objects.filter(is_active_employee=True).order_by(
        "first_surname", "second_surname", "given_name").only(
        "pk", "first_surname", "second_surname", "given_name")
    return {
        "profiles": profiles,
        "signatures": signatures,
        "profiles_with_signature": {s.company_id for s in signatures},
        "people": people,
    }


class SignatureTabView(SignatureAccessMixin, View):
    """
    GET: the "Firmas" tab.
    ---
    GET: la pestaña "Firmas" (firmas guardadas y generar documentos).
    """

    def get(self, request):
        return render(request, "panel/signatures/_pane.html",
                      _pane_context())


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
        results, errors, names, notes = [], [], set(), []
        for upload in files:
            if upload.size > MAX_FORM_BYTES:
                errors.append("%s: pasa de 25 MB" % upload.name)
                continue
            try:
                filled = forms.fill_form(upload.read(), values, png)
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
        if errors:
            return JsonResponse({"error": "No se ha generado nada. "
                                          + "; ".join(errors)}, status=400)
        logger.info("# [FIRMAS] %d documento(s) firmados con '%s' (%s) por "
                    "%s.", len(results), signature.label,
                    profile.legal_name, request.user.username)
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
        # Cómo se rellenó cada uno y qué pedía que no se ha puesto.
        response["X-Signed-Notes"] = quote(json.dumps(notes))
        return response
