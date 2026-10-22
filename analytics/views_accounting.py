# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/analytics/views_accounting.py
"""
Accounting tools page: accounting entry CSV merge.

---

Herramientas de contabilidad (S133, entrada propia de la barra
lateral): unión de CSV de asientos contables. La pantalla pide una
carpeta, lista sus CSV por orden alfabético, el
usuario los reordena arrastrándolos y al pulsar "Generar" se suben en
ese orden; esta vista los une y devuelve el CSV para descargar.
"""
import logging

from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.views.generic import View

from analytics.accounting_csv import MergeError, merge, merge_invoices
from panel.mixins import SupervisorAccessMixin

logger = logging.getLogger(__name__)

MAX_FILES = 200
# Tools: kind in the URL -> (merge function, output name, unit label).
# Herramientas: tipo en la URL -> (unión, nombre de salida, unidad).
TOOLS = {
    "asientos": (merge, "ASIENTOS-UNIDOS", "asientos"),
    "facturas": (merge_invoices, "FACTURAS-UNIDAS", "facturas"),
}
MAX_FILE_BYTES = 20 * 1024 * 1024


class AccountingToolsView(SupervisorAccessMixin, View):
    """
    Accounting tools page.

    ---

    Página de Herramientas de contabilidad. Pasa company_user y
    active_nav para la barra lateral, como el resto de páginas.
    """

    def get(self, request):
        """
        Render the page.

        ---

        Pinta la página.
        """
        from analytics.views import _get_own_presence

        company_user = request.user.company_user
        tools = [
            {
                "title": "Unir asientos contables (CSV)",
                "icon": "bi-filetype-csv",
                "unit": "asientos",
                "url": reverse(
                    "analytics:accounting_csv_merge", args=["asientos"],
                ),
                "help": (
                    "se ponen uno detrás de otro, la columna B se numera "
                    "seguida (todas las líneas de un asiento con el mismo "
                    "número) y la columna K queda vacía."
                ),
            },
            {
                "title": "Unir facturas (CSV)",
                "icon": "bi-receipt",
                "unit": "facturas",
                "url": reverse(
                    "analytics:accounting_csv_merge", args=["facturas"],
                ),
                "help": (
                    "se ponen uno detrás de otro con una sola cabecera, el "
                    "ORDEN queda correlativo, el contador de facturas "
                    "(ASIENTO) sube con cada factura nueva y repite el "
                    "número en las líneas de la misma factura, y de las "
                    "líneas resumen solo queda la última."
                ),
            },
        ]
        return render(request, "panel/accounting_tools.html", {
            "tools": tools,
            "company_user": company_user,
            "company": company_user.company,
            "active_nav": "accounting_tools",
            "own_presence": _get_own_presence(company_user),
        })


class AccountingCsvMergeView(SupervisorAccessMixin, View):
    """
    Merge the uploaded CSV files, in the order sent, and return it.

    ---

    Une los CSV en el orden en que llegan (el que ha dejado el usuario
    en la lista) y devuelve el CSV unido, con el número de filas y de
    asientos o facturas en las cabeceras X-Rows y X-Entries. `kind`:
    "asientos" o "facturas" (TOOLS). Si algo falla, JSON
    con el motivo (400).
    """

    def post(self, request, kind):
        """
        Merge and return the file.

        ---

        Une y devuelve el fichero.
        """
        if kind not in TOOLS:
            return JsonResponse({"error": "Herramienta desconocida."},
                                status=404)
        merge_files, prefix, unit = TOOLS[kind]
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
            data, rows, entries = merge_files(files)
        except MergeError as exc:
            return JsonResponse({"error": str(exc)}, status=400)
        logger.info(
            "# [CSV %s] %s une %d ficheros: %d filas, %d %s.",
            kind.upper(), request.user.username, len(files), rows, entries,
            unit,
        )
        name = "%s-%s.csv" % (
            prefix, timezone.localtime().strftime("%Y%m%d-%H%M"),
        )
        response = HttpResponse(data, content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="%s"' % name
        response["X-Rows"] = str(rows)
        response["X-Entries"] = str(entries)
        response["X-Unit"] = unit
        response["X-Filename"] = name
        return response
