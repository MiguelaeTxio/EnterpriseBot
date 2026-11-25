# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/new_ui/views_docs.py
"""
Record actions of the new interface (documents, photo, data, QR).

---

Acciones de la ficha en la nueva interfaz (S163): ver y descargar un
documento, foto de la persona o de la máquina, guardar los datos de la
persona, subir documentos, exportar la tarjeta técnica y el QR. Son
COPIAS de las vistas de la interfaz antigua (panel/views_documentation_h30.py,
panel/views_machine_menu.py, panel/views_machine_qr.py), con las mismas
reglas y los mismos servicios de negocio, pero en rutas propias: la
nueva interfaz no llama a la antigua, para poder borrar cualquiera de
las dos sin romper la otra (Miguel Ángel, S163).
"""

from datetime import date, datetime

from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.views import View

from document_explorer.models import (
    DocumentIndexEntry, DocumentTypeCatalog, JobPosition, PersonIdentity,
    PersonIdPhoto,
)
from document_explorer.subject_upload_service import (
    SubjectUploadError, upload_subject_document,
)
from fleet import qr_sheet_service as qr
from fleet.models import MachineAsset, MachineQrMedia
from new_ui.docs_core import _realign_person_document_names
from new_ui.mixins import SuperuserRequiredMixin
from spare_parts.gcs_service import generate_signed_url

IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif")


def _company(request):
    return request.user.company_user.company


def _machine(request, pk):
    return get_object_or_404(MachineAsset, pk=pk, company=_company(request))


class DocumentFileView(SuperuserRequiredMixin, View):
    """
    GET: open a document (?descargar=1: download it with its name).

    ---

    GET: abre un documento (URL firmada del cubo); con ?descargar=1, lo
    descarga con su nombre. Los confidenciales (nóminas) se sirven
    descifrados, nunca por URL del cubo. Copia de DocumentViewView.
    """

    def get(self, request, pk):
        entry = get_object_or_404(DocumentIndexEntry, pk=pk,
                                  deleted_at__isnull=True)
        download = request.GET.get("descargar") == "1"
        if entry.is_confidential:
            from document_explorer.confidential import file_response

            return file_response(entry, request.user.company_user,
                                 attachment=download)
        url = generate_signed_url(
            entry.bucket, entry.blob_name,
            download_name=(entry.name or "documento") if download else "")
        return redirect(url)


class PersonPhotoView(SuperuserRequiredMixin, View):
    """
    GET: the person's ID photo crop (JPEG). Copy of PersonalPhotoView.

    ---

    GET: la foto de carné recortada de la persona (JPEG).
    """

    def get(self, request, pk):
        id_photo = get_object_or_404(PersonIdPhoto, person_id=pk)
        response = HttpResponse(bytes(id_photo.image),
                                content_type="image/jpeg")
        response["Cache-Control"] = "private, max-age=86400"
        return response


class PersonPhotoUploadView(SuperuserRequiredMixin, View):
    """
    POST: upload the profile photo straight to the person record.

    ---

    POST: sube la foto de perfil directamente a la ficha (sin leerla ni
    archivarla como documento). Copia de PersonalPhotoUploadView.
    """

    MAX_BYTES = 20 * 1024 * 1024

    def post(self, request, pk):
        from document_explorer.id_photo_service import (
            IdPhotoError, save_uploaded,
        )

        person = get_object_or_404(PersonIdentity, pk=pk)
        upload = request.FILES.get("file")
        if upload is None:
            return JsonResponse({"ok": False, "error": "Falta la foto."},
                                status=400)
        if upload.size > self.MAX_BYTES:
            return JsonResponse({"ok": False,
                                 "error": "La foto pesa más de 20 MB."},
                                status=400)
        try:
            save_uploaded(person, upload.read())
        except IdPhotoError as exc:
            return JsonResponse({"ok": False, "error": str(exc)}, status=400)
        return JsonResponse({"ok": True})


class PersonUpdateView(SuperuserRequiredMixin, View):
    """
    POST: save the editable data of a person. Copy of PersonalUpdateView.

    ---

    POST: guarda los datos editables de la persona (datos personales,
    contacto, dirección, alta/baja, nº de la S.S., categoría,
    observaciones y requisitos de documentación). DNI, empresa y
    caducidades vienen del Excel de personal y no se tocan aquí. Si
    cambia el nombre, se renombran sus documentos.
    """

    TEXT_EDITABLE_FIELDS = (
        "given_name", "first_surname", "second_surname", "phone",
        "phone_secondary", "email", "address_street", "postal_code",
        "city", "province", "ss_affiliation_number",
        "professional_category", "nickname",
        "emergency_contact", "phone_emergency", "notes",
    )
    DATE_EDITABLE_FIELDS = ("hire_date", "termination_date")
    EDITABLE_FIELDS = TEXT_EDITABLE_FIELDS + DATE_EDITABLE_FIELDS
    NAME_FIELDS = ("given_name", "first_surname", "second_surname")

    def post(self, request, pk):
        person = get_object_or_404(PersonIdentity, pk=pk)
        old_names = tuple(getattr(person, f) for f in self.NAME_FIELDS)
        updated_fields = []
        for field in self.TEXT_EDITABLE_FIELDS:
            if field in request.POST:
                setattr(person, field, request.POST.get(field, "").strip())
                updated_fields.append(field)
        for field in self.DATE_EDITABLE_FIELDS:
            if field in request.POST:
                raw_value = request.POST.get(field, "").strip()
                if raw_value:
                    try:
                        year, month, day = (int(x)
                                            for x in raw_value.split("-"))
                        setattr(person, field, date(year, month, day))
                    except ValueError:
                        return JsonResponse({
                            "ok": False,
                            "error": "Fecha con formato inválido en %s."
                            % field}, status=400)
                else:
                    setattr(person, field, None)
                updated_fields.append(field)
        requirements = None
        if "document_requirements_sent" in request.POST:
            wanted = {int(v) for v in
                      request.POST.getlist("document_requirements")
                      if v.isdigit()}
            requirements = list(JobPosition.objects.filter(pk__in=wanted))
            if len(requirements) != len(wanted):
                return JsonResponse({"ok": False,
                                     "error": "Algún requisito ya no existe."},
                                    status=400)
        if not updated_fields and requirements is None:
            return JsonResponse({"ok": False,
                                 "error": "Sin campos que actualizar."},
                                status=400)
        try:
            person.full_clean(validate_unique=False)
        except ValidationError as exc:
            return JsonResponse({"ok": False,
                                 "error": "; ".join(exc.messages)},
                                status=400)
        with transaction.atomic():
            if updated_fields:
                person.save(update_fields=updated_fields)
            if requirements is not None:
                person.document_requirements.set(requirements)
        renamed = 0
        if tuple(getattr(person, f) for f in self.NAME_FIELDS) != old_names:
            renamed = _realign_person_document_names(person)
        return JsonResponse({"ok": True, "renamed_documents": renamed})


class SubjectUploadView(SuperuserRequiredMixin, View):
    """
    POST: upload one or several documents of a person or machine.

    ---

    POST: sube uno o varios documentos de una persona o máquina (tipo,
    caducidad o fecha del documento), con la comprobación del contenido
    y la sustitución del anterior (upload_subject_document). Copia de
    SubjectDocumentUploadView.
    """

    def post(self, request, domain, subject_pk):
        document_type_code = request.POST.get("document_type_code", "")
        expiry_date_str = request.POST.get("expiry_date", "")
        issue_date_str = request.POST.get("issue_date", "")
        uploaded_files = request.FILES.getlist("file")
        if not uploaded_files or not document_type_code:
            return JsonResponse(
                {"error": "Falta el archivo o el tipo documental."},
                status=400)
        document_type = get_object_or_404(
            DocumentTypeCatalog, code=document_type_code, is_active=True)
        typed_date = None
        if expiry_date_str:
            try:
                typed_date = datetime.strptime(expiry_date_str,
                                               "%Y-%m-%d").date()
            except ValueError:
                return JsonResponse({"error": "Fecha con formato inválido."},
                                    status=400)
        typed_issue_date = None
        if issue_date_str and not document_type.tracks_expiry:
            try:
                typed_issue_date = datetime.strptime(issue_date_str,
                                                     "%Y-%m-%d").date()
            except ValueError:
                return JsonResponse({"error": "Fecha con formato inválido."},
                                    status=400)
        if domain == "machine":
            subject = _machine(request, subject_pk)
            ct = ContentType.objects.get_for_model(MachineAsset)
            subject_label = "%s -- %s" % (subject.code, subject.brand_model)
        elif domain == "personal":
            subject = get_object_or_404(PersonIdentity, pk=subject_pk)
            ct = ContentType.objects.get_for_model(PersonIdentity)
            subject_label = "%s %s, %s" % (
                subject.first_surname, subject.second_surname,
                subject.given_name)
        else:
            raise Http404
        results, errors = [], []
        for uploaded_file in uploaded_files:
            try:
                result = upload_subject_document(
                    subject=subject, domain_content_type=ct,
                    document_type=document_type, data=uploaded_file.read(),
                    original_filename=uploaded_file.name,
                    typed_date=typed_date, subject_label=subject_label,
                    typed_issue_date=typed_issue_date, check_content=True,
                )
            except SubjectUploadError as exc:
                errors.append({"file": uploaded_file.name,
                               "error": str(exc)})
                continue
            stored = result["entry"]
            stored_date = stored.expiry_date or stored.issue_date
            item = {
                "entry_id": stored.pk,
                "entry_name": stored.name,
                "superseded_count": result["superseded_count"],
                "date_label": (stored_date.strftime("%d/%m/%Y")
                               if stored_date else ""),
                "date_kind": ("caducidad" if stored.expiry_date
                              else "documento"),
                "needs_date": bool(document_type.tracks_expiry
                                   or document_type.is_cumulative),
            }
            check = result.get("check") or {}
            if check.get("type_mismatch"):
                item["type_mismatch"] = check["type_mismatch"]
            if check.get("filled"):
                item["filled"] = check["filled"]
            if check.get("different"):
                item["different"] = {
                    label: {"current": pair[0], "read": pair[1]}
                    for label, pair in check["different"].items()}
            if result["warning"]:
                item["warning"] = {
                    "system_date": result["warning"][
                        "system_date"].isoformat(),
                    "typed_date": result["warning"]["typed_date"].isoformat(),
                    "source": result["warning"]["source"],
                }
            results.append(item)
        return JsonResponse({"ok": not errors, "uploaded": results,
                             "errors": errors})


class MachineSetAvatarView(SuperuserRequiredMixin, View):
    """
    POST entry_id: one of the machine's image documents as its photo.

    ---

    POST: fija como foto de la máquina uno de sus documentos-imagen.
    Copia de MachineSetAvatarView.
    """

    def post(self, request, pk):
        machine = _machine(request, pk)
        entry_id = request.POST.get("entry_id", "").strip()
        if not entry_id:
            return JsonResponse({"ok": False, "error": "Falta entry_id."},
                                status=400)
        entry = get_object_or_404(
            DocumentIndexEntry, pk=entry_id,
            domain_content_type=ContentType.objects.get_for_model(
                MachineAsset),
            domain_object_id=machine.pk,
            deleted_at__isnull=True, purged_at__isnull=True,
        )
        if not entry.name.lower().endswith(IMAGE_EXTENSIONS):
            return JsonResponse({"ok": False,
                                 "error": "Ese documento no es una imagen."},
                                status=400)
        machine.avatar_document = entry
        machine.save(update_fields=["avatar_document"])
        return JsonResponse({"ok": True})


class MachineCardExportView(SuperuserRequiredMixin, View):
    """
    GET ?fmt=pdf|docx|html|png|jpg: the technical card as a download.

    ---

    GET: la tarjeta técnica como descarga (new_ui/machine_card.py).
    """

    def get(self, request, pk):
        from new_ui.machine_card import (
            FORMATS, card_export_response, card_sections, machine_title,
        )

        machine = _machine(request, pk)
        fmt = (request.GET.get("fmt") or "pdf").lower()
        if fmt not in FORMATS:
            raise Http404
        return card_export_response(machine, machine_title(machine),
                                    card_sections(machine), fmt)


class MachineQrImageView(SuperuserRequiredMixin, View):
    """
    GET: the machine's QR as PNG to print. Copy of MachineQrImageView.

    ---

    GET: el QR del centro de gasto en PNG, para imprimirlo.
    """

    def get(self, request, pk):
        machine = _machine(request, pk)
        sheet = qr.sheet_for(machine)
        # S163 (25/11): la pegatina lleva debajo el código del vehículo.
        data = qr.sticker_png(qr.public_url(request, sheet), machine.code)
        response = HttpResponse(data, content_type="image/png")
        response["Content-Disposition"] = (
            'attachment; filename="QR_%s.png"' % machine.code)
        return response


class MachineQrPrintView(SuperuserRequiredMixin, View):
    """
    GET: a page to print the machine's QR sticker (QR + its code).

    ---

    S163 (25/11): la pegatina para imprimir: el QR y debajo el código
    del vehículo; se abre el cuadro de imprimir solo.
    """

    def get(self, request, pk):
        from django.shortcuts import render

        machine = _machine(request, pk)
        sheet = qr.sheet_for(machine)
        return render(request, "new_ui/qr_print.html", {
            "code": machine.code,
            "qr_svg": qr.qr_image(qr.public_url(request, sheet), "svg",
                                  scale=10),
        })


class MachineQrActionView(SuperuserRequiredMixin, View):
    """
    POST action=notes|upload|caption|delete|editor_password (JSON).

    ---

    POST: lo que se edita de la página del QR desde la pestaña QR
    (observaciones, fotos y vídeos, su descripción, quitarlos y la
    contraseña del editor QR del fichaje). Copia de las acciones de
    MachineQrSheetView, con respuesta JSON.
    """

    def post(self, request, pk):
        machine = _machine(request, pk)
        sheet = qr.sheet_for(machine)
        company_user = request.user.company_user
        action = request.POST.get("action", "")
        if action == "notes":
            sheet.observations = request.POST.get("observations", "").strip()
            sheet.updated_by = company_user
            sheet.save(update_fields=["observations", "updated_by",
                                      "updated_at"])
            return JsonResponse({"ok": True,
                                 "message": "Observaciones guardadas."})
        if action == "upload":
            files = request.FILES.getlist("files")
            if not files:
                return JsonResponse({"ok": False, "message": (
                    "Elige al menos una foto o vídeo.")}, status=400)
            added, errors = 0, []
            for upload in files:
                try:
                    qr.add_media(sheet, upload,
                                 request.POST.get("caption", ""),
                                 company_user)
                    added += 1
                except qr.QrSheetError as exc:
                    errors.append(str(exc))
            if added:
                sheet.updated_by = company_user
                sheet.save(update_fields=["updated_by", "updated_at"])
            message = "Subidos: %d." % added
            if errors:
                message += " " + " ".join(errors)
            return JsonResponse({"ok": not errors, "message": message},
                                status=200 if added else 400)
        if action in ("caption", "delete"):
            media = get_object_or_404(MachineQrMedia, sheet=sheet,
                                      pk=request.POST.get("media_id") or 0)
            if action == "caption":
                media.caption = request.POST.get("caption", "").strip()[:300]
                media.save(update_fields=["caption"])
                return JsonResponse({"ok": True,
                                     "message": "Descripción guardada."})
            qr.delete_media(media)
            return JsonResponse({"ok": True, "message": "Quitado."})
        if action == "editor_password":
            try:
                qr.set_editor_password(machine.company,
                                       request.POST.get("password", ""),
                                       company_user)
            except qr.QrSheetError as exc:
                return JsonResponse({"ok": False, "message": str(exc)},
                                    status=400)
            return JsonResponse({"ok": True, "message": (
                "Contraseña del editor QR del fichaje guardada.")})
        return JsonResponse({"ok": False, "message": "Acción desconocida."},
                            status=400)
