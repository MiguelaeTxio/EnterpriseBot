# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/new_ui/views_dossiers.py
"""
Dossiers in the new interface (S163).

Everything the old interface did with dossiers, from the Actions panel:
templates (create, edit, delete), the dossier of the marked documents,
the dossier of the marked workers or machines with a template (download
or e-mail, all together), and marking who lacks a document of the
template. Logic copied into new_ui/dossier_core.py.

---

Dosieres en la nueva interfaz (S163), todo desde el panel Acciones:
- Documentos › Dosieres: crear, modificar y borrar plantillas.
- Personal/Centros de gasto › Documentos: dosier con los documentos
  marcados (PDF único, uno por persona o máquina, ZIP o correo).
- Personal/Centros de gasto › General: dosier de los marcados con una
  plantilla (descargar o correo, todo junto) y comprobar a quién le
  falta algún documento de la plantilla.
Lógica copiada en new_ui/dossier_core.py; nada de la interfaz antigua.
"""
import json
from collections import OrderedDict

from django.contrib.contenttypes.models import ContentType
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views import View

from document_explorer.models import (
    DocumentIndexEntry, DocumentTypeCatalog, EpiItemCatalog,
    PersonalDossierTemplate, PersonIdentity,
)
from fleet.models import MachineAsset
from new_ui import dossier_core as core
from new_ui.docs_core import BUCKET
from new_ui.mixins import SuperuserRequiredMixin

SCOPE_OF_SECTION = {
    "per": PersonalDossierTemplate.SCOPE_PERSONAL,
    "cdg": PersonalDossierTemplate.SCOPE_MACHINE,
}

# Un color por familia, en el orden de FAMILY_CHOICES (copiado del
# gestor de plantillas antiguo, S105).
FAMILY_COLORS = {
    DocumentTypeCatalog.FAMILY_CIRCULACION: "#e3f2fd",
    DocumentTypeCatalog.FAMILY_TECNICA_SEGURIDAD: "#fff3e0",
    DocumentTypeCatalog.FAMILY_SEGUROS: "#e8f5e9",
    DocumentTypeCatalog.FAMILY_FINANCIERO: "#f3e5f5",
    DocumentTypeCatalog.FAMILY_BAJAS_MAQUINA: "#fbe9e7",
    DocumentTypeCatalog.FAMILY_ADMINISTRATIVO: "#e0f7fa",
    DocumentTypeCatalog.FAMILY_IDENTIDAD_PERSONAL: "#fff9c4",
    DocumentTypeCatalog.FAMILY_LABORAL: "#ede7f6",
    DocumentTypeCatalog.FAMILY_SALUD_BAJAS_PERSONA: "#ffebee",
    DocumentTypeCatalog.FAMILY_PRL_FORMACION: "#e8eaf6",
    DocumentTypeCatalog.FAMILY_OTROS_DOCUMENTOS: "#eeeeee",
    DocumentTypeCatalog.FAMILY_MEDIA: "#f1f8e9",
}


def _company(request):
    return request.user.company_user.company


def _family_sections(for_person):
    """
    Active document types of a scope grouped by family, with colour.

    ---

    Los tipos activos del ámbito (Personal: PERSONAL y BOTH; Maquinaria:
    MACHINE y BOTH), por familia en el orden del catálogo, cada familia
    con su color. En Personal, Circulación se rotula Conducción.
    """
    domains = ["PERSONAL", "BOTH"] if for_person else ["MACHINE", "BOTH"]
    by_family = OrderedDict()
    for dt in DocumentTypeCatalog.objects.filter(
        is_active=True, domain__in=domains,
    ).order_by("family", "label"):
        by_family.setdefault(dt.family or "", []).append(dt)
    known = [code for code, _label in DocumentTypeCatalog.FAMILY_CHOICES]
    codes = [code for code in known if code in by_family]
    codes += sorted(c for c in by_family if c and c not in known)
    if "" in by_family:
        codes.append("")
    return [
        {
            "title": DocumentTypeCatalog.family_label(
                code, for_person=for_person) if code else "Sin familia",
            "color": FAMILY_COLORS.get(code, "#f5f5f5"),
            "items": [(dt.pk, dt.label) for dt in by_family[code]],
        }
        for code in codes
    ]


def _epi_sections():
    groups = OrderedDict()
    for epi in EpiItemCatalog.objects.filter(
        is_active=True,
    ).order_by("family", "label"):
        groups.setdefault(epi.family, []).append((epi.pk, epi.label))
    return [{"title": "EPIs -- %s" % family, "items": items}
            for family, items in groups.items()]


def dossier_context(section, company):
    """
    Context of the dossier actions of a section.

    ---

    Contexto de las acciones de dosier de una sección: el editor de
    plantillas en Documentos; las plantillas del ámbito en Personal y
    Centros de gasto.
    """
    if section == "doc":
        return {
            "dossier_person_sections": _family_sections(True),
            "dossier_machine_sections": _family_sections(False),
            "dossier_epi_sections": _epi_sections(),
        }
    scope = SCOPE_OF_SECTION.get(section)
    if not scope:
        return {}
    return {
        "dossier_templates": list(company.dossier_templates.filter(
            scope=scope).order_by("name").values_list("pk", "name")),
        "dossier_formats": [
            (core.FORMAT_COMBINED, "Un PDF con todo"),
            (core.FORMAT_PER_SUBJECT,
             "Un PDF por persona" if section == "per"
             else "Un PDF por máquina"),
            (core.FORMAT_ZIP, "ZIP con los originales"),
        ],
    }


def _ids(request, name="selected"):
    return [v for v in request.POST.getlist(name) if str(v).isdigit()]


def _error(message, status=400):
    return JsonResponse({"ok": False, "message": message}, status=status)


def _deliver(request, subjects, skipped):
    """
    The dossier as a download or as an Outlook draft, never silent.

    ---

    Entrega el dosier: descarga (`action=download`) o borrador `.eml`
    (`action=email`). Lo omitido va en la cabecera X-Nui-Message para
    que la página lo diga.
    """
    output_format = request.POST.get("format", core.FORMAT_COMBINED)
    if output_format not in core.FORMATS:
        return _error("Elige cómo lo quieres: PDF, uno por cada o ZIP.")
    action = request.POST.get("action", "download")
    try:
        if action == "email":
            data, size = core.build_eml(
                subjects, output_format,
                request.POST.get("body_html", "").strip(),
                request.user.company_user,
            )
            content_type = "message/rfc822"
            filename = "documentacion_%s.eml" % (
                timezone.localdate().isoformat())
        else:
            data, content_type, filename = core.download(
                subjects, output_format)
            size = len(data)
    except core.DossierError as exc:
        return _error(str(exc))
    notes = ["Dosier de %d %s." % (
        len(subjects), "elemento" if len(subjects) == 1 else "elementos")]
    if skipped:
        notes.append("Sin documentos y fuera del dosier: %s." % (
            "; ".join(skipped)))
    if action == "email" and size > core.SIZE_WARNING_BYTES:
        notes.append(
            "Ojo: los adjuntos pasan de 20 MB y muchos servidores de "
            "correo lo rechazan; mejor el ZIP o varios correos.")
    response = HttpResponse(data, content_type=content_type)
    response["Content-Disposition"] = 'attachment; filename="%s"' % filename
    response["X-Nui-Message"] = json.dumps(" ".join(notes))
    return response


# ------------------------------------------------------------- plantillas
class DossierTemplateDataView(SuperuserRequiredMixin, View):
    """
    GET: one template as JSON, to load it in the editor.

    ---

    GET: una plantilla en JSON para cargarla en el editor (Acciones ›
    Esta fila › Modificar).
    """

    def get(self, request, pk):
        template = get_object_or_404(
            PersonalDossierTemplate, pk=pk, company=_company(request))
        return JsonResponse({
            "ok": True, "id": template.pk, "name": template.name,
            "scope": template.scope,
            "type_ids": list(template.document_types.values_list(
                "pk", flat=True)),
            "epi_ids": list(template.epi_items.values_list("pk", flat=True)),
        })


class DossierTemplateSaveView(SuperuserRequiredMixin, View):
    """
    POST: create a template, or edit one (`template_pk`).

    ---

    POST: crea una plantilla o modifica una (`template_pk`): nombre
    (vacío: "Dossier N"), ámbito al crearla, y los tipos y EPIs
    marcados (al menos uno). El formato se elige al usarla.
    """

    def post(self, request):
        company = _company(request)
        template_pk = request.POST.get("template_pk", "").strip()
        if template_pk.isdigit():
            template = get_object_or_404(
                PersonalDossierTemplate, pk=template_pk, company=company)
        else:
            scope = request.POST.get("scope", "")
            template = PersonalDossierTemplate(
                company=company,
                created_by=request.user.company_user,
                scope=(scope if scope in dict(
                    PersonalDossierTemplate.SCOPE_CHOICES)
                    else PersonalDossierTemplate.SCOPE_PERSONAL),
            )
        name = request.POST.get("name", "").strip()
        if not name:
            name = template.name if template.pk else "Dossier %d" % (
                company.dossier_templates.count() + 1)
        type_ids = _ids(request, "document_type_ids")
        epi_ids = (
            _ids(request, "epi_item_ids")
            if template.scope == PersonalDossierTemplate.SCOPE_PERSONAL
            else [])
        if not type_ids and not epi_ids:
            return _error("Marca al menos un tipo de documento o un EPI.")
        created = not template.pk
        template.name = name
        template.save()
        template.document_types.set(type_ids)
        template.epi_items.set(epi_ids)
        return JsonResponse({
            "ok": True, "id": template.pk,
            "message": "Plantilla «%s» %s." % (
                template.name, "creada" if created else "guardada"),
        })


class DossierTemplateDeleteView(SuperuserRequiredMixin, View):
    """
    POST `selected`: delete the marked templates (never documents).

    ---

    POST `selected`: borra las plantillas marcadas; los documentos no
    se tocan.
    """

    def post(self, request):
        ids = _ids(request)
        if not ids:
            return _error("Marca primero las plantillas a borrar.")
        qs = _company(request).dossier_templates.filter(pk__in=ids)
        names = list(qs.values_list("name", flat=True))
        qs.delete()
        return JsonResponse({
            "ok": True,
            "message": "Borradas %d plantillas: %s." % (
                len(names), ", ".join(names)) if names
            else "No había nada que borrar.",
        })


# ---------------------------------------------- dosier de los documentos
class DossierDocumentsView(SuperuserRequiredMixin, View):
    """
    POST `selected` (document ids): dossier of the marked documents.

    ---

    POST `selected` (documentos marcados en Personal/Centros de gasto ›
    Documentos): un dosier por persona o máquina con sus documentos
    marcados, en el formato elegido, para descargar o en un correo.
    """

    def post(self, request):
        ids = _ids(request)
        if not ids:
            return _error("Marca primero los documentos del dosier.")
        entries = DocumentIndexEntry.objects.filter(
            pk__in=ids, bucket=BUCKET,
            entry_kind=DocumentIndexEntry.KIND_FILE,
            deleted_at__isnull=True, purged_at__isnull=True,
        ).select_related("document_type", "domain_content_type").order_by(
            "document_type__family", "document_type__label")
        grouped = OrderedDict()
        for entry in entries:
            if entry.domain_object_id is None:
                continue
            key = (entry.domain_content_type_id, entry.domain_object_id)
            grouped.setdefault(key, []).append(entry)
        if not grouped:
            return _error(
                "Ninguno de los marcados es un documento de una persona "
                "o máquina.")
        person_ct = ContentType.objects.get_for_model(PersonIdentity)
        subjects = []
        for (ct_id, object_id), items in grouped.items():
            model = PersonIdentity if ct_id == person_ct.pk else MachineAsset
            subject = model.objects.filter(pk=object_id).first()
            if subject is not None:
                subjects.append(
                    (subject, core.subject_label(subject), items, None))
        subjects.sort(key=lambda s: s[1])
        return _deliver(request, subjects, [])


# --------------------------------------- dosier de los marcados con plantilla
def _template_subjects(request, section):
    """
    (template, subjects, skipped, error) for the marked rows.

    ---

    Resuelve la plantilla elegida contra las personas o máquinas
    marcadas en General: (plantilla, sujetos, omitidos, error).
    """
    scope = SCOPE_OF_SECTION.get(section)
    if scope is None:
        return None, [], [], "Sección no válida."
    ids = _ids(request)
    if not ids:
        return None, [], [], (
            "Marca primero en el listado a quién preparar el dosier.")
    template = _company(request).dossier_templates.filter(
        pk=request.POST.get("template_id", ""), scope=scope).first()
    if template is None:
        return None, [], [], "Elige la plantilla de dosier."
    model = PersonIdentity if section == "per" else MachineAsset
    order = (("first_surname", "second_surname", "given_name")
             if section == "per" else ("code",))
    subjects, skipped = [], []
    for subject in model.objects.filter(pk__in=ids).order_by(*order):
        entries = core.template_entries(subject, template)
        epi = core.template_epi_deliveries(subject, template)
        label = core.subject_label(subject)
        if entries or epi:
            subjects.append((subject, label, entries, epi))
        else:
            skipped.append(label)
    return template, subjects, skipped, None


class DossierTemplateApplyView(SuperuserRequiredMixin, View):
    """
    POST: the marked workers or machines with a template, all together.

    ---

    POST: dosier de los marcados (Personal o Centros de gasto ›
    General) con la plantilla elegida: el vigente de cada tipo en este
    momento, todo en una descarga o en un solo correo. Quien no tiene
    ningún documento de la plantilla queda fuera y se avisa.
    """

    def post(self, request, section):
        _template, subjects, skipped, error = _template_subjects(
            request, section)
        if error:
            return _error(error)
        if not subjects:
            return _error(
                "Ninguno de los marcados tiene documentos vigentes de la "
                "plantilla elegida.")
        return _deliver(request, subjects, skipped)


class DossierMissingCheckView(SuperuserRequiredMixin, View):
    """
    POST: which marked rows lack a current document of the template.

    ---

    POST: a quién de los marcados le falta hoy algún documento vigente
    de la plantilla; devuelve sus ids (el listado los resalta) y qué le
    falta a cada uno.
    """

    def post(self, request, section):
        scope = SCOPE_OF_SECTION.get(section)
        ids = _ids(request)
        if scope is None or not ids:
            return _error("Marca primero en el listado a quién comprobar.")
        template = _company(request).dossier_templates.filter(
            pk=request.POST.get("template_id", ""), scope=scope).first()
        if template is None:
            return _error("Elige la plantilla de dosier.")
        model = PersonIdentity if section == "per" else MachineAsset
        missing, lines = [], []
        for subject in model.objects.filter(pk__in=ids):
            lacking = core.missing_types(subject, template)
            if lacking:
                missing.append(str(subject.pk))
                lines.append("%s: %s" % (
                    core.subject_label(subject), ", ".join(lacking)))
        if not missing:
            message = "Todos los marcados (%d) tienen todo lo de «%s»." % (
                len(ids), template.name)
        else:
            message = "A %d de %d les falta algo de «%s» (resaltados): %s" % (
                len(missing), len(ids), template.name, " · ".join(lines))
        return JsonResponse({
            "ok": True, "missing": missing, "message": message,
        })
