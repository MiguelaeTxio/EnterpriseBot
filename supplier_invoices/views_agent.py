# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/supplier_invoices/views_agent.py
"""
Webhooks of the H28 agent for the local FACTURACIÓN folder.

---

H28 (S151, sesión invasora). Webhooks del agente H28 para la carpeta
local FACTURACIÓN de OneDrive (ver local_sync_service). Mismo token
que el latido y el resto de webhooks del agente.
"""
import json
import urllib.parse

from django.http import (
    HttpResponse, HttpResponseForbidden, JsonResponse,
)
from django.shortcuts import get_object_or_404
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from document_explorer.subject_upload_service import BUCKET
from document_explorer.views import _agent_token_ok
from spare_parts.gcs_service import download_bytes

from .invoice_service import InvoiceUploadError, register_upload
from .local_sync_service import mark_local, sync_plan
from .models import SupplierInvoice

MAX_UPLOAD_BYTES = 50 * 1024 * 1024


@method_decorator(csrf_exempt, name="dispatch")
class AgentInvoiceSyncView(View):
    """
    POST: the agent sends what it has locally, gets what to do.

    ---

    POST (JSON `{"local": [{"sha256", "folder"}]}`): lo que hay en la
    carpeta local; responde qué subir, qué pasar a procesadas y qué
    bajar.
    """

    def post(self, request):
        if not _agent_token_ok(request):
            return HttpResponseForbidden("Token inválido.")
        try:
            payload = json.loads(request.body.decode("utf-8") or "{}")
        except (ValueError, UnicodeDecodeError):
            return JsonResponse(
                {"ok": False, "error": "JSON no válido."}, status=400,
            )
        local_items = payload.get("local") or []
        if not isinstance(local_items, list):
            local_items = []
        return JsonResponse(dict(
            sync_plan([i for i in local_items if isinstance(i, dict)]),
            ok=True,
        ))


@method_decorator(csrf_exempt, name="dispatch")
class AgentInvoiceUploadView(View):
    """
    POST: one invoice from the local "FACTURAS NUEVAS" folder.

    ---

    POST: una factura de la carpeta local "FACTURAS NUEVAS". El cuerpo
    es el archivo tal cual; el nombre va en la cabecera `X-File-Name`
    (codificado como URL).
    """

    def post(self, request):
        if not _agent_token_ok(request):
            return HttpResponseForbidden("Token inválido.")
        name = urllib.parse.unquote(
            request.headers.get("X-File-Name", ""),
        ).replace("\\", "/").rsplit("/", 1)[-1].strip()
        data = request.body
        if not name or not data:
            return JsonResponse(
                {"ok": False, "error": "Falta el archivo o su nombre."},
                status=400,
            )
        if len(data) > MAX_UPLOAD_BYTES:
            return JsonResponse(
                {"ok": False, "error": "%s: archivo demasiado grande."
                 % name},
                status=400,
            )
        try:
            invoice, created, note = register_upload(
                name, data, None, from_local=True,
            )
        except InvoiceUploadError as exc:
            return JsonResponse({"ok": False, "error": str(exc)}, status=400)
        return JsonResponse({
            "ok": True, "created": created, "note": note,
            "sha256": invoice.sha256, "status": invoice.status,
        })


class AgentInvoiceFileView(View):
    """
    GET: the file of one invoice, for the agent to download.

    ---

    GET: el archivo de una factura, para que el agente lo baje a la
    carpeta local.
    """

    def get(self, request, pk):
        if not _agent_token_ok(request):
            return HttpResponseForbidden("Token inválido.")
        invoice = get_object_or_404(
            SupplierInvoice.objects.select_related("entry"),
            pk=pk, entry__isnull=False,
        )
        data = download_bytes(BUCKET, invoice.entry.blob_name)
        response = HttpResponse(
            data,
            content_type=invoice.content_type or "application/octet-stream",
        )
        response["Content-Length"] = str(len(data))
        return response


@method_decorator(csrf_exempt, name="dispatch")
class AgentInvoiceLocalView(View):
    """
    POST: the agent reports an invoice already in the local folder.

    ---

    POST: el agente avisa de que la factura ya está en la carpeta
    local.
    """

    def post(self, request, pk):
        if not _agent_token_ok(request):
            return HttpResponseForbidden("Token inválido.")
        invoice = get_object_or_404(SupplierInvoice, pk=pk)
        mark_local(invoice)
        return JsonResponse({"ok": True})
