# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/new_ui/views_requests.py
"""
Workers' requests (Personal › Solicitudes), new interface.

---

Solicitudes de los trabajadores en la nueva interfaz (S163), copiado de
panel/views_worker_requests.py (la lógica vive en
hr_calendar.worker_requests):
- «Gestionar» de cada fila abre en Acciones su detalle con sus
  acciones: aprobar o denegar las que llevan fechas, entregar un
  documento (subido o de su ficha), denegar un documento, responder una
  reclamación, subir y revisar el justificante y deshacer la resolución.
- Sobre las marcadas: aprobar, denegar (con motivo) o validar el
  justificante.
- Los archivos de cada solicitud (las nóminas confidenciales, solo para
  quien puede verlas).
"""
import logging
import mimetypes
from urllib.parse import quote

from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import render
from django.views import View

from document_explorer.models import DocumentTypeCatalog
from hr_calendar import worker_requests as wr
from hr_calendar.models import WorkerRequest, WorkerRequestFile
from new_ui.mixins import SuperuserRequiredMixin

logger = logging.getLogger(__name__)


def _item(request, pk):
    item = WorkerRequest.objects.select_related(
        "person", "resolved_by__user", "proof_reviewed_by__user",
        "created_by__user",
    ).filter(pk=pk, company=request.user.company_user.company).first()
    if item is None:
        raise Http404
    item.person_label = wr.person_label(item.person)
    item.detail = wr.detail_text(item)
    item.days = wr.day_count(item)
    item.is_pending = item.status == WorkerRequest.Status.PENDING
    item.is_dated = item.kind in wr.DATED_KINDS
    return item


class RequestDetailView(SuperuserRequiredMixin, View):
    """
    GET: one request with its actions (shown in Acciones).

    ---

    GET: una solicitud con sus acciones, para el panel Acciones.
    """

    def get(self, request, pk):
        item = _item(request, pk)
        documents = []
        if item.kind == WorkerRequest.Kind.DOCUMENT:
            documents = list(wr.person_documents(item.person)[:200])
        return render(request, "new_ui/_request_detail.html", {
            "item": item,
            "files": item.files.select_related("uploaded_by__user"),
            "document_label": wr.DOCUMENT_LABELS.get(item.document_code, ""),
            "default_type": wr.DOCUMENT_TYPES.get(item.document_code, ""),
            "delivery_types": DocumentTypeCatalog.objects.filter(
                domain="PERSONAL", is_active=True).order_by("label")
            if item.kind == WorkerRequest.Kind.DOCUMENT else [],
            "person_documents": documents,
        })


class RequestActionView(SuperuserRequiredMixin, View):
    """
    POST `action`: approve, deny, answer, deliver, proof, proof_valid,
    proof_invalid or undo.

    ---

    POST: una acción sobre una solicitud (la de siempre de
    hr_calendar.worker_requests).
    """

    def post(self, request, pk):
        item = _item(request, pk)
        cu = request.user.company_user
        action = request.POST.get("action", "")
        text = request.POST.get("response", "")
        try:
            if action == "approve":
                wr.approve(item, cu, text)
                message = "Aprobada."
            elif action == "deny":
                wr.deny(item, cu, text)
                message = "Denegada."
            elif action == "answer":
                wr.answer(item, cu, text)
                message = "Respuesta guardada."
            elif action == "deliver":
                upload = request.FILES.get("file")
                entry_id = request.POST.get("entry_id", "")
                wr.deliver(
                    item, cu, text,
                    data=upload.read() if upload else None,
                    filename=upload.name if upload else "",
                    type_code=request.POST.get("type_code", ""),
                    entry_id=int(entry_id) if entry_id.isdigit() else None)
                message = "Documento entregado."
            elif action == "proof":
                upload = request.FILES.get("file")
                if upload is None:
                    raise wr.RequestError("Elige el archivo.")
                wr.add_proof(item, upload.read(), upload.name, cu)
                message = "Justificante guardado."
            elif action in ("proof_valid", "proof_invalid"):
                wr.review_proof(item, cu, action == "proof_valid")
                message = "Justificante revisado."
            elif action == "undo":
                wr.undo(item, cu)
                message = "Vuelve a estar pendiente."
            else:
                raise wr.RequestError("Acción desconocida.")
        except wr.RequestError as exc:
            return JsonResponse({"ok": False, "message": str(exc)},
                                status=400)
        except Exception:  # noqa: BLE001 -- se registra y se avisa
            logger.exception("[new_ui solicitudes] acción %s en #%s",
                             action, pk)
            return JsonResponse({"ok": False, "message": "No se ha podido "
                                 "completar la acción."}, status=400)
        return JsonResponse({"ok": True, "message": message})


class RequestMassView(SuperuserRequiredMixin, View):
    """
    POST `action` (approve | deny | proof_valid), `response`: the marked.

    ---

    POST: aprobar, denegar (con motivo) o validar el justificante de las
    marcadas, una a una; las que no se pueden se cuentan con su motivo.
    """

    def post(self, request):
        cu = request.user.company_user
        action = request.POST.get("action", "")
        reason = request.POST.get("response", "")
        ids = [v for v in request.POST.getlist("selected") if v.isdigit()]
        done, failed = 0, []
        for item in WorkerRequest.objects.filter(
                company=cu.company, pk__in=ids).select_related("person"):
            try:
                if action == "approve":
                    wr.approve(item, cu)
                elif action == "deny":
                    wr.deny(item, cu, reason)
                elif action == "proof_valid":
                    wr.review_proof(item, cu, True)
                else:
                    raise wr.RequestError("Acción desconocida.")
                done += 1
            except wr.RequestError as exc:
                failed.append("%s: %s" % (wr.person_label(item.person), exc))
        message = "%d hechas." % done
        if failed:
            message += " No se pudieron %d: %s" % (len(failed),
                                                   "; ".join(failed[:5]))
        return JsonResponse({"ok": bool(done) or not failed,
                             "message": message},
                            status=200 if done or not failed else 400)


class RequestFileView(SuperuserRequiredMixin, View):
    """
    GET: a file of a request (confidential payslips, decrypted only for
    whoever may see them).

    ---

    GET: un archivo de una solicitud; la nómina confidencial, solo para
    quien puede verla.
    """

    def get(self, request, pk):
        from spare_parts.gcs_service import download_bytes

        stored = WorkerRequestFile.objects.select_related(
            "request", "entry").filter(
            pk=pk,
            request__company=request.user.company_user.company).first()
        if stored is None or stored.entry is None:
            raise Http404
        if stored.entry.is_confidential:
            from document_explorer.confidential import file_response

            return file_response(stored.entry, request.user.company_user)
        entry = stored.entry
        data = download_bytes(entry.bucket, entry.blob_name)
        content_type = (entry.content_type
                        or mimetypes.guess_type(entry.name)[0]
                        or "application/octet-stream")
        response = HttpResponse(data, content_type=content_type)
        response["Content-Disposition"] = (
            "inline; filename*=UTF-8''%s" % quote(entry.name))
        return response
