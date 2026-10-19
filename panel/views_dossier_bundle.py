# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/views_dossier_bundle.py
"""
One e-mail with the documentation of several workers and machines
together (S130). Miguel Ángel: the documentation "tiene que ir toda
junta para no generar varios correos a la misma empresa" -- workers,
machines, or workers and machines, always ONE e-mail. A single worker
or machine is just a selection of one.

GET returns the dossier templates of the company (personal and
machine) for the shared modal of the Documentation hub. POST builds
the `.eml` as an Outlook draft (`X-Unsent: 1`): no recipient, default
body listing what is attached, the sender's signature and the
attachments in the chosen format:

- `combined`: one PDF with every dossier one after another, each with
  its own cover.
- `per_subject`: one PDF per worker or machine, all in the same mail.
- `zip`: one ZIP with a folder per worker or machine holding the
  original files.

A dossier that cannot become a PDF (no supported format) goes in as
its own ZIP, never dropped. Workers or machines with no current
document of the chosen template are left out and reported.

---

Un solo correo con la documentación de varios trabajadores y máquinas
juntos (S130). Miguel Ángel: la documentación "tiene que ir toda junta
para no generar varios correos a la misma empresa" -- trabajadores,
máquinas, o trabajadores y máquinas, siempre UN correo. Uno solo es
simplemente una selección de uno.

GET devuelve las plantillas de dosier de la empresa (de personal y de
maquinaria) para el modal común del hub de Documentación. POST
construye el `.eml` como borrador de Outlook (`X-Unsent: 1`): sin
destinatario, con un cuerpo por defecto que enumera lo adjunto, la
firma de quien envía y los adjuntos en el formato elegido (ver arriba).
Un dosier que no puede pasar a PDF va como su propio ZIP, nunca se
pierde. Los trabajadores o máquinas sin ningún documento vigente de la
plantilla elegida se omiten y se avisan.
"""

import io
import json
import zipfile
from email.message import EmailMessage as StdEmailMessage
from email.utils import make_msgid
from html import escape as html_escape

from django.contrib.staticfiles.finders import find as find_static
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.views import View

from document_explorer.models import PersonalDossierTemplate, PersonIdentity
from document_management.pdf_merge_service import merge_pdfs
from fleet.models import MachineAsset
from panel.mixins import DocsUploadAccessMixin
from panel.views_documentation_h30 import (
    DossierBuildError,
    _build_dossier_pdf_bytes,
    _build_dossier_zip_bytes,
    _resolve_machine_template_entries,
    _resolve_template_entries,
    _resolve_template_epi_deliveries,
)

FORMAT_COMBINED = "combined"
FORMAT_PER_SUBJECT = "per_subject"
FORMAT_ZIP = "zip"
FORMATS = (FORMAT_COMBINED, FORMAT_PER_SUBJECT, FORMAT_ZIP)

# Most mail servers refuse messages above 20-25 MB; the page warns.
# La mayoría de servidores de correo rechazan más de 20-25 MB; la
# página avisa.
SIZE_WARNING_BYTES = 20 * 1024 * 1024


def _person_label(person):
    return "%s %s, %s" % (
        person.first_surname, person.second_surname, person.given_name,
    )


def _machine_label(machine):
    return "%s -- %s" % (machine.code, machine.brand_model or "")


def _template(company, pk, scope):
    if not pk:
        return None
    return company.dossier_templates.filter(pk=pk, scope=scope).first()


def _collect_subjects(request, company):
    """
    Resolve the selected workers and machines against their template.
    Returns (subjects, skipped, error): subjects is a list of
    (subject, label, entries, epi_deliveries).
    ---
    Resuelve los trabajadores y máquinas marcados contra su plantilla.
    """
    person_ids = [x for x in request.POST.getlist("person_ids") if x]
    machine_ids = [x for x in request.POST.getlist("machine_ids") if x]
    if not person_ids and not machine_ids:
        return None, None, "No hay ningún trabajador ni máquina seleccionado."

    person_template = _template(
        company, request.POST.get("person_template_id", "").strip(),
        PersonalDossierTemplate.SCOPE_PERSONAL,
    )
    machine_template = _template(
        company, request.POST.get("machine_template_id", "").strip(),
        PersonalDossierTemplate.SCOPE_MACHINE,
    )
    if person_ids and person_template is None:
        return None, None, "Falta la plantilla de dosier de los trabajadores."
    if machine_ids and machine_template is None:
        return None, None, "Falta la plantilla de dosier de las máquinas."

    subjects = []
    skipped = []
    people = PersonIdentity.objects.filter(pk__in=person_ids).order_by(
        "first_surname", "second_surname", "given_name",
    )
    for person in people:
        entries = _resolve_template_entries(person, person_template)
        epi_deliveries = _resolve_template_epi_deliveries(
            person, person_template,
        )
        if entries or epi_deliveries:
            subjects.append(
                (person, _person_label(person), entries, epi_deliveries),
            )
        else:
            skipped.append(_person_label(person))
    machines = MachineAsset.objects.filter(pk__in=machine_ids).order_by("code")
    for machine in machines:
        entries = _resolve_machine_template_entries(machine, machine_template)
        if entries:
            subjects.append((machine, _machine_label(machine), entries, None))
        else:
            skipped.append(_machine_label(machine))
    if not subjects:
        return None, skipped, (
            "Ninguno de los seleccionados tiene documentos vigentes de "
            "la plantilla elegida."
        )
    return subjects, skipped, None


def _attachments(subjects, output_format):
    """
    Build the attachments: a list of (bytes, maintype, subtype, filename).
    ---
    Construye los adjuntos: lista de (bytes, tipo, subtipo, nombre).
    """
    today = timezone.localdate().isoformat()
    attachments = []

    if output_format == FORMAT_ZIP:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as outer:
            for subject, label, entries, epi in subjects:
                zip_bytes, zip_name = _build_dossier_zip_bytes(
                    subject, entries, epi_deliveries=epi,
                )
                folder = zip_name.rsplit(".", 1)[0]
                with zipfile.ZipFile(io.BytesIO(zip_bytes)) as inner:
                    for info in inner.infolist():
                        outer.writestr(
                            "%s/%s" % (folder, info.filename),
                            inner.read(info.filename),
                        )
        attachments.append((
            buffer.getvalue(), "application", "zip",
            "Documentacion_%s.zip" % today,
        ))
        return attachments

    pdf_parts = []
    for subject, label, entries, epi in subjects:
        try:
            pdf_bytes, pdf_name = _build_dossier_pdf_bytes(
                subject, entries, epi_deliveries=epi,
            )
        except DossierBuildError:
            zip_bytes, zip_name = _build_dossier_zip_bytes(
                subject, entries, epi_deliveries=epi,
            )
            attachments.append((zip_bytes, "application", "zip", zip_name))
            continue
        if output_format == FORMAT_COMBINED:
            pdf_parts.append(pdf_bytes)
        else:
            attachments.append((pdf_bytes, "application", "pdf", pdf_name))
    if pdf_parts:
        attachments.insert(0, (
            merge_pdfs(pdf_parts), "application", "pdf",
            "Documentacion_%s.pdf" % today,
        ))
    return attachments


def _default_body_html(subjects):
    people = [label for subject, label, _e, _d in subjects
              if not isinstance(subject, MachineAsset)]
    machines = [label for subject, label, _e, _d in subjects
                if isinstance(subject, MachineAsset)]
    parts = [
        "<p>Buenos días:</p>",
        "<p>Les adjuntamos la documentación de:</p>",
    ]
    if people:
        parts.append("<p><strong>Trabajadores</strong></p><ul>")
        parts.extend("<li>%s</li>" % html_escape(name) for name in people)
        parts.append("</ul>")
    if machines:
        parts.append("<p><strong>Maquinaria</strong></p><ul>")
        parts.extend("<li>%s</li>" % html_escape(name) for name in machines)
        parts.append("</ul>")
    parts.append(
        "<p>Quedamos a su disposición para cualquier aclaración.</p>"
        "<p>Un saludo.</p>",
    )
    return "".join(parts)


def _subject_line(subjects):
    n_people = sum(
        1 for subject, *_rest in subjects
        if not isinstance(subject, MachineAsset)
    )
    n_machines = len(subjects) - n_people
    pieces = []
    if n_people:
        pieces.append(
            "%d trabajador%s" % (n_people, "es" if n_people != 1 else ""),
        )
    if n_machines:
        pieces.append(
            "%d máquina%s" % (n_machines, "s" if n_machines != 1 else ""),
        )
    return "Documentación -- " + " y ".join(pieces)


def build_bundle_eml(subjects, output_format, body_html, sender_company_user):
    """
    Build the draft `.eml`. Returns (eml_bytes, attachments_size).
    ---
    Construye el `.eml` borrador. Devuelve (bytes, tamaño de adjuntos).
    """
    attachments = _attachments(subjects, output_format)
    if not (body_html or "").strip():
        body_html = _default_body_html(subjects)

    msg = StdEmailMessage()
    msg["Subject"] = _subject_line(subjects)
    msg["X-Unsent"] = "1"
    msg.set_content(
        "Documentación adjunta.\n"
        "Este cliente de correo no muestra HTML -- abra este mensaje "
        "con un cliente compatible."
    )
    signature_html = (
        (sender_company_user.email_signature_html or "").strip()
        if sender_company_user else ""
    )
    logo_cid = make_msgid()
    msg.add_alternative(
        f"""
        <html><body style="font-family: Arial, sans-serif;">
          <p style="margin-bottom:16px;">
            <img src="cid:{logo_cid[1:-1]}" alt="Grupo Álvarez" height="40">
          </p>
          {body_html}
          {signature_html}
        </body></html>
        """,
        subtype="html",
    )
    logo_path = find_static("panel/img/grupo_alvarez_logo.png")
    if logo_path:
        with open(logo_path, "rb") as logo_file:
            msg.get_payload()[1].add_related(
                logo_file.read(), "image", "png", cid=logo_cid,
            )
    size = 0
    for data, maintype, subtype, filename in attachments:
        msg.add_attachment(
            data, maintype=maintype, subtype=subtype, filename=filename,
        )
        size += len(data)
    return bytes(msg), size


class DossierBundleEmailView(DocsUploadAccessMixin, View):
    """
    GET: dossier templates for the modal. POST: the single `.eml`.
    ---
    GET: plantillas de dosier para el modal. POST: el `.eml` único.
    """

    def get(self, request):
        company = request.user.company_user.company
        templates = company.dossier_templates.order_by("name")

        def listed(scope):
            return [
                {"id": t.pk, "name": t.name}
                for t in templates if t.scope == scope
            ]

        return JsonResponse({
            "person_templates": listed(PersonalDossierTemplate.SCOPE_PERSONAL),
            "machine_templates": listed(PersonalDossierTemplate.SCOPE_MACHINE),
        })

    def post(self, request):
        company_user = request.user.company_user
        output_format = request.POST.get("format", FORMAT_COMBINED)
        if output_format not in FORMATS:
            return JsonResponse({"error": "Formato no válido."}, status=400)
        subjects, skipped, error = _collect_subjects(
            request, company_user.company,
        )
        if error:
            return JsonResponse(
                {"error": error, "skipped": skipped or []}, status=400,
            )
        try:
            eml_bytes, size = build_bundle_eml(
                subjects, output_format,
                request.POST.get("body_html", "").strip(), company_user,
            )
        except DossierBuildError as exc:
            return JsonResponse({"error": str(exc)}, status=400)

        today = timezone.localdate().isoformat()
        response = HttpResponse(eml_bytes, content_type="message/rfc822")
        response["Content-Disposition"] = (
            f'attachment; filename="documentacion_{today}.eml"'
        )
        response["X-Bundle-Skipped"] = json.dumps(skipped)
        response["X-Bundle-Size"] = str(size)
        response["X-Bundle-Too-Big"] = "1" if size > SIZE_WARNING_BYTES else "0"
        return response
