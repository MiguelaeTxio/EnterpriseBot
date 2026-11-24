# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/new_ui/views_requirements.py
"""
Documentation requirements in the new interface (S163).

---

Requisitos de documentación en la nueva interfaz (S163), copiados del
gestor antiguo (panel/views_documentation_h30.py JobPosition*,
PersonMassSetJobPositionView; fleet/views.py
MachineAssetBulkSetDocumentRequirementView):
- Documentos › Lista de requisitos: crear y modificar (tipos de
  documento de Personal, de Centros de gasto y comunes, y clases del
  permiso de conducción), activar o desactivar, borrar, y pasar un tipo
  de la categoría 1 a la 2 o al revés.
- Personal / Centros de gasto: añadir o quitar un requisito a los
  marcados (varios por persona o máquina).
El catálogo es único (personas y máquinas); los cambios en masa van por
document_explorer.required_documentation_service, como allí.
"""
from collections import OrderedDict

from django.db import IntegrityError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views import View

from document_explorer.models import (
    DocumentTypeCatalog, DrivingLicenceCategory, JobPosition,
    PersonIdentity,
)
from fleet.models import MachineAsset
from new_ui.mixins import SuperuserRequiredMixin
from new_ui.views_dossiers import FAMILY_COLORS

GROUP_OF_DOMAIN = {
    DocumentTypeCatalog.DOMAIN_PERSONAL: "personal",
    DocumentTypeCatalog.DOMAIN_EPI: "personal",
    DocumentTypeCatalog.DOMAIN_MACHINE: "machine",
}
GROUP_TITLES = (
    ("personal", "Personal"),
    ("machine", "Centros de gasto"),
    ("common", "Comunes (personas, máquinas y empresa)"),
)


def _ok(message, **extra):
    return JsonResponse({"ok": True, "message": message, **extra})


def _error(message):
    return JsonResponse({"ok": False, "message": message}, status=400)


def _ids(request):
    return [v for v in request.POST.getlist("selected") if v.isdigit()]


def requirement_sections():
    """
    Catalog types split into Personal, cost centres and common, by family.

    ---

    Todo el catálogo activo, separado en Personal (persona y EPI),
    Centros de gasto (máquina) y Comunes, y dentro por familia con su
    color; cada tipo con su categoría (1 esencial / 2 resto).
    """
    by_group = OrderedDict((key, OrderedDict()) for key, _t in GROUP_TITLES)
    known = [code for code, _label in DocumentTypeCatalog.FAMILY_CHOICES]
    types = DocumentTypeCatalog.objects.filter(is_active=True).order_by(
        "family", "label")
    for dt in types:
        group = GROUP_OF_DOMAIN.get(dt.domain, "common")
        by_group[group].setdefault(dt.family or "", []).append(dt)
    out = []
    for group, title in GROUP_TITLES:
        families = by_group[group]
        codes = [c for c in known if c in families]
        codes += sorted(c for c in families if c and c not in known)
        if "" in families:
            codes.append("")
        sections = [{
            "title": DocumentTypeCatalog.family_label(
                code, for_person=group == "personal") if code
            else "Sin familia",
            "color": FAMILY_COLORS.get(code, "#f5f5f5"),
            "items": [(dt.pk, dt.label, dt.requirement_category)
                      for dt in families[code]],
        } for code in codes]
        if sections:
            out.append({"key": group, "title": title, "sections": sections})
    return out


def requirements_context(section):
    """
    Context of the requirement actions of a section.

    ---

    Documentos: el editor de requisitos. Personal y Centros de gasto:
    los requisitos para añadir o quitar a los marcados.
    """
    if section == "doc":
        return {
            "req_groups": requirement_sections(),
            "req_driving": list(DrivingLicenceCategory.objects.order_by(
                "display_order", "code")),
            "req_categories": DocumentTypeCatalog.REQUIREMENT_CATEGORY_CHOICES,
        }
    if section in ("per", "cdg"):
        return {"req_positions": list(JobPosition.objects.order_by("name"))}
    return {}


class RequirementDataView(SuperuserRequiredMixin, View):
    """
    GET: one requirement as form fields.

    ---

    GET: un requisito como campos del formulario.
    """

    def get(self, request, pk):
        position = get_object_or_404(JobPosition, pk=pk)
        return JsonResponse({"ok": True, "title": position.name, "fields": {
            "position_pk": str(position.pk), "name": position.name,
            "document_type_ids": [str(pk) for pk in
                                  position.required_document_types
                                  .values_list("pk", flat=True)],
            "driving_category_ids": [str(pk) for pk in
                                     position.required_driving_categories
                                     .values_list("pk", flat=True)],
        }})


class RequirementSaveView(SuperuserRequiredMixin, View):
    """
    POST: create a requirement, or change one (`position_pk`).

    ---

    POST: crea un requisito o modifica uno: nombre (único), tipos de
    documento obligatorios y clases de permiso exigidas. Se puede
    guardar sin ningún tipo (se sigue perfilando después).
    """

    def post(self, request):
        raw = request.POST.get("position_pk", "").strip()
        if raw:
            position = get_object_or_404(
                JobPosition, pk=raw if raw.isdigit() else 0)
        else:
            position = JobPosition(created_by=request.user.company_user)
        name = request.POST.get("name", "").strip()
        if not name:
            return _error("Falta el nombre del requisito.")
        # S163 (24/11), como en la antigua: desde el visor, con otro
        # nombre se crea uno nuevo con lo marcado y el original no se toca.
        if (position.pk and request.POST.get("rename_as_new") == "1"
                and name != position.name):
            position = JobPosition(created_by=request.user.company_user)
        created = position.pk is None
        position.name = name
        try:
            position.save()
        except IntegrityError:
            return _error("Ya existe un requisito con ese nombre.")
        position.required_document_types.set(
            request.POST.getlist("document_type_ids"))
        position.required_driving_categories.set(
            request.POST.getlist("driving_category_ids"))
        return _ok("Requisito «%s» %s." % (
            name, "creado" if created else "guardado"), id=position.pk)


class RequirementBulkView(SuperuserRequiredMixin, View):
    """
    POST `action` on the marked requirements: activate, deactivate, delete.

    ---

    POST sobre los requisitos marcados: activar, desactivar (no genera
    avisos, pero sigue asignado) o borrar (quien lo tuviera se queda sin
    él; las personas y máquinas no se tocan).
    """

    def post(self, request):
        positions = JobPosition.objects.filter(pk__in=_ids(request))
        names = list(positions.values_list("name", flat=True))
        if not names:
            return _error("Marca primero los requisitos.")
        action = request.POST.get("action", "")
        if action in ("activate", "deactivate"):
            positions.update(is_active=action == "activate",
                             updated_at=timezone.now())
            return _ok("%s: %s." % (
                "Activados" if action == "activate" else "Desactivados",
                ", ".join(names)))
        if action == "delete":
            positions.delete()
            return _ok("Borrados: %s." % ", ".join(names))
        return _error("Acción no válida.")


class TypeCategoryView(SuperuserRequiredMixin, View):
    """
    POST: move one document type to category 1 or 2.

    ---

    POST: pasa un tipo de documento a la categoría 1 (esencial) o 2
    (resto) desde el propio gestor de requisitos.
    """

    def post(self, request):
        category = request.POST.get("category", "")
        valid = {str(code) for code, _label
                 in DocumentTypeCatalog.REQUIREMENT_CATEGORY_CHOICES}
        doc_type = DocumentTypeCatalog.objects.filter(
            pk=request.POST.get("type_id") or 0).first()
        if doc_type is None or category not in valid:
            return _error("Elige el tipo y la categoría.")
        doc_type.requirement_category = int(category)
        doc_type.save(update_fields=["requirement_category"])
        return _ok("%s pasa a la %s." % (
            doc_type.label, dict(DocumentTypeCatalog
                                 .REQUIREMENT_CATEGORY_CHOICES)[
                int(category)].lower()))


class RequirementAssignView(SuperuserRequiredMixin, View):
    """
    POST: add or remove a requirement on the marked persons/machines.

    ---

    POST a las personas (per) o máquinas (cdg) marcadas: `mode=add`
    añade el requisito elegido sin tocar los demás; `mode=remove` lo
    quita (sin requisito elegido, les quita todos).
    """

    def post(self, request, section):
        from document_explorer.required_documentation_service import (
            MASS_ADD, MASS_REMOVE, bulk_change_requirements,
        )

        model = {"per": PersonIdentity, "cdg": MachineAsset}.get(section)
        ids = _ids(request)
        if model is None or not ids:
            return _error("Marca primero en el listado a quién.")
        mode = request.POST.get("mode", "")
        raw = request.POST.get("position_id", "").strip()
        position = JobPosition.objects.filter(
            pk=raw if raw.isdigit() else 0).first()
        if mode not in (MASS_ADD, MASS_REMOVE) or (
                mode == MASS_ADD and position is None):
            return _error("Elige el requisito que añadir.")
        if raw and position is None:
            return _error("Ese requisito ya no existe.")
        updated = bulk_change_requirements(model, ids, mode, position)
        noun = "persona(s)" if section == "per" else "centro(s) de gasto"
        if mode == MASS_ADD:
            what = "con el requisito «%s» añadido" % position.name
        elif position is not None:
            what = "sin el requisito «%s»" % position.name
        else:
            what = "sin requisitos de documentación"
        return _ok("%d %s %s." % (updated, noun, what))


class RequirementSheetView(SuperuserRequiredMixin, View):
    """
    GET: one requirement in the viewer, edited like the old screen.

    ---

    GET: un requisito en el visor (al pulsar su fila), como el gestor
    antiguo (panel/_doc_type_picker.html, S128): nombre y Guardar
    (otro nombre crea uno nuevo), activar, desactivar y eliminar; los
    documentos por familias con su color, Personal / Centros de gasto /
    Todos y categoría 1 / 2 / ambas (lo marcado se ve siempre), marcar
    o desmarcar al vuelo, cambiar categorías y, a la derecha, lo
    marcado.
    """

    def get(self, request, pk):
        position = get_object_or_404(JobPosition, pk=pk)
        marked = set(position.required_document_types.values_list(
            "pk", flat=True))
        groups = requirement_sections()
        chosen = []
        for group in groups:
            for section in group["sections"]:
                section["items"] = [
                    {"pk": pk_, "label": label, "cat": cat,
                     "on": pk_ in marked}
                    for pk_, label, cat in section["items"]]
                chosen += [item["label"] for item in section["items"]
                           if item["on"]]
        driving = set(position.required_driving_categories.values_list(
            "pk", flat=True))
        return render(request, "new_ui/_requirement_sheet.html", {
            "position": position,
            "groups": groups,
            "chosen": chosen,
            "driving": [(c, c.pk in driving) for c in
                        DrivingLicenceCategory.objects.order_by(
                            "display_order", "code")],
            "chosen_driving": [c.code for c in
                               DrivingLicenceCategory.objects.filter(
                                   pk__in=driving).order_by(
                                   "display_order", "code")],
        })
