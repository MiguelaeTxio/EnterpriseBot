# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/views_person_menu.py
"""
Right-click menu of a worker: jump to any of their views (H24, S144).

---

Menú del botón derecho sobre un trabajador (H24, S144). Miguel Ángel:
"poder clicar con el derecho y que nos abriera un submenú para ir a
sitios de ese trabajador. Desde la ficha de personal hasta [...]
repostajes, cualquier cosa". El clic izquierdo sigue haciendo lo de
cada vista; el derecho, sobre cualquier enlace a un trabajador (su
ficha, su página de fichajes o un elemento con data-person-pk), abre el
menú (panel/static/panel/js/context_menu.js).

- `PersonMenuView` (JSON): los destinos que tiene ese trabajador y que
  el usuario puede abrir (sin cuenta del panel no hay calendario ni
  partes; sin repostador de GasoGes, no hay repostajes).
- `PersonGoView`: deja puesto el filtro de la pestaña de destino (la
  misma persistencia de filtros que usa cada pestaña, directriz 4.15) y
  redirige: así la pestaña abre ya con ese trabajador.
"""
from django.http import Http404, JsonResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.views import View

from document_explorer.models import PersonIdentity
from ivr_config.models import CompanyUser
from panel.mixins import CompanyUserRequiredMixin

_SUPERVISOR_ROLES = (
    CompanyUser.ROLE_ADMIN, CompanyUser.ROLE_ADMIN_SUPERVISOR,
    CompanyUser.ROLE_SUPERVISOR, CompanyUser.ROLE_WORKSHOPBOSS,
)


def _person(pk):
    person = PersonIdentity.objects.select_related("company_user").filter(
        pk=pk).first()
    if person is None:
        raise Http404
    return person


def _refuel_user(person):
    from fleet.models import GasoGesUser

    return GasoGesUser.objects.filter(person=person).order_by("pk").first()


def _destinations(request, person):
    """
    [(code, label, icon)] the user can open for this worker.
    ---
    Los destinos disponibles para este trabajador y este usuario.
    """
    role = request.user.company_user.role
    supervisor = role in _SUPERVISOR_ROLES
    items = [("ficha", "Ficha de Personal", "bi-person-vcard")]
    if supervisor:
        items.append(("fichajes", "Fichajes", "bi-clock-history"))
        items.append(("horarios", "Horario y sección", "bi-clock"))
    items.append(("vacaciones", "Vacaciones", "bi-sun"))
    if person.company_user_id:
        items.append(("calendario", "Calendario", "bi-calendar3"))
        items.append(("partes", "Partes de trabajo", "bi-file-earmark-text"))
    if _refuel_user(person) is not None:
        items.append(("repostajes", "Repostajes", "bi-fuel-pump"))
    return items


class PersonMenuView(CompanyUserRequiredMixin, View):
    """
    GET: the worker's name and the menu entries (JSON).
    ---
    GET: el nombre del trabajador y las entradas del menú (JSON).
    """

    def get(self, request, pk):
        person = _person(pk)
        name = ("%s %s, %s" % (person.first_surname, person.second_surname,
                               person.given_name)).replace("  ", " ")
        return JsonResponse({
            "name": name.strip(),
            "items": [
                {"code": code, "label": label, "icon": icon,
                 "url": reverse("panel:person_go", args=[person.pk, code])}
                for code, label, icon in _destinations(request, person)
            ],
        })


def _set_filters(company_user, screen_key, filters):
    """
    Leave a tab's saved filters pointing at one worker.
    ---
    Deja los filtros guardados de una pestaña apuntando a un
    trabajador (conserva las demás claves del estado, como la
    selección).
    """
    from panel.models import PanelNavigationState

    obj, _created = PanelNavigationState.objects.get_or_create(
        company_user=company_user, screen_key=screen_key,
        defaults={"state": {}},
    )
    state = obj.state if isinstance(obj.state, dict) else {}
    saved = state.get("filters") if isinstance(
        state.get("filters"), dict) else {}
    state["filters"] = {**saved, **filters}
    obj.state = state
    obj.save(update_fields=["state", "updated_at"])


def _set_hub_tab_filters(company_user, tab, filters):
    """
    The documentation hub keeps some tabs' filters under filters[tab].
    ---
    El hub de Documentación guarda los filtros de algunas pestañas en
    filters[pestaña] (Personal, Calendario).
    """
    from panel.models import PanelNavigationState

    obj, _created = PanelNavigationState.objects.get_or_create(
        company_user=company_user, screen_key="documentation_hub",
        defaults={"state": {}},
    )
    state = obj.state if isinstance(obj.state, dict) else {}
    all_filters = state.get("filters") if isinstance(
        state.get("filters"), dict) else {}
    all_filters[tab] = filters
    state["filters"] = all_filters
    obj.state = state
    obj.save(update_fields=["state", "updated_at"])


class PersonGoView(CompanyUserRequiredMixin, View):
    """
    GET: go to one view of the worker, with its filter already set.
    ---
    GET: ir a una vista del trabajador con su filtro ya puesto.
    """

    def get(self, request, pk, code):
        person = _person(pk)
        if code not in {c for c, _l, _i in _destinations(request, person)}:
            raise Http404
        cu = request.user.company_user
        hub = reverse("panel:documentation_hub")
        if code == "ficha":
            return redirect("panel:documentation_personal_detail", pk=pk)
        if code == "fichajes":
            return redirect("panel:clock_worker", pk=pk)
        if code == "horarios":
            _set_filters(cu, "worker_schedules", {
                "search": person.dni, "active": "", "company": "",
                "section": "", "schedule": ""})
            return redirect(hub + "?tab=horarios")
        if code == "vacaciones":
            _set_filters(cu, "vacation_balance", {
                "search": person.dni, "active": "", "company": "",
                "section": ""})
            return redirect(hub + "?tab=vacaciones")
        if code == "calendario":
            _set_hub_tab_filters(cu, "calendario", {
                "operator_pk": str(person.company_user_id), "group_pk": ""})
            return redirect(hub + "?tab=calendario")
        if code == "partes":
            return redirect(reverse("panel:work_order_admin_history")
                            + "?operator_pk=%d" % person.company_user_id)
        if code == "repostajes":
            from panel.views_refuels import VIEW_SUPPLIES

            _set_filters(cu, "refuels", {
                "view": VIEW_SUPPLIES, "search": _refuel_user(person).name})
            return redirect(hub + "?tab=repostajes")
        raise Http404
