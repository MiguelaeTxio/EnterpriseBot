# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/views_signatures_lists.py
"""
S153. The "Firmas" tab in the panel's single list format (directives
4.24 and 4.27): four lists (signed documents, signatures, certificates
and agents) with a fixed top row (search and filters, selection groups,
actions) and the list with "Selección actual" below.

---

S153. La pestaña "Firmas" con el formato único de listados del panel
(directrices 4.24 y 4.27). Miguel Ángel: "si tenemos un listado
digital, un listado de firmas normales, tenemos un listado de
certificados y ya no nos caben tantos listados, unas pestañas para los
listados [...] el fijo, un filtro de selección, grupo de selección,
exactamente lo mismo". Cuatro listados: Documentos firmados (digitales
y normales), Firmas, Certificados y Agentes. Filtros, orden, listado
elegido y selección persistidos por usuario.
"""
import datetime
import logging

from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views import View

from document_explorer import signing_agent_service as agents
from document_explorer.confidential import ConfidentialError
from document_explorer.models import (
    CertificateAlertDismissal,
    CompanyFiscalProfile,
    CompanySignature,
    PersonIdentity,
    SignedFormFile,
    SignedFormJob,
    SigningAgent,
)
from panel.navigation_persistence import (
    apply_list_navigation,
    get_saved_state_key,
)
from panel.views_signatures import SignatureAccessMixin, _files_response

logger = logging.getLogger(__name__)

TAB_SCREEN_KEY = "signatures"
LISTS = (
    ("documentos", "Documentos firmados"),
    ("firmas", "Firmas"),
    ("certificados", "Certificados"),
    ("agentes", "Agentes"),
)
LIST_KEYS = tuple(key for key, _label in LISTS)
DEFAULT_LIST = "documentos"
FILTER_KEYS = ("search", "company", "status", "kind", "validity",
               "group", "sort")
_MAX_SORT_KEYS = 4

COLUMNS = {
    "documentos": (
        ("created", "Fecha"), ("name", "Documento"),
        ("company", "Empresa"), ("signer", "Firma"),
        ("person", "Trabajador"), ("kind", "Tipo"),
        ("status", "Estado"),
    ),
    "firmas": (
        ("company", "Empresa"), ("signer", "Quién firma"),
        ("image", "Firma"), ("cert", "Certificado digital"),
        ("created", "Guardada"),
    ),
    "certificados": (
        ("company", "Empresa"), ("cif", "CIF"), ("holder", "Titular"),
        ("expires", "Válido hasta"), ("state", "Situación"),
    ),
    "agentes": (
        ("online", "Conexión"), ("name", "Ordenador"),
        ("host", "Equipo"), ("seen", "Último contacto"),
        ("autofirma", "AutoFirma"), ("certs", "Certificados"),
    ),
}
DEFAULT_SORT = {
    "documentos": "-created",
    "firmas": "company",
    "certificados": "company,-expires",
    "agentes": "name",
}
STATUS_CHOICES = (
    (SignedFormFile.STATUS_PENDING, "Pendiente de firma"),
    (SignedFormFile.STATUS_DONE, "Firmado"),
    (SignedFormFile.STATUS_ERROR, "Con error"),
    ("cancelled", "Cancelado"),
)
KIND_CHOICES = tuple(SignedFormJob.KIND_CHOICES)
VALIDITY_CHOICES = (
    ("current", "Se usa al firmar"),
    ("valid", "Vigente (otro)"),
    ("expired", "Caducado"),
)
_MIN = datetime.datetime.min.replace(tzinfo=datetime.timezone.utc)


def _csv(request, key, default):
    if key in request.GET:
        return [v for v in request.GET.get(key, "").split(",") if v]
    return list(default)


def _parse_sort(raw, lista):
    valid = {key for key, _label in COLUMNS[lista]}
    keys, seen = [], set()
    for token in (raw or "").split(","):
        token = token.strip()
        key = token.lstrip("-")
        if key in valid and key not in seen:
            keys.append((key, token.startswith("-")))
            seen.add(key)
    return keys[:_MAX_SORT_KEYS]


def _sort_controls(raw, lista):
    sort_keys = _parse_sort(raw, lista)
    active = [key for key, _desc in sort_keys]
    columns = []
    for key, label in COLUMNS[lista]:
        if key in active:
            idx = active.index(key)
            desc = sort_keys[idx][1]
            new_desc = (not desc) if idx == 0 else desc
            new_keys = [(key, new_desc)] + [
                (k, d) for k, d in sort_keys if k != key]
            arrow = "down" if desc else "up"
            priority = idx + 1 if len(sort_keys) > 1 else ""
        else:
            arrow, priority = "", ""
            new_keys = [(key, False)] + sort_keys
        columns.append({
            "key": key, "label": label, "arrow": arrow,
            "priority": priority,
            "next": ",".join(("-" if d else "") + k
                             for k, d in new_keys[:_MAX_SORT_KEYS]),
        })
    return {
        "sort_columns": columns,
        "sort_active": bool(sort_keys),
        "current_sort": ",".join(("-" if d else "") + k
                                 for k, d in sort_keys),
    }


def _sort_rows(rows, sort_keys):
    for key, desc in reversed(sort_keys):
        present = [r for r in rows if r["sort"].get(key) is not None]
        missing = [r for r in rows if r["sort"].get(key) is None]
        rows = sorted(present, key=lambda r: r["sort"][key],
                      reverse=desc) + missing
    return rows


def _person_label(person):
    if person is None:
        return ""
    surnames = " ".join(p for p in (person.first_surname,
                                    person.second_surname) if p)
    return ("%s, %s" % (surnames, person.given_name)).strip(", ")


# ------------------------------------------------------------------
# Filas de cada listado
# ------------------------------------------------------------------
def _document_rows():
    files = SignedFormFile.objects.select_related(
        "job__signature__company", "job__person",
        "job__created_by__user",
    ).defer("unsigned_encrypted", "signed_encrypted").order_by(
        "-job__created_at", "pk")
    rows = []
    for item in files:
        job = item.job
        status = ("cancelled" if job.status == SignedFormJob.STATUS_CANCELLED
                  and item.status != SignedFormFile.STATUS_DONE
                  else item.status)
        person = _person_label(job.person)
        rows.append({
            "key": str(item.pk),
            "label": "%s · %s" % (item.name, job.created_at.strftime(
                "%d/%m/%Y")),
            "item": item, "job": job, "status": status,
            "status_label": dict(STATUS_CHOICES).get(status, status),
            "person": person, "person_id": job.person_id or "",
            "company_id": job.signature.company_id,
            "kind": job.kind,
            "can_cancel": job.status == SignedFormJob.STATUS_PENDING,
            "can_download": item.status == SignedFormFile.STATUS_DONE,
            "text": " ".join([item.name, job.signature.company.legal_name,
                              job.signature.label, person]).lower(),
            "sort": {
                "created": job.created_at, "name": item.name.lower(),
                "company": job.signature.company.legal_name.lower(),
                "signer": job.signature.label.lower(),
                "person": person.lower() or None,
                "kind": job.get_kind_display(), "status": status,
            },
        })
    return rows


def _certificates_context():
    company_certs = agents.company_certificates()
    signing_agents = list(SigningAgent.objects.filter(is_active=True))
    aliases = sorted({alias for agent in signing_agents
                      for alias in agent.aliases or []})
    return company_certs, aliases, any(a.certificates
                                       for a in signing_agents)


def _signature_rows():
    company_certs, aliases, agents_v3 = _certificates_context()
    certs_by_cif = {entry["cif"]: entry for entry in company_certs}
    rows = []
    for signature in CompanySignature.objects.select_related(
            "company", "created_by__user"):
        signature.cert_entry = certs_by_cif.get(signature.certificate_cif)
        rows.append({
            "key": str(signature.pk),
            "label": "%s · %s" % (signature.label,
                                  signature.company.legal_name),
            "signature": signature,
            "company_id": signature.company_id,
            "text": " ".join([signature.label,
                              signature.company.legal_name,
                              signature.certificate_cif,
                              signature.certificate_alias]).lower(),
            "sort": {
                "company": signature.company.legal_name.lower(),
                "signer": signature.label.lower(),
                "cert": (signature.certificate_cif
                         or signature.certificate_alias or None),
                "created": signature.created_at,
            },
        })
    return rows, {"company_certs": company_certs,
                  "certificate_aliases": aliases, "agents_v3": agents_v3}


def _certificate_rows(profiles_by_cif):
    company_certs, _aliases, _v3 = _certificates_context()
    rows = []
    for entry in company_certs:
        profile = profiles_by_cif.get(entry["cif"].upper())
        for cert in entry["certs"]:
            if cert is entry["current"]:
                state, label = "current", "Se usa al firmar"
            elif cert["valid"]:
                state, label = "valid", "Vigente"
            else:
                state, label = "expired", "Caducado"
            rows.append({
                "key": cert["thumbprint"],
                "label": "%s · %s · %s" % (
                    entry["company"], cert["holder"],
                    cert["expires"].strftime("%d/%m/%Y")),
                "entry": entry, "cert": cert, "state": state,
                "state_label": label,
                "warning": state == "current" and entry["level"],
                "company_id": profile.pk if profile else None,
                "text": " ".join([entry["company"], entry["cif"],
                                  cert["holder"]]).lower(),
                "sort": {
                    "company": entry["company"].lower(),
                    "cif": entry["cif"], "holder": cert["holder"].lower(),
                    "expires": cert["expires"], "state": label,
                },
            })
    return rows


def _agent_rows():
    rows = []
    for agent in SigningAgent.objects.filter(is_active=True):
        online = agents.is_online(agent)
        rows.append({
            "key": str(agent.pk), "label": agent.name, "agent": agent,
            "online": online, "company_id": None,
            "text": " ".join([agent.name, agent.host]).lower(),
            "sort": {
                "online": "1" if online else "0",
                "name": agent.name.lower(), "host": agent.host.lower(),
                "seen": agent.last_seen_at,
                "autofirma": agent.autofirma_version or None,
                "certs": len(agent.aliases or []),
            },
        })
    return rows


# ------------------------------------------------------------------
# Contexto
# ------------------------------------------------------------------
def _current_list(request):
    """
    The chosen list (GET "lista", or the one saved for the user).
    ---
    El listado elegido: el de la URL o, si no viene, el último que miró
    el usuario (PanelNavigationState "signatures").
    """
    lista = request.GET.get("lista", "")
    cu = request.user.company_user
    if lista in LIST_KEYS:
        from panel.models import PanelNavigationState

        PanelNavigationState.objects.update_or_create(
            company_user=cu, screen_key=TAB_SCREEN_KEY,
            defaults={"state": {"lista": lista}})
        return lista
    saved = get_saved_state_key(cu, TAB_SCREEN_KEY, "lista", DEFAULT_LIST)
    return saved if saved in LIST_KEYS else DEFAULT_LIST


def _list_context(request, lista):
    from panel.person_groups import (
        PERSON_KIND, group_filter_select_context,
    )

    profiles = list(CompanyFiscalProfile.objects.order_by("legal_name"))
    companies = _csv(request, "company", [str(p.pk) for p in profiles])
    search = request.GET.get("search", "").strip().lower()
    context = {"lista": lista, "profiles": profiles,
               "filter_company": companies, "filter_search":
               request.GET.get("search", "")}
    if lista == "documentos":
        rows = _document_rows()
        statuses = _csv(request, "status",
                        [key for key, _l in STATUS_CHOICES])
        kinds = _csv(request, "kind", [key for key, _l in KIND_CHOICES])
        rows = [r for r in rows if r["status"] in statuses
                and r["kind"] in kinds]
        group = request.GET.get("group", "")
        if group:
            from panel.person_groups import filter_by_group

            wanted = set(filter_by_group(
                PersonIdentity.objects.all(), group,
                PERSON_KIND).values_list("pk", flat=True))
            rows = [r for r in rows if r["person_id"] in wanted]
        context.update({
            "filter_status": statuses, "filter_kind": kinds,
            "status_choices": STATUS_CHOICES, "kind_choices": KIND_CHOICES,
            **group_filter_select_context(request, PERSON_KIND),
        })
    elif lista == "firmas":
        rows, extra = _signature_rows()
        context.update(extra)
    elif lista == "certificados":
        by_cif = {p.tax_id.upper().replace("-", "").strip(): p
                  for p in profiles if p.tax_id}
        rows = _certificate_rows(by_cif)
        validity = _csv(request, "validity",
                        [key for key, _l in VALIDITY_CHOICES])
        rows = [r for r in rows if r["state"] in validity]
        context.update({"filter_validity": validity,
                        "validity_choices": VALIDITY_CHOICES})
    else:
        rows = _agent_rows()
    if lista != "agentes":
        rows = [r for r in rows if r["company_id"] is None
                or str(r["company_id"]) in companies]
    for word in search.split():
        rows = [r for r in rows if word in r["text"]]
    if request.GET.get("only_selected") == "1":
        wanted = set(request.GET.get("selected_ids", "").split(","))
        rows = [r for r in rows if r["key"] in wanted]
    raw_sort = request.GET.get("sort", DEFAULT_SORT[lista])
    rows = _sort_rows(rows, _parse_sort(raw_sort, lista))
    context.update({"rows": rows, **_sort_controls(raw_sort, lista)})
    return context


def _screen_key(lista):
    return "%s_%s" % (TAB_SCREEN_KEY, lista)


def _pane_context(request):
    from panel.person_groups import group_filter_context

    lista = _current_list(request)
    screen_key = _screen_key(lista)
    apply_list_navigation(request, screen_key, FILTER_KEYS)
    cu = request.user.company_user
    saved_selection = get_saved_state_key(cu, screen_key, "selection", [])
    if not isinstance(saved_selection, list):
        saved_selection = []
    company_certs = agents.company_certificates()
    dismissed = set(CertificateAlertDismissal.objects.values_list(
        "cif", "alert_key"))
    signatures = list(CompanySignature.objects.select_related("company"))
    people = PersonIdentity.objects.filter(
        is_active_employee=True).order_by(
        "first_surname", "second_surname", "given_name").only(
        "pk", "first_surname", "second_surname", "given_name")
    return {
        **_list_context(request, lista),
        **group_filter_context(request),
        "lists": LISTS,
        "screen_key": screen_key,
        "saved_selection": saved_selection,
        "cert_alerts": [e for e in company_certs if e["level"]
                        and (e["cif"], e["alert_key"]) not in dismissed],
        "signatures": signatures,
        "profiles_with_signature": {s.company_id for s in signatures},
        "people": people,
    }


class SignatureTabView(SignatureAccessMixin, View):
    """
    GET: the "Firmas" tab (chosen list in the single list format).
    ---
    GET: la pestaña "Firmas" con el listado elegido.
    """

    def get(self, request):
        return render(request, "panel/signatures/_pane.html",
                      _pane_context(request))


class SignatureResultsView(SignatureAccessMixin, View):
    """
    GET: the table of the chosen list only.
    ---
    GET: solo la tabla del listado elegido (filtros y orden).
    """

    def get(self, request):
        lista = _current_list(request)
        apply_list_navigation(request, _screen_key(lista), FILTER_KEYS)
        return render(request, "panel/signatures/_table.html",
                      _list_context(request, lista))


class SignedFileDownloadView(SignatureAccessMixin, View):
    """
    GET: one signed document.
    ---
    GET: un documento firmado (digital o normal).
    """

    def get(self, request, pk):
        item = SignedFormFile.objects.filter(
            pk=pk, status=SignedFormFile.STATUS_DONE).first()
        if item is None:
            return HttpResponse("Ese documento ya no está.", status=404)
        try:
            return _files_response([(item.name, agents.signed_pdf(item))])
        except ConfidentialError as exc:
            return HttpResponse(str(exc), status=500)


class SignedFilesBulkDownloadView(SignatureAccessMixin, View):
    """
    GET: the marked signed documents (PDF or ZIP).
    ---
    GET: los documentos firmados marcados (?ids=1,2,3), uno o un ZIP.
    """

    def get(self, request):
        ids = [pk for pk in request.GET.get("ids", "").split(",")
               if pk.isdigit()]
        files = SignedFormFile.objects.filter(
            pk__in=ids, status=SignedFormFile.STATUS_DONE).order_by("pk")
        try:
            results, names = [], set()
            for item in files:
                name, number = item.name, 2
                while name in names:
                    name = "%s (%d).pdf" % (item.name[:-4], number)
                    number += 1
                names.add(name)
                results.append((name, agents.signed_pdf(item)))
        except ConfidentialError as exc:
            return HttpResponse(str(exc), status=500)
        if not results:
            return HttpResponse(
                "Ninguno de los marcados está firmado todavía.", status=404)
        return _files_response(results)


class SignatureMassView(SignatureAccessMixin, View):
    """
    POST: delete the marked signatures or disable the marked agents.
    ---
    POST: borra las firmas marcadas (action=delete_signatures) o da de
    baja los agentes marcados (action=disable_agents). JSON {done}.
    """

    def post(self, request):
        action = request.POST.get("action", "")
        ids = [pk for pk in request.POST.get("ids", "").split(",")
               if pk.isdigit()]
        if action == "delete_signatures":
            items = CompanySignature.objects.filter(pk__in=ids)
            done = items.count()
            logger.info("# [FIRMAS] %s borra %d firma(s): %s",
                        request.user.username, done,
                        ", ".join(s.label for s in items))
            items.delete()
        elif action == "disable_agents":
            done = SigningAgent.objects.filter(pk__in=ids).update(
                is_active=False)
        else:
            return JsonResponse({"error": "Acción desconocida."},
                                status=400)
        return JsonResponse({"done": done,
                             "at": timezone.now().isoformat()})
