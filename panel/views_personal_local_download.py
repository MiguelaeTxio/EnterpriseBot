# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/views_personal_local_download.py
"""
H24 (S144). State of the local download that closes a worker's
onboarding.

---

H24 (S144). Estado de la descarga a la carpeta local con la que
termina el alta de un trabajador (Miguel Ángel: "cuando esté
finalizada, termina el pipeline"). La pantalla de alta la consulta cada
pocos segundos; la descarga la hace el agente H28
(`document_explorer.local_download_service`).
"""
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views import View

from document_explorer.local_download_service import status_payload
from document_explorer.models import LocalDownloadJob
from panel.mixins import DocsUploadAccessMixin


class PersonalLocalDownloadStatusView(DocsUploadAccessMixin, View):
    """
    JSON state of one local download.

    ---

    Estado (JSON) de una descarga a la carpeta local.
    """

    def get(self, request, pk):
        job = get_object_or_404(LocalDownloadJob, pk=pk)
        return JsonResponse(status_payload(job))
