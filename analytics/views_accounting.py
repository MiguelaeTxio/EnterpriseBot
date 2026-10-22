# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/analytics/views_accounting.py
"""
Accounting entry CSV merge in Costes de operarios.

---

Unión de CSV de asientos contables en Costes de operarios (S133): se
suben los ficheros y se descarga el CSV unido.
"""
import logging

from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import redirect
from django.utils import timezone
from django.views.generic import View

from analytics.accounting_csv import MergeError, merge
from panel.mixins import SupervisorAccessMixin

logger = logging.getLogger(__name__)

MAX_FILES = 50
MAX_FILE_BYTES = 20 * 1024 * 1024


class AccountingCsvMergeView(SupervisorAccessMixin, View):
    """
    Merge the uploaded CSV files and download the result.

    ---

    Une los CSV subidos (en orden alfabético de nombre, el que se ve en
    la pantalla antes de unir) y devuelve el CSV unido para descargar.
    Si algo falla, vuelve a Costes de operarios con el motivo.
    """

    def post(self, request):
        """
        Merge and download.

        ---

        Une y descarga.
        """
        uploads = sorted(
            request.FILES.getlist("files"), key=lambda f: f.name.lower(),
        )
        if not uploads:
            messages.error(request, "Elige los ficheros CSV que quieres unir.")
            return redirect("analytics:analytics_costs")
        if len(uploads) > MAX_FILES:
            messages.error(
                request, "Como máximo %d ficheros a la vez." % MAX_FILES,
            )
            return redirect("analytics:analytics_costs")
        files = []
        for upload in uploads:
            if upload.size > MAX_FILE_BYTES:
                messages.error(
                    request, "%s es demasiado grande." % upload.name,
                )
                return redirect("analytics:analytics_costs")
            files.append((upload.name, upload.read()))
        try:
            data, rows, entries = merge(files)
        except MergeError as exc:
            messages.error(request, str(exc))
            return redirect("analytics:analytics_costs")
        logger.info(
            "# [CSV ASIENTOS] %s une %d ficheros: %d filas, %d asientos.",
            request.user.username, len(files), rows, entries,
        )
        response = HttpResponse(data, content_type="text/csv")
        response["Content-Disposition"] = (
            'attachment; filename="ASIENTOS-UNIDOS-%s.csv"'
            % timezone.localtime().strftime("%Y%m%d-%H%M")
        )
        return response
