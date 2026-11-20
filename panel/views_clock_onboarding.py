# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/views_clock_onboarding.py
"""
Clock-in onboarding report page and its export (S149).

---

S149 (Miguel Ángel, 20/11). Página "Informe del alta en el fichaje":
resumen por situación (el mapa), filtros (situación, sección, nombre) y
la tabla; exportación a Excel, PDF o imprimir con el modal común de
plantillas (pantalla "clock_onboarding"). Filas:
panel/clock_onboarding_report.py.
"""
from django.http import HttpResponse
from django.shortcuts import render
from django.views import View

from panel.clock_onboarding_report import STATES, build_rows, not_clocking
from panel.mixins import SupervisorAccessMixin

NOT_CLOCKING = "no_fichan"


def _filtered(request, rows):
    """The rows that pass the filters of the request (GET or POST)."""
    data = request.POST if request.method == "POST" else request.GET
    state = data.get("estado", NOT_CLOCKING)
    section = data.get("seccion", "")
    text = (data.get("q") or "").strip().lower()
    result = []
    for row in rows:
        if state == NOT_CLOCKING and not not_clocking(row):
            continue
        if state not in ("", NOT_CLOCKING) and row["state"] != state:
            continue
        if section and row["section"] != section:
            continue
        if text and text not in (row["label"] + " " + row["dni"] + " "
                                 + row["username"]).lower():
            continue
        result.append(row)
    return result, state, section, text


class ClockOnboardingReportView(SupervisorAccessMixin, View):
    """
    GET: the onboarding report page.
    ---
    GET: la página del informe del alta en el fichaje.
    """

    def get(self, request):
        rows = build_rows(request.user.company_user.company)
        shown, state, section, text = _filtered(request, rows)
        counts = {key: 0 for key, _l, _b in STATES}
        for row in rows:
            counts[row["state"]] += 1
        summary = [(key, label, badge, counts[key])
                   for key, label, badge in STATES]
        return render(request, "panel/clock_onboarding/page.html", {
            "rows": shown,
            "total": len(rows),
            "not_clocking": sum(1 for r in rows if not_clocking(r)),
            "summary": summary,
            "states": STATES,
            "state": state,
            "section": section,
            "q": text,
            "sections": sorted({r["section"] for r in rows if r["section"]}),
            "not_clocking_key": NOT_CLOCKING,
        })


class ClockOnboardingExportView(SupervisorAccessMixin, View):
    """
    POST: the filtered report to Excel, PDF or print.
    ---
    POST: el informe con los filtros de la página, en Excel, PDF o para
    imprimir, con la plantilla elegida en el modal común.
    """

    def post(self, request):
        from openpyxl import Workbook

        from panel.export_formats import workbook_response
        from panel.screen_exports import columns_for, get_screen, write_sheet

        rows, _state, _section, _text = _filtered(
            request, build_rows(request.user.company_user.company))
        if not rows:
            return HttpResponse("No hay nadie con esos filtros.", status=400)
        columns = columns_for(request, get_screen("clock_onboarding"))
        if columns is None:
            return HttpResponse("Plantilla no encontrada.", status=404)
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "ALTA EN EL FICHAJE"
        write_sheet(sheet, columns, rows)
        return workbook_response(request, workbook, "alta_en_el_fichaje")
