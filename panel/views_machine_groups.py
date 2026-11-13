# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/views_machine_groups.py
"""
Save and delete of the machine selection groups (H31, S148), the
"Grupos de selección" box of the "Centros de Gasto" tab. Same rules as
the people groups (panel/person_groups.py with MACHINE_KIND).

---

Guardar y borrar grupos de selección de máquinas (H31, S148), el
recuadro "Grupos de selección" de Centros de Gasto. Miguel Ángel:
"Vamos a hacer lo mismo que en personal, creando los grupos de
selección". Mismas reglas que los de personas (panel/person_groups.py
con MACHINE_KIND): solo quien lo creó lo cambia o lo borra.
"""
import re

from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.template.loader import render_to_string
from django.views import View

from fleet.models import MachineGroupTemplate
from panel.mixins import FleetAccessMixin
from panel.person_groups import (
    MACHINE_KIND,
    GroupError,
    delete_group,
    group_tree,
    parent_choices,
    save_group,
)

TREE_TEMPLATE = "panel/documentation_h30/_person_groups_tree.html"


def _tree_payload(request):
    """
    Repainted tree and "Dentro de" choices after a change.

    ---

    Árbol repintado y opciones de "Dentro de" tras un cambio.
    """
    editor = request.user.company_user
    return {
        "tree_html": render_to_string(TREE_TEMPLATE, {
            "person_group_nodes": group_tree(editor, MACHINE_KIND),
            # S153: ids del árbol de la vista que pide (el mismo recuadro
            # en Centros de gasto, Revisiones, Repostajes, Avisos...).
            "pg_id": re.sub(r"[^A-Za-z0-9_-]", "",
                            request.POST.get("pg_id", ""))[:40]
            or "machineGroup",
        }, request=request),
        "parents": parent_choices(editor=editor, kind=MACHINE_KIND),
    }


class MachineGroupSaveView(FleetAccessMixin, View):
    """
    POST: creates a group (no pk) or updates one (name, parent and
    machines). Returns the repainted tree.

    ---

    POST: crea un grupo (sin pk) o cambia uno (nombre, dónde va y sus
    máquinas). Devuelve el árbol repintado.
    """

    def post(self, request, group_pk=None):
        editor = request.user.company_user
        if group_pk:
            group = get_object_or_404(MachineGroupTemplate, pk=group_pk)
        else:
            group = MachineGroupTemplate(created_by=editor)
        try:
            group, machines = save_group(
                group, request.POST.get("name", ""),
                request.POST.get("parent_id", ""),
                request.POST.getlist("machine_ids"),
                editor=editor, kind=MACHINE_KIND,
            )
        except GroupError as exc:
            return JsonResponse({"ok": False, "error": str(exc)}, status=400)
        payload = {"ok": True, "id": group.pk, "name": group.name}
        payload.update(_tree_payload(request))
        return JsonResponse(payload)


class MachineGroupDeleteView(FleetAccessMixin, View):
    """
    POST: deletes a group without subgroups (never the machines).

    ---

    POST: borra un grupo sin subgrupos (nunca toca las máquinas).
    """

    def post(self, request, group_pk):
        group = get_object_or_404(MachineGroupTemplate, pk=group_pk)
        try:
            delete_group(group, editor=request.user.company_user)
        except GroupError as exc:
            return JsonResponse({"ok": False, "error": str(exc)}, status=400)
        payload = {"ok": True}
        payload.update(_tree_payload(request))
        return JsonResponse(payload)
