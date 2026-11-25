# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/new_ui/views_cae.py
"""
Empresa › Coordinación › Correos CAE in the new interface (S156).

Own views and templates of the new interface (Miguel Ángel: the new
and the old interface never share routines, so either can be removed
alone). They only use the CAE domain services (cae_mail.models,
cae_mail.resolution, cae_mail.tasks), the same way the new interface
uses document_explorer services.

---

Empresa › Coordinación › Correos CAE en la nueva interfaz (S156).
Vistas y plantillas propias: la nueva y la antigua no comparten rutinas
(Miguel Ángel: "que no estén mezcladas nueva y vieja para poder
eliminar la vieja cuando proceda"). Solo usan los servicios de dominio
de la CAE (modelos, resolution, tarea de lectura).
"""
import datetime
import io
import zipfile
from urllib.parse import quote

from django.contrib.contenttypes.models import ContentType

from django.db import transaction
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views import View

from cae_mail.models import CaeDemand, CaeMail
from cae_mail.resolution import (
    FOUND, STATUS_LABELS, holder_of, resolve_mail,
)
from document_explorer.confidential import can_open, open_bytes
from document_explorer.models import (
    CompanyFiscalProfile, DocumentIndexEntry, DocumentTypeCatalog,
    PersonIdentity,
)
from fleet.models import MachineAsset
from new_ui.mixins import SuperuserRequiredMixin

_ATTEND = "attend"
_REOPEN = "reopen"
_REREAD = "reread"


def _ok(message, **extra):
    return JsonResponse({"ok": True, "message": message, **extra})


def _error(message, status=400):
    return JsonResponse({"ok": False, "message": message}, status=status)


def _ids(request, name="selected"):
    return [v for v in request.POST.getlist(name) if v.isdigit()]


class CaeSheetView(SuperuserRequiredMixin, View):
    """
    GET: what one notice asks for and what we have (viewer).
    ---
    GET: en el visor, qué pide un aviso y qué tenemos de cada cosa,
    con lo que tenemos marcado para descargar.
    """

    def get(self, request, pk):
        mail = get_object_or_404(CaeMail, pk=pk)
        rows, counts = resolve_mail(mail)
        for row in rows:
            row["holder_kind"] = _holder_kind(row["demand"])
        pending = [row for row in rows if row["status"] != FOUND]
        return render(request, "new_ui/_cae_sheet.html", {
            "mail": mail,
            "rows": rows,
            "pending": pending,
            **(_fix_choices() if pending else {}),
            "counts": [
                (key, STATUS_LABELS[key], counts[key])
                for key in STATUS_LABELS if counts[key]
            ],
            "downloadable": sum(1 for row in rows if row["entry"]),
        })


class CaeBulkView(SuperuserRequiredMixin, View):
    """
    POST selected + action: attend, reopen or read again the notices.
    ---
    POST con los avisos marcados (o el del visor) y la acción: darlos
    por atendidos, reabrirlos o volver a leerlos con Gemini.
    """

    def post(self, request):
        from cae_mail.tasks import process_cae_mail_task

        action = request.POST.get("action", "")
        mails = CaeMail.objects.filter(pk__in=_ids(request))
        if not mails.exists():
            return _error("Marca primero los avisos.")
        if action == _ATTEND:
            done = mails.filter(attended_at__isnull=True).update(
                attended_at=timezone.now(), attended_by=request.user)
            return _ok("%d aviso(s) dados por atendidos." % done)
        if action == _REOPEN:
            done = mails.filter(attended_at__isnull=False).update(
                attended_at=None, attended_by=None)
            return _ok("%d aviso(s) reabiertos." % done)
        if action == _REREAD:
            pks = list(mails.values_list("pk", flat=True))
            mails.update(status=CaeMail.STATUS_PENDING, processed_at=None)
            for pk in pks:
                transaction.on_commit(
                    lambda pk=pk: process_cae_mail_task.delay(pk))
            return _ok("%d aviso(s) volviéndose a leer; en un minuto "
                       "están listos." % len(pks))
        return _error("Acción desconocida.")


def _found_entries(mails):
    """Documents we have and still valid for the notices.
    ---
    Los documentos que tenemos y valen (ni caducados ni el mismo que
    caduca en la fecha del aviso) de lo que piden los avisos, sin
    repetir.
    """
    seen = {}
    for mail in mails:
        rows, _counts = resolve_mail(mail)
        for row in rows:
            if row["status"] == FOUND:
                seen[row["entry"].pk] = row["entry"]
    return list(seen.values())


class CaeDownloadView(SuperuserRequiredMixin, View):
    """
    POST: download what we have (one file as is, several in a ZIP).
    ---
    POST: descarga lo que tenemos: los documentos marcados en el visor
    (`entries`) o, desde Acciones, todo lo que tenemos de lo que piden
    los avisos marcados (`selected`). Uno tal cual; varios, en un ZIP.
    """

    def post(self, request):
        company_user = request.user.company_user
        entry_ids = _ids(request, "entries")
        if entry_ids:
            entries = list(DocumentIndexEntry.objects.filter(
                pk__in=entry_ids, entry_kind=DocumentIndexEntry.KIND_FILE,
                deleted_at__isnull=True, purged_at__isnull=True,
            ))
        else:
            entries = _found_entries(
                CaeMail.objects.filter(pk__in=_ids(request)))
        entries = [e for e in entries if can_open(e, company_user)]
        if not entries:
            return _error("No hay nada nuestro que descargar de lo marcado.")
        if len(entries) == 1:
            entry = entries[0]
            data, name = open_bytes(entry, company_user), entry.name
            content_type = "application/octet-stream"
        else:
            buffer = io.BytesIO()
            used = {}
            with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
                for entry in sorted(entries, key=lambda e: e.name):
                    name = entry.name
                    count = used.get(name.lower(), 0) + 1
                    used[name.lower()] = count
                    if count > 1:
                        stem, dot, ext = name.rpartition(".")
                        name = ("%s (%d).%s" % (stem, count, ext) if dot
                                else "%s (%d)" % (name, count))
                    zf.writestr(name, open_bytes(entry, company_user))
            data = buffer.getvalue()
            name = "Documentación CAE %s.zip" % timezone.localdate(
            ).strftime("%Y-%m-%d")
            content_type = "application/zip"
        response = HttpResponse(data, content_type=content_type)
        ascii_name = name.encode("ascii", "replace").decode().replace(
            "?", "_")
        response["Content-Disposition"] = (
            "attachment; filename=\"%s\"; filename*=UTF-8''%s"
            % (ascii_name, quote(name)))
        return response


# ------------------------------------------------ resolver lo que falta
# S156. Miguel Ángel: "es necesario poder resolverlo todo desde la App".
# Cada documento pedido que no tenemos (o caducado, o falta el nuevo)
# se resuelve desde su aviso: subirlo a la ficha de su titular, pedirlo
# al trabajador por WhatsApp o, si la lectura no supo de qué tipo es o
# de quién, elegirlo a mano.

_KIND_PERSON = "person"
_KIND_MACHINE = "machine"
_KIND_COMPANY = "company"
_SUBJECT_OF_KIND = {
    _KIND_PERSON: CaeDemand.SUBJECT_WORKER,
    _KIND_MACHINE: CaeDemand.SUBJECT_MACHINE,
    _KIND_COMPANY: CaeDemand.SUBJECT_COMPANY,
}


def _holder_kind(demand):
    if demand.subject_type == demand.SUBJECT_WORKER:
        return _KIND_PERSON
    if demand.subject_type == demand.SUBJECT_MACHINE:
        return _KIND_MACHINE
    return _KIND_COMPANY


def _fix_choices():
    """Types and holders to choose from when fixing a demand.
    ---
    Tipos (por ámbito) y titulares (empresas del grupo, trabajadores en
    activo y centros de gasto activos) para corregir a mano una línea.
    """
    types = DocumentTypeCatalog.objects.filter(is_active=True).order_by(
        "label")
    domains = dict(DocumentTypeCatalog.DOMAIN_CHOICES)
    groups = {}
    for doc_type in types:
        groups.setdefault(domains.get(doc_type.domain, doc_type.domain),
                          []).append(doc_type)
    return {
        "fix_types": sorted(groups.items()),
        "fix_companies": CompanyFiscalProfile.objects.order_by(
            "legal_name"),
        "fix_people": PersonIdentity.objects.filter(
            is_active_employee=True).order_by(
            "first_surname", "second_surname", "given_name"),
        "fix_machines": MachineAsset.objects.filter(
            is_active=True).order_by("code"),
    }


def _demand(request):
    pk = request.POST.get("demand", "")
    return CaeDemand.objects.select_related(
        "document_type", "company", "person", "machine",
    ).filter(pk=pk).first() if pk.isdigit() else None


class CaeFixView(SuperuserRequiredMixin, View):
    """
    POST demand, document_type_code, holder ("kind:pk"): fix a demand.
    ---
    POST: corrige a mano el tipo de documento y el titular (empresa,
    trabajador o centro de gasto) de una línea del aviso.
    """

    def post(self, request):
        demand = _demand(request)
        if demand is None:
            return _error("Línea no encontrada.")
        code = request.POST.get("document_type_code", "").strip()
        doc_type = DocumentTypeCatalog.objects.filter(
            code=code, is_active=True).first() if code else None
        kind, _sep, pk = request.POST.get("holder", "").partition(":")
        model = {_KIND_PERSON: PersonIdentity, _KIND_MACHINE: MachineAsset,
                 _KIND_COMPANY: CompanyFiscalProfile}.get(kind)
        holder = model.objects.filter(pk=pk).first() if (
            model and pk.isdigit()) else None
        if doc_type is None and holder is None:
            return _error("Elige el tipo, el titular o los dos.")
        fields = []
        if doc_type is not None:
            demand.document_type = doc_type
            fields.append("document_type")
        if holder is not None:
            demand.subject_type = _SUBJECT_OF_KIND[kind]
            demand.person = holder if kind == _KIND_PERSON else None
            demand.machine = holder if kind == _KIND_MACHINE else None
            demand.company = holder if kind == _KIND_COMPANY else None
            fields += ["subject_type", "person", "machine", "company"]
        demand.save(update_fields=fields)
        return _ok("Línea corregida.")


class CaeAskView(SuperuserRequiredMixin, View):
    """
    POST demand: ask the worker for the document by WhatsApp.
    ---
    POST: pide por WhatsApp al trabajador el documento de la línea
    (solicitudes de trabajadores; cualquier tipo, lo pide la
    plataforma).
    """

    def post(self, request):
        from document_explorer.worker_request_service import create_requests

        demand = _demand(request)
        if demand is None or demand.person is None or (
                demand.document_type is None):
            return _error("La línea necesita trabajador y tipo.")
        summary = create_requests(
            [(demand.person.pk, demand.document_type.pk)],
            request.user.company_user, any_type=True)
        if summary["sent"]:
            message = "Pedido por WhatsApp."
        elif summary["queued"]:
            message = ("Pedido; queda en cola hasta que entregue lo que "
                       "tiene pendiente.")
        else:
            message = "No se ha pedido."
        details = summary["send_errors"] + summary["skipped"]
        if details:
            message += " " + " ".join(details)
        if not (summary["sent"] or summary["queued"]):
            return _error(message)
        return _ok(message)


class CaeCompanyUploadView(SuperuserRequiredMixin, View):
    """
    POST demand, file, date: upload a group company's document.
    ---
    POST: sube el documento de una empresa del grupo que pide la línea
    (seguro, TC, certificado...) a su carpeta de DOC. EMPRESA, enlazado
    a la empresa. Los de trabajadores y máquinas van por la subida de
    siempre (new_ui:document_upload).
    """

    def post(self, request):
        from document_explorer.subject_upload_service import (
            SubjectUploadError, upload_subject_document,
        )

        demand = _demand(request)
        holder = holder_of(demand) if demand else None
        upload = request.FILES.get("file")
        if not isinstance(holder, CompanyFiscalProfile) or (
                demand.document_type is None):
            return _error("La línea necesita empresa y tipo.")
        if upload is None:
            return _error("Elige el archivo.")
        typed = None
        raw = (request.POST.get("date") or "").strip()
        if raw:
            try:
                typed = datetime.date.fromisoformat(raw)
            except ValueError:
                return _error("La fecha no es válida.")
        doc_type = demand.document_type
        try:
            with transaction.atomic():
                result = upload_subject_document(
                    subject=holder,
                    domain_content_type=ContentType.objects.get_for_model(
                        CompanyFiscalProfile),
                    document_type=doc_type, data=upload.read(),
                    original_filename=upload.name,
                    typed_date=typed if doc_type.tracks_expiry else None,
                    typed_issue_date=(None if doc_type.tracks_expiry
                                      else typed),
                    subject_label=holder.legal_name,
                    uploaded_by=request.user.company_user,
                    filename_date=typed)
        except SubjectUploadError as exc:
            return _error("No se pudo archivar: %s" % exc)
        entry = result["entry"]
        message = "Guardado %s en %s." % (entry.name, entry.parent_path)
        if result.get("superseded_count"):
            message += " Sustituye a %d anterior(es)." % (
                result["superseded_count"])
        return _ok(message)
