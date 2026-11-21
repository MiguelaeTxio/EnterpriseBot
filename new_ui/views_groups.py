# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/new_ui/views_groups.py
"""
Save and delete of selection groups from the new interface.

---

Guardar y borrar grupos de selección desde la nueva interfaz (S163):
copia adaptada de PersonGroupTemplateSaveView/DeleteView
(panel/views_documentation_h30.py) y MachineGroupSaveView/DeleteView
(panel/views_machine_groups.py), con las reglas de new_ui/groups.py.
`kind` en la ruta: "personas" o "maquinas". Los grupos son datos
comunes con la interfaz antigua (los mismos que se ven en ella).
"""

import re

from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404
from django.template.loader import render_to_string
from django.views import View

from document_explorer.models import PersonIdentity
from new_ui.groups import (
    MACHINE_KIND, PERSON_KIND, GroupError, delete_group, group_tree,
    parent_choices, save_group,
)
from new_ui.mixins import SuperuserRequiredMixin

TREE_TEMPLATE = "new_ui/_groups_tree.html"


def _kind(kind):
    if kind == "personas":
        return PERSON_KIND
    if kind == "maquinas":
        return MACHINE_KIND
    raise Http404


def _group_model(kind):
    from django.apps import apps

    if kind is MACHINE_KIND:
        return apps.get_model("fleet", "MachineGroupTemplate")
    return apps.get_model("document_explorer", "PersonGroupTemplate")


def _tree_payload(request, kind):
    editor = request.user.company_user
    return {
        "tree_html": render_to_string(TREE_TEMPLATE, {
            "person_group_nodes": group_tree(editor, kind),
            "pg_id": re.sub(r"[^A-Za-z0-9_-]", "",
                            request.POST.get("pg_id", ""))[:40] or "nuiGroup",
        }, request=request),
        "parents": parent_choices(editor=editor, kind=kind),
    }


class GroupSaveView(SuperuserRequiredMixin, View):
    """
    POST: create a group (no pk) or change one; repainted tree back.

    ---

    POST: crea un grupo (sin pk) o cambia uno (nombre, dónde va y sus
    miembros). Devuelve el árbol repintado. Solo quien lo creó lo
    cambia (save_group).
    """

    def post(self, request, kind, group_pk=None):
        group_kind = _kind(kind)
        model = _group_model(group_kind)
        editor = request.user.company_user
        if group_pk:
            group = get_object_or_404(model, pk=group_pk)
        else:
            group = model(created_by=editor)
        if group_kind is MACHINE_KIND:
            member_ids = [pk for pk in request.POST.getlist("machine_ids")
                          if pk.isdigit()]
        else:
            member_ids = [pk for pk in request.POST.getlist("person_ids")
                          if pk.isdigit()]
            user_ids = [pk for pk in request.POST.getlist("user_ids")
                        if pk.isdigit()]
            if user_ids:
                member_ids += [str(pk) for pk in PersonIdentity.objects.filter(
                    company_user_id__in=user_ids).values_list("pk", flat=True)]
        try:
            group, members = save_group(
                group, request.POST.get("name", ""),
                request.POST.get("parent_id", ""),
                sorted(set(member_ids)), editor=editor, kind=group_kind,
            )
        except GroupError as exc:
            return JsonResponse({"ok": False, "error": str(exc)}, status=400)
        payload = {"ok": True, "id": group.pk, "name": group.name}
        payload.update(_tree_payload(request, group_kind))
        return JsonResponse(payload)


class GroupDeleteView(SuperuserRequiredMixin, View):
    """
    POST: delete a group without subgroups (never its members).

    ---

    POST: borra un grupo sin subgrupos (nunca toca a sus miembros).
    """

    def post(self, request, kind, group_pk):
        group_kind = _kind(kind)
        group = get_object_or_404(_group_model(group_kind), pk=group_pk)
        try:
            delete_group(group, editor=request.user.company_user)
        except GroupError as exc:
            return JsonResponse({"ok": False, "error": str(exc)}, status=400)
        payload = {"ok": True}
        payload.update(_tree_payload(request, group_kind))
        return JsonResponse(payload)
