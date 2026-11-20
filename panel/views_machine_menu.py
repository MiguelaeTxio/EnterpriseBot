# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/views_machine_menu.py
"""
Right-click menu and technical card of a cost centre (S163, invasora).

---

Menú del botón derecho y tarjeta técnica de un centro de gasto (S163,
sesión invasora de UX). Miguel Ángel, en Especificaciones: al pulsar
una máquina "mostrar una tarjeta técnica de la máquina en cuestión, no
la ficha", y el menú contextual propio de la aplicación, que solo
existía para los trabajadores (panel/views_person_menu.py, S144), en
todas las vistas.

- `machine_destinations`: los destinos de una máquina que el usuario
  puede abrir (sin consultas: el rol y el código bastan). Lo usan el
  menú del botón derecho y el menú de tres puntos de las filas.
- `MachineMenuView` (JSON): el menú del botón derecho
  (panel/static/panel/js/context_menu.js).
- `MachineGoView`: deja puesto el filtro de la pestaña de destino y
  redirige (la pestaña abre ya con esa máquina).
- `MachineCardView`: la tarjeta técnica (fragmento HTML de una ventana).
"""
from django.http import Http404, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views import View

from fleet.models import MachineAsset
from panel.mixins import CompanyUserRequiredMixin, FleetAccessMixin

# Código de destino -> (texto, icono). El orden es el del menú.
CARD = "tarjeta"
_LABELS = {
    CARD: ("Tarjeta técnica", "bi-card-list"),
    "ficha": ("Ficha del centro de gasto", "bi-truck"),
    "libro": ("Libro historial", "bi-journal-text"),
    "revisiones_firmadas": ("Revisiones del libro", "bi-clipboard-check"),
    "partes": ("Partes de taller", "bi-tools"),
    "averias": ("Averías", "bi-exclamation-triangle"),
    "revisiones": ("Revisiones (horas y km)", "bi-wrench-adjustable"),
    "repostajes": ("Repostajes", "bi-fuel-pump"),
    "equipos": ("Equipos", "bi-people"),
    "especificaciones": ("Especificaciones", "bi-rulers"),
}
# Pestañas del hub de Documentación: (screen_key, filtros que se fijan).
_HUB_TABS = {
    "revisiones": ("service_tab", "revisiones"),
    "especificaciones": ("specs_tab", "especificaciones"),
    "equipos": ("crews", "equipos"),
}


def _machine(request, pk):
    machine = MachineAsset.objects.filter(
        pk=pk, company=request.user.company_user.company,
    ).first()
    if machine is None:
        raise Http404
    return machine


def machine_destinations(company_user, machine):
    """
    [(code, label, icon)] the user can open for this cost centre.
    ---
    Los destinos de este centro de gasto que puede abrir el usuario. El
    taller (libro, partes, averías) con los mismos roles que Centros de
    gasto (FleetAccessMixin); el libro y sus revisiones, solo en las
    máquinas que lo llevan (grúas A y H).
    """
    workshop = company_user.role in FleetAccessMixin.allowed_roles
    codes = [CARD, "ficha"]
    if workshop and machine.is_logbook_crane:
        codes += ["libro", "revisiones_firmadas"]
    if workshop:
        codes += ["partes", "averias"]
    codes += ["revisiones", "repostajes", "equipos", "especificaciones"]
    return [(code,) + _LABELS[code] for code in codes]


def machine_menu_items(company_user, machine):
    """
    The menu entries ready to paint: label, icon, url and card flag.
    ---
    Las entradas del menú listas para pintar. La tarjeta técnica se abre
    en una ventana (`card`: True), el resto son enlaces.
    """
    items = []
    for code, label, icon in machine_destinations(company_user, machine):
        if code == CARD:
            url = reverse("panel:machine_card", args=[machine.pk])
        else:
            url = reverse("panel:machine_go", args=[machine.pk, code])
        items.append({
            "code": code, "label": label, "icon": icon, "url": url,
            "card": code == CARD,
        })
    return items


def machine_title(machine):
    """
    "A59 · LIEBHERR LTM 1230-5.1 · 1234ABC" for headers.
    ---
    Rótulo corto del centro de gasto para cabeceras.
    """
    return " · ".join(
        part for part in (machine.code, machine.brand_model, machine.plate)
        if part
    )


class MachineMenuView(CompanyUserRequiredMixin, View):
    """
    GET: the cost centre's name and the menu entries (JSON).
    ---
    GET: el rótulo del centro de gasto y las entradas del menú (JSON).
    """

    def get(self, request, pk):
        machine = _machine(request, pk)
        return JsonResponse({
            "name": machine_title(machine),
            "items": machine_menu_items(
                request.user.company_user, machine),
        })


def _set_filters(company_user, screen_key, filters):
    """
    Leave a list's saved filters pointing at one cost centre.
    ---
    Deja los filtros guardados de un listado apuntando a un centro de
    gasto (conserva las demás claves del estado, como la selección).
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


class MachineGoView(CompanyUserRequiredMixin, View):
    """
    GET: go to one view of the cost centre, with its filter already set.
    ---
    GET: ir a una vista del centro de gasto. Las pestañas del hub abren
    ya filtradas por su código, sin los demás filtros que pudieran
    ocultarlo (familia, estado, grupo).
    """

    def get(self, request, pk, code):
        machine = _machine(request, pk)
        company_user = request.user.company_user
        allowed = {c for c, _l, _i in machine_destinations(
            company_user, machine)}
        if code not in allowed or code == CARD:
            raise Http404
        if code == "ficha":
            return redirect("panel:documentation_machine_detail", pk=pk)
        if code == "libro":
            return redirect("panel:machine_workshop_logbooks", pk=pk)
        if code == "revisiones_firmadas":
            return redirect("panel:machine_workshop_reviews", pk=pk)
        if code == "partes":
            return redirect("panel:machine_workshop_tasks", pk=pk)
        if code == "averias":
            return redirect("panel:machine_workshop_tickets", pk=pk)
        hub = reverse("panel:documentation_hub")
        if code == "repostajes":
            from panel.views_refuels import VIEW_VEHICLES

            _set_filters(company_user, "refuels", {
                "view": VIEW_VEHICLES, "search": machine.code})
            return redirect(hub + "?tab=repostajes")
        screen_key, tab = _HUB_TABS[code]
        filters = {"search": machine.code, "group": ""}
        if code in ("revisiones", "especificaciones"):
            filters.update({"family": "", "is_active": ""})
        if code == "especificaciones":
            filters.update({
                "cap_min": "", "cap_max": "", "tm_min": "", "tm_max": "",
                "mma_min": "", "mma_max": "", "with_specs": "0",
            })
        if code == "equipos":
            filters["state"] = ""
        _set_filters(company_user, screen_key, filters)
        return redirect(hub + "?tab=" + tab)


def _metres(value_mm):
    if value_mm is None:
        return ""
    return ("%.2f" % (value_mm / 1000)).replace(".", ",") + " m"


def _number(value, unit=""):
    if value is None or value == "":
        return ""
    text = ("%.2f" % value).rstrip("0").rstrip(".").replace(".", ",")
    return text + (" " + unit if unit else "")


def card_sections(machine):
    """
    [(title, [(label, value)])] of the technical card (empty values out).
    ---
    Los apartados de la tarjeta técnica, solo con los datos que tiene
    la máquina. Todo resuelto aquí; la plantilla solo pinta.
    """
    mma = machine.max_authorized_mass_kg
    identification = [
        ("Marca y modelo", machine.brand_model),
        ("Tipo", machine.type_name),
        ("Familia", machine.family),
        ("Matrícula", machine.plate),
        ("Nº de bastidor", machine.chassis_number),
        ("Nº de serie de la grúa", machine.crane_serial_number),
        ("Año de fabricación", machine.manufacture_year or ""),
        ("Primera matriculación", (
            machine.first_registration_date.strftime("%d/%m/%Y")
            if machine.first_registration_date else "")),
        ("Categoría ITV", machine.itv_category),
        ("Empresa", machine.company_name),
        ("Estado", "Activo" if machine.is_active else "Inactivo"),
    ]
    elevation = [
        ("Capacidad de elevación", _number(machine.capacity_tonnes, "t")),
        ("Capacidad máxima (según libro)", machine.max_capacity),
        ("Momento de carga", _number(machine.capacity_tm, "t·m")),
    ]
    weights = [
        ("Masa máxima autorizada", (
            "%s (%s kg)" % (_number(mma / 1000, "t"),
                            "{:,}".format(mma).replace(",", "."))
            if mma else "")),
        ("Masa", (
            "{:,} kg".format(machine.mass_kg).replace(",", ".")
            if machine.mass_kg else "")),
        ("Número de ejes", machine.axle_count or ""),
        ("Masa por eje", machine.axle_mass),
        ("Largo", _metres(machine.length_mm)),
        ("Ancho", _metres(machine.width_mm)),
        ("Alto", _metres(machine.height_mm)),
    ]
    owner = [
        ("Primer propietario", machine.first_owner_name),
        ("NIF/CIF", machine.first_owner_tax_id),
        ("Domicilio", machine.first_owner_address),
        ("C.P. y población", machine.first_owner_city),
    ]
    sections = []
    for title, rows in (
        ("Identificación", identification),
        ("Elevación", elevation),
        ("Pesos y dimensiones", weights),
        ("Titularidad inicial", owner),
    ):
        rows = [(label, value) for label, value in rows if value != ""
                and value is not None]
        if rows:
            sections.append((title, rows))
    return sections


class MachineCardView(CompanyUserRequiredMixin, View):
    """
    GET: the technical card of a cost centre (window fragment).
    ---
    GET: la tarjeta técnica del centro de gasto: identificación,
    elevación, pesos y dimensiones, titularidad inicial y de dónde se
    leyeron los datos; abajo, los accesos (libro historial, ficha...).
    """

    def get(self, request, pk):
        machine = _machine(request, pk)
        company_user = request.user.company_user
        avatar = machine.avatar_document
        return render(request, "panel/machine_card/_card.html", {
            "machine": machine,
            "title": machine_title(machine),
            "sections": card_sections(machine),
            "avatar_url": (
                reverse("panel:documentation_document_view",
                        args=[avatar.pk])
                if avatar is not None and not avatar.deleted_at else ""
            ),
            "links": [
                item for item in machine_menu_items(company_user, machine)
                if not item["card"]
            ],
            "specs_read_at": machine.specs_read_at,
            "specs_source": machine.specs_source,
        })
