# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/new_ui/views_notices.py
"""
Document notices (Documentos › Avisos pendientes / Configuración de
avisos), new interface.

---

Avisos de documentos en la nueva interfaz (S163), copiado de
panel/views_document_alerts.py y de la antelación de las revisiones
(panel/views_machine_service.py):
- Documentos › Avisos pendientes (vista propia): Personal o Centros de
  gasto, de quién (míos, todos, sin destinatario), requisito y tipo
  como botones y el buscador común; caducados, próximos, faltan y el
  calendario de avisos futuros. En cada aviso de Personal: casilla para
  pedirlo al trabajador por WhatsApp, «Subir» el documento que aporta
  la empresa y «Cita solicitada» del reconocimiento médico.
- Documentos › Configuración de avisos (vista propia): los avisos de
  cada documento obligatorio de cada requisito, el WhatsApp de mis
  avisos, la antelación de los avisos de revisión y los destinatarios
  (el ámbito de cada supervisor).
"""
import datetime
import json

from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views import View

from document_explorer import document_notice_service as notices
from document_explorer.models import (
    DocumentTypeCatalog, JobPosition, NoticeAppointmentRequest,
    NoticeRecipientScope, PersonGroupTemplate, PersonIdentity,
    RequirementAlertRule,
)
from document_explorer.notice_recipients import (
    RECIPIENT_ROLES, load_scopes, recipients_for,
)
from fleet.models import MachineAsset
from ivr_config.models import CompanyUser
from new_ui import notice_core as core
from new_ui.mixins import SuperuserRequiredMixin

NOTICE_UPLOAD_EXTENSIONS = ("pdf", "jpg", "jpeg", "png", "webp", "heic")
MONTH_NAMES = (
    "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio",
    "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
)
DOC_REQUEST_ROLES = {
    CompanyUser.ROLE_DOCS_SUPERVISOR, CompanyUser.ROLE_ADMIN,
    CompanyUser.ROLE_ADMIN_SUPERVISOR,
}
SERVICE_SETTINGS_ROLES = {"ADMIN", "ADMIN_SUPERVISOR", "DOCS_SUPERVISOR"}


def _ok(message):
    return JsonResponse({"ok": True, "message": message})


def _error(message, status=400):
    return JsonResponse({"ok": False, "message": message}, status=status)


def _allowed_subjects(request, domain):
    """
    pks allowed by the common filters (people or machines).

    ---

    Las personas o máquinas que dejan pasar los filtros comunes
    (estado, empresa, grupo, sección...): se aplican igual que en sus
    listados.
    """
    from new_ui.lists import filtered, list_def

    section = "per" if domain == notices.DOMAIN_PERSONAL else "cdg"
    company = request.user.company_user.company
    # S163 (24/11): «Buscar» no filtra aquí a las personas/máquinas: se
    # aplica a cada aviso (persona, máquina o documento), como la antigua.
    params = request.GET.copy()
    params.pop("q", None)
    return set(filtered(list_def(section, "general"), company,
                        params, None).values_list("pk", flat=True))


# ------------------------------------------------------- avisos pendientes
def render_pending(request):
    """
    Documentos › Avisos pendientes (see the module docstring).

    ---

    La vista de avisos pendientes: qué toca avisar ya y el calendario
    de los futuros, con los filtros de la vista y los comunes.
    """
    data = request.GET
    domain = data.get("av_domain")
    if domain not in (notices.DOMAIN_PERSONAL, notices.DOMAIN_MACHINE):
        domain = notices.DOMAIN_PERSONAL
    requirement_pk = core._int_or_none(data.get("av_req"))
    doc_type_pk = core._int_or_none(data.get("av_type"))
    query = (data.get("q") or "").strip()
    company_user = request.user.company_user
    can_filter_mine = company_user.role in RECIPIENT_ROLES
    who = data.get("av_who")
    valid_who = (("mine", "all", "none") if can_filter_mine
                 else ("all", "none"))
    if who not in valid_who:
        who = ("mine" if company_user.role == CompanyUser.ROLE_DOCS_SUPERVISOR
               else "all")
    allowed = _allowed_subjects(request, domain)
    pending, _scheduled, calendar_items = notices.compute_notices(
        domain, include_service=True)
    requirement_ids = {pk for n in pending for pk in n.requirement_ids} | {
        pk for item in calendar_items for pk in item.notice.requirement_ids}
    requirement_options = list(JobPosition.objects.filter(
        pk__in=requirement_ids).order_by("name").values("pk", "name"))
    type_ids = {n.document_type_id for n in pending} | {
        item.notice.document_type_id for item in calendar_items}
    type_options = list(DocumentTypeCatalog.objects.filter(
        pk__in=type_ids).order_by("label").values("pk", "label"))
    if requirement_pk not in {o["pk"] for o in requirement_options}:
        requirement_pk = None
    if doc_type_pk not in {o["pk"] for o in type_options}:
        doc_type_pk = None
    scopes = load_scopes(company_user.company)
    for notice in pending + [item.notice for item in calendar_items]:
        if not hasattr(notice, "recipient_names"):
            recipients = recipients_for(notice, scopes)
            notice.recipient_ids = {r.pk for r in recipients}
            notice.recipient_names = ", ".join(
                r.user.get_full_name() or r.user.username
                for r in recipients)

    def keep(notice):
        if notice.subject_id not in allowed:
            return False
        if who == "mine" and company_user.pk not in notice.recipient_ids:
            return False
        if who == "none" and notice.recipient_ids:
            return False
        if (requirement_pk is not None
                and requirement_pk not in notice.requirement_ids):
            return False
        if doc_type_pk is not None and notice.document_type_id != doc_type_pk:
            return False
        if query and not all(word in ("%s %s %s" % (
                notice.subject_label, notice.document_label,
                getattr(notice, "service_text", ""))).lower()
                for word in query.lower().split()):
            return False
        return True

    pending = [n for n in pending if keep(n)]
    calendar_items = [item for item in calendar_items if keep(item.notice)]
    months = []
    for item in calendar_items:
        key = item.trigger_date.strftime("%Y-%m")
        if not months or months[-1]["key"] != key:
            months.append({"key": key, "label": "%s %d" % (
                MONTH_NAMES[item.trigger_date.month - 1],
                item.trigger_date.year), "items": []})
        months[-1]["items"].append(item)
    for notice in pending:
        _texts(notice)
    for notice in pending + [item.notice for item in calendar_items]:
        notice.sheet_url = _sheet_url(notice)
    is_personal = domain == notices.DOMAIN_PERSONAL
    can_request_docs = (is_personal
                        and company_user.role in DOC_REQUEST_ROLES)
    if is_personal:
        core._annotate_worker_requests(pending, can_request_docs)
    has_service_plans = False
    if is_personal:
        has_subjects = PersonIdentity.objects.filter(
            is_active_employee=True,
            document_requirements__is_active=True).exists()
    else:
        has_service_plans = MachineAsset.objects.filter(
            Q(service_hours_interval__isnull=False)
            | Q(service_crane_hours_interval__isnull=False,
                has_crane_hours=True)
            | Q(service_every_km__gt=0), is_active=True).exists()
        has_subjects = has_service_plans or MachineAsset.objects.filter(
            is_active=True, document_requirements__is_active=True).exists()
    return render(request, "new_ui/_notices_pending.html", {
        "domain": domain,
        "is_personal": is_personal,
        "domains": ((notices.DOMAIN_PERSONAL, "Personal"),
                    (notices.DOMAIN_MACHINE, "Centros de gasto")),
        "who": who,
        "who_options": [(k, v) for k, v in (
            ("mine", "Míos"), ("all", "Todos"),
            ("none", "Sin destinatario")) if k in valid_who],
        "requirement_options": requirement_options,
        "type_options": type_options,
        "selected_requirement": requirement_pk,
        "selected_doc_type": doc_type_pk,
        "groups": [
            ("Caducados" if is_personal
             else "Caducados y revisiones vencidas",
             [n for n in pending if n.kind == notices.KIND_EXPIRED],
             "text-danger", "Ningún documento caducado.",
             "text-bg-danger"),
            ("Próximos a caducar" if is_personal
             else "Próximos a caducar y revisiones próximas",
             [n for n in pending if n.kind == notices.KIND_UPCOMING],
             "text-warning-emphasis",
             "Ningún aviso de caducidad ha llegado todavía.",
             "text-bg-warning"),
            ("Faltan",
             [n for n in pending if n.kind == notices.KIND_MISSING], "",
             "No falta ningún documento con aviso configurado.",
             "text-bg-secondary"),
        ],
        "calendar_months": months,
        "calendar_count": len(calendar_items),
        "has_any_rules": (RequirementAlertRule.objects.exists()
                          or (not is_personal and has_service_plans)),
        "has_subjects": has_subjects,
        "can_request_docs": can_request_docs,
    })


def _plural(count, word):
    return "%d %s%s" % (count, word, "" if count == 1 else "s")


def _texts(notice):
    """
    The «when» and «what» lines of a pending notice.

    ---

    Las dos líneas de cada aviso (cuándo y qué), resueltas aquí para
    que la plantilla solo pinte.
    """
    if getattr(notice, "is_service", False):
        notice.when_text = ("revisión vencida"
                            if notice.kind == notices.KIND_EXPIRED
                            else "revisión próxima")
        notice.what_text = "%s — %s" % (notice.document_label,
                                        notice.service_text)
    elif notice.kind == notices.KIND_MISSING:
        notice.when_text = getattr(notice, "requirement_name", "") or ""
        notice.what_text = "Falta: %s" % notice.document_label
    elif notice.kind == notices.KIND_EXPIRED:
        days = -(notice.days_left or 0)
        notice.when_text = "hace %s" % _plural(days, "día")
        notice.what_text = "%s — caducó el %s" % (
            notice.document_label, notice.expiry_date.strftime("%d/%m/%Y"))
    else:
        step = getattr(notice, "reached_step", None)
        notice.when_text = "faltan %s" % _plural(notice.days_left or 0,
                                                 "día")
        notice.what_text = "%s — caduca el %s%s" % (
            notice.document_label, notice.expiry_date.strftime("%d/%m/%Y"),
            " (aviso de %s)" % step.label if step is not None else "")


class NoticeRequestView(SuperuserRequiredMixin, View):
    """
    POST `selected` ("person:type"): ask the workers by WhatsApp.

    ---

    POST: luz verde para pedir por WhatsApp a los trabajadores los
    documentos marcados (los que faltan o caducan).
    """

    def post(self, request):
        from document_explorer.worker_request_service import create_requests

        pairs = []
        for item in request.POST.getlist("selected"):
            person_id, _sep, type_id = str(item).partition(":")
            if person_id.isdigit() and type_id.isdigit():
                pairs.append((int(person_id), int(type_id)))
        if not pairs:
            return _error("Marca primero los avisos que pedir (solo los "
                          "que se pueden pedir llevan casilla).")
        summary = create_requests(pairs, request.user.company_user)
        lines = ["Solicitudes nuevas: %d. Enviadas ahora por WhatsApp: %d."
                 % (summary["queued"], summary["sent"])]
        if summary["queued"] > summary["sent"]:
            lines.append("El resto queda en cola: se pide al trabajador "
                         "cuando entregue el anterior.")
        lines.extend("No enviado -- %s" % e for e in summary["send_errors"])
        lines.extend("Descartado -- %s" % e for e in summary["skipped"])
        return _ok(" ".join(lines))


class NoticeUploadView(SuperuserRequiredMixin, View):
    """
    POST `person`, `doc_type`, `file`, `date`: upload a company-provided
    document from its notice.

    ---

    POST: sube a la ficha del trabajador, desde su aviso, el documento
    que aporta la empresa (la fecha es la de caducidad si el tipo
    caduca; si no, la del documento).
    """

    def post(self, request):
        from document_explorer.subject_upload_service import (
            SubjectUploadError, upload_subject_document,
        )

        found = core._person_and_type(request.POST.get("person"),
                                      request.POST.get("doc_type"))
        upload = request.FILES.get("file")
        if found is None or upload is None:
            return _error("Falta el trabajador, el tipo o el archivo.")
        person, doc_type = found
        extension = (upload.name.rsplit(".", 1)[-1].lower()
                     if "." in upload.name else "")
        if extension not in NOTICE_UPLOAD_EXTENSIONS:
            return _error("Solo se admiten PDF e imágenes.")
        typed = None
        raw_date = (request.POST.get("date") or "").strip()
        if raw_date:
            try:
                typed = datetime.date.fromisoformat(raw_date)
            except ValueError:
                return _error("La fecha no es válida.")
        try:
            with transaction.atomic():
                result = upload_subject_document(
                    subject=person,
                    domain_content_type=ContentType.objects.get_for_model(
                        PersonIdentity),
                    document_type=doc_type, data=upload.read(),
                    original_filename=upload.name,
                    typed_date=typed if doc_type.tracks_expiry else None,
                    typed_issue_date=(None if doc_type.tracks_expiry
                                      else typed),
                    subject_label=core._person_label(person),
                    uploaded_by=request.user.company_user,
                    check_content=True)
        except SubjectUploadError as exc:
            return _error("No se pudo archivar: %s" % exc)
        message = "%s subido a la ficha de %s." % (
            doc_type.label, core._person_label(person))
        mismatch = (result.get("check") or {}).get("type_mismatch")
        if mismatch:
            message += (" Ojo: el documento parece %s, no %s. Revísalo en "
                        "la ficha (Cambiar tipo)." % (mismatch["label"],
                                                       doc_type.label))
        warning = result.get("warning")
        if warning:
            message += (" Ojo: el documento dice %s y escribiste %s; se ha "
                        "guardado la tuya." % (
                            warning["system_date"].strftime("%d/%m/%Y"),
                            warning["typed_date"].strftime("%d/%m/%Y")))
        return _ok(message)


class NoticeAppointmentView(SuperuserRequiredMixin, View):
    """
    POST `person`, `doc_type`, `action` (mark | cancel): appointment.

    ---

    POST: anota o anula «Cita solicitada» en el aviso del
    reconocimiento médico.
    """

    def post(self, request):
        found = core._person_and_type(request.POST.get("person"),
                                      request.POST.get("doc_type"))
        action = request.POST.get("action")
        if found is None or action not in ("mark", "cancel"):
            return _error("Petición no válida.")
        person, doc_type = found
        if doc_type.code not in core.APPOINTMENT_TYPE_CODES:
            return _error("Este documento no lleva cita.")
        company_user = request.user.company_user
        if action == "mark":
            NoticeAppointmentRequest.objects.create(
                person=person, document_type=doc_type,
                requested_by=company_user)
            return _ok("Cita solicitada anotada para %s." % (
                core._person_label(person)))
        NoticeAppointmentRequest.objects.filter(
            person=person, document_type=doc_type,
            cancelled_at__isnull=True,
        ).update(cancelled_at=timezone.now(), cancelled_by=company_user)
        return _ok("Cita solicitada anulada para %s." % (
            core._person_label(person)))


# ---------------------------------------------------- configuración
def render_config(request):
    """
    Documentos › Configuración de avisos (see the module docstring).

    ---

    La vista de configuración: requisitos como botones con los avisos
    de cada documento obligatorio del elegido, mi WhatsApp, la
    antelación de las revisiones y los destinatarios.
    """
    company_user = request.user.company_user
    positions = list(JobPosition.objects.prefetch_related(
        "required_document_types").order_by("name"))
    selected = core._int_or_none(request.GET.get("av_cfg_req"))
    if selected not in {p.pk for p in positions}:
        selected = positions[0].pk if positions else None
    position = next((p for p in positions if p.pk == selected), None)
    types = []
    if position is not None:
        rules = {rule.document_type_id: core._alert_rule_to_dict(rule)
                 for rule in RequirementAlertRule.objects.filter(
                     job_position=position)}
        for doc_type in sorted(position.required_document_types.all(),
                               key=lambda t: t.label):
            types.append({"type": doc_type,
                          "rule": rules.get(doc_type.pk) or {}})
    from fleet.models import MachineServiceAlertSettings

    service = MachineServiceAlertSettings.objects.filter(
        company=company_user.company).first()
    recipients = core._recipients_context(company_user)
    # S163 (24/11), como en la antigua: al lado de cada requisito,
    # cuántos de sus documentos obligatorios tienen algún aviso.
    configured = {}
    for rule in RequirementAlertRule.objects.all():
        if any(core._alert_rule_to_dict(rule).get(k) for k in (
                "missing", "d30", "d15", "d7", "d1", "c1v", "c2v")):
            configured.setdefault(rule.job_position_id, set()).add(
                rule.document_type_id)
    for p in positions:
        required = {t.pk for t in p.required_document_types.all()}
        p.nui_alert_count = "%d/%d" % (
            len(configured.get(p.pk, set()) & required), len(required))
    # El destinatario elegido (como el requisito): el de la URL, uno
    # mismo o el primero.
    sups = recipients["supervisors"]
    sup_pk = core._int_or_none(request.GET.get("av_cfg_sup"))
    supervisor = (next((s for s in sups if s["id"] == sup_pk), None)
                  or next((s for s in sups if s["is_me"]), None)
                  or (sups[0] if sups else None))
    return render(request, "new_ui/_notices_config.html", {
        "supervisor": supervisor,
        "positions": positions,
        "position": position,
        "types": types,
        "units": RequirementAlertRule.UNIT_CHOICES,
        "whatsapp_enabled": NoticeRecipientScope.objects.filter(
            company_user=company_user, whatsapp_enabled=True).exists(),
        "can_toggle_whatsapp": company_user.role in RECIPIENT_ROLES,
        "hours_advance": service.hours_advance if service else None,
        "km_advance": service.km_advance if service else None,
        "can_edit_service": company_user.role in SERVICE_SETTINGS_ROLES,
        "supervisors": recipients["supervisors"],
        "options": recipients["options"],
    })


class AlertRulesSaveView(SuperuserRequiredMixin, View):
    """
    POST: the notices of the mandatory documents of one requirement.

    ---

    POST: guarda los avisos de los documentos obligatorios de un
    requisito (campos por tipo: missing_<id>, d30_<id>, d15_<id>,
    d7_<id>, d1_<id>, c1v_<id>, c1u_<id>, c2v_<id>, c2u_<id>). Valida
    todo antes de escribir; los avisos de tipos que ya no son
    obligatorios se borran.
    """

    def post(self, request, position_pk):
        position = JobPosition.objects.filter(pk=position_pk).first()
        if position is None:
            return _error("Ese requisito ya no existe.")
        required = list(position.required_document_types.all())
        post = request.POST
        payload = {}
        for doc_type in required:
            pk = doc_type.pk
            payload[str(pk)] = {
                key: post.get("%s_%d" % (key, pk))
                for key in ("missing", "d30", "d15", "d7", "d1", "c1v",
                            "c1u", "c2v", "c2u")}
            for flag in ("missing", "d30", "d15", "d7", "d1"):
                payload[str(pk)][flag] = post.get("%s_%d" % (flag, pk)) == "1"
        try:
            rules = core._parse_alert_rules(json.dumps(payload), required)
        except core.AlertRuleError as exc:
            return _error(str(exc))
        with transaction.atomic():
            RequirementAlertRule.objects.filter(
                job_position=position,
            ).exclude(document_type_id__in=rules.keys()).delete()
            for type_pk, fields in rules.items():
                RequirementAlertRule.objects.update_or_create(
                    job_position=position, document_type_id=type_pk,
                    defaults=fields)
        return _ok("Avisos de «%s» guardados." % position.name)


class WhatsAppToggleView(SuperuserRequiredMixin, View):
    """POST `enabled`: my own WhatsApp notices on or off."""

    def post(self, request):
        company_user = request.user.company_user
        if company_user.role not in RECIPIENT_ROLES:
            return _error("Solo los supervisores de documentación y los "
                          "administradores reciben avisos.", 403)
        enabled = request.POST.get("enabled") == "1"
        scope, _created = NoticeRecipientScope.objects.get_or_create(
            company_user=company_user)
        scope.whatsapp_enabled = enabled
        scope.updated_by = company_user
        scope.save(update_fields=["whatsapp_enabled", "updated_by",
                                  "updated_at"])
        return _ok("Mis avisos por WhatsApp: %s." % (
            "activados" if enabled else "desactivados"))


def _count(raw, label):
    raw = (raw or "").strip().replace(".", "").replace(" ", "")
    if not raw:
        return None
    if not raw.isdigit():
        raise ValueError("%s debe ser un número entero." % label)
    return int(raw)


class ServiceAdvanceSaveView(SuperuserRequiredMixin, View):
    """
    POST `hours_advance`, `km_advance`: advance of the service notices.

    ---

    POST: la antelación de los avisos de revisión, en horas y en km
    (vacío: solo se avisa de las vencidas).
    """

    def post(self, request):
        from fleet.models import MachineServiceAlertSettings

        company_user = request.user.company_user
        if company_user.role not in SERVICE_SETTINGS_ROLES:
            return _error("Solo los supervisores de documentación y los "
                          "administradores configuran los avisos.", 403)
        try:
            hours = _count(request.POST.get("hours_advance"),
                           "La antelación en horas")
            km = _count(request.POST.get("km_advance"),
                        "La antelación en km")
        except ValueError as exc:
            return _error(str(exc))
        with transaction.atomic():
            settings, _created = (
                MachineServiceAlertSettings.objects.get_or_create(
                    company=company_user.company))
            settings.hours_advance = hours or None
            settings.km_advance = km or None
            settings.updated_by = company_user
            settings.save()
        return _ok("Antelación de los avisos de revisión guardada.")


class ScopeSaveView(SuperuserRequiredMixin, View):
    """
    POST: the notice scope of one recipient (lists of marked options).

    ---

    POST: guarda el ámbito de avisos de un destinatario (solo el propio
    destinatario o el administrador). Lo que no es una opción real se
    descarta.
    """

    def post(self, request, supervisor_pk):
        editor = request.user.company_user
        supervisor = CompanyUser.objects.filter(
            pk=supervisor_pk, company=editor.company,
            role__in=RECIPIENT_ROLES).first()
        if supervisor is None:
            return _error("Ese destinatario ya no existe.")
        if not core._can_edit_scope(editor, supervisor):
            return _error("Solo el propio supervisor o el administrador "
                          "pueden cambiar estos avisos.", 403)
        post = request.POST

        def ids(key):
            return [int(v) for v in post.getlist(key) if v.isdigit()]

        def texts(key):
            return [v for v in post.getlist(key) if v]

        with transaction.atomic():
            scope, _created = NoticeRecipientScope.objects.get_or_create(
                company_user=supervisor)
            scope.personal_all = post.get("personal_all") == "1"
            scope.personal_companies = texts("personal_companies")
            scope.machine_all = post.get("machine_all") == "1"
            scope.machine_families = texts("machine_families")
            scope.machine_companies = texts("machine_companies")
            scope.updated_by = editor
            scope.save()
            scope.personal_groups.set(PersonGroupTemplate.objects.filter(
                pk__in=ids("personal_groups")))
            scope.personal_persons.set(PersonIdentity.objects.filter(
                pk__in=ids("personal_persons")))
            scope.machines.set(MachineAsset.objects.filter(
                pk__in=ids("machines")))
            scope.excluded_requirements.set(JobPosition.objects.filter(
                pk__in=ids("excluded_requirements")))
            scope.excluded_document_types.set(
                DocumentTypeCatalog.objects.filter(
                    pk__in=ids("excluded_document_types")))
        name = supervisor.user.get_full_name() or supervisor.user.username
        return _ok("Destinatario %s guardado." % name)



# ---------------------------------------------------- ventana de un aviso
def _sheet_url(notice):
    """La ventana de un aviso (S163, 24/11): qué pasa y cómo resolverlo."""
    from urllib.parse import urlencode

    from django.urls import reverse

    return "%s?%s" % (reverse("new_ui:notice_sheet"), urlencode({
        "d": notice.domain, "s": notice.subject_id,
        "t": notice.document_type_id or "",
        "l": notice.document_label if notice.is_service else "",
        "k": notice.kind}))


class NoticeSheetView(SuperuserRequiredMixin, View):
    """
    GET: one notice in the viewer, with every way to solve it.

    ---

    GET: un aviso en el visor (al pulsarlo en Avisos pendientes o en el
    calendario), con todos los cauces para resolverlo (Miguel Ángel,
    24/11: «resolver la falta o la desactualización del documento con
    todas las cosas que necesitamos»): subir el documento (o la versión
    nueva) aquí mismo, pedírselo al trabajador por WhatsApp, la cita del
    reconocimiento médico e ir a su ficha. Como en la antigua, pulsar un
    aviso lleva a su documentación.
    """

    def get(self, request):
        from django.http import HttpResponse

        domain = request.GET.get("d")
        if domain not in (notices.DOMAIN_PERSONAL, notices.DOMAIN_MACHINE):
            return HttpResponse("Aviso no válido.", status=400)
        subject_id = core._int_or_none(request.GET.get("s"))
        type_id = core._int_or_none(request.GET.get("t"))
        label = request.GET.get("l", "")
        kind = request.GET.get("k", "")
        pending, _scheduled, calendar_items = notices.compute_notices(
            domain, include_service=True)

        def same(n):
            if n.subject_id != subject_id:
                return False
            if label:
                return n.is_service and n.document_label == label
            return n.document_type_id == type_id

        notice = (next((n for n in pending if same(n) and n.kind == kind),
                       None)
                  or next((n for n in pending if same(n)), None))
        future = notice is None
        if notice is None:
            item = next((i for i in calendar_items if same(i.notice)), None)
            notice = item.notice if item else None
        if notice is None:
            return HttpResponse(
                '<p class="small text-muted mb-0">Este aviso ya no está '
                'pendiente: puede que ya se haya resuelto. Recarga la '
                'lista.</p>')
        company_user = request.user.company_user
        recipients = recipients_for(notice, load_scopes(company_user.company))
        notice.recipient_names = ", ".join(
            r.user.get_full_name() or r.user.username for r in recipients)
        is_personal = domain == notices.DOMAIN_PERSONAL
        if not future:
            _texts(notice)
        if is_personal and not notice.is_service:
            core._annotate_worker_requests(
                [notice], company_user.role in DOC_REQUEST_ROLES)
        doc_type = (DocumentTypeCatalog.objects.filter(pk=type_id).first()
                    if type_id else None)
        return render(request, "new_ui/_notice_sheet.html", {
            "notice": notice,
            "future": future,
            "is_personal": is_personal,
            "doc_type": doc_type,
            "upload_domain": "personal" if is_personal else "machine",
            "is_missing": notice.kind == notices.KIND_MISSING,
            "goto_section": "per" if is_personal else "cdg",
            "goto_tab": ("revisiones" if notice.is_service
                         else "documentos"),
        })


class NoticeAskView(SuperuserRequiredMixin, View):
    """
    GET: «Pedir cualquier otro documento» in the viewer.

    ---

    GET: pedir por WhatsApp cualquier documento a los trabajadores que
    se marquen aquí (la antigua «Pedir documentos»): buscar y marcar
    trabajadores con móvil, elegir los documentos y pedir o cancelar lo
    pedido. Usa las mismas vistas que Personal › Comunicaciones.
    """

    def get(self, request):
        from document_explorer.person_phone_service import mobile_of
        from new_ui.views_notify import notify_context

        company = request.user.company_user.company
        people = []
        for person in PersonIdentity.objects.filter(
                Q(company=company) | Q(company__isnull=True),
                is_active_employee=True).order_by(
                "first_surname", "second_surname", "given_name"):
            people.append({
                "pk": person.pk,
                "label": "%s %s, %s" % (person.first_surname,
                                        person.second_surname or "",
                                        person.given_name),
                "mobile": mobile_of(person)})
        return render(request, "new_ui/_notice_ask.html", {
            "people": people,
            "ask_types": notify_context("per").get("ask_types", []),
        })
