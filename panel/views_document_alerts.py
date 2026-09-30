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
    DocumentTypeCatalog, JobPosition, NoticeRecipientScope,
    PersonGroupTemplate, PersonIdentity, RequirementAlertRule,
    WorkerDocumentRequest, WorkerDocumentSubmission,
)
from document_explorer.person_phone_service import mobile_of
from document_explorer.worker_request_service import create_requests
from document_explorer.notice_recipients import (
    RECIPIENT_ROLES, CompanyKeyResolver, docs_supervisors, load_scopes,
    recipients_for,
)
from document_management.models import DocumentAlertSettings
from fleet.models import MachineAsset
from ivr_config.models import CompanyUser
from panel.mixins import (
    CompanyUserRequiredMixin, DocsUploadAccessMixin, SupervisorAccessMixin,
)
from panel.models import PanelNavigationState

NAV_SCREEN_KEY = "documentation_hub"
NAV_TAB_KEY = "avisos"
MONTH_NAMES = (
    "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio",
    "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
)
# H30 (S125): quién da luz verde para pedir documentación al trabajador.
DOC_REQUEST_ROLES = {
    CompanyUser.ROLE_DOCS_SUPERVISOR,
    CompanyUser.ROLE_ADMIN,
}
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


def _can_edit_scope(editor, supervisor):
    """
    True if `editor` may edit the notice scope of `supervisor`.

    ---

    Cada supervisor edita su propio ámbito y el administrador todos
    (decisión de Miguel Ángel, S122).
    """
    return (
        editor.pk == supervisor.pk
        or editor.role == CompanyUser.ROLE_ADMIN
    )


def _personal_company_options():
    """
    Employer companies of the active workers, sorted.

    ---

    Empresas empleadoras de los trabajadores activos, ordenadas (las
    opciones de "Empresas" en Personal).
    """
    return sorted(
        value for value in set(
            PersonIdentity.objects.filter(
                is_active_employee=True,
            ).values_list("employer_company", flat=True),
        ) if value
    )


def _current_companies(values, options, resolver):
    """
    Stored company texts translated to the current option spelling.

    ---

    Traduce las empresas guardadas en el ámbito a la grafía de la
    opción actual de la misma empresa (S126: "TRANSGRUAL S.L." guardado
    antes de normalizar -> "TRANSGRUAL SL"), para que la casilla salga
    marcada y al guardar quede la grafía vigente. Lo que no casa con
    ninguna opción se devuelve tal cual (la pantalla lo muestra aparte,
    nunca oculto).
    """
    by_key = {resolver.key(option): option for option in options}
    result = []
    for value in values:
        current = by_key.get(resolver.key(value), value)
        if current not in result:
            result.append(current)
    return result


def _scope_to_dict(scope, company_options=None, resolver=None):
    """
    Serialize one NoticeRecipientScope (or None) for the client.

    ---

    Serializa el ámbito de un supervisor para el cliente; sin ficha,
    todo vacío (no recibe nada). Con `company_options` y `resolver`,
    las empresas salen en la grafía de las opciones actuales.
    """
    if scope is None:
        return {
            "personal_all": False, "personal_companies": [],
            "personal_groups": [], "personal_persons": [],
            "machine_all": False, "machine_families": [],
            "machine_companies": [], "machines": [],
            "excluded_requirements": [], "excluded_document_types": [],
        }
    return {
        "personal_all": scope.personal_all,
        "personal_companies": (
            _current_companies(
                scope.personal_companies, company_options, resolver,
            ) if resolver is not None
            else list(scope.personal_companies)
        ),
        "personal_groups": [g.pk for g in scope.personal_groups.all()],
        "personal_persons": [p.pk for p in scope.personal_persons.all()],
        "machine_all": scope.machine_all,
        "machine_families": list(scope.machine_families),
        "machine_companies": list(scope.machine_companies),
        "machines": [m.pk for m in scope.machines.all()],
        "excluded_requirements": [
            r.pk for r in scope.excluded_requirements.all()
        ],
        "excluded_document_types": [
            t.pk for t in scope.excluded_document_types.all()
        ],
    }


def _recipients_context(editor):
    """
    Supervisors, their scopes and the option lists of "Destinatarios".

    ---

    Datos de la sección "Destinatarios": supervisores de documentación
    con su ámbito y si el usuario actual puede editarlo, y las listas
    de opciones reales (empresas, grupos, personas, familias, máquinas,
    requisitos y documentos).
    """
    supervisors = docs_supervisors(editor.company)
    resolver = CompanyKeyResolver()
    company_options = _personal_company_options()
    scopes = {
        scope.company_user_id: scope
        for scope in NoticeRecipientScope.objects.filter(
            company_user__in=supervisors,
        ).prefetch_related(
            "personal_groups", "personal_persons", "machines",
            "excluded_requirements", "excluded_document_types",
        )
    }
    active_people = PersonIdentity.objects.filter(is_active_employee=True)
    active_machines = MachineAsset.objects.filter(is_active=True)
    required_type_ids = set(
        JobPosition.required_document_types.through.objects.values_list(
            "documenttypecatalog_id", flat=True,
        ),
    )
    return {
        "supervisors": [
            {
                "id": supervisor.pk,
                "name": (
                    supervisor.user.get_full_name()
                    or supervisor.user.username
                ),
                "can_edit": _can_edit_scope(editor, supervisor),
                "is_me": supervisor.pk == editor.pk,
                "scope": _scope_to_dict(
                    scopes.get(supervisor.pk), company_options, resolver,
                ),
            }
            for supervisor in supervisors
        ],
        "options": {
            "personal_companies": company_options,
            "personal_groups": [
                {"id": g.pk, "label": g.name}
                for g in PersonGroupTemplate.objects.order_by("name")
            ],
            "personal_persons": [
                {
                    "id": p.pk,
                    "label": "%s %s, %s" % (
                        p.first_surname, p.second_surname or "",
                        p.given_name,
                    ),
                }
                for p in active_people.order_by(
                    "first_surname", "second_surname", "given_name",
                )
            ],
            "machine_families": sorted(
                value for value in set(
                    active_machines.values_list("family", flat=True),
                ) if value
            ),
            "machine_companies": sorted(
                value for value in set(
                    active_machines.values_list(
                        "company_code", flat=True,
                    ),
                ) if value
            ),
            "machines": [
                {"id": m.pk, "label": "%s -- %s" % (m.code, m.brand_model)}
                for m in active_machines.order_by("code")
            ],
            "excluded_requirements": [
                {"id": r.pk, "label": r.name}
                for r in JobPosition.objects.order_by("name")
            ],
            "excluded_document_types": [
                {"id": t.pk, "label": t.label}
                for t in DocumentTypeCatalog.objects.filter(
                    pk__in=required_type_ids,
                ).order_by("label")
            ],
        },
    }


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
            for key in ("domain", "requirement", "doc_type", "q", "who")
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
            "recipients_data": _recipients_context(company_user),
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


def _annotate_worker_requests(pending, can_request_docs):
    """
    Request state and "can be requested" flag of each personal notice.

    ---

    Estado de la solicitud al trabajador y marca "se puede pedir" de
    cada aviso de Personal (H30, S125). Se puede pedir si quien mira
    puede dar luz verde, el tipo lo aporta el trabajador, la persona
    tiene móvil válido y acceso al panel, y no hay ya una solicitud
    abierta. Plantillas
    tontas: el texto del estado se decide aquí.
    """
    person_ids = {notice.subject_id for notice in pending}
    people = PersonIdentity.objects.select_related(
        "company_user__user",
    ).in_bulk(person_ids)
    worker_type_ids = set(
        DocumentTypeCatalog.objects.filter(worker_provides=True)
        .values_list("pk", flat=True)
    )
    open_requests = {
        (req.person_id, req.document_type_id): req
        for req in WorkerDocumentRequest.objects.filter(
            person_id__in=person_ids,
            status__in=WorkerDocumentRequest.OPEN_STATUSES,
        )
    }
    last_rejected = {}
    for submission in WorkerDocumentSubmission.objects.filter(
        request__in=list(open_requests.values()),
        status=WorkerDocumentSubmission.STATUS_REJECTED,
    ).order_by("created_at"):
        last_rejected[submission.request_id] = submission
    for notice in pending:
        notice.request_key = "%s:%s" % (
            notice.subject_id, notice.document_type_id,
        )
        request_obj = open_requests.get(
            (notice.subject_id, notice.document_type_id),
        )
        notice.request_state = ""
        notice.request_state_class = "text-bg-info"
        if request_obj is not None:
            rejected = last_rejected.get(request_obj.pk)
            if request_obj.send_error:
                notice.request_state = (
                    "WhatsApp no enviado: %s" % request_obj.send_error
                )
                notice.request_state_class = "text-bg-danger"
            elif rejected is not None:
                notice.request_state = "Entregado no conforme: %s" % (
                    rejected.reason.removeprefix("No conforme: ")
                )
                notice.request_state_class = "text-bg-warning"
            elif request_obj.status == WorkerDocumentRequest.STATUS_SENT:
                notice.request_state = "Pedido por WhatsApp el %s" % (
                    request_obj.sent_at.strftime("%d/%m %H:%M")
                )
            else:
                notice.request_state = "En cola para pedir por WhatsApp"
        person = people.get(notice.subject_id)
        notice.is_requestable = bool(
            can_request_docs and request_obj is None
            and notice.document_type_id in worker_type_ids
            and person is not None and mobile_of(person)
        )


class DocumentRequestCreateView(DocsUploadAccessMixin, View):
    """
    POST: green light to ask the selected workers for their documents.

    ---

    POST: luz verde del supervisor para pedir por WhatsApp a los
    trabajadores seleccionados los documentos que les faltan o
    caducan (H30, S125). Cuerpo JSON {"items": ["persona:tipo", ...]}.
    Responde JSON con un resumen legible -- la pantalla lo muestra,
    ninguna acción en silencio.
    """

    def post(self, request):
        try:
            payload = json.loads(request.body.decode("utf-8") or "{}")
        except (ValueError, UnicodeDecodeError):
            return JsonResponse(
                {"ok": False, "error": "Petición no válida."}, status=400,
            )
        pairs = []
        for item in payload.get("items") or []:
            person_id, _, type_id = str(item).partition(":")
            if person_id.isdigit() and type_id.isdigit():
                pairs.append((int(person_id), int(type_id)))
        if not pairs:
            return JsonResponse(
                {"ok": False, "error": "No hay nada seleccionado."},
                status=400,
            )
        summary = create_requests(pairs, request.user.company_user)
        lines = ["Solicitudes nuevas: %d. Enviadas ahora por WhatsApp: %d." % (
            summary["queued"], summary["sent"],
        )]
        if summary["queued"] > summary["sent"]:
            lines.append(
                "El resto queda en cola: se pide al trabajador cuando "
                "entregue el anterior."
            )
        lines.extend("No enviado -- %s" % e for e in summary["send_errors"])
        lines.extend("Descartado -- %s" % e for e in summary["skipped"])
        return JsonResponse({"ok": True, "message": "\n".join(lines)})


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
        # H30 (S122): a quién va cada aviso. Un supervisor de
        # documentación ve por defecto solo los suyos; el administrador
        # también puede recibirlos y filtrar los suyos (S126).
        company_user = request.user.company_user
        is_supervisor = (
            company_user.role == CompanyUser.ROLE_DOCS_SUPERVISOR
        )
        can_filter_mine = company_user.role in RECIPIENT_ROLES
        who = request.GET.get("who")
        valid_who = ("mine", "all", "none") if can_filter_mine else (
            "all", "none",
        )
        if who not in valid_who:
            who = "mine" if is_supervisor else "all"

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

        scopes = load_scopes(company_user.company)
        all_notices = pending + [item.notice for item in calendar_items]
        for notice in all_notices:
            if not hasattr(notice, "recipient_names"):
                recipients = recipients_for(notice, scopes)
                notice.recipient_ids = {r.pk for r in recipients}
                notice.recipient_names = ", ".join(
                    r.user.get_full_name() or r.user.username
                    for r in recipients
                )

        def keep(notice):
            if who == "mine" and company_user.pk not in notice.recipient_ids:
                return False
            if who == "none" and notice.recipient_ids:
                return False
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

        can_request_docs = (
            domain == notices.DOMAIN_PERSONAL
            and company_user.role in DOC_REQUEST_ROLES
        )
        if domain == notices.DOMAIN_PERSONAL:
            _annotate_worker_requests(pending, can_request_docs)

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
            "who": who,
            "can_filter_mine": can_filter_mine,
            "can_request_docs": can_request_docs,
        })


class NoticeScopeSaveView(CompanyUserRequiredMixin, View):
    """
    POST: save the notice scope of one documentation supervisor.

    ---

    POST: guarda el ámbito de avisos de un destinatario (supervisor de
    documentación o administrador, S126) (JSON `scope`). Solo el propio
    destinatario o el administrador.
    Valores fuera de las opciones reales se descartan.
    """

    def post(self, request, supervisor_pk):
        editor = request.user.company_user
        supervisor = get_object_or_404(
            CompanyUser, pk=supervisor_pk, company=editor.company,
            role__in=RECIPIENT_ROLES,
        )
        if not _can_edit_scope(editor, supervisor):
            return JsonResponse(
                {"ok": False, "error": "Solo el propio supervisor o el "
                 "administrador pueden cambiar estos avisos."},
                status=403,
            )
        try:
            payload = json.loads(request.POST.get("scope") or "{}")
        except ValueError:
            payload = None
        if not isinstance(payload, dict):
            return JsonResponse(
                {"ok": False, "error": "Los datos enviados no son válidos."},
                status=400,
            )

        def ids(key):
            return [
                _int_or_none(value) for value in payload.get(key) or []
                if _int_or_none(value) is not None
            ]

        def texts(key):
            return [
                str(value) for value in payload.get(key) or [] if value
            ]

        with transaction.atomic():
            scope, _created = NoticeRecipientScope.objects.get_or_create(
                company_user=supervisor,
            )
            scope.personal_all = bool(payload.get("personal_all"))
            scope.personal_companies = texts("personal_companies")
            scope.machine_all = bool(payload.get("machine_all"))
            scope.machine_families = texts("machine_families")
            scope.machine_companies = texts("machine_companies")
            scope.updated_by = editor
            scope.save()
            scope.personal_groups.set(
                PersonGroupTemplate.objects.filter(
                    pk__in=ids("personal_groups"),
                ),
            )
            scope.personal_persons.set(
                PersonIdentity.objects.filter(
                    pk__in=ids("personal_persons"),
                ),
            )
            scope.machines.set(
                MachineAsset.objects.filter(pk__in=ids("machines")),
            )
            scope.excluded_requirements.set(
                JobPosition.objects.filter(
                    pk__in=ids("excluded_requirements"),
                ),
            )
            scope.excluded_document_types.set(
                DocumentTypeCatalog.objects.filter(
                    pk__in=ids("excluded_document_types"),
                ),
            )
        scope = NoticeRecipientScope.objects.prefetch_related(
            "personal_groups", "personal_persons", "machines",
            "excluded_requirements", "excluded_document_types",
        ).get(pk=scope.pk)
        return JsonResponse({"ok": True, "scope": _scope_to_dict(
            scope, _personal_company_options(), CompanyKeyResolver(),
        )})
