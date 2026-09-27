# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/views_lifting_accessories.py
"""
H30 (S121). "Accesorios de elevación" tab of the Documentation hub:
the full CRUD of lifting accessories (list, create, file, deliveries,
reviews, bulk review/retire) plus the editable catalogue of types.

---

H30 (S121). Pestaña "Accesorios de elevación" del hub de
Documentación: el CRUD completo de los accesorios de elevación
(listado, alta, ficha, entregas, revisiones, revisión y retirada
masivas) y el catálogo editable de tipos. Decisión de Miguel Ángel
(S121): "aunque los accesorios aparezcan en la ficha de la maquinaria,
que tengan su CRUD en pestaña, como los EPIs". La ficha de máquina solo
los muestra (sección de solo lectura, ver MachineDetailView).

Formato de la directriz 4.24 (panel fijo, scroll solo en la lista,
orden múltiple, casillas, acciones masivas siempre visibles) y
navegación persistida por usuario (4.15), con las piezas compartidas
ya existentes: panel.navigation_persistence y _fixed_list_layout.html.
"""

from datetime import date
from urllib.parse import quote

from django.contrib import messages
from django.db import transaction
from django.http import HttpResponse, HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views import View

from document_explorer import lifting_accessory_service as service
from document_explorer.models import (
    LIFTING_ACCESSORY_REVIEW_MONTHS,
    LiftingAccessory,
    LiftingAccessoryModel,
    LiftingAccessoryAssignment,
    LiftingAccessoryReview,
    LiftingAccessoryType,
    add_months,
)
from fleet.cost_center_search import search_cost_centers
from ivr_config.models import CompanyUser
from panel.forms_lifting_accessories import (
    LiftingAccessoryAssignmentForm,
    LiftingAccessoryCertificateForm,
    LiftingAccessoryForm,
    LiftingAccessoryModelForm,
    LiftingAccessoryReturnForm,
    LiftingAccessoryReviewForm,
    LiftingAccessoryTypeForm,
)
from panel.mixins import CompanyUserRequiredMixin, DocsUploadAccessMixin
from panel.navigation_persistence import (
    apply_list_navigation,
    get_saved_state_key,
)

SCREEN_KEY = "lifting_accessories"
FILTER_KEYS = ("search", "type", "status", "sort")
MANAGE_ROLES = {CompanyUser.ROLE_ADMIN, CompanyUser.ROLE_DOCS_SUPERVISOR}

# Columnas ordenables -> función que da el valor de cada fila ya
# calculada (_annotate). Todo el orden se aplica en Python: el volumen
# real es de decenas de accesorios y varias columnas (máquina,
# responsable, caducidad) son datos derivados, no columnas de la tabla.
_SORT_VALUES = {
    "model": lambda a: (a.model.name if a.model else a.accessory_type.label),
    "identifier": lambda a: a.identifier.upper(),
    "description": lambda a: a.description.upper(),
    "load": lambda a: a.working_load_kg,
    "machine": lambda a: a.current_machine.code if a.current_machine else None,
    "responsible": lambda a: a.responsible_label.upper() or None,
    "review": lambda a: a.last_review_date,
    "expiry": lambda a: a.expiry,
    "certificate": lambda a: a.has_certificate,
    "status": lambda a: a.is_active,
}
_MAX_SORT_KEYS = 4

# Cabeceras de la tabla, en orden (clave de _SORT_VALUES, etiqueta).
_COLUMNS = (
    ("model", "Modelo"),
    ("identifier", "Nº certificado / serie"),
    ("description", "Descripción"),
    ("load", "Carga (kg)"),
    ("machine", "Centro de gasto"),
    ("responsible", "Responsable"),
    ("review", "Última revisión"),
    ("expiry", "Caducidad"),
    ("certificate", "Certificado"),
    ("status", "Estado"),
)


def _can_manage(request):
    """
    ADMIN and DOCS_SUPERVISOR manage; everyone else only reads.
    ---
    ADMIN y DOCS_SUPERVISOR gestionan; el resto solo consulta (mismos
    roles que DocsUploadAccessMixin).
    """
    return request.user.company_user.role in MANAGE_ROLES


def _parse_sort(raw):
    """
    "key,-key,..." -> [(key, descending)], valid and unique keys only.
    ---
    "clave,-clave,..." -> [(clave, descendente)], solo claves válidas y
    sin repetir, como máximo _MAX_SORT_KEYS (mismo formato S116/S117).
    """
    keys, seen = [], set()
    for token in (raw or "").split(","):
        token = token.strip()
        key = token.lstrip("-")
        if key in _SORT_VALUES and key not in seen:
            keys.append((key, token.startswith("-")))
            seen.add(key)
    return keys[:_MAX_SORT_KEYS]


def _sort_controls(raw):
    """
    Next "sort" value, arrow and priority of every column header.
    ---
    Valor de "sort" que envía cada cabecera, su flecha y su prioridad
    -- mismas reglas que Centros de gasto (S117): clic en una columna la
    promueve a principal conservando las demás; clic en la principal
    invierte su sentido. Resuelto aquí, nunca en la plantilla.
    """
    sort_keys = _parse_sort(raw)
    active = [key for key, _desc in sort_keys]
    sort_next, arrows, priority = {}, {}, {}
    for key in _SORT_VALUES:
        if key in active:
            idx = active.index(key)
            desc = sort_keys[idx][1]
            arrows[key] = "down" if desc else "up"
            priority[key] = idx + 1 if len(sort_keys) > 1 else ""
            new_desc = (not desc) if idx == 0 else desc
            new_keys = [(key, new_desc)] + [
                (k, d) for k, d in sort_keys if k != key
            ]
        else:
            arrows[key] = ""
            priority[key] = ""
            new_keys = [(key, False)] + sort_keys
        sort_next[key] = ",".join(
            ("-" if d else "") + k for k, d in new_keys[:_MAX_SORT_KEYS]
        )
    return {
        "sort_columns": [
            {
                "key": key, "label": label, "next": sort_next[key],
                "arrow": arrows[key], "priority": priority[key],
            }
            for key, label in _COLUMNS
        ],
        "sort_active": bool(sort_keys),
        "current_sort": ",".join(("-" if d else "") + k for k, d in sort_keys),
    }


def _sort_rows(rows, sort_keys):
    """
    Stable multi-key sort; empty values always go last.
    ---
    Orden estable por varias claves (de la menos a la más importante);
    los valores vacíos siempre al final, en ambos sentidos.
    """
    rows = sorted(rows, key=lambda a: (a.accessory_type.display_order,
                                       a.identifier.upper()))
    for key, desc in reversed(sort_keys):
        getter = _SORT_VALUES[key]
        present = [a for a in rows if getter(a) is not None]
        missing = [a for a in rows if getter(a) is None]
        rows = sorted(present, key=getter, reverse=desc) + missing
    return rows


def _person_label(person):
    """
    "Surnames, Name" of a worker (never the ID number).
    ---
    "Apellidos, Nombre" de un trabajador (nunca el DNI).
    """
    if person is None:
        return ""
    surnames = " ".join(
        p for p in (person.first_surname, person.second_surname) if p
    )
    return "%s, %s" % (surnames, person.given_name)


def _annotate(accessories):
    """
    Attach the derived data every screen shows: current machine and
    responsible, last review, effective expiry and the expired flag.
    ---
    Añade los datos derivados que pinta cada pantalla: máquina y
    responsable actuales, última revisión, caducidad efectiva y aviso
    de caducado. Una consulta por relación (prefetch), nunca por fila.
    """
    today = date.today()
    accessories = list(accessories.select_related(
        "accessory_type", "model",
    ).prefetch_related(
        "assignments__machine", "assignments__responsible_person",
        "reviews",
    ))
    certificates = service.certificates_of(accessories)
    for accessory in accessories:
        accessory.certificates = certificates.get(accessory.pk, [])
        accessory.has_certificate = bool(accessory.certificates)
        open_assignments = [
            a for a in accessory.assignments.all() if a.end_date is None
        ]
        current = max(
            open_assignments, key=lambda a: (a.start_date, a.pk),
            default=None,
        )
        reviews = list(accessory.reviews.all())
        last_review = max(
            reviews, key=lambda r: (r.review_date, r.pk), default=None,
        )
        accessory.current_assignment_row = current
        accessory.current_machine = current.machine if current else None
        accessory.responsible_label = _person_label(
            current.responsible_person if current else None,
        )
        accessory.last_review_date = (
            last_review.review_date if last_review else None
        )
        if last_review is not None:
            accessory.expiry = last_review.expiry_date
        elif accessory.supply_date:
            accessory.expiry = add_months(
                accessory.supply_date, LIFTING_ACCESSORY_REVIEW_MONTHS,
            )
        else:
            accessory.expiry = None
        accessory.is_expired = bool(
            accessory.is_active and accessory.expiry
            and accessory.expiry < today
        )
    return accessories


def _param(request, key, default=""):
    """
    Read from GET, falling back to the _f_ copy posted by the actions.
    ---
    Lee de GET y, si no está, de la copia _f_ que envían las acciones
    (mismo mecanismo que Centros de gasto) -- así la tabla repintada
    tras una acción respeta lo que se estaba viendo.
    """
    return request.GET.get(key) or request.POST.get("_f_" + key, default)


def _list_context(request):
    """
    Context of the table fragment: filtered, annotated, sorted rows.
    ---
    Contexto del fragmento de tabla: filas filtradas, anotadas y
    ordenadas.
    """
    company = request.user.company_user.company
    qs = LiftingAccessory.objects.filter(company=company)
    search = _param(request, "search").strip()
    type_id = _param(request, "type")
    status = _param(request, "status")
    if type_id.isdigit():
        qs = qs.filter(accessory_type_id=int(type_id))
    if status == "1":
        qs = qs.filter(is_active=True)
    elif status == "0":
        qs = qs.filter(is_active=False)
    elif status == "none":
        qs = qs.none()
    rows = _annotate(qs)
    if search:
        needle = search.upper()
        rows = [
            a for a in rows
            if needle in " ".join((
                a.identifier, a.traceability, a.description, a.dimensions,
                a.standard, a.manufacturer, a.accessory_type.label,
                a.model.name if a.model else "",
                a.current_machine.code if a.current_machine else "",
                a.responsible_label,
            )).upper()
        ]
    if request.GET.get("only_selected") == "1":
        wanted = {
            pk for pk in request.GET.get("selected_ids", "").split(",")
            if pk.isdigit()
        }
        rows = [a for a in rows if str(a.pk) in wanted]
    rows = _sort_rows(rows, _parse_sort(_param(request, "sort")))
    return {
        "accessories": rows,
        "filter_search": search,
        "filter_type": type_id,
        "filter_status": status,
        "is_filtered": bool(search or type_id or status),
        "can_manage": _can_manage(request),
        **_sort_controls(_param(request, "sort")),
    }


def _types_context(request):
    """
    Catalogue of accessory types with their number of accessories.
    ---
    Catálogo de tipos de accesorio con su número de accesorios, y si el
    usuario puede editarlo (resuelto aquí, plantillas tontas).
    """
    from django.db.models import Count

    return {
        "accessory_types": LiftingAccessoryType.objects.annotate(
            n_accessories=Count("accessories"),
        ).order_by("display_order", "label"),
        "can_manage_types": _can_manage(request),
    }


def _models_context(request):
    """
    Catalogue models with their units in the store and in total.
    ---
    Modelos del catálogo con sus unidades en el almacén y en total, y si
    el usuario puede editarlos (resuelto aquí, plantillas tontas).
    """
    from django.db.models import Count

    company = request.user.company_user.company
    in_store = service.store_counts(company)
    models_list = list(LiftingAccessoryModel.objects.select_related(
        "accessory_type",
    ).annotate(n_total=Count("accessories")).order_by(
        "display_order", "name",
    ))
    for model in models_list:
        model.n_store = in_store.get(model.pk, 0)
    return {
        "accessory_models": models_list,
        "can_manage_models": _can_manage(request),
        "model_form": LiftingAccessoryModelForm(),
    }


def _table_response(request, message=""):
    """
    Table fragment, with an optional toast message in a header.
    ---
    Fragmento de tabla, con un mensaje de aviso opcional en cabecera.
    """
    response = render(
        request, "panel/lifting_accessories/_table.html",
        _list_context(request),
    )
    if message:
        response["X-Lifting-Message"] = quote(message)
    return response


def _selected(request):
    """
    Accessories of the user's company among the posted "selected" ids.
    ---
    Accesorios de la empresa del usuario entre los ids "selected"
    enviados -- nunca de otra empresa, aunque se manipule el id.
    """
    ids = [pk for pk in request.POST.getlist("selected") if pk.isdigit()]
    return LiftingAccessory.objects.filter(
        company=request.user.company_user.company, pk__in=ids,
    )


class LiftingAccessoryTabView(CompanyUserRequiredMixin, View):
    """
    GET: whole tab (fixed panel, list, selection and type catalogue).
    ---
    GET: la pestaña completa (panel fijo, lista, selección y catálogo
    de tipos), cargada por htmx desde hub.html.
    """

    def get(self, request):
        apply_list_navigation(request, SCREEN_KEY, FILTER_KEYS)
        company = request.user.company_user.company
        saved_selection = get_saved_state_key(
            request.user.company_user, SCREEN_KEY, "selection", [],
        )
        if not isinstance(saved_selection, list):
            saved_selection = []
        context = {
            **_list_context(request),
            **_types_context(request),
            **_models_context(request),
            "screen_key": SCREEN_KEY,
            "saved_selection": saved_selection,
            "active_types": LiftingAccessoryType.objects.filter(
                is_active=True,
            ).order_by("display_order", "label"),
            "create_form": LiftingAccessoryForm(
                company=company, is_create=True,
            ),
            "assign_form": LiftingAccessoryAssignmentForm(
                company=company, initial={"start_date": date.today()},
            ),
            # Mismo formulario para la entrega por modelo, con otros ids
            # (los dos modales conviven en la página); los nombres de
            # campo son los mismos, así ambos acaban en la entrega masiva.
            "model_assign_form": LiftingAccessoryAssignmentForm(
                company=company, initial={"start_date": date.today()},
                auto_id="bym_%s",
            ),
            "review_form": LiftingAccessoryReviewForm(with_document=False),
            "type_form": LiftingAccessoryTypeForm(),
        }
        return render(
            request, "panel/lifting_accessories/_pane.html", context,
        )


class LiftingAccessoryResultsView(CompanyUserRequiredMixin, View):
    """
    GET: only the table (search, filters, sort), stored per user.
    ---
    GET: solo la tabla (búsqueda, filtros, orden), guardada por usuario.
    """

    def get(self, request):
        apply_list_navigation(request, SCREEN_KEY, FILTER_KEYS)
        return render(
            request, "panel/lifting_accessories/_table.html",
            _list_context(request),
        )


class LiftingAccessoryCreateView(DocsUploadAccessMixin, View):
    """
    POST: create one NEW accessory, with its mandatory certificate.
    ---
    POST: alta de un accesorio NUEVO (que no existe todavía), con su
    certificado obligatorio, que se sube ya tipado y enlazado. Sin
    entrega: entregar es un acto aparte (S121). Con errores, repinta el
    formulario dentro del modal (HX-Retarget).
    """

    def post(self, request):
        company = request.user.company_user.company
        form = LiftingAccessoryForm(
            request.POST, request.FILES, company=company, is_create=True,
        )
        if not form.is_valid():
            response = render(
                request, "panel/lifting_accessories/_create_form.html",
                {"create_form": form},
            )
            response["HX-Retarget"] = "#lifting-create-form-container"
            response["HX-Reswap"] = "innerHTML"
            return response
        with transaction.atomic():
            accessory = form.save(commit=False)
            accessory.company = company
            accessory.save()
            service.upload_certificate(
                accessory, form.cleaned_data["certificate_file"],
            )
        return _table_response(request, "Accesorio %s dado de alta." % (
            accessory.identifier,
        ))


class LiftingAccessoryBulkStatusView(DocsUploadAccessMixin, View):
    """
    POST: retire or reactivate the selected accessories.
    ---
    POST: retirar del servicio o reactivar los accesorios marcados.
    Retirar cierra su entrega abierta con fecha de hoy.
    """

    def post(self, request):
        action = request.POST.get("action")
        if action not in ("retire", "reactivate"):
            return HttpResponseBadRequest("Acción no válida.")
        changed = service.set_active(
            _selected(request), is_active=(action == "reactivate"),
        )
        verb = "retirados" if action == "retire" else "reactivados"
        return _table_response(request, "%d accesorios %s." % (changed, verb))


class LiftingAccessoryBulkReviewView(DocsUploadAccessMixin, View):
    """
    POST: record the same review (date, optional expiry) on each
    selected accessory.
    ---
    POST: registra la misma revisión (fecha y caducidad opcional) en
    cada accesorio marcado -- la revisión anual se hace por lotes.
    """

    def post(self, request):
        form = LiftingAccessoryReviewForm(request.POST, with_document=False)
        if not form.is_valid():
            errors = "; ".join(
                str(err) for errs in form.errors.values() for err in errs
            )
            return HttpResponseBadRequest(errors or "Datos no válidos.")
        accessories = list(_selected(request))
        with transaction.atomic():
            for accessory in accessories:
                service.register_review(
                    accessory, form.cleaned_data["review_date"],
                    form.cleaned_data.get("explicit_expiry_date"),
                )
        return _table_response(
            request,
            "Revisión registrada en %d accesorios." % len(accessories),
        )


class LiftingAccessoryBulkAssignView(DocsUploadAccessMixin, View):
    """
    POST: deliver the selected accessories to one cost centre and one
    responsible person on one date.
    ---
    POST: entrega los accesorios marcados a un mismo centro de gasto y
    una misma persona responsable, con la misma fecha (p. ej. el juego
    de eslingas de una grúa y su operador). Cada uno cierra su entrega
    anterior (historial).
    """

    def post(self, request):
        form = LiftingAccessoryAssignmentForm(
            request.POST, company=request.user.company_user.company,
        )
        if not form.is_valid():
            errors = "; ".join(
                str(err) for errs in form.errors.values() for err in errs
            )
            return HttpResponseBadRequest(errors or "Datos no válidos.")
        accessories = list(_selected(request).filter(is_active=True))
        with transaction.atomic():
            for accessory in accessories:
                service.assign_accessory(
                    accessory, form.cleaned_data["responsible_person"],
                    form.cleaned_data["cost_center"],
                    form.cleaned_data["start_date"],
                    notes=form.cleaned_data.get("notes", ""),
                )
        return _table_response(request, "%d accesorios entregados a %s." % (
            len(accessories), form.cleaned_data["cost_center"].code,
        ))


class LiftingAccessoryModelUnitsView(DocsUploadAccessMixin, View):
    """
    GET ?model=&quantity=: units of the model in the store, the oldest
    `quantity` pre-ticked, for the delivery by model.
    ---
    GET ?model=&quantity=: unidades del modelo en el almacén, con las
    `quantity` más antiguas ya marcadas -- paso de la entrega por modelo
    (Miguel Ángel, S121, opción 1). El supervisor confirma o cambia las
    marcas según las etiquetas (trazabilidad, que es lo que va en la
    etiqueta según EN 1492-1, y nº de certificado).
    """

    def get(self, request):
        company = request.user.company_user.company
        model = get_object_or_404(
            LiftingAccessoryModel, pk=request.GET.get("model") or 0,
        )
        try:
            quantity = max(int(request.GET.get("quantity") or 1), 1)
        except ValueError:
            quantity = 1
        units = list(service.units_in_store(model, company))
        for index, unit in enumerate(units):
            unit.preselected = index < quantity
        return render(request, "panel/lifting_accessories/_model_units.html", {
            "model": model,
            "units": units,
            "quantity": quantity,
            "short": quantity > len(units),
        })


class LiftingAccessoryModelSaveView(DocsUploadAccessMixin, View):
    """
    POST: create (no pk) or edit (pk) one model; returns the catalogue.
    GET: the catalogue as it is now (refresh after a delivery).
    ---
    POST: alta (sin pk) o edición (con pk) de un modelo; devuelve el
    catálogo de modelos repintado. GET: el catálogo tal como está (se
    repinta tras una entrega, para actualizar lo que queda en almacén).
    """

    def get(self, request, model_pk=None):
        return render(
            request, "panel/lifting_accessories/_models.html",
            _models_context(request),
        )

    def post(self, request, model_pk=None):
        instance = (
            get_object_or_404(LiftingAccessoryModel, pk=model_pk)
            if model_pk else None
        )
        form = LiftingAccessoryModelForm(request.POST, instance=instance)
        context = {}
        if form.is_valid():
            form.save()
        else:
            context["model_errors"] = "; ".join(
                str(err) for errs in form.errors.values() for err in errs
            )
            context["model_error_pk"] = model_pk
        context.update(_models_context(request))
        return render(
            request, "panel/lifting_accessories/_models.html", context,
        )


class LiftingAccessoryModelRemoveView(DocsUploadAccessMixin, View):
    """
    POST: remove a model -- deleted if unused, otherwise deactivated.
    ---
    POST: quitar un modelo -- se borra si no tiene unidades; si las
    tiene, se desactiva (conserva el histórico). "reactivate" lo vuelve
    a activar.
    """

    def post(self, request, model_pk):
        model = get_object_or_404(LiftingAccessoryModel, pk=model_pk)
        if request.POST.get("action") == "reactivate":
            model.is_active = True
            model.save(update_fields=["is_active"])
        elif model.accessories.exists():
            model.is_active = False
            model.save(update_fields=["is_active"])
        else:
            model.delete()
        return render(
            request, "panel/lifting_accessories/_models.html",
            _models_context(request),
        )


class LiftingAccessoryCostCenterSearchView(DocsUploadAccessMixin, View):
    """
    GET: cost centres matching ?q=, same JSON as the daily work order.
    ---
    GET: centros de gasto que coinciden con ?q=, mismo JSON y misma
    regla que el parte diario digital (fleet.cost_center_search) -- el
    endpoint del parte exige rol de taller; este, el de documentación.
    """

    def get(self, request):
        assets = list(search_cost_centers(
            request.user.company_user.company, request.GET.get("q", ""),
        ).values("code", "brand_model", "plate"))
        return JsonResponse({"assets": assets})


class LiftingAccessoryDetailView(CompanyUserRequiredMixin, View):
    """
    File of one accessory: data (editable), certificate, deliveries and
    reviews, with the forms to add a delivery, a return and a review.
    ---
    Ficha de un accesorio: datos (editables), certificado, entregas y
    revisiones, con los formularios de nueva entrega, devolución y
    revisión. Solo ADMIN y DOCS_SUPERVISOR guardan (POST).
    """

    template_name = "panel/lifting_accessories/detail.html"

    def _get_accessory(self, request, pk):
        return get_object_or_404(
            LiftingAccessory, pk=pk,
            company=request.user.company_user.company,
        )

    def _render(self, request, accessory, form=None, assignment_form=None,
                return_form=None, review_form=None, certificate_form=None,
                status=200):
        company = request.user.company_user.company
        annotated = _annotate(LiftingAccessory.objects.filter(pk=accessory.pk))
        accessory = annotated[0]
        assignments = [
            {
                "row": row,
                "responsible": _person_label(row.responsible_person),
            }
            for row in sorted(
                accessory.assignments.all(),
                key=lambda a: (a.start_date, a.pk), reverse=True,
            )
        ]
        reviews = list(accessory.reviews.all().select_related(
            "source_entry",
        ).order_by("-review_date", "-id"))
        from panel.url_utils import safe_back_url

        return render(request, self.template_name, {
            "accessory": accessory,
            "assignments": assignments,
            "reviews": reviews,
            "form": form or LiftingAccessoryForm(
                instance=accessory, company=company,
            ),
            "assignment_form": assignment_form
            or LiftingAccessoryAssignmentForm(
                company=company, initial={"start_date": date.today()},
            ),
            "return_form": return_form or LiftingAccessoryReturnForm(
                initial={"end_date": date.today()},
            ),
            "review_form": review_form or LiftingAccessoryReviewForm(
                initial={"review_date": date.today()},
            ),
            "certificate_form": certificate_form
            or LiftingAccessoryCertificateForm(),
            "has_open_assignment": accessory.current_assignment_row
            is not None,
            "can_manage": _can_manage(request),
            "back_url": safe_back_url(
                request, request.GET.get("back_url"),
                reverse("panel:documentation_hub") + "?tab=accesorios",
            ),
            "active_nav": "documentation_hub",
        }, status=status)

    def get(self, request, pk):
        return self._render(request, self._get_accessory(request, pk))

    def post(self, request, pk):
        if not _can_manage(request):
            return HttpResponse(status=403)
        accessory = self._get_accessory(request, pk)
        form = LiftingAccessoryForm(
            request.POST, instance=accessory,
            company=request.user.company_user.company,
        )
        if not form.is_valid():
            return self._render(request, accessory, form=form, status=400)
        form.save()
        messages.success(request, "Datos del accesorio guardados.")
        return redirect(request.get_full_path())


class _AccessoryActionView(DocsUploadAccessMixin, View):
    """
    Base of the POST actions of the accessory file (PRG to the file).
    ---
    Base de las acciones POST de la ficha (vuelven a la ficha, PRG).
    """

    def _accessory(self, request, pk):
        return get_object_or_404(
            LiftingAccessory, pk=pk,
            company=request.user.company_user.company,
        )

    def _back(self, request, pk):
        url = reverse("panel:lifting_accessory_detail", args=[pk])
        back_url = request.POST.get("back_url")
        if back_url:
            url += "?back_url=" + quote(back_url)
        return redirect(url)

    def _invalid(self, request, pk, **forms):
        view = LiftingAccessoryDetailView()
        return view._render(
            request, self._accessory(request, pk), status=400, **forms,
        )


class LiftingAccessoryAssignView(_AccessoryActionView):
    """
    POST: new delivery (closes the previous open one).
    ---
    POST: nueva entrega (cierra la anterior abierta).
    """

    def post(self, request, pk):
        accessory = self._accessory(request, pk)
        form = LiftingAccessoryAssignmentForm(
            request.POST, company=request.user.company_user.company,
        )
        if not form.is_valid():
            return self._invalid(request, pk, assignment_form=form)
        service.assign_accessory(
            accessory, form.cleaned_data["responsible_person"],
            form.cleaned_data["cost_center"],
            form.cleaned_data["start_date"],
            notes=form.cleaned_data.get("notes", ""),
        )
        messages.success(request, "Entrega registrada.")
        return self._back(request, pk)


class LiftingAccessoryReturnView(_AccessoryActionView):
    """
    POST: return (closes the open delivery).
    ---
    POST: devolución (cierra la entrega abierta).
    """

    def post(self, request, pk):
        accessory = self._accessory(request, pk)
        form = LiftingAccessoryReturnForm(request.POST)
        if not form.is_valid():
            return self._invalid(request, pk, return_form=form)
        current = LiftingAccessoryAssignment.objects.filter(
            accessory=accessory, end_date__isnull=True,
        ).first()
        if current and form.cleaned_data["end_date"] < current.start_date:
            form.add_error(
                "end_date",
                "La devolución no puede ser anterior a la entrega.",
            )
            return self._invalid(request, pk, return_form=form)
        service.return_accessory(accessory, form.cleaned_data["end_date"])
        messages.success(request, "Devolución registrada.")
        return self._back(request, pk)


class LiftingAccessoryReviewCreateView(_AccessoryActionView):
    """
    POST: new review of the accessory.
    ---
    POST: nueva revisión del accesorio.
    """

    def post(self, request, pk):
        accessory = self._accessory(request, pk)
        form = LiftingAccessoryReviewForm(request.POST, request.FILES)
        if not form.is_valid():
            return self._invalid(request, pk, review_form=form)
        service.register_review(
            accessory, form.cleaned_data["review_date"],
            form.cleaned_data.get("explicit_expiry_date"),
            form.cleaned_data.get("review_file"),
        )
        messages.success(request, "Revisión registrada.")
        return self._back(request, pk)


class LiftingAccessoryCertificateAddView(_AccessoryActionView):
    """
    POST: upload one more certificate (e.g. a renewed one).
    ---
    POST: sube otro certificado (p. ej. uno renovado), ya tipado
    CERT_ACCESORIO_ELEVACION y enlazado, como la ficha técnica de un
    EPI. Nunca se elige un archivo existente ni se desenlaza a mano
    (S121): lo que está en el bucket lo enlaza el sistema.
    """

    def post(self, request, pk):
        accessory = self._accessory(request, pk)
        form = LiftingAccessoryCertificateForm(request.POST, request.FILES)
        if not form.is_valid():
            return self._invalid(request, pk, certificate_form=form)
        service.upload_certificate(
            accessory, form.cleaned_data["certificate_file"],
        )
        messages.success(request, "Certificado subido.")
        return self._back(request, pk)


class LiftingAccessoryReviewDeleteView(_AccessoryActionView):
    """
    POST: delete a review recorded by mistake.
    ---
    POST: borra una revisión registrada por error (solo el registro; el
    documento vinculado, si lo hay, no se toca -- 4.12).
    """

    def post(self, request, pk, review_pk):
        accessory = self._accessory(request, pk)
        get_object_or_404(
            LiftingAccessoryReview, pk=review_pk, accessory=accessory,
        ).delete()
        messages.success(request, "Revisión eliminada.")
        return self._back(request, pk)


class LiftingAccessoryTypeSaveView(DocsUploadAccessMixin, View):
    """
    POST: create (no pk) or edit (pk) one type; returns the catalogue.
    ---
    POST: alta (sin pk) o edición (con pk) de un tipo; devuelve el
    catálogo repintado.
    """

    def post(self, request, type_pk=None):
        instance = (
            get_object_or_404(LiftingAccessoryType, pk=type_pk)
            if type_pk else None
        )
        form = LiftingAccessoryTypeForm(request.POST, instance=instance)
        context = _types_context(request)
        if form.is_valid():
            form.save()
        else:
            context["type_errors"] = "; ".join(
                str(err) for errs in form.errors.values() for err in errs
            )
            context["type_error_pk"] = type_pk
        return render(
            request, "panel/lifting_accessories/_types.html", context,
        )


class LiftingAccessoryTypeRemoveView(DocsUploadAccessMixin, View):
    """
    POST: remove a type -- deleted if unused, otherwise deactivated.
    ---
    POST: quitar un tipo -- se borra si no tiene accesorios; si los
    tiene, se desactiva (conserva su histórico). "reactivate" lo vuelve
    a activar.
    """

    def post(self, request, type_pk):
        accessory_type = get_object_or_404(LiftingAccessoryType, pk=type_pk)
        if request.POST.get("action") == "reactivate":
            accessory_type.is_active = True
            accessory_type.save(update_fields=["is_active"])
        elif accessory_type.accessories.exists():
            accessory_type.is_active = False
            accessory_type.save(update_fields=["is_active"])
        else:
            accessory_type.delete()
        return render(
            request, "panel/lifting_accessories/_types.html",
            _types_context(request),
        )
