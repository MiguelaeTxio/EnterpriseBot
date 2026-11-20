# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/crane_albaranes/views_panel.py
"""
Panel page "Grúas": crane albaranes, sites and clients (H11, S162).

---

Página "Grúas" del panel (H11, S162): pestañas Albaranes, Obras y
Clientes, con el formato único de listados (directrices 4.24 y 4.27):
arriba, fijo, Buscar y filtrar · Grupos de selección (solo Albaranes,
por el gruista) · Acciones; abajo la lista (con Ampliar) y "Selección
actual". Miguel Ángel: "cómo se definen las obras por clientes, con su
ubicación, su número, el número de proyecto [...] el conjunto de obras
[...] cómo se envían por WhatsApp las órdenes de trabajo a cada
trabajador".
"""
import datetime
import logging
from decimal import Decimal, InvalidOperation

from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views import View

from crane_albaranes import listing
from crane_albaranes.models import CraneAlbaran
from crane_albaranes.services import (
    LOCATION_ONLY_NOTICE,
    apply_worksite,
    create_albaran,
    fill_from_clock,
    finish_signed,
    pdf_bytes,
    pdf_name,
    person_label,
    send_worker_notice,
    worker_url,
)
from panel.mixins import CompanyUserRequiredMixin
from panel.models import PanelNavigationState
from panel.navigation_persistence import (
    apply_list_navigation,
    get_saved_state_key,
)

logger = logging.getLogger(__name__)

HUB_KEY = "cranes_hub"
TABS = ("albaranes", "obras", "clientes")
_ACCESS_ROLES = ("DOCS_SUPERVISOR", "SUPERVISOR")


def can_access(company_user):
    """
    Same gate as Documentación: admins and supervisors.
    ---
    La misma puerta que Documentación: administradores y supervisores.
    """
    return company_user is not None and (
        company_user.is_admin_level
        or company_user.role in _ACCESS_ROLES)


class CraneAccessMixin(CompanyUserRequiredMixin):
    """
    403 for users outside the gate.
    ---
    403 a quien no entra por la puerta de la página Grúas.
    """

    def dispatch(self, request, *args, **kwargs):
        company_user = getattr(request.user, "company_user", None)
        if request.user.is_authenticated and not can_access(company_user):
            return HttpResponse("Sin acceso a Grúas.", status=403)
        return super().dispatch(request, *args, **kwargs)


def _company(request):
    return request.user.company_user.company


def _date(raw):
    try:
        return datetime.date.fromisoformat((raw or "").strip())
    except ValueError:
        return None


def _time(raw):
    try:
        return datetime.time.fromisoformat((raw or "").strip()[:5])
    except ValueError:
        return None


def _decimal(raw):
    text = (raw or "").strip().replace(",", ".")
    if not text:
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def _int(raw):
    text = (raw or "").strip()
    return int(text) if text.isdigit() else None


class CranesHubView(CraneAccessMixin, View):
    """
    GET: the page with its tabs, on the tab the user left open.
    ---
    GET: la página con sus pestañas, en la que el usuario dejó abierta
    (directriz 4.15).
    """

    def get(self, request):
        state = PanelNavigationState.objects.filter(
            company_user=request.user.company_user,
            screen_key=HUB_KEY).first()
        active = (state.state or {}).get("active_tab") if state else None
        return render(request, "crane_albaranes/hub.html", {
            "active_nav": "cranes_hub",
            "active_tab": active if active in TABS else TABS[0],
            "screen_key": HUB_KEY,
        })


# ---------------------------------------------------------------------
# Albaranes
# ---------------------------------------------------------------------

ALB_KEY = "crane_albaranes"
ALB_FILTERS = ("search", "status", "date_from", "date_to", "group",
               "sort")
ALB_COLUMNS = (
    ("number", "Nº"),
    ("day", "Fecha"),
    ("time", "Hora"),
    ("person", "Gruista"),
    ("worksite", "Obra"),
    ("client", "Cliente"),
    ("machine", "Máquina"),
    ("hours", "Horas"),
    ("status", "Estado"),
    ("delivery", "Entrega"),
)
ALB_DEFAULT_SORT = "-day,time,person"
STATUS_COLORS = {
    "PREPARED": "secondary", "SENT": "primary", "SEND_FAILED": "danger",
    "OPENED": "info", "SIGNED": "success", "DELIVERED": "success",
    "DELIVERY_FAILED": "warning", "CANCELLED": "dark",
}


def _albaran_rows(company):
    rows = []
    for alb in CraneAlbaran.objects.filter(company=company).select_related(
            "person", "worksite", "machine"):
        person = person_label(alb.person)
        site = alb.worksite.name if alb.worksite_id else alb.work_place
        rows.append({
            "key": str(alb.pk), "a": alb, "person": person,
            "person_id": alb.person_id, "site": site,
            "color": STATUS_COLORS.get(alb.status, "secondary"),
            "label": "%s · %s · %s" % (alb.number,
                                       alb.day.strftime("%d/%m"), person),
            "text": " ".join(str(v) for v in (
                alb.number, person, site, alb.client_name,
                alb.machine.code if alb.machine_id else "",
                alb.task, alb.work_done, alb.order_number,
                alb.get_status_display())).lower(),
            "sort": {
                "number": alb.number, "day": alb.day,
                "time": alb.planned_time, "person": person.lower() or None,
                "worksite": (site or "").lower() or None,
                "client": alb.client_name.lower() or None,
                "machine": alb.machine.code if alb.machine_id else None,
                "hours": alb.hours_worked,
                "status": alb.get_status_display(),
                "delivery": alb.delivered_at,
            },
        })
    return rows


def _albaran_context(request):
    from document_explorer.models import PersonIdentity
    from panel.person_groups import (
        PERSON_KIND, filter_by_group, group_filter_select_context,
    )

    rows = _albaran_rows(_company(request))
    statuses = listing.csv_param(request, "status", [
        s for s in CraneAlbaran.Status.values if s != "CANCELLED"])
    rows = [r for r in rows if r["a"].status in statuses]
    date_from = _date(request.GET.get("date_from"))
    date_to = _date(request.GET.get("date_to"))
    if date_from:
        rows = [r for r in rows if r["a"].day >= date_from]
    if date_to:
        rows = [r for r in rows if r["a"].day <= date_to]
    group = request.GET.get("group", "")
    if group:
        wanted = set(filter_by_group(
            PersonIdentity.objects.all(), group,
            PERSON_KIND).values_list("pk", flat=True))
        rows = [r for r in rows if r["person_id"] in wanted]
    for word in request.GET.get("search", "").strip().lower().split():
        rows = [r for r in rows if word in r["text"]]
    if request.GET.get("only_selected") == "1":
        wanted = set(request.GET.get("selected_ids", "").split(","))
        rows = [r for r in rows if r["key"] in wanted]
    raw_sort = request.GET.get("sort", ALB_DEFAULT_SORT)
    rows = listing.sort_rows(rows, listing.parse_sort(raw_sort,
                                                      ALB_COLUMNS))
    return {
        "rows": rows,
        "filter_search": request.GET.get("search", ""),
        "filter_status": statuses,
        "filter_date_from": request.GET.get("date_from", ""),
        "filter_date_to": request.GET.get("date_to", ""),
        "status_choices": CraneAlbaran.Status.choices,
        **group_filter_select_context(request, PERSON_KIND),
        **listing.sort_controls(raw_sort, ALB_COLUMNS),
    }


def _form_choices(company):
    """
    Sites, machines, workers and issuers for the albarán form.
    ---
    Obras, máquinas, gruistas y empresas emisoras del formulario.
    """
    from document_explorer.models import (
        CompanyFiscalProfile,
        PersonIdentity,
    )
    from fleet.models import MachineAsset
    from worksites.models import Worksite

    return {
        "worksites": Worksite.objects.filter(is_active=True).select_related(
            "client").order_by("name"),
        "machines": MachineAsset.objects.filter(
            company=company, is_active=True).order_by("code").only(
            "pk", "code", "plate", "brand_model", "type_name"),
        "people": PersonIdentity.objects.filter(
            company=company, is_active_employee=True).order_by(
            "first_surname", "second_surname", "given_name").only(
            "pk", "first_surname", "second_surname", "given_name"),
        "issuers": CompanyFiscalProfile.objects.order_by("legal_name"),
    }


class AlbaranTabView(CraneAccessMixin, View):
    """
    GET: the Albaranes tab.
    ---
    GET: la pestaña Albaranes completa.
    """

    def get(self, request):
        from panel.person_groups import group_filter_context

        apply_list_navigation(request, ALB_KEY, ALB_FILTERS)
        cu = request.user.company_user
        saved = get_saved_state_key(cu, ALB_KEY, "selection", [])
        return render(request, "crane_albaranes/_albaranes_pane.html", {
            **_albaran_context(request),
            **group_filter_context(request),
            **_form_choices(cu.company),
            "saved_selection": saved if isinstance(saved, list) else [],
            "today": timezone.localdate(),
            "is_location_only": LOCATION_ONLY_NOTICE,
        })


class AlbaranResultsView(CraneAccessMixin, View):
    """
    GET: the table only.
    ---
    GET: solo la tabla (filtros y orden).
    """

    def get(self, request):
        apply_list_navigation(request, ALB_KEY, ALB_FILTERS)
        return render(request, "crane_albaranes/_albaranes_table.html",
                      _albaran_context(request))


def _albaran_of(request, pk):
    albaran = CraneAlbaran.objects.filter(
        company=_company(request), pk=pk).select_related(
        "worksite", "machine", "person", "issuer").first()
    if albaran is None:
        raise Http404
    return albaran


_TEXT_FIELDS = ("client_name", "client_tax_id", "client_address",
                "client_locality", "client_province", "client_phone",
                "order_number", "work_place", "work_locality", "tonnage",
                "helpers", "task", "work_done", "observations")


def save_albaran_form(albaran, data, company):
    """
    Apply a posted albarán form (office or worker).
    ---
    Aplica el formulario de un albarán (oficina o gruista). Los campos
    que no vienen no se tocan.
    """
    from document_explorer.models import (
        CompanyFiscalProfile,
        PersonIdentity,
    )
    from fleet.models import MachineAsset
    from worksites.models import Worksite

    if "worksite" in data:
        site = Worksite.objects.filter(pk=data.get("worksite") or 0).first()
        if site is not None and site.pk != albaran.worksite_id:
            for field in ("client_name", "client_tax_id", "client_address",
                          "client_locality", "client_province",
                          "client_phone", "work_place", "work_locality",
                          "order_number"):
                setattr(albaran, field, "")
            albaran.min_hours = None
            apply_worksite(albaran, site)
    if "machine" in data:
        albaran.machine = MachineAsset.objects.filter(
            company=company, pk=data.get("machine") or 0).first()
    if "person" in data:
        albaran.person = PersonIdentity.objects.filter(
            company=company, pk=data.get("person") or 0).first()
    if "issuer" in data:
        albaran.issuer = CompanyFiscalProfile.objects.filter(
            pk=data.get("issuer") or 0).first()
    if "day" in data and _date(data.get("day")):
        albaran.day = _date(data.get("day"))
    for field in ("planned_time", "base_out", "work_in", "work_out",
                  "base_in"):
        if field in data:
            setattr(albaran, field, _time(data.get(field)))
    for field in ("hours_worked", "min_hours"):
        if field in data:
            setattr(albaran, field, _decimal(data.get(field)))
    for field in ("trips", "km"):
        if field in data:
            setattr(albaran, field, _int(data.get(field)))
    for field in _TEXT_FIELDS:
        if field in data:
            max_length = CraneAlbaran._meta.get_field(field).max_length
            value = (data.get(field) or "").strip()
            setattr(albaran, field, value[:max_length] if max_length
                    else value)
    for field in ("vehicle_on_site", "continues_previous"):
        if "%s_present" % field in data:
            setattr(albaran, field, data.get(field) == "1")
    goods = dict(albaran.goods or {})
    for key in ("load_company", "load_place", "load_tractor",
                "load_trailer", "unload_company", "unload_place",
                "unload_tractor", "unload_trailer", "unload_date",
                "owner_company"):
        if "goods_%s" % key in data:
            goods[key] = (data.get("goods_%s" % key) or "").strip()[:120]
    albaran.goods = {k: v for k, v in goods.items() if v}


class AlbaranCreateView(CraneAccessMixin, View):
    """
    POST: a new albarán prepared by the office.
    ---
    POST: un albarán nuevo preparado por la oficina (obra, gruista,
    máquina, fecha y trabajo). JSON {pk, number}.
    """

    def post(self, request):
        from document_explorer.models import PersonIdentity
        from fleet.models import MachineAsset
        from worksites.models import Worksite

        company = _company(request)
        day = _date(request.POST.get("day"))
        site = Worksite.objects.filter(
            pk=request.POST.get("worksite") or 0).first()
        person = PersonIdentity.objects.filter(
            company=company, pk=request.POST.get("person") or 0).first()
        if day is None or site is None or person is None:
            return JsonResponse({"error": "Elige la fecha, la obra y el "
                                          "gruista."}, status=400)
        machine = MachineAsset.objects.filter(
            company=company, pk=request.POST.get("machine") or 0).first()
        albaran = create_albaran(
            company, day=day, worksite=site, machine=machine,
            person=person, created_by=request.user.company_user,
            planned_time=_time(request.POST.get("planned_time")),
            task=(request.POST.get("task") or "").strip(),
            tonnage=(request.POST.get("tonnage") or "").strip()[:20])
        return JsonResponse({"pk": albaran.pk, "number": albaran.number})


class AlbaranDetailView(CraneAccessMixin, View):
    """
    GET: the albarán form (modal body). POST: save it.
    ---
    GET: el formulario del albarán (cuerpo de la ventana). POST: lo
    guarda; firmado ya no se edita.
    """

    def get(self, request, pk):
        albaran = _albaran_of(request, pk)
        return render(request, "crane_albaranes/_albaran_form.html", {
            "a": albaran, **_form_choices(_company(request)),
            "worker_link": worker_url(albaran),
        })

    def post(self, request, pk):
        albaran = _albaran_of(request, pk)
        if not albaran.can_edit:
            return JsonResponse({"error": "Firmado: ya no se edita."},
                                status=400)
        save_albaran_form(albaran, request.POST, _company(request))
        albaran.save()
        return JsonResponse({"ok": True})


class AlbaranMassView(CraneAccessMixin, View):
    """
    POST: send by WhatsApp, fill from the clock, cancel or deliver again.
    ---
    POST con los marcados: `send` (WhatsApp al gruista), `clock` (horas
    desde los fichajes), `cancel` (anular), `deliver` (reenviar al
    cliente los firmados) o `delete` (solo los que no se han enviado).
    JSON {done, errors}.
    """

    def post(self, request):
        ids = [pk for pk in request.POST.get("ids", "").split(",")
               if pk.isdigit()]
        albaranes = list(CraneAlbaran.objects.filter(
            company=_company(request), pk__in=ids).select_related(
            "person", "worksite", "machine", "client"))
        action = request.POST.get("action", "")
        done, errors = 0, []
        for albaran in albaranes:
            if action == "send":
                if not albaran.can_edit:
                    errors.append("%s: ya firmado." % albaran.number)
                elif send_worker_notice(albaran):
                    done += 1
                else:
                    errors.append("%s: %s" % (albaran.number,
                                              albaran.notice_error))
            elif action == "clock":
                if albaran.can_edit and fill_from_clock(albaran,
                                                        overwrite=True):
                    albaran.save()
                    done += 1
            elif action == "cancel":
                if albaran.is_signed:
                    errors.append("%s: firmado, no se anula." %
                                  albaran.number)
                    continue
                albaran.status = CraneAlbaran.Status.CANCELLED
                albaran.save(update_fields=["status", "updated_at"])
                done += 1
            elif action == "deliver":
                if not albaran.is_signed:
                    errors.append("%s: sin firmar." % albaran.number)
                elif finish_signed(albaran):
                    done += 1
                else:
                    errors.append("%s: %s" % (albaran.number,
                                              albaran.delivery_error))
            elif action == "delete":
                if albaran.status != CraneAlbaran.Status.PREPARED:
                    errors.append("%s: ya enviado; se anula, no se "
                                  "borra." % albaran.number)
                    continue
                albaran.delete()
                done += 1
            else:
                return JsonResponse({"error": "Acción desconocida."},
                                    status=400)
        logger.info("# [ALBARÁN GRÚA] %s: %s %d/%d",
                    request.user.username, action, done, len(albaranes))
        return JsonResponse({"done": done, "errors": errors})


class AlbaranPdfView(CraneAccessMixin, View):
    """
    GET: the albarán PDF (signed or as it is now).
    ---
    GET: el PDF del albarán, firmado o tal como está.
    """

    def get(self, request, pk):
        albaran = _albaran_of(request, pk)
        response = HttpResponse(pdf_bytes(albaran),
                                content_type="application/pdf")
        response["Content-Disposition"] = 'inline; filename="%s"' % (
            pdf_name(albaran))
        return response


class PlanningTemplateView(CraneAccessMixin, View):
    """
    GET: the empty planning Excel.
    ---
    GET: la plantilla del planning en Excel.
    """

    def get(self, request):
        import io

        from crane_albaranes.planning import template_workbook

        buffer = io.BytesIO()
        template_workbook().save(buffer)
        response = HttpResponse(
            buffer.getvalue(),
            content_type="application/vnd.openxmlformats-officedocument."
                         "spreadsheetml.sheet")
        response["Content-Disposition"] = (
            'attachment; filename="PLANNING_GRUAS.xlsx"')
        return response


class PlanningUploadView(CraneAccessMixin, View):
    """
    POST: load a planning Excel.
    ---
    POST: carga un planning; JSON con los albaranes creados y las filas
    que no se han podido cargar (y por qué).
    """

    def post(self, request):
        from crane_albaranes.planning import import_planning

        uploaded = request.FILES.get("file")
        if uploaded is None:
            return JsonResponse({"error": "Elige el Excel del planning."},
                                status=400)
        try:
            planning = import_planning(_company(request), uploaded,
                                       request.user.company_user)
        except (ValueError, KeyError) as exc:
            return JsonResponse({"error": str(exc)}, status=400)
        except Exception as exc:  # noqa: BLE001 -- Excel ilegible
            logger.exception("# [PLANNING GRÚAS] %s", uploaded.name)
            return JsonResponse({"error": "No se ha podido leer el Excel "
                                          "(%s)." % exc}, status=400)
        return JsonResponse({
            "created": planning.rows_created, "rows": planning.rows_total,
            "problems": planning.problems,
            "items": [
                [a.pk, "%s · %s · %s" % (a.number, a.day.strftime("%d/%m"),
                                         person_label(a.person))]
                for a in planning.albaranes.select_related("person")],
        })


class AlbaranExportView(CraneAccessMixin, View):
    """
    POST: the marked albaranes to Excel, PDF or print.
    ---
    POST: los marcados a Excel, PDF o imprimir, con la plantilla elegida.
    """

    def post(self, request):
        from openpyxl import Workbook

        from panel.export_formats import workbook_response
        from panel.screen_exports import columns_for, get_screen, write_sheet

        ids = {v for v in request.POST.getlist("selected") if v.isdigit()}
        ordered = listing.sort_rows(
            _albaran_rows(_company(request)),
            listing.parse_sort(ALB_DEFAULT_SORT, ALB_COLUMNS))
        rows = [r for r in ordered if r["key"] in ids]
        if not rows:
            return HttpResponse("No hay ningún albarán seleccionado.",
                                status=400)
        columns = columns_for(request, get_screen("crane_albaranes"))
        if columns is None:
            return HttpResponse("Plantilla no encontrada.", status=404)
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "ALBARANES"
        write_sheet(sheet, columns, rows)
        return workbook_response(request, workbook, "albaranes_gruas")


# ---------------------------------------------------------------------
# Obras
# ---------------------------------------------------------------------

SITE_KEY = "crane_worksites"
SITE_FILTERS = ("search", "state", "client", "sort")
SITE_COLUMNS = (
    ("code", "Código"),
    ("name", "Obra"),
    ("client", "Cliente"),
    ("project", "Nº de proyecto"),
    ("place", "Ubicación"),
    ("contact", "Contacto"),
    ("delivery", "Entrega"),
    ("albaranes", "Albaranes"),
)
SITE_DEFAULT_SORT = "code"


def _site_rows():
    from django.db.models import Count

    from worksites.models import Worksite

    rows = []
    for site in Worksite.objects.select_related("client").annotate(
            n_alb=Count("crane_albaranes")):
        place = ", ".join(p for p in (site.address, site.locality,
                                      site.province) if p)
        rows.append({
            "key": str(site.pk), "w": site, "place": place,
            "client": site.client_label,
            "label": "%s · %s" % (site.code, site.name),
            "text": " ".join((site.code, site.name, site.client_label,
                              site.project_number, site.order_number,
                              place, site.contact_name)).lower(),
            "sort": {
                "code": site.code, "name": site.name.lower(),
                "client": site.client_label.lower() or None,
                "project": site.project_number or None,
                "place": place.lower() or None,
                "contact": site.contact_name.lower() or None,
                "delivery": site.get_delivery_channel_display(),
                "albaranes": site.n_alb,
            },
        })
    return rows


def _site_context(request):
    from worksites.models import Client

    rows = _site_rows()
    states = listing.csv_param(request, "state", ["active"])
    rows = [r for r in rows if ("active" if r["w"].is_active
                                else "ended") in states]
    client = request.GET.get("client", "")
    if client.isdigit():
        rows = [r for r in rows if r["w"].client_id == int(client)]
    for word in request.GET.get("search", "").strip().lower().split():
        rows = [r for r in rows if word in r["text"]]
    if request.GET.get("only_selected") == "1":
        wanted = set(request.GET.get("selected_ids", "").split(","))
        rows = [r for r in rows if r["key"] in wanted]
    raw_sort = request.GET.get("sort", SITE_DEFAULT_SORT)
    rows = listing.sort_rows(rows, listing.parse_sort(raw_sort,
                                                      SITE_COLUMNS))
    return {
        "rows": rows,
        "filter_search": request.GET.get("search", ""),
        "filter_state": states,
        "filter_client": client,
        "state_choices": (("active", "Activas"), ("ended", "Finalizadas")),
        "clients": Client.objects.filter(is_active=True),
        **listing.sort_controls(raw_sort, SITE_COLUMNS),
    }


class WorksiteTabView(CraneAccessMixin, View):
    """
    GET: the Obras tab.
    ---
    GET: la pestaña Obras.
    """

    def get(self, request):
        from ivr_config.models import Company
        from worksites.models import Worksite

        apply_list_navigation(request, SITE_KEY, SITE_FILTERS)
        cu = request.user.company_user
        saved = get_saved_state_key(cu, SITE_KEY, "selection", [])
        return render(request, "crane_albaranes/_worksites_pane.html", {
            **_site_context(request),
            "saved_selection": saved if isinstance(saved, list) else [],
            "delivery_choices": Worksite.DELIVERY_CHOICES,
            "companies": Company.objects.order_by("name"),
        })


class WorksiteResultsView(CraneAccessMixin, View):
    """
    GET: the table only.
    ---
    GET: solo la tabla.
    """

    def get(self, request):
        apply_list_navigation(request, SITE_KEY, SITE_FILTERS)
        return render(request, "crane_albaranes/_worksites_table.html",
                      _site_context(request))


def _geo(raw, limit):
    value = _decimal(raw)
    if value is None or abs(value) > limit:
        return None
    return value.quantize(Decimal("0.000001"))


class WorksiteSaveView(CraneAccessMixin, View):
    """
    GET: one site as JSON (to edit). POST: create or update it.
    ---
    GET: una obra en JSON, para editarla. POST: alta (sin `pk`) o cambio
    de una obra. El código OBRA-0001 lo pone el sistema.
    """

    FIELDS = ("name", "address", "locality", "province", "project_number",
              "order_number", "contact_name", "contact_phone",
              "delivery_email", "delivery_whatsapp", "notes")

    def get(self, request):
        from worksites.models import Worksite

        site = Worksite.objects.filter(
            pk=request.GET.get("pk") or 0).first()
        if site is None:
            raise Http404
        data = {f: getattr(site, f) for f in self.FIELDS}
        data.update({
            "pk": site.pk, "code": site.code,
            "client": site.client_id or "",
            "managing_company": site.managing_company_id or "",
            "latitude": str(site.latitude or ""),
            "longitude": str(site.longitude or ""),
            "min_hours": str(site.min_hours or ""),
            "delivery_channel": site.delivery_channel,
        })
        return JsonResponse(data)

    def post(self, request):
        from worksites.models import Client, Worksite

        data = request.POST
        site = Worksite.objects.filter(pk=data.get("pk") or 0).first()
        name = (data.get("name") or "").strip()
        client = Client.objects.filter(pk=data.get("client") or 0).first()
        if not name or client is None:
            return JsonResponse({"error": "La obra necesita nombre y "
                                          "cliente."}, status=400)
        site = site or Worksite()
        for field in self.FIELDS:
            max_length = Worksite._meta.get_field(field).max_length
            value = (data.get(field) or "").strip()
            setattr(site, field, value[:max_length] if max_length
                    else value)
        site.client = client
        site.client_name = client.name
        site.managing_company_id = (
            int(data["managing_company"]) if (
                data.get("managing_company") or "").isdigit() else None)
        site.latitude = _geo(data.get("latitude"), 90)
        site.longitude = _geo(data.get("longitude"), 180)
        if site.latitude is None or site.longitude is None:
            # Sin coordenadas escritas, las de la dirección (Google).
            from budgets.service_geocode import geocode

            point = geocode(", ".join(p for p in (
                site.address, site.locality, site.province) if p))
            if point:
                site.latitude = _geo(str(point[0]), 90)
                site.longitude = _geo(str(point[1]), 180)
        site.min_hours = _decimal(data.get("min_hours"))
        channel = data.get("delivery_channel")
        if channel in dict(Worksite.DELIVERY_CHOICES):
            site.delivery_channel = channel
        site.save()
        if not site.code:
            site.code = "OBRA-%04d" % site.pk
            site.save(update_fields=["code"])
        return JsonResponse({"pk": site.pk, "code": site.code})


class WorksiteMassView(CraneAccessMixin, View):
    """
    POST: end, reactivate or delete the marked sites.
    ---
    POST: finaliza (`end`), reactiva (`reactivate`) o borra (`delete`,
    solo las que no tienen albaranes ni circulares) las marcadas.
    """

    def post(self, request):
        from worksites.models import Worksite

        ids = [pk for pk in request.POST.get("ids", "").split(",")
               if pk.isdigit()]
        sites = Worksite.objects.filter(pk__in=ids)
        action = request.POST.get("action", "")
        errors = []
        if action in ("end", "reactivate"):
            done = sites.update(is_active=(action == "reactivate"))
        elif action == "delete":
            done = 0
            for site in sites:
                if (site.crane_albaranes.exists()
                        or site.document_acknowledgments.exists()):
                    errors.append("%s tiene albaranes o circulares: "
                                  "finalízala." % site.code)
                    continue
                site.delete()
                done += 1
        else:
            return JsonResponse({"error": "Acción desconocida."},
                                status=400)
        return JsonResponse({"done": done, "errors": errors})


class WorksiteExportView(CraneAccessMixin, View):
    """
    POST: the marked sites to Excel, PDF or print.
    ---
    POST: las obras marcadas a Excel, PDF o imprimir.
    """

    def post(self, request):
        from openpyxl import Workbook

        from panel.export_formats import workbook_response
        from panel.screen_exports import columns_for, get_screen, write_sheet

        ids = {v for v in request.POST.getlist("selected") if v.isdigit()}
        ordered = listing.sort_rows(
            _site_rows(),
            listing.parse_sort(SITE_DEFAULT_SORT, SITE_COLUMNS))
        rows = [r for r in ordered if r["key"] in ids]
        if not rows:
            return HttpResponse("No hay ninguna obra seleccionada.",
                                status=400)
        columns = columns_for(request, get_screen("crane_worksites"))
        if columns is None:
            return HttpResponse("Plantilla no encontrada.", status=404)
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "OBRAS"
        write_sheet(sheet, columns, rows)
        return workbook_response(request, workbook, "obras")


# ---------------------------------------------------------------------
# Clientes
# ---------------------------------------------------------------------

CLIENT_KEY = "crane_clients"
CLIENT_FILTERS = ("search", "state", "sort")
CLIENT_COLUMNS = (
    ("name", "Cliente"),
    ("tax_id", "N.I.F."),
    ("place", "Localidad"),
    ("phone", "Teléfono"),
    ("email", "Correo"),
    ("sites", "Obras"),
)
CLIENT_DEFAULT_SORT = "name"


def _client_rows():
    from django.db.models import Count

    from worksites.models import Client

    rows = []
    for client in Client.objects.annotate(n_sites=Count("worksites")):
        place = ", ".join(p for p in (client.locality, client.province)
                          if p)
        rows.append({
            "key": str(client.pk), "c": client, "place": place,
            "label": client.name,
            "text": " ".join((client.name, client.tax_id, client.address,
                              place, client.phone, client.email)).lower(),
            "sort": {
                "name": client.name.lower(),
                "tax_id": client.tax_id or None,
                "place": place.lower() or None,
                "phone": client.phone or None,
                "email": client.email.lower() or None,
                "sites": client.n_sites,
            },
        })
    return rows


def _client_context(request):
    rows = _client_rows()
    states = listing.csv_param(request, "state", ["active"])
    rows = [r for r in rows if ("active" if r["c"].is_active
                                else "inactive") in states]
    for word in request.GET.get("search", "").strip().lower().split():
        rows = [r for r in rows if word in r["text"]]
    if request.GET.get("only_selected") == "1":
        wanted = set(request.GET.get("selected_ids", "").split(","))
        rows = [r for r in rows if r["key"] in wanted]
    raw_sort = request.GET.get("sort", CLIENT_DEFAULT_SORT)
    rows = listing.sort_rows(rows, listing.parse_sort(raw_sort,
                                                      CLIENT_COLUMNS))
    return {
        "rows": rows,
        "filter_search": request.GET.get("search", ""),
        "filter_state": states,
        "state_choices": (("active", "Activos"), ("inactive", "De baja")),
        **listing.sort_controls(raw_sort, CLIENT_COLUMNS),
    }


class ClientTabView(CraneAccessMixin, View):
    """
    GET: the Clientes tab.
    ---
    GET: la pestaña Clientes.
    """

    def get(self, request):
        apply_list_navigation(request, CLIENT_KEY, CLIENT_FILTERS)
        cu = request.user.company_user
        saved = get_saved_state_key(cu, CLIENT_KEY, "selection", [])
        return render(request, "crane_albaranes/_clients_pane.html", {
            **_client_context(request),
            "saved_selection": saved if isinstance(saved, list) else [],
        })


class ClientResultsView(CraneAccessMixin, View):
    """
    GET: the table only.
    ---
    GET: solo la tabla.
    """

    def get(self, request):
        apply_list_navigation(request, CLIENT_KEY, CLIENT_FILTERS)
        return render(request, "crane_albaranes/_clients_table.html",
                      _client_context(request))


class ClientSaveView(CraneAccessMixin, View):
    """
    GET: one client as JSON. POST: create or update it.
    ---
    GET: un cliente en JSON. POST: alta o cambio de un cliente.
    """

    FIELDS = ("name", "tax_id", "address", "locality", "province",
              "phone", "email", "notes")

    def get(self, request):
        from worksites.models import Client

        client = Client.objects.filter(
            pk=request.GET.get("pk") or 0).first()
        if client is None:
            raise Http404
        data = {f: getattr(client, f) for f in self.FIELDS}
        data["pk"] = client.pk
        return JsonResponse(data)

    def post(self, request):
        from worksites.models import Client

        data = request.POST
        name = (data.get("name") or "").strip()
        if not name:
            return JsonResponse({"error": "Falta el nombre del cliente."},
                                status=400)
        client = Client.objects.filter(pk=data.get("pk") or 0).first()
        tax_id = (data.get("tax_id") or "").upper().replace(" ", "")
        if client is None and tax_id:
            # Un cliente que ya existe con ese N.I.F. se actualiza, no se
            # duplica (el traspaso automático desde otro programa puede
            # pasar el mismo cliente más de una vez).
            client = Client.objects.filter(tax_id=tax_id).first()
        client = client or Client()
        for field in self.FIELDS:
            max_length = Client._meta.get_field(field).max_length
            value = (data.get(field) or "").strip()
            setattr(client, field, value[:max_length] if max_length
                    else value)
        client.tax_id = client.tax_id.upper().replace(" ", "")
        client.save()
        client.worksites.update(client_name=client.name)
        return JsonResponse({"pk": client.pk})


class ClientMassView(CraneAccessMixin, View):
    """
    POST: deactivate, reactivate or delete the marked clients.
    ---
    POST: dar de baja, reactivar o borrar (solo sin obras) los marcados.
    """

    def post(self, request):
        from worksites.models import Client

        ids = [pk for pk in request.POST.get("ids", "").split(",")
               if pk.isdigit()]
        clients = Client.objects.filter(pk__in=ids)
        action = request.POST.get("action", "")
        errors = []
        if action in ("deactivate", "reactivate"):
            done = clients.update(is_active=(action == "reactivate"))
        elif action == "delete":
            done = 0
            for client in clients:
                if client.worksites.exists():
                    errors.append("%s tiene obras: dalo de baja." %
                                  client.name)
                    continue
                client.delete()
                done += 1
        else:
            return JsonResponse({"error": "Acción desconocida."},
                                status=400)
        return JsonResponse({"done": done, "errors": errors})


class ClientExportView(CraneAccessMixin, View):
    """
    POST: the marked clients to Excel, PDF or print.
    ---
    POST: los clientes marcados a Excel, PDF o imprimir.
    """

    def post(self, request):
        from openpyxl import Workbook

        from panel.export_formats import workbook_response
        from panel.screen_exports import columns_for, get_screen, write_sheet

        ids = {v for v in request.POST.getlist("selected") if v.isdigit()}
        ordered = listing.sort_rows(
            _client_rows(),
            listing.parse_sort(CLIENT_DEFAULT_SORT, CLIENT_COLUMNS))
        rows = [r for r in ordered if r["key"] in ids]
        if not rows:
            return HttpResponse("No hay ningún cliente seleccionado.",
                                status=400)
        columns = columns_for(request, get_screen("crane_clients"))
        if columns is None:
            return HttpResponse("Plantilla no encontrada.", status=404)
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "CLIENTES"
        write_sheet(sheet, columns, rows)
        return workbook_response(request, workbook, "clientes")
