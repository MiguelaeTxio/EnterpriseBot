# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/views_document_alerts.py
"""
H30 (S122). "Avisos" tab of the Documentation hub: notice settings of
each documentation requirement and the switch of the automatic
WhatsApp sending.

---

H30 (S122). Pestaña "Avisos" del hub de Documentación. Miguel Ángel:
"separar lo que es la gestión de los requisitos [...] crear una
pestaña nueva [...] de alertas donde ya no es necesario presentar el
listado de documentos, sino el listado de requisitos con el visor de
los documentos que va a llevar cada requisito y los avisos que vamos
a asignar a esos documentos". La creación de requisitos sigue en su
propia pestaña, sin cambios.

Aquí vive también el interruptor del envío automático por WhatsApp
(`DocumentAlertSettings`), apagado mientras la documentación no esté
al día.
"""
import json

from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views import View

from document_explorer.models import JobPosition, RequirementAlertRule
from document_management.models import DocumentAlertSettings
from ivr_config.models import CompanyUser
from panel.mixins import CompanyUserRequiredMixin, SupervisorAccessMixin
from panel.models import PanelNavigationState

NAV_SCREEN_KEY = "documentation_hub"
NAV_TAB_KEY = "avisos"
WHATSAPP_TOGGLE_ROLES = {
    CompanyUser.ROLE_SUPERVISOR,
    CompanyUser.ROLE_WORKSHOPBOSS,
    CompanyUser.ROLE_ADMIN,
}


class AlertRuleError(Exception):
    """
    Invalid notice configuration (message ready to show).

    ---

    Configuración de avisos no válida (mensaje listo para mostrar).
    """


def _alert_rule_to_dict(rule):
    """
    Serialize one RequirementAlertRule for the client.

    ---

    Serializa un RequirementAlertRule para el cliente (mismas claves
    que envía el JS al guardar).
    """
    return {
        "missing": rule.notify_missing,
        "d30": rule.notify_30_days,
        "d15": rule.notify_15_days,
        "d7": rule.notify_7_days,
        "d1": rule.notify_day_before,
        "c1v": rule.custom_1_value,
        "c1u": rule.custom_1_unit,
        "c2v": rule.custom_2_value,
        "c2u": rule.custom_2_unit,
    }


def _parse_custom_notice(raw_value, raw_unit, slot, type_label):
    """
    Validate one custom notice (amount + unit).

    ---

    Valida un aviso personalizado (número + unidad). Vacío = sin
    aviso. Devuelve (valor, unidad) o lanza AlertRuleError.
    """
    if raw_value in (None, ""):
        return None, ""
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        raise AlertRuleError(
            "Aviso personalizado %d de '%s': la antelación debe ser un "
            "número entero." % (slot, type_label)
        )
    valid_units = {code for code, _ in RequirementAlertRule.UNIT_CHOICES}
    if value < 1 or value > 999 or raw_unit not in valid_units:
        raise AlertRuleError(
            "Aviso personalizado %d de '%s': indica una antelación "
            "entre 1 y 999 y si son días o meses." % (slot, type_label)
        )
    return value, raw_unit


def _parse_alert_rules(raw_json, required_types):
    """
    Parse and validate the notices of a requirement's mandatory types.

    ---

    Lee y valida la configuración de avisos enviada por el cliente
    (JSON {id_tipo: {...}}) para los tipos obligatorios REALES del
    requisito -- cualquier otro id se ignora. Los avisos de caducidad
    se fuerzan a False en tipos sin caducidad (`tracks_expiry=False`):
    la verdad es el catálogo, nunca el cliente.
    """
    try:
        payload = json.loads(raw_json or "{}")
    except ValueError:
        raise AlertRuleError("La configuración de avisos no es válida.")
    if not isinstance(payload, dict):
        raise AlertRuleError("La configuración de avisos no es válida.")

    parsed = {}
    for doc_type in required_types:
        config = payload.get(str(doc_type.pk)) or {}
        tracks = doc_type.tracks_expiry
        custom_1 = (None, "")
        custom_2 = (None, "")
        if tracks:
            custom_1 = _parse_custom_notice(
                config.get("c1v"), config.get("c1u"), 1, doc_type.label,
            )
            custom_2 = _parse_custom_notice(
                config.get("c2v"), config.get("c2u"), 2, doc_type.label,
            )
        parsed[doc_type.pk] = {
            "notify_missing": bool(config.get("missing")),
            "notify_30_days": tracks and bool(config.get("d30")),
            "notify_15_days": tracks and bool(config.get("d15")),
            "notify_7_days": tracks and bool(config.get("d7")),
            "notify_day_before": tracks and bool(config.get("d1")),
            "custom_1_value": custom_1[0],
            "custom_1_unit": custom_1[1],
            "custom_2_value": custom_2[0],
            "custom_2_unit": custom_2[1],
        }
    return parsed


def _persisted_position_pk(company_user):
    """
    Requirement selected last time in this tab (4.15).

    ---

    Requisito seleccionado la última vez en esta pestaña, guardado en
    `PanelNavigationState` (directriz 4.15), o None.
    """
    nav_state = PanelNavigationState.objects.filter(
        company_user=company_user, screen_key=NAV_SCREEN_KEY,
    ).first()
    state = nav_state.state if nav_state else None
    if not isinstance(state, dict):
        return None
    filters = state.get("filters")
    if not isinstance(filters, dict):
        return None
    tab_state = filters.get(NAV_TAB_KEY)
    if not isinstance(tab_state, dict):
        return None
    try:
        return int(tab_state.get("position"))
    except (TypeError, ValueError):
        return None


class DocumentAlertsPaneView(CompanyUserRequiredMixin, View):
    """
    GET: "Avisos" tab fragment (loaded by htmx in the hub).

    ---

    GET: fragmento de la pestaña "Avisos" (lo carga htmx en el hub).
    Lista de requisitos a un lado; al elegir uno, el visor muestra
    sus documentos obligatorios con sus avisos. Todo el catálogo de
    requisitos viaja en un único JSON para que cambiar de requisito
    no requiera otra petición.
    """

    def get(self, request):
        company_user = request.user.company_user
        positions = JobPosition.objects.prefetch_related(
            "required_document_types",
        ).order_by("name")
        rules_by_position = {}
        for rule in RequirementAlertRule.objects.all():
            rules_by_position.setdefault(rule.job_position_id, {})[
                str(rule.document_type_id)
            ] = _alert_rule_to_dict(rule)

        positions_data = []
        for position in positions:
            rules = rules_by_position.get(position.pk, {})
            types = sorted(
                position.required_document_types.all(),
                key=lambda doc_type: doc_type.label,
            )
            positions_data.append({
                "id": position.pk,
                "name": position.name,
                "types": [
                    {
                        "id": doc_type.pk,
                        "label": doc_type.label,
                        "tracks_expiry": doc_type.tracks_expiry,
                    }
                    for doc_type in types
                ],
                "rules": rules,
            })

        selected_pk = _persisted_position_pk(company_user)
        if selected_pk not in {item["id"] for item in positions_data}:
            selected_pk = None

        return render(request, "panel/document_alerts/pane.html", {
            "positions_data": positions_data,
            "selected_position_pk": selected_pk,
            "whatsapp_enabled": DocumentAlertSettings.is_whatsapp_enabled(
                company_user.company,
            ),
            "can_toggle_whatsapp": (
                company_user.role in WHATSAPP_TOGGLE_ROLES
            ),
        })


class DocumentAlertRulesSaveView(CompanyUserRequiredMixin, View):
    """
    POST: save the notices of one requirement's mandatory documents.

    ---

    POST: guarda los avisos de los documentos obligatorios de un
    requisito. Valida todo antes de escribir y escribe en una sola
    transacción; los avisos de tipos que ya no son obligatorios en el
    requisito se borran.
    """

    def post(self, request, position_pk):
        position = get_object_or_404(JobPosition, pk=position_pk)
        required_types = list(position.required_document_types.all())
        try:
            rules = _parse_alert_rules(
                request.POST.get("alert_rules"), required_types,
            )
        except AlertRuleError as exc:
            return JsonResponse(
                {"ok": False, "error": str(exc)}, status=400,
            )

        with transaction.atomic():
            RequirementAlertRule.objects.filter(
                job_position=position,
            ).exclude(document_type_id__in=rules.keys()).delete()
            for type_pk, fields in rules.items():
                RequirementAlertRule.objects.update_or_create(
                    job_position=position,
                    document_type_id=type_pk,
                    defaults=fields,
                )

        saved = {
            str(rule.document_type_id): _alert_rule_to_dict(rule)
            for rule in RequirementAlertRule.objects.filter(
                job_position=position,
            )
        }
        return JsonResponse({"ok": True, "rules": saved})


class DocumentAlertWhatsAppToggleView(SupervisorAccessMixin, View):
    """
    POST: switch the automatic WhatsApp sending on or off.

    ---

    POST: enciende o apaga el envío automático por WhatsApp de los
    avisos de la empresa del usuario (`enabled` = "1" o "0").
    """

    def post(self, request):
        company_user = request.user.company_user
        enabled = request.POST.get("enabled") == "1"
        settings_row, _created = (
            DocumentAlertSettings.objects.get_or_create(
                company=company_user.company,
            )
        )
        settings_row.whatsapp_enabled = enabled
        settings_row.updated_by = company_user
        settings_row.save(
            update_fields=["whatsapp_enabled", "updated_by", "updated_at"],
        )
        return JsonResponse({"ok": True, "enabled": enabled})
