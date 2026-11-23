# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/new_ui/notice_core.py
"""
Helpers of the document notices (Avisos), new interface.

---

Auxiliares de los avisos de documentos para la nueva interfaz (S163),
copia de panel/views_document_alerts.py (validar los avisos de cada
requisito, ámbitos de los destinatarios, estado de las peticiones al
trabajador, «Subir» y «Cita solicitada» de los documentos que aporta la
empresa), sin depender de ella.
"""
import json

from django.contrib.contenttypes.models import ContentType
from django.utils import timezone

from document_explorer.models import (
    DocumentIndexEntry, DocumentTypeCatalog, JobPosition,
    NoticeAppointmentRequest, NoticeRecipientScope, PersonGroupTemplate,
    PersonIdentity, RequirementAlertRule, WorkerDocumentRequest,
    WorkerDocumentSubmission,
)
from document_explorer.notice_recipients import (
    CompanyKeyResolver, docs_supervisors,
)
from document_explorer.person_phone_service import mobile_of
from fleet.models import MachineAsset
from ivr_config.models import CompanyUser

# Tipos que aporta la empresa con «Cita solicitada» en su aviso.
APPOINTMENT_TYPE_CODES = ("RECONOCIMIENTO_MEDICO",)


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
        or editor.role in CompanyUser.ADMIN_ROLES
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
                "whatsapp": bool(
                    scopes.get(supervisor.pk)
                    and scopes[supervisor.pk].whatsapp_enabled
                ),
                "scope": _scope_to_dict(
                    scopes.get(supervisor.pk), company_options, resolver,
                ),
            }
            for supervisor in supervisors
        ],
        "options": {
            "personal_companies": company_options,
            "personal_groups": [
                # S147: con su ruta ("Plataformas › Comercial").
                {"id": g.pk, "label": g.path_label()}
                for g in sorted(
                    PersonGroupTemplate.objects.select_related(
                        "parent__parent"),
                    key=lambda g: g.path_label().upper(),
                )
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


def _annotate_worker_requests(pending, can_request_docs):
    """
    Request state and "can be requested" flag of each personal notice.

    ---

    Estado de la solicitud al trabajador y marca "se puede pedir" de
    cada aviso de Personal (H30, S125). Se puede pedir si quien mira
    puede dar luz verde, el tipo lo aporta el trabajador, la persona
    tiene móvil válido y no hay ya una solicitud abierta. Pedir no
    exige acceso al panel (Miguel Ángel, S126). Plantillas tontas: el
    texto del estado se decide aquí.
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
    _annotate_company_documents(pending, people, can_request_docs)


def _open_appointments(pending):
    """
    Open "appointment requested" marks of the pending notices.

    ---

    Marcas "Cita solicitada" abiertas de los avisos pendientes, por
    (persona, tipo): la más reciente sin anular y sin un documento de
    ese tipo de la persona entrado después de pedirla (entonces la cita
    ya tuvo respuesta y la marca se cierra sola).
    """
    person_ids = {notice.subject_id for notice in pending}
    person_ct = ContentType.objects.get_for_model(PersonIdentity)
    latest = {}
    for appointment in NoticeAppointmentRequest.objects.filter(
        person_id__in=person_ids, cancelled_at__isnull=True,
    ).select_related("requested_by__user"):
        key = (appointment.person_id, appointment.document_type_id)
        if key not in latest:
            latest[key] = appointment
    open_marks = {}
    for key, appointment in latest.items():
        answered = DocumentIndexEntry.objects.filter(
            domain_content_type=person_ct,
            domain_object_id=appointment.person_id,
            document_type_id=appointment.document_type_id,
            indexed_at__gte=appointment.requested_at,
            deleted_at__isnull=True,
            purged_at__isnull=True,
        ).exists()
        if not answered:
            open_marks[key] = appointment
    return open_marks


def _annotate_company_documents(pending, people, can_manage):
    """
    Upload and "appointment requested" data of each personal notice.

    ---

    Datos de las acciones de los avisos de documentos que aporta la
    EMPRESA, no el trabajador (H30, S126, punto 2): "Subir" el documento
    directamente a la ficha desde la fila del aviso y, en el
    reconocimiento médico, "Cita solicitada" con quién y cuándo.
    Plantillas tontas: textos y flags se deciden aquí.
    """
    types = DocumentTypeCatalog.objects.in_bulk({
        notice.document_type_id for notice in pending
        if notice.document_type_id
    })
    appointments = _open_appointments(pending)
    for notice in pending:
        doc_type = types.get(notice.document_type_id)
        company_provided = bool(
            doc_type is not None and not doc_type.worker_provides
        )
        notice.can_upload = bool(
            can_manage and company_provided
            and people.get(notice.subject_id) is not None
        )
        notice.upload_key = "%s:%s" % (
            notice.subject_id, notice.document_type_id,
        )
        notice.upload_date_label = (
            "Fecha de caducidad" if doc_type and doc_type.tracks_expiry
            else "Fecha del documento"
        )
        notice.can_mark_appointment = bool(
            notice.can_upload and doc_type.code in APPOINTMENT_TYPE_CODES
        )
        appointment = appointments.get(
            (notice.subject_id, notice.document_type_id),
        )
        notice.appointment_state = ""
        if notice.can_mark_appointment and appointment is not None:
            who = appointment.requested_by
            notice.appointment_state = "Cita solicitada el %s%s" % (
                timezone.localtime(appointment.requested_at).strftime(
                    "%d/%m/%Y %H:%M",
                ),
                " por %s" % (
                    who.user.get_full_name() or who.user.username
                ) if who else "",
            )


def _person_and_type(person_pk, type_pk):
    """
    The worker and document type of a notice action, or None.

    ---

    Trabajador y tipo documental de una acción sobre un aviso, o None
    si alguno no existe.
    """
    person = PersonIdentity.objects.filter(pk=person_pk).first()
    doc_type = DocumentTypeCatalog.objects.filter(pk=type_pk).first()
    if person is None or doc_type is None:
        return None
    return person, doc_type


def _person_label(person):
    """
    "SURNAMES, Name" of a worker.

    ---

    "APELLIDOS, Nombre" del trabajador.
    """
    surnames = " ".join(
        part for part in (person.first_surname, person.second_surname)
        if part
    )
    return "%s, %s" % (surnames, person.given_name)
