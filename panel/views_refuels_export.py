# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/views_refuels_export.py
"""
Excel export of the Refuels tab (H30), with templates per view.

---

Exportación a Excel de la pestaña Repostajes (H30), con plantillas.
S144, Miguel Ángel: "eligiendo las columnas que queremos que aparezcan
en el Excel. Cuando se da al botón de exportar a Excel, da la opción de
elegir las columnas que queremos que salgan. Incluso de poder usar
plantillas como hacemos en otras vistas". Mismo planteamiento que la
exportación de Personal (panel/views_personal_export.py): el botón abre
un modal con la plantilla; plantillas propias (una por defecto) y
globales de empresa que solo crea o edita un ADMIN; cada vista de la
pestaña (Repostajes, Vehículos, Repostadores, Preguntas) tiene su
catálogo de columnas y sus plantillas. La plantilla "Todas las
columnas" que se crea la primera vez da el mismo Excel que antes.

Exporta las filas marcadas o, si no hay ninguna, todas las del filtro
(sin el tope de 1.000 de la pantalla).

S144 (lista de Alberto): en Repostadores, columnas con los vehículos
de cada repostador ("Km en vez de horas en" y "Vehículos repostados").
"""
import json

from django.db.models import Count, Q
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.views import View

from fleet.models import (
    GasoGesSupply,
    GasoGesVehicle,
    RefuelExportTemplate,
)
from ivr_config.models import CompanyUser
from panel.export_formats import workbook_response
from panel.mixins import CompanyUserRequiredMixin
from panel.views_refuels import (
    VIEW_QUESTIONS,
    VIEW_SUPPLIES,
    VIEW_USERS,
    VIEW_VEHICLES,
    _DEFAULT_ORDER,
    _all_active,
    _date_range,
    _filtered_questions,
    _filtered_supplies,
    _question_row,
    _user_groups,
    _user_rows,
    _vehicle_groups,
    _vehicle_label,
    _vehicle_rows,
    _view,
)

_DATE = "DD/MM/YYYY"
_TIME = "HH:MM"
_DATETIME = "DD/MM/YYYY HH:MM"


def _float(value):
    return float(value) if value is not None else None


def _naive(value):
    return value.replace(tzinfo=None) if value else None


def _code(machine):
    return machine.code if machine else ""


def _yes(value):
    return "Sí" if value else "No"


# (clave, cabecera, ancho, getter, formato). El getter recibe la fila de
# la vista: el suministro (Repostajes) o el diccionario de _vehicle_rows,
# _user_rows o _question_row. Orden = el de la plantilla "Todas las
# columnas" y el del editor.
# ---
# (key, header, width, getter, number format).
_COLUMNS = {
    VIEW_SUPPLIES: (
        ("fecha", "Fecha", 12,
         lambda s: timezone.localtime(s.supplied_at).date(), _DATE),
        ("hora", "Hora", 8,
         lambda s: timezone.localtime(s.supplied_at).time().replace(
             microsecond=0), _TIME),
        ("centro", "Centro de gasto", 14,
         lambda s: _code(s.vehicle.machine), None),
        ("matricula", "Matrícula (GasoGes)", 16,
         lambda s: s.vehicle.plate, None),
        ("nombre", "Nombre (GasoGes)", 28, lambda s: s.vehicle.name, None),
        ("quien", "Quién repostó", 32,
         lambda s: s.user.name if s.user else "", None),
        ("km", "KM tecleado", 12, lambda s: s.meter_value, None),
        ("unidad", "Unidad", 11,
         lambda s: s.vehicle.get_unit_display(), None),
        ("litros", "Litros", 9, lambda s: _float(s.litres), None),
        ("precio", "Precio", 9, lambda s: _float(s.price), None),
        ("estado", "Estado", 24, lambda s: s.get_status_display(), None),
        ("motivo", "Motivo", 48, lambda s: s.status_note, None),
        ("horas", "Horas sin anotar", 20,
         lambda s: s.get_hours_issue_display() if s.hours_issue else "",
         None),
    ),
    VIEW_VEHICLES: (
        ("centro", "Centro de gasto", 14, lambda r: _code(r["machine"]),
         None),
        ("vehiculo", "Vehículo (GasoGes)", 18,
         lambda r: r["vehicle_label"], None),
        ("nombre", "Nombre (GasoGes)", 28, lambda r: r["vehicle_name"],
         None),
        ("repostajes", "Repostajes", 11, lambda r: r["count"], None),
        ("litros", "Litros", 10, lambda r: _float(r["litres"]), None),
        ("ultimo", "Último repostaje", 17, lambda r: _naive(r["last"]),
         _DATETIME),
        ("ultimos_km", "Últimos KM (GasoGes)", 18, lambda r: r["last_km"],
         None),
        ("unidad", "Unidad", 11, lambda r: r["unit"], None),
        ("dudosos", "Dudosos", 9, lambda r: r["anomalies"], None),
        ("km_horas", "Km en vez de horas", 12, lambda r: r["hours_km"],
         None),
        ("sin_anotar", "Sin anotar", 10, lambda r: r["hours_empty"], None),
        ("repostadores", "Repostadores", 12, lambda r: r["others"], None),
        ("pregunta", "Se pregunta al chófer", 18,
         lambda r: _yes(r["ask_driver"]), None),
        ("averiado", "Contador averiado", 16,
         lambda r: _yes(r["meter_broken"]), None),
    ),
    VIEW_USERS: (
        ("repostador", "Repostador (GasoGes)", 32, lambda r: r["name"],
         None),
        ("ficha", "Ficha de trabajador", 36, lambda r: r["person_label"],
         None),
        ("repostajes", "Repostajes", 11, lambda r: r["count"], None),
        ("litros", "Litros", 10, lambda r: _float(r["litres"]), None),
        ("ultimo", "Último repostaje", 17, lambda r: _naive(r["last"]),
         _DATETIME),
        ("dudosos", "Dudosos", 9, lambda r: r["anomalies"], None),
        ("en_horas", "En vehículos de horas", 12,
         lambda r: r["hours_count"], None),
        ("km_horas", "Km en vez de horas", 12, lambda r: r["hours_km"],
         None),
        ("km_horas_en", "Km en vez de horas en (repostajes)", 40,
         lambda r: r["codes_km"], None),
        ("sin_anotar", "Sin anotar", 10, lambda r: r["hours_empty"], None),
        ("vehiculos", "Vehículos", 10, lambda r: r["others"], None),
        ("vehiculos_codigos", "Vehículos repostados (repostajes)", 40,
         lambda r: r["codes_all"], None),
        ("pregunta", "Se le pregunta", 14,
         lambda r: _yes(r["ask_driver"]), None),
    ),
    VIEW_QUESTIONS: (
        ("enviada", "Enviada", 17, lambda r: _naive(r["sent"]), _DATETIME),
        ("chofer", "Chófer", 34, lambda r: r["driver"], None),
        ("centro", "Centro de gasto", 14, lambda r: _code(r["machine"]),
         None),
        ("vehiculo", "Vehículo (GasoGes)", 18,
         lambda r: r["vehicle_label"], None),
        ("pregunta", "Pregunta", 22, lambda r: r["kind"], None),
        ("dato", "Dato tecleado", 13, lambda r: r["value"], None),
        ("unidad", "Unidad", 11, lambda r: r["unit"], None),
        ("motivo", "Por qué se pregunta", 60, lambda r: r["reason"], None),
        ("estado", "En qué quedó", 30, lambda r: r["status"], None),
        ("respuesta", "Respuesta", 20, lambda r: r["answer"], None),
        ("respondida", "Respondida", 17, lambda r: _naive(r["answered"]),
         _DATETIME),
    ),
}
_BY_KEY = {
    view: {column[0]: column for column in columns}
    for view, columns in _COLUMNS.items()
}
_SHEETS = {
    VIEW_SUPPLIES: ("Repostajes", "repostajes"),
    VIEW_VEHICLES: ("Vehículos", "repostajes_vehiculos"),
    VIEW_USERS: ("Repostadores", "repostajes_repostadores"),
    VIEW_QUESTIONS: ("Preguntas", "repostajes_preguntas"),
}


def _template_view(value):
    return value if value in _COLUMNS else VIEW_SUPPLIES


def _is_admin(company_user):
    return company_user.role in CompanyUser.ADMIN_ROLES


def _visible_templates(company_user, view):
    """
    The user's own templates of the view and the company's global ones;
    with neither, an "all columns" default one is created first.

    ---

    Las plantillas propias de la vista y las globales de la empresa; si
    no hay ninguna, se crea antes una propia por defecto con todas las
    columnas (el Excel de antes de S144).
    """
    company = company_user.company
    own = RefuelExportTemplate.objects.filter(
        company=company, company_user=company_user, view=view,
        is_global=False)
    shared = RefuelExportTemplate.objects.filter(
        company=company, view=view, is_global=True)
    if not own.exists() and not shared.exists():
        RefuelExportTemplate.objects.create(
            company=company, company_user=company_user, view=view,
            name="Todas las columnas", is_default=True,
            columns=[column[0] for column in _COLUMNS[view]])
    return list(own.order_by("-is_default", "name")) + list(
        shared.order_by("name"))


def _as_dict(template, company_user):
    known = _BY_KEY[template.view]
    return {
        "id": template.pk,
        "name": template.name,
        "is_global": template.is_global,
        "is_default": template.is_default,
        "columns": [key for key in template.columns if key in known],
        "editable": (
            _is_admin(company_user) if template.is_global
            else template.company_user_id == company_user.pk),
    }


def _editable_template(company_user, pk):
    template = RefuelExportTemplate.objects.filter(
        pk=pk, company=company_user.company).first()
    if template is None:
        return None
    if template.is_global:
        return template if _is_admin(company_user) else None
    return template if template.company_user_id == company_user.pk else None


class RefuelsExportTemplateListView(CompanyUserRequiredMixin, View):
    """
    GET ?view=: the templates of the view and its column catalogue.

    ---

    GET ?view=: las plantillas de esa vista y su catálogo de columnas.
    """

    def get(self, request):
        company_user = request.user.company_user
        view = _template_view(request.GET.get("view"))
        return JsonResponse({
            "templates": [_as_dict(template, company_user)
                          for template in _visible_templates(
                              company_user, view)],
            "columns": [{"key": column[0], "label": column[1]}
                        for column in _COLUMNS[view]],
            "is_admin": _is_admin(company_user),
        })


class RefuelsExportTemplateSaveView(CompanyUserRequiredMixin, View):
    """
    POST (JSON): create (no id) or update (id) a template.
    {id?, view, name, columns[], is_default, is_global}.

    ---

    POST (JSON): crea (sin id) o actualiza (con id) una plantilla.
    """

    def post(self, request):
        company_user = request.user.company_user
        try:
            data = json.loads(request.body or b"{}")
        except ValueError:
            return JsonResponse({"error": "Datos no válidos."}, status=400)
        pk = data.get("id")
        if pk:
            template = _editable_template(company_user, pk)
            if template is None:
                return JsonResponse(
                    {"error": "No puedes modificar esta plantilla."},
                    status=403)
        else:
            is_global = bool(data.get("is_global")) and _is_admin(
                company_user)
            template = RefuelExportTemplate(
                company=company_user.company, is_global=is_global,
                company_user=None if is_global else company_user,
                view=_template_view(data.get("view")))
        name = (data.get("name") or "").strip()[:100]
        known = _BY_KEY[template.view]
        columns = [key for key in (data.get("columns") or [])
                   if key in known]
        if not name:
            return JsonResponse({"error": "Falta el nombre."}, status=400)
        if not columns:
            return JsonResponse(
                {"error": "Elige al menos una columna."}, status=400)
        same_name = RefuelExportTemplate.objects.filter(
            company=company_user.company, view=template.view,
            name__iexact=name, is_global=template.is_global)
        if not template.is_global:
            same_name = same_name.filter(company_user=company_user)
        if same_name.exclude(pk=template.pk).exists():
            return JsonResponse(
                {"error": "Ya hay una plantilla con ese nombre."},
                status=400)
        template.name = name
        template.columns = columns
        template.is_default = (
            bool(data.get("is_default")) and not template.is_global)
        template.save()
        return JsonResponse({"ok": True, "id": template.pk})


class RefuelsExportTemplateDeleteView(CompanyUserRequiredMixin, View):
    """
    POST: delete a template the user may edit.

    ---

    POST: borra una plantilla que el usuario puede editar.
    """

    def post(self, request, pk):
        template = _editable_template(request.user.company_user, pk)
        if template is None:
            return JsonResponse(
                {"error": "No puedes borrar esta plantilla."}, status=403)
        template.delete()
        return JsonResponse({"ok": True})


def _vehicle_code(vehicle):
    return vehicle.machine.code if vehicle.machine else _vehicle_label(
        vehicle)


def _user_vehicle_codes(request, rows):
    """
    Vehicles each refueller used, all and with km instead of hours.

    ---

    Vehículos que repostó cada repostador de `rows` (por pk, 0 = sin
    usuario), con cuántos repostajes en cada uno: todos, y solo los de
    km en vez de horas (S144, lista de Alberto). Mismo alcance que los
    totales de la fila: los repostajes del filtro o, con "Todos los
    activos", todo el histórico.
    """
    pks = [row["pk"] for row in rows]
    if _all_active(request, VIEW_USERS):
        supplies = GasoGesSupply.objects.all()
    else:
        supplies = _filtered_supplies(request)
    chosen = Q(user_id__in=[pk for pk in pks if pk])
    if 0 in pks:
        chosen |= Q(user__isnull=True)
    counts = list(supplies.filter(chosen).order_by().values(
        "user_id", "vehicle_id").annotate(
        n_all=Count("id"),
        n_km=Count("id", filter=Q(
            hours_issue=GasoGesSupply.HOURS_ISSUE_KM))))
    vehicles = GasoGesVehicle.objects.select_related("machine").in_bulk(
        {line["vehicle_id"] for line in counts})
    per_user = {}
    for line in counts:
        vehicle = vehicles.get(line["vehicle_id"])
        if vehicle is None:
            continue
        per_user.setdefault(line["user_id"] or 0, []).append(
            (_vehicle_code(vehicle), line["n_all"], line["n_km"]))

    def joined(items, index):
        items = sorted((item for item in items if item[index]),
                       key=lambda item: (-item[index], item[0]))
        return ", ".join("%s (%d)" % (item[0], item[index])
                         for item in items)

    return {pk: (joined(items, 1), joined(items, 2))
            for pk, items in per_user.items()}


def _export_rows(request, view, wanted):
    """
    The rows of the view to export: the marked ones or all the filtered.

    ---

    Las filas de la vista: las marcadas o, sin ninguna, todas las del
    filtro.
    """
    if view == VIEW_VEHICLES:
        return _vehicle_rows(_vehicle_groups(
            request, _DEFAULT_ORDER[VIEW_VEHICLES], wanted or None))
    if view == VIEW_USERS:
        rows = _user_rows(_user_groups(
            request, _DEFAULT_ORDER[VIEW_USERS], wanted or None))
        codes = _user_vehicle_codes(request, rows)
        for row in rows:
            row["codes_all"], row["codes_km"] = codes.get(
                row["pk"], ("", ""))
        return rows
    if view == VIEW_QUESTIONS:
        questions = _filtered_questions(request)
        if wanted:
            questions = questions.filter(pk__in=wanted)
        return [_question_row(question)
                for question in questions.order_by("sent_at", "id")]
    supplies = (GasoGesSupply.objects.select_related(
        "vehicle", "vehicle__machine", "user").filter(pk__in=wanted)
        if wanted else _filtered_supplies(request))
    return supplies.order_by("supplied_at", "id")


def _excel_response(book, prefix, request):
    """
    The workbook as an .xlsx download named with the date range.

    ---

    El libro como descarga .xlsx, con las fechas del filtro en el nombre.
    """
    date_from, date_to = _date_range(request)
    return workbook_response(request, book, "%s_%s_%s.xlsx" % (
        prefix, date_from.strftime("%Y%m%d"), date_to.strftime("%Y%m%d")))


class RefuelsExportView(CompanyUserRequiredMixin, View):
    """
    GET ?template_pk=N + the tab's filters: Excel of the current view
    with the template's columns in its order.

    ---

    GET ?template_pk=N + los filtros de la pestaña: el Excel de la
    vista actual (repostajes, vehículos, repostadores o preguntas), de
    las filas marcadas o de todas las del filtro, con las columnas de la
    plantilla en su orden.
    """

    def get(self, request):
        from openpyxl import Workbook
        from openpyxl.styles import Font
        from openpyxl.utils import get_column_letter

        company_user = request.user.company_user
        view = _view(request)
        template_pk = request.GET.get("template_pk", "")
        template = None
        if template_pk.isdigit():
            template = next(
                (item for item in _visible_templates(company_user, view)
                 if item.pk == int(template_pk)), None)
        if template is None:
            return HttpResponse("Plantilla no encontrada.", status=404)
        known = _BY_KEY[view]
        columns = [known[key] for key in template.columns if key in known]
        wanted = [int(pk) for pk in request.GET.get(
            "selected_ids", "").split(",") if pk.isdigit()]

        book = Workbook()
        sheet = book.active
        title, prefix = _SHEETS[view]
        sheet.title = title
        sheet.append([column[1] for column in columns])
        for row in _export_rows(request, view, wanted):
            sheet.append([column[3](row) for column in columns])
        for cell in sheet[1]:
            cell.font = Font(bold=True)
        sheet.freeze_panes = "A2"
        for index, column in enumerate(columns, start=1):
            letter = get_column_letter(index)
            sheet.column_dimensions[letter].width = column[2]
            if column[4]:
                for cell in sheet[letter][1:]:
                    cell.number_format = column[4]
        return _excel_response(book, prefix, request)
