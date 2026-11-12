# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/views_machine_alerts.py
"""
Notices of one cost centre (S148), from its own file.

---

Avisos de UN centro de gasto (S148), desde su ficha. Miguel Ángel:
"podemos dar avisos desde la propia pantalla de avisos para hacerlo de
forma masiva, pero sería conveniente también poder colocar avisos a
cada centro de gasto para los determinados documentos que tienen
caducidad". Mismos avisos que la pestaña Avisos (si falta, 30/15/7
días, día anterior y dos personalizados); para ese tipo y esa máquina
sustituyen a los de su requisito. Con todo desmarcado, la máquina
vuelve a los avisos del requisito.
"""
import json

from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views import View

from document_explorer.document_notice_service import (
    _custom_pairs,
    merge_rules,
)
from document_explorer.models import (
    DocumentTypeCatalog,
    MachineAlertRule,
    RequirementAlertRule,
)
from document_explorer.required_documentation_service import (
    get_requirements,
)
from fleet.models import MachineAsset
from panel.mixins import FleetManageAccessMixin
from panel.views_document_alerts import (
    AlertRuleError,
    _alert_rule_to_dict,
    _parse_alert_rules,
)

_NOTICE_FIELDS = (
    "notify_missing", "notify_30_days", "notify_15_days", "notify_7_days",
    "notify_day_before", "custom_1_value", "custom_2_value",
)


def _machine_types():
    return list(DocumentTypeCatalog.objects.filter(
        is_active=True,
        domain__in=(DocumentTypeCatalog.DOMAIN_MACHINE,
                    DocumentTypeCatalog.DOMAIN_BOTH),
    ).exclude(family=DocumentTypeCatalog.FAMILY_MEDIA).order_by("label"))


def machine_alerts_context(machine, present_type_ids):
    """
    Data of the "Avisos" block of the machine file (json_script).
    ---
    Datos del bloque "Avisos" de la ficha: tipos con aviso del
    requisito o propio, o con caducidad entre sus documentos; y el
    resto de tipos con caducidad para añadir.
    """
    types = _machine_types()
    # S153: varios requisitos por máquina; las reglas de un mismo tipo
    # se juntan como en la pestaña Avisos (merge_rules).
    requirements = get_requirements(machine)
    grouped = {}
    for rule in RequirementAlertRule.objects.filter(
            job_position__in=requirements).select_related("document_type"):
        grouped.setdefault(rule.document_type_id, []).append(rule)
    requirement_rules = {
        type_id: _merged_rule_to_dict(merge_rules(rules))
        for type_id, rules in grouped.items()
    }
    own_rules = {
        rule.document_type_id: _alert_rule_to_dict(rule)
        for rule in MachineAlertRule.objects.filter(machine=machine)
    }
    shown, others = [], []
    for doc_type in types:
        item = {
            "id": doc_type.pk, "label": doc_type.label,
            "tracks_expiry": doc_type.tracks_expiry,
            "requirement": requirement_rules.get(doc_type.pk),
            "own": own_rules.get(doc_type.pk),
        }
        if (doc_type.pk in requirement_rules or doc_type.pk in own_rules
                or (doc_type.tracks_expiry
                    and doc_type.pk in present_type_ids)):
            shown.append(item)
        elif doc_type.tracks_expiry:
            others.append(item)
    return {
        "machine_alerts_data": {
            "shown": shown, "others": others,
            "requirement": (
                ", ".join(req.name for req in requirements)
                if requirement_rules else ""),
        },
        "machine_alerts_own_count": len(own_rules),
    }


def _merged_rule_to_dict(rule):
    """
    Serialize a requirement rule (single or merged) for the client.
    ---
    S153. Serializa una regla de requisito, sola o combinada de varios
    requisitos, con las mismas claves que `_alert_rule_to_dict` (la
    ficha solo la muestra; caben dos avisos personalizados).
    """
    pairs = [pair for pair in _custom_pairs(rule) if pair[0] and pair[1]]
    pairs += [(None, "")] * (2 - len(pairs))
    return {
        "missing": rule.notify_missing,
        "d30": rule.notify_30_days,
        "d15": rule.notify_15_days,
        "d7": rule.notify_7_days,
        "d1": rule.notify_day_before,
        "c1v": pairs[0][0],
        "c1u": pairs[0][1],
        "c2v": pairs[1][0],
        "c2u": pairs[1][1],
    }


class MachineAlertRulesSaveView(FleetManageAccessMixin, View):
    """
    POST alert_rules (JSON {type_id: config}): the machine's own notices.
    ---
    POST con los avisos propios de la máquina. Un tipo con todo
    desmarcado se borra (vuelve a los del requisito). Valida todo antes
    de escribir; una sola transacción.
    """

    def post(self, request, pk):
        machine = get_object_or_404(
            MachineAsset, pk=pk, company=request.user.company_user.company)
        try:
            payload = json.loads(request.POST.get("alert_rules") or "{}")
        except ValueError:
            payload = None
        if not isinstance(payload, dict):
            return JsonResponse(
                {"ok": False, "error": "Configuración no válida."},
                status=400)
        types = [t for t in _machine_types() if str(t.pk) in payload]
        try:
            rules = _parse_alert_rules(json.dumps(payload), types)
        except AlertRuleError as exc:
            return JsonResponse({"ok": False, "error": str(exc)}, status=400)
        editor = request.user.company_user
        with transaction.atomic():
            for type_pk, fields in rules.items():
                if not any(fields[name] for name in _NOTICE_FIELDS):
                    MachineAlertRule.objects.filter(
                        machine=machine, document_type_id=type_pk,
                    ).delete()
                    continue
                MachineAlertRule.objects.update_or_create(
                    machine=machine, document_type_id=type_pk,
                    defaults=dict(fields, updated_by=editor),
                )
        return JsonResponse({"ok": True, "rules": {
            str(rule.document_type_id): _alert_rule_to_dict(rule)
            for rule in MachineAlertRule.objects.filter(machine=machine)
        }})
