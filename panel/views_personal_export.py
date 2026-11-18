# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/views_personal_export.py
"""
Excel export of the Personal list (Documentación > Personal, H31,
S129), with templates like the parte export: Miguel Ángel, "ese botón
de exportación a Excel debería de abrir un modal para elegir
plantilla, etcétera, como tenemos hecho ya en otros sitios".

The export takes the marked workers or, with none marked, everyone the
list shows with its current search, filters and order (the same
_person_list_page the list uses). Templates: personal ones per user
(one default) and company-wide global ones that only ADMIN creates or
edits (document_explorer.PersonalExportTemplate). S153: anyone who can
see the Personal list can export it (same CompanyUserRequiredMixin as
the list): Miguel Ángel, "todas las exportaciones exactamente igual que
tengo yo" en las vistas a las que se tiene acceso.

---

Exportación a Excel del listado de Personal, con plantillas como la
de partes. Exporta los marcados o, sin ninguno marcado, todos los que
enseña el listado con su búsqueda, filtros y orden. Plantillas
personales (una por defecto) y globales de empresa (solo ADMIN). S153:
la exporta quien puede ver el listado de Personal (antes solo ADMIN,
SUPERVISOR y WORKSHOPBOSS; Yolanda no tenía el botón).
"""
import json

from django.http import HttpResponse, JsonResponse
from django.views import View

from document_explorer.models import PersonalExportTemplate
from ivr_config.models import CompanyUser
from panel.export_formats import workbook_response
from panel.export_templates import find_template, with_panel_template
from panel.mixins import CompanyUserRequiredMixin


def _cell(value):
    return None if value == "" else value


def _label(person):
    surnames = " ".join(
        p for p in (person.first_surname, person.second_surname) if p
    )
    return "%s, %s" % (surnames, person.given_name)


# S148: columnas que enseña el panel y no tenía el Excel (las pone
# _person_list_page: person.onboarding y person.ws_row).
def _requirements(person):
    """
    S153: names of the person's requirements (several), comma-joined.
    ---
    S153: nombres de los requisitos de la persona (varios), separados
    por comas.
    """
    return ", ".join(
        req.name for req in sorted(
            person.document_requirements.all(), key=lambda r: r.name,
        )
    )


def _requirement_state(person):
    """
    S153: what the person lacks or has expired.
    ---
    S153: lo que le falta o tiene caducado: del requisito elegido en el
    filtro si lo hay, si no de todos sus requisitos activos (las mismas
    insignias del listado). "Al día" si no le falta nada.
    """
    if getattr(person, "requirement_status_checked", False):
        labels = person.requirement_status
    else:
        if not person.document_requirements.all():
            return ""
        labels = getattr(person, "alert_labels", [])
    return "; ".join(labels) or "Al día"


def _onboarding(person):
    state = getattr(person, "onboarding", None)
    return getattr(state, "label", "") if state else ""


def _section(person):
    row = getattr(person, "ws_row", None)
    state = getattr(row, "state", None)
    section = getattr(state, "section", None)
    return section.name if section else ""


def _schedule(person):
    row = getattr(person, "ws_row", None)
    schedule = getattr(row, "schedule", None)
    return schedule.label if schedule else "Sin horario"


# (key, header, width, getter, is_date). Order = order offered in the
# template editor; the Excel keeps the order of the template.
# (clave, cabecera, ancho, getter, es_fecha).
PERSONAL_EXPORT_COLUMNS = (
    ("apellidos_nombre", "Apellidos, Nombre", 34, _label, False),
    ("primer_apellido", "Primer apellido", 18,
     lambda p: p.first_surname, False),
    ("segundo_apellido", "Segundo apellido", 18,
     lambda p: p.second_surname, False),
    ("nombre", "Nombre", 18, lambda p: p.given_name, False),
    ("dni", "DNI/NIE", 12, lambda p: p.dni, False),
    ("fecha_nacimiento", "Fecha de nacimiento", 12,
     lambda p: p.birth_date, True),
    ("empresa", "Empresa", 30, lambda p: p.employer_legal_name, False),
    ("estado", "Estado", 9,
     lambda p: "Activo" if p.is_active_employee else "Baja", False),
    ("fecha_alta", "Fecha de alta", 12, lambda p: p.hire_date, True),
    ("fecha_baja", "Fecha de baja", 12, lambda p: p.termination_date, True),
    ("categoria", "Categoría profesional", 24,
     lambda p: p.professional_category, False),
    ("requisito", "Requisitos de documentación", 26, _requirements, False),
    ("estado_requisito", "Situación de la documentación", 50,
     _requirement_state, False),
    ("telefono", "Teléfono de empresa", 14, lambda p: p.phone, False),
    ("telefono_2", "Teléfono particular", 14,
     lambda p: p.phone_secondary, False),
    ("email", "Correo electrónico", 30, lambda p: p.email, False),
    ("direccion", "Dirección", 32, lambda p: p.address_street, False),
    ("codigo_postal", "Código postal", 9, lambda p: p.postal_code, False),
    ("poblacion", "Población", 18, lambda p: p.city, False),
    ("provincia", "Provincia", 14, lambda p: p.province, False),
    ("num_ss", "Nº afiliación Seguridad Social", 16,
     lambda p: p.ss_affiliation_number, False),
    ("cad_dni", "Caducidad DNI/NIE", 12, lambda p: p.dni_expiry_date, True),
    ("cad_carnet", "Caducidad carnet de conducir", 12,
     lambda p: p.driving_license_expiry_date, True),
    ("cad_gruista", "Caducidad carnet de gruista", 12,
     lambda p: p.crane_operator_card_expiry_date, True),
    ("cad_cap", "Caducidad CAP", 12,
     lambda p: p.driver_qualification_card_expiry_date, True),
    ("cad_tacografo", "Caducidad tarjeta de tacógrafo", 12,
     lambda p: p.tachograph_card_expiry_date, True),
    ("reconocimiento", "Reconocimiento médico", 12,
     lambda p: p.medical_exam_date, True),
    ("usuario_panel", "Usuario del panel", 9,
     lambda p: "Sí" if p.company_user_id else "No", False),
    ("documentos", "Documentos", 10,
     lambda p: getattr(p, "doc_count", None), False),
    ("alta_fichaje", "Alta en el fichaje", 22, _onboarding, False),
    ("seccion", "Sección", 22, _section, False),
    ("horario", "Horario", 22, _schedule, False),
)
_COLUMNS_BY_KEY = {c[0]: c for c in PERSONAL_EXPORT_COLUMNS}
DEFAULT_COLUMNS = [
    "apellidos_nombre", "dni", "empresa", "estado", "fecha_alta",
    "categoria", "requisito", "telefono", "email",
]
# S148: la plantilla "Vista del panel" = las columnas del listado.
PANEL_COLUMNS = [
    "apellidos_nombre", "dni", "fecha_alta", "documentos", "requisito",
    "estado_requisito", "alta_fichaje", "seccion", "horario",
]
# La que se creaba sola como por defecto antes de S148.
AUTO_TEMPLATES = (("Listado estándar", DEFAULT_COLUMNS),)


def column_choices():
    return [{"key": c[0], "label": c[1]} for c in PERSONAL_EXPORT_COLUMNS]


def _is_admin(company_user):
    return company_user.role in CompanyUser.ADMIN_ROLES


def _visible_templates(company_user):
    """
    The user's own templates and the company's global ones.
    ---
    Las plantillas propias y las globales de la empresa. S148: ya no se
    crea ninguna sola; sin plantillas propias está la "Vista del panel"
    (panel/export_templates.py).
    """
    company = company_user.company
    own = PersonalExportTemplate.objects.filter(
        company=company, company_user=company_user, is_global=False,
    )
    shared = PersonalExportTemplate.objects.filter(
        company=company, is_global=True,
    )
    return list(own.order_by("-is_default", "name")) + list(
        shared.order_by("name"),
    )


def _as_dict(template, company_user):
    return {
        "id": template.pk,
        "name": template.name,
        "is_global": template.is_global,
        "is_default": template.is_default,
        "columns": [k for k in template.columns if k in _COLUMNS_BY_KEY],
        "editable": (
            _is_admin(company_user) if template.is_global
            else template.company_user_id == company_user.pk
        ),
    }


def _editable_template(company_user, pk):
    template = PersonalExportTemplate.objects.filter(
        pk=pk, company=company_user.company,
    ).first()
    if template is None:
        return None
    if template.is_global:
        return template if _is_admin(company_user) else None
    return template if template.company_user_id == company_user.pk else None


SPLIT_CHOICES = (
    ("", "Sin separar"),
    ("empresa", "Por empresa"),
    ("seccion", "Por sección"),
    ("grupos", "Por grupos de selección"),
)


def _group_choices(company_user):
    """
    The person selection groups, in tree order, for the split option.
    ---
    Los grupos de selección de personas, en el orden del árbol, para
    "Separar por grupos de selección" (S153).
    """
    from panel.person_groups import group_tree

    return [
        {"id": node["group"].pk, "label": node["group"].name,
         "depth": node["depth"], "total": node["total"]}
        for node in group_tree(company_user)
        if node["kind"] == "group"
    ]


def _split_groups(request, people, values):
    """
    [(label, rows)] for the chosen split, or None when not splitting.
    ---
    S153: separa las filas por empresa, sección o los grupos de
    selección elegidos (una persona sale en cada grupo elegido en el
    que esté, contando sus subgrupos). Lo que no cae en ninguno va al
    final como "Sin empresa", "Sin sección" o "Sin grupo".
    """
    split = request.GET.get("split", "")
    if split in ("empresa", "seccion"):
        getter = ((lambda p: p.employer_legal_name) if split == "empresa"
                  else _section)
        empty = "Sin empresa" if split == "empresa" else "Sin sección"
        buckets = {}
        for person, row in zip(people, values):
            buckets.setdefault(getter(person) or "", []).append(row)
        labels = sorted(k for k in buckets if k)
        groups = [(label, buckets[label]) for label in labels]
        if "" in buckets:
            groups.append((empty, buckets[""]))
        return groups
    if split == "grupos":
        from panel.person_groups import group_tree

        wanted = [int(pk) for pk in request.GET.get(
            "split_groups", "").split(",") if pk.isdigit()]
        nodes = {node["group"].pk: node
                 for node in group_tree(request.user.company_user)
                 if node["kind"] == "group"}

        def members(pk, seen=None):
            seen = seen or set()
            if pk in seen or pk not in nodes:
                return set()
            seen.add(pk)
            ids = set(nodes[pk]["member_ids"])
            for child in nodes[pk]["children"]:
                ids |= members(child, seen)
            return ids

        groups, placed = [], set()
        for pk in wanted:
            if pk not in nodes:
                continue
            ids = members(pk)
            rows = [row for person, row in zip(people, values)
                    if person.pk in ids]
            placed |= ids
            groups.append((nodes[pk]["group"].name, rows))
        rest = [row for person, row in zip(people, values)
                if person.pk not in placed]
        if rest:
            groups.append(("Sin grupo", rest))
        return groups
    return None


class PersonalExportTemplateListView(CompanyUserRequiredMixin, View):
    """
    GET: the templates the user can use, and the column catalogue.
    ---
    GET: las plantillas que puede usar y el catálogo de columnas.
    """

    def get(self, request):
        cu = request.user.company_user
        return JsonResponse({
            "templates": with_panel_template(
                [_as_dict(t, cu) for t in _visible_templates(cu)],
                PANEL_COLUMNS, AUTO_TEMPLATES,
            ),
            "columns": column_choices(),
            "is_admin": _is_admin(cu),
            "groups": _group_choices(cu),
        })


class PersonalExportTemplateSaveView(CompanyUserRequiredMixin, View):
    """
    POST (JSON): create (no id) or update (id) a template.
    {id?, name, columns[], is_default, is_global}.
    ---
    POST (JSON): crea (sin id) o actualiza (con id) una plantilla.
    """

    def post(self, request):
        cu = request.user.company_user
        try:
            data = json.loads(request.body or b"{}")
        except ValueError:
            return JsonResponse({"error": "Datos no válidos."}, status=400)
        name = (data.get("name") or "").strip()[:100]
        columns = [
            k for k in (data.get("columns") or []) if k in _COLUMNS_BY_KEY
        ]
        if not name:
            return JsonResponse({"error": "Falta el nombre."}, status=400)
        if not columns:
            return JsonResponse(
                {"error": "Elige al menos una columna."}, status=400,
            )
        pk = data.get("id")
        if pk:
            template = _editable_template(cu, pk)
            if template is None:
                return JsonResponse(
                    {"error": "No puedes modificar esta plantilla."},
                    status=403,
                )
        else:
            is_global = bool(data.get("is_global")) and _is_admin(cu)
            template = PersonalExportTemplate(
                company=cu.company, is_global=is_global,
                company_user=None if is_global else cu,
            )
        same_name = PersonalExportTemplate.objects.filter(
            company=cu.company, name__iexact=name,
            is_global=template.is_global,
        )
        if not template.is_global:
            same_name = same_name.filter(company_user=cu)
        if same_name.exclude(pk=template.pk).exists():
            return JsonResponse(
                {"error": "Ya hay una plantilla con ese nombre."}, status=400,
            )
        template.name = name
        template.columns = columns
        template.is_default = (
            bool(data.get("is_default")) and not template.is_global
        )
        template.save()
        return JsonResponse({"ok": True, "id": template.pk})


class PersonalExportTemplateDeleteView(CompanyUserRequiredMixin, View):
    """
    POST: delete a template the user may edit.
    ---
    POST: borra una plantilla que el usuario puede editar.
    """

    def post(self, request, pk):
        template = _editable_template(request.user.company_user, pk)
        if template is None:
            return JsonResponse(
                {"error": "No puedes borrar esta plantilla."}, status=403,
            )
        template.delete()
        return JsonResponse({"ok": True})


class PersonalExportView(CompanyUserRequiredMixin, View):
    """
    GET ?template_pk=N + the list's own parameters (search, filters,
    order; only_selected=1&selected_ids=... for the marked ones): the
    Excel, one row per worker, the template's columns in its order.
    ---
    GET ?template_pk=N + los parámetros del propio listado: el Excel,
    una fila por trabajador, con las columnas de la plantilla en su
    orden.
    """

    def get(self, request):
        from django.utils import timezone
        from openpyxl import Workbook
        from openpyxl.styles import Font

        from panel.views_documentation_h30 import _person_list_page

        cu = request.user.company_user
        template = find_template(
            request.GET.get("template_pk"), _visible_templates(cu),
            PANEL_COLUMNS,
        )
        if template is None:
            return HttpResponse("Plantilla no encontrada.", status=404)
        columns = [
            _COLUMNS_BY_KEY[k] for k in template.columns
            if k in _COLUMNS_BY_KEY
        ]
        people = list(_person_list_page(request)["page"].object_list)

        header = [c[1] for c in columns]
        values = [[_cell(c[3](person)) for c in columns]
                  for person in people]

        def setup_columns(sheet, offset):
            for index, column in enumerate(columns, start=1 + offset):
                letter = sheet.cell(row=1, column=index).column_letter
                sheet.column_dimensions[letter].width = column[2]
                if column[4]:
                    for cell in sheet[letter][1:]:
                        cell.number_format = "DD/MM/YYYY"

        book = Workbook()
        groups = _split_groups(request, people, values)
        if groups is not None:
            # S153: separado por empresa, sección o grupos de selección,
            # en colores (una hoja) o en hojas.
            from panel.xlsx_style import write_grouped

            mode = ("sheets" if request.GET.get("split_mode") == "sheets"
                    else "colors")
            write_grouped(book, header, groups, mode, setup_columns,
                          group_label=dict(SPLIT_CHOICES)[
                              request.GET.get("split")].replace(
                              "Por ", "").capitalize(),
                          title="Personal")
        else:
            sheet = book.active
            sheet.title = "Personal"
            sheet.append(header)
            for row in values:
                sheet.append(row)
            for cell in sheet[1]:
                cell.font = Font(bold=True)
            sheet.freeze_panes = "A2"
            setup_columns(sheet, 0)
        filename = "personal_%s.xlsx" % timezone.localdate().strftime(
            "%Y%m%d",
        )
        return workbook_response(request, book, filename)
