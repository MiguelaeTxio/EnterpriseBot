# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/analytics/views_accounting.py
"""
Accounting entry CSV merge in Costes de operarios.

---

Unión de CSV de asientos contables en Costes de operarios (S133). La
pantalla pide una carpeta, lista sus CSV por orden alfabético, el
usuario los reordena arrastrándolos y al pulsar "Generar" se suben en
ese orden; esta vista los une y devuelve el CSV para descargar.
"""
import logging

from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.views.generic import View

from analytics.accounting_csv import MergeError, merge
from panel.mixins import SupervisorAccessMixin

logger = logging.getLogger(__name__)

MAX_FILES = 200
MAX_FILE_BYTES = 20 * 1024 * 1024


class AccountingCsvMergeView(SupervisorAccessMixin, View):
    """
    Merge the uploaded CSV files, in the order sent, and return it.

    ---

    Une los CSV en el orden en que llegan (el que ha dejado el usuario
    en la lista) y devuelve el CSV unido, con el número de filas y de
    asientos en las cabeceras X-Rows y X-Entries. Si algo falla, JSON
    con el motivo (400).
    """

    def post(self, request):
        """
        Merge and return the file.

        ---

        Une y devuelve el fichero.
        """
        uploads = request.FILES.getlist("files")
        if not uploads:
            return JsonResponse(
                {"error": "No hay ficheros CSV que unir."}, status=400,
            )
        if len(uploads) > MAX_FILES:
            return JsonResponse(
                {"error": "Como máximo %d ficheros a la vez." % MAX_FILES},
                status=400,
            )
        files = []
        for upload in uploads:
            if upload.size > MAX_FILE_BYTES:
                return JsonResponse(
                    {"error": "%s es demasiado grande." % upload.name},
                    status=400,
                )
            files.append((upload.name, upload.read()))
        try:
            data, rows, entries = merge(files)
        except MergeError as exc:
            return JsonResponse({"error": str(exc)}, status=400)
        logger.info(
            "# [CSV ASIENTOS] %s une %d ficheros: %d filas, %d asientos.",
            request.user.username, len(files), rows, entries,
        )
        name = "ASIENTOS-UNIDOS-%s.csv" % (
            timezone.localtime().strftime("%Y%m%d-%H%M")
        )
        response = HttpResponse(data, content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="%s"' % name
        response["X-Rows"] = str(rows)
        response["X-Entries"] = str(entries)
        response["X-Filename"] = name
        return response
