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
from urllib.parse import urlencode

from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.views import View

from document_explorer import document_notice_service as notices
from document_explorer.models import (
    DocumentTypeCatalog, JobPosition, PersonIdentity, RequirementAlertRule,
)
from document_management.models import DocumentAlertSettings
from fleet.models import MachineAsset
from ivr_config.models import CompanyUser
from panel.mixins import CompanyUserRequiredMixin, SupervisorAccessMixin
from panel.models import PanelNavigationState

NAV_SCREEN_KEY = "documentation_hub"
NAV_TAB_KEY = "avisos"
MONTH_NAMES = (
    "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio",
    "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
)
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


def _persisted_tab_state(company_user):
    """
    Saved navigation of the "Avisos" tab (4.15), always a dict.

    ---

    Navegación guardada de la pestaña "Avisos" (directriz 4.15):
    subpestaña, requisito elegido en Configuración y filtros de
    Pendientes. Siempre un dict (vacío si no hay nada guardado).
    """
    nav_state = PanelNavigationState.objects.filter(
        company_user=company_user, screen_key=NAV_SCREEN_KEY,
    ).first()
    state = nav_state.state if nav_state else None
    if not isinstance(state, dict):
        return {}
    filters = state.get("filters")
    if not isinstance(filters, dict):
        return {}
    tab_state = filters.get(NAV_TAB_KEY)
    return tab_state if isinstance(tab_state, dict) else {}


def _int_or_none(value):
    """
    int(value) or None.

    ---

    Entero o None si no se puede convertir.
    """
    try:
        return int(value)
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

        tab_state = _persisted_tab_state(company_user)
        selected_pk = _int_or_none(tab_state.get("position"))
        if selected_pk not in {item["id"] for item in positions_data}:
            selected_pk = None
        subtab = tab_state.get("subtab")
        if subtab not in ("pendientes", "configuracion"):
            subtab = "pendientes"
        notices_query = {
            key: str(tab_state.get(key) or "")
            for key in ("domain", "requirement", "doc_type", "q")
        }

        return render(request, "panel/document_alerts/pane.html", {
            "positions_data": positions_data,
            "selected_position_pk": selected_pk,
            "active_subtab": subtab,
            "tab_state": {
                "subtab": subtab,
                "position": selected_pk,
                **notices_query,
            },
            "notices_url": "%s?%s" % (
                reverse("panel:document_notices"),
                urlencode({
                    key: value for key, value in notices_query.items()
                    if value
                }),
            ),
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


class DocumentNoticesView(CompanyUserRequiredMixin, View):
    """
    GET: "Pendientes" sub-tab (fragment, htmx).

    ---

    GET: subpestaña "Pendientes" de Avisos (fragmento, htmx). Miguel
    Ángel: dos paneles -- lo que ya toca avisar (caducados, próximos
    con su fecha de aviso alcanzada, y faltantes) y el calendario
    completo de avisos futuros -- "la vista dividida en paneles
    verticales y horizontales agrupando temáticas [...] paneles
    scrollables con partes fijas". Conmutador Personal / Centros de
    gasto; filtros por requisito, tipo y texto. Todo se decide aquí;
    la plantilla solo pinta.
    """

    def get(self, request):
        domain = request.GET.get("domain")
        if domain not in (notices.DOMAIN_PERSONAL, notices.DOMAIN_MACHINE):
            domain = notices.DOMAIN_PERSONAL
        requirement_pk = _int_or_none(request.GET.get("requirement"))
        doc_type_pk = _int_or_none(request.GET.get("doc_type"))
        query = (request.GET.get("q") or "").strip()

        pending, _scheduled, calendar_items = notices.compute_notices(
            domain,
        )

        requirement_names = sorted({n.requirement_name for n in pending} | {
            item.notice.requirement_name for item in calendar_items
        })
        requirement_options = list(
            JobPosition.objects.filter(name__in=requirement_names)
            .order_by("name").values("pk", "name"),
        )
        type_ids = {
            n.document_type_id for n in pending
        } | {item.notice.document_type_id for item in calendar_items}
        type_options = list(
            DocumentTypeCatalog.objects.filter(pk__in=type_ids)
            .order_by("label").values("pk", "label"),
        )

        # Un filtro que no existe en este dominio (p. ej. tras cambiar
        # de Personal a Centros de gasto) se descarta, nunca vacía la
        # lista sin motivo visible.
        requirement_name = next((
            option["name"] for option in requirement_options
            if option["pk"] == requirement_pk
        ), None)
        if requirement_name is None:
            requirement_pk = None
        if doc_type_pk not in {option["pk"] for option in type_options}:
            doc_type_pk = None

        def keep(notice):
            if (
                requirement_name is not None
                and notice.requirement_name != requirement_name
            ):
                return False
            if (
                doc_type_pk is not None
                and notice.document_type_id != doc_type_pk
            ):
                return False
            if query and query.lower() not in (
                "%s %s" % (notice.subject_label, notice.document_label)
            ).lower():
                return False
            return True

        pending = [notice for notice in pending if keep(notice)]
        calendar_items = [
            item for item in calendar_items if keep(item.notice)
        ]
        detail_url_name = (
            "panel:documentation_personal_detail"
            if domain == notices.DOMAIN_PERSONAL
            else "panel:documentation_machine_detail"
        )
        for notice in pending:
            notice.detail_url = reverse(
                detail_url_name, kwargs={"pk": notice.subject_id},
            )
        for item in calendar_items:
            item.notice.detail_url = reverse(
                detail_url_name, kwargs={"pk": item.notice.subject_id},
            )

        calendar_months = []
        for item in calendar_items:
            month_key = item.trigger_date.strftime("%Y-%m")
            if not calendar_months or calendar_months[-1]["key"] != month_key:
                calendar_months.append({
                    "key": month_key,
                    "label": "%s %d" % (
                        MONTH_NAMES[item.trigger_date.month - 1],
                        item.trigger_date.year,
                    ),
                    "items": [],
                })
            calendar_months[-1]["items"].append(item)

        for notice in pending:
            # Plantillas tontas: días ya calculados en positivo.
            if notice.days_left is not None and notice.days_left < 0:
                notice.days_ago = -notice.days_left
        if domain == notices.DOMAIN_PERSONAL:
            has_subjects = PersonIdentity.objects.filter(
                is_active_employee=True, job_position__isnull=False,
            ).exists()
        else:
            has_subjects = MachineAsset.objects.filter(
                is_active=True, document_requirement__isnull=False,
            ).exists()

        expired = [n for n in pending if n.kind == notices.KIND_EXPIRED]
        upcoming = [n for n in pending if n.kind == notices.KIND_UPCOMING]
        missing = [n for n in pending if n.kind == notices.KIND_MISSING]
        return render(request, "panel/document_alerts/_notices.html", {
            "domain": domain,
            "is_personal": domain == notices.DOMAIN_PERSONAL,
            "requirement_options": requirement_options,
            "type_options": type_options,
            "selected_requirement": requirement_pk,
            "selected_doc_type": doc_type_pk,
            "query": query,
            "expired": expired,
            "upcoming": upcoming,
            "missing": missing,
            "calendar_months": calendar_months,
            "calendar_count": len(calendar_items),
            "has_any_rules": RequirementAlertRule.objects.exists(),
            "has_subjects": has_subjects,
        })
