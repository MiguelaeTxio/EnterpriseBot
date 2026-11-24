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
import io
import zipfile
from urllib.parse import quote

from django.db import transaction
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views import View

from cae_mail.models import CaeMail
from cae_mail.resolution import STATUS_LABELS, resolve_mail
from document_explorer.confidential import can_open, open_bytes
from document_explorer.models import DocumentIndexEntry
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
        return render(request, "new_ui/_cae_sheet.html", {
            "mail": mail,
            "rows": rows,
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
    """Documents we have (current or expired) for the notices.
    ---
    Los documentos que tenemos (vigentes o caducados) de lo que piden
    los avisos, sin repetir.
    """
    seen = {}
    for mail in mails:
        rows, _counts = resolve_mail(mail)
        for row in rows:
            if row["entry"] is not None:
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
