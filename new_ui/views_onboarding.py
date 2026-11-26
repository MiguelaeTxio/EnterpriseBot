# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/new_ui/views_onboarding.py
"""
Clock-in onboarding report (Personal › Alta en el fichaje), new UI.

---

Informe del alta en el fichaje en la nueva interfaz (S163), copiado de
panel/views_clock_onboarding.py y de las columnas de su exportación
(panel/screen_export_catalog.CLOCK_ONBOARDING): quién tiene el alta del
fichaje enviada, recibida, abierta, si entró y si ficha. Es la vista
Personal › Alta en el fichaje: resumen por situación (que filtra),
sección, el buscador común y la tabla; exportación a Excel, PDF, HTML o
imprimir con plantillas de columnas (las mismas que la antigua,
pantalla «clock_onboarding»).
"""
from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone
from django.views import View

from new_ui.mixins import SuperuserRequiredMixin
from new_ui.onboarding_report import STATES, build_rows, not_clocking

NOT_CLOCKING = "no_fichan"
DT = "DD/MM/YYYY HH:MM"


def _naive(value):
    """Hora local sin zona, como la espera Excel."""
    return timezone.localtime(value).replace(tzinfo=None) if value else None


# (clave, cabecera, ancho, valor(fila), formato)
COLUMNS = (
    ("trabajador", "Trabajador", 34, lambda r: r["label"], None),
    ("dni", "DNI", 12, lambda r: r["dni"], None),
    ("seccion", "Sección", 18, lambda r: r["section"], None),
    ("telefono", "Teléfono", 15, lambda r: r["phone"], None),
    ("usuario", "Usuario del panel", 22, lambda r: r["username"], None),
    ("situacion", "Situación", 34, lambda r: r["state_label"], None),
    ("alta", "Alta enviada", 16, lambda r: _naive(r["first_sent"]), DT),
    ("envios", "Envíos", 8, lambda r: r["sends"], None),
    ("reenvio", "Último reenvío", 16, lambda r: _naive(r["last_sent"]), DT),
    ("whatsapp", "WhatsApp", 20, lambda r: r["whatsapp"], None),
    ("whatsapp_fecha", "Estado del WhatsApp", 16,
     lambda r: _naive(r["whatsapp_at"]), DT),
    ("abierta", "Abrió la circular", 16, lambda r: _naive(r["opened"]), DT),
    ("acceso", "Último acceso al panel", 16,
     lambda r: _naive(r["last_login"]), DT),
    ("primer_fichaje", "Primer fichaje", 16,
     lambda r: _naive(r["first_clock"]), DT),
    ("ultimo_fichaje", "Último fichaje", 16,
     lambda r: _naive(r["last_clock"]), DT),
    ("dias_alta", "Días sin fichar desde el alta", 12,
     lambda r: r["days_since_first"], None),
    ("dias_reenvio", "Días sin fichar desde el reenvío", 12,
     lambda r: r["days_since_resend"], None),
    ("dias_fichaje", "Días desde el último fichaje", 12,
     lambda r: r["days_since_clock"], None),
    ("ficha", "Ficha (ajuste)", 10, lambda r: "" if r["clocks"] is None
     else "Sí" if r["clocks"] else "No", None),
)
PANEL_COLUMNS = [
    "trabajador", "seccion", "situacion", "alta", "envios", "reenvio",
    "whatsapp", "abierta", "acceso", "ultimo_fichaje", "dias_alta",
    "dias_reenvio", "dias_fichaje",
]
_BY_KEY = {c[0]: c for c in COLUMNS}


def _plain(text):
    """Lower case and without accents, to compare searches."""
    import unicodedata

    return "".join(c for c in unicodedata.normalize("NFD", text.lower())
                   if unicodedata.category(c) != "Mn")


def _filtered(data, rows):
    """The rows that pass the filters (situation, section, search)."""
    text = (data.get("q") or "").strip().lower()
    # S163 (26/11): buscando a alguien, sin situación elegida, se busca
    # entre todos (no solo entre los que aún no fichan).
    state = data.get("alta_estado", "" if text else NOT_CLOCKING)
    section = data.get("alta_seccion", "")
    result = []
    for row in rows:
        if state == NOT_CLOCKING and not not_clocking(row):
            continue
        if state not in ("", NOT_CLOCKING) and row["state"] != state:
            continue
        if section and row["section"] != section:
            continue
        haystack = _plain(row["label"] + " " + row["dni"] + " "
                          + row["username"])
        if text and not all(_plain(word) in haystack
                            for word in text.split()):
            continue
        result.append(row)
    return result, state, section


def render_report(request):
    """
    The «Alta en el fichaje» view (summary, filters and table).

    ---

    La vista «Alta en el fichaje»: resumen por situación (cada una
    filtra), secciones, y la tabla con las columnas de la vista del
    panel.
    """
    rows = build_rows(request.user.company_user.company)
    shown, state, section = _filtered(request.GET, rows)
    counts = {key: 0 for key, _l, _b in STATES}
    for row in rows:
        counts[row["state"]] += 1
    return render(request, "new_ui/_onboarding.html", {
        "rows": shown,
        "total": len(rows),
        "not_clocking": sum(1 for r in rows if not_clocking(r)),
        "summary": [(key, label, badge, counts[key])
                    for key, label, badge in STATES],
        "state": state,
        "section": section,
        "sections": sorted({r["section"] for r in rows if r["section"]}),
        "not_clocking_key": NOT_CLOCKING,
    })


class OnboardingExportView(SuperuserRequiredMixin, View):
    """
    POST: the filtered report to Excel, PDF, HTML or print.

    ---

    POST: el informe con los filtros de la vista, con las columnas de la
    plantilla elegida (o las marcadas).
    """

    def post(self, request):
        from openpyxl import Workbook
        from openpyxl.styles import Font
        from openpyxl.utils import get_column_letter

        from new_ui.export_formats import workbook_response
        from new_ui.screen_templates import chosen_keys

        rows, _state, _section = _filtered(
            request.POST, build_rows(request.user.company_user.company))
        if not rows:
            return HttpResponse("No hay nadie con esos filtros.", status=400)
        columns = [_BY_KEY[k] for k in chosen_keys(
            request, "clock_onboarding", PANEL_COLUMNS)]
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "ALTA EN EL FICHAJE"
        sheet.append([c[1] for c in columns])
        for cell in sheet[1]:
            cell.font = Font(bold=True)
        for row in rows:
            sheet.append([c[3](row) for c in columns])
        for index, column in enumerate(columns, start=1):
            letter = get_column_letter(index)
            sheet.column_dimensions[letter].width = column[2]
            if column[4]:
                for cell in sheet[letter][1:]:
                    cell.number_format = column[4]
        sheet.freeze_panes = "A2"
        return workbook_response(request, workbook, "alta_en_el_fichaje")
