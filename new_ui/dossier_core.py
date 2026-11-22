# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/new_ui/dossier_core.py
"""
Dossier building for the new interface (S163).

Copied from the old interface (panel/views_documentation_h30.py: the
dossier PDF/ZIP builders and template resolution; panel/
views_dossier_bundle.py: one e-mail or download for several workers
and machines), renamed so the new interface never calls the old code.

---

Construcción de dosieres de la nueva interfaz (S163), copiada de la
antigua (panel/views_documentation_h30.py: constructores del PDF único
y del ZIP y resolución de plantillas; panel/views_dossier_bundle.py: un
correo o una descarga con varios trabajadores y máquinas juntos). Regla
de Miguel Ángel: copiar y renombrar, nunca llamar a lo antiguo, para
poder borrar cualquiera de las dos interfaces sin tocar la otra.

Un "sujeto" es una tupla (persona o máquina, rótulo, documentos,
entregas de EPI). Formatos de salida:
- combined: un PDF con todos los dosieres seguidos, cada uno con su
  portada.
- per_subject: un PDF por persona o máquina.
- zip: un ZIP con una carpeta por persona o máquina y los originales.
Un dosier que no puede pasar a PDF va como su propio ZIP, nunca se
pierde.
"""
import io
import re
import zipfile
from datetime import date, datetime
from email.message import EmailMessage as StdEmailMessage
from email.utils import make_msgid
from html import escape as html_escape

from django.contrib.contenttypes.models import ContentType
from django.contrib.staticfiles.finders import find as find_static
from django.utils import timezone
from django.utils.text import slugify

from document_explorer import naming_service
from document_explorer.models import (
    DocumentIndexEntry, EpiDelivery, PersonIdentity,
)
from document_explorer.required_documentation_service import (
    get_required_type_ids,
)
from document_management.pdf_merge_service import (
    EmptyDocumentListError, build_index_page, convert_to_pdf_bytes,
    merge_pdfs,
)
from fleet.models import MachineAsset
from new_ui.docs_core import BUCKET, _split_current_obsolete
from new_ui.eml_utils import eml_bytes
from spare_parts.gcs_service import download_bytes

FORMAT_COMBINED = "combined"
FORMAT_PER_SUBJECT = "per_subject"
FORMAT_ZIP = "zip"
FORMATS = (FORMAT_COMBINED, FORMAT_PER_SUBJECT, FORMAT_ZIP)

# La mayoría de servidores de correo rechazan más de 20-25 MB.
SIZE_WARNING_BYTES = 20 * 1024 * 1024

_NAME_DATE_RE = re.compile(r"_(\d{8})(?:_\d+)?\.[A-Za-z0-9]+$")


class DossierError(Exception):
    """
    No document can go in the dossier.

    ---

    Ningún documento puede entrar en el dosier (formato no soportado o
    nada que incluir). Lo muestra quien llama.
    """


# ---------------------------------------------------------------- rótulos
def person_label(person):
    return "%s %s, %s" % (
        person.first_surname, person.second_surname, person.given_name,
    )


def machine_label(machine):
    return "%s -- %s" % (machine.code, machine.brand_model or "")


def subject_label(subject):
    if isinstance(subject, MachineAsset):
        return machine_label(subject)
    return person_label(subject)


def _subject_texts(subject):
    """
    Cover lines and filename token of a person's or machine's dossier.

    ---

    Líneas de portada y token del nombre de archivo del dosier: persona
    (nombre, DNI, empresa) o máquina (código, marca y modelo,
    matrícula).
    """
    if isinstance(subject, MachineAsset):
        title = "%s -- %s" % (subject.code, subject.brand_model or "")
        plate = "Matrícula: %s" % (subject.plate or "sin matrícula")
        lines = [(title, 13, False), (plate, 11, False)]
        return lines, naming_service._sanitize_token(subject.code)
    person_line = (
        f"{subject.first_surname} {subject.second_surname}, "
        f"{subject.given_name} ({subject.dni})"
    )
    lines = [
        (person_line, 13, False),
        (subject.employer_legal_name or "Sin empresa asignada", 11, False),
    ]
    token = naming_service.build_person_folder_name(
        subject.first_surname, subject.second_surname, subject.given_name,
    )
    return lines, token


def _entry_bytes(entry):
    """
    Bytes of a dossier entry; a generated logbook goes as external book.

    ---

    Bytes de un documento del dosier. Un libro historial generado por
    la plataforma va siempre como libro para externos (sin mecánicos);
    los escaneados, tal cual.
    """
    source = getattr(entry, "logbook_source", None)
    if source is not None and source.kind == source.KIND_GENERATED:
        from fleet.logbook_service import render_logbook_pdf

        return render_logbook_pdf(source.machine, external=True)
    return download_bytes(entry.bucket, entry.blob_name)


def _with_epi_entries(entries, epi_deliveries):
    entries = list(entries)
    entry_ids = {entry.pk for entry in entries}
    return entries + [
        d.source_entry for d in (epi_deliveries or [])
        if d.source_entry_id and d.source_entry_id not in entry_ids
    ]


def _family_name(entry):
    return (
        entry.document_type.get_person_family_display()
        if entry.document_type_id else "—"
    )


# ------------------------------------------------------------ constructores
def build_pdf(subject, entries, epi_deliveries=None):
    """
    One PDF: cover with index + every document. Returns (bytes, name).

    ---

    Un PDF único: portada con índice y los documentos detrás. Lo que no
    se puede pasar a PDF (Word, Excel...) se anota en la portada como
    "no incluido", nunca se pierde en silencio. Las nóminas
    confidenciales nunca entran. Lanza DossierError si no entra nada.
    """
    included_pdfs = []
    included_lines = []
    skipped_lines = []
    for entry in _with_epi_entries(entries, epi_deliveries):
        extension = entry.name.rsplit(".", 1)[-1] if "." in entry.name else ""
        label = (
            entry.document_type.label if entry.document_type_id else entry.name
        )
        if entry.is_confidential:
            skipped_lines.append("%s -- confidencial" % label)
            continue
        family = _family_name(entry)
        pdf_bytes = convert_to_pdf_bytes(_entry_bytes(entry), extension)
        if pdf_bytes is None:
            skipped_lines.append(
                f"{label} ({family}) -- formato .{extension or '?'} "
                "no soportado",
            )
            continue
        included_pdfs.append(pdf_bytes)
        if entry.expiry_date:
            when = f"vigente {entry.expiry_date}"
        elif entry.issue_date:
            when = f"emisión {entry.issue_date}"
        else:
            when = "sin fecha"
        included_lines.append(f"{label} -- {family} -- {when}")

    if not included_pdfs:
        raise DossierError(
            "Ningún documento tiene un formato que se pueda pasar a PDF "
            "(usa el ZIP para estos archivos).",
        )

    subject_lines, token = _subject_texts(subject)
    header_lines = [
        ("DOSSIER DE DOCUMENTACIÓN", 18, True),
        *subject_lines,
        (f"Generado: {timezone.localdate().isoformat()}", 10, False),
        (f"Documentos incluidos: {len(included_lines)}", 11, True),
    ]
    footer_note = (
        "No incluidos en este PDF (formato no soportado -- "
        "descárgalos en ZIP): " + "; ".join(skipped_lines)
        if skipped_lines else None
    )
    cover = build_index_page(header_lines, included_lines, footer_note)
    try:
        merged = merge_pdfs([cover] + included_pdfs)
    except EmptyDocumentListError as exc:
        raise DossierError(str(exc)) from exc
    return merged, f"Dossier_{token}_{timezone.localdate().isoformat()}.pdf"


def build_zip(subject, entries, epi_deliveries=None):
    """
    ZIP with the original files, one folder per family. (bytes, name).

    ---

    ZIP con los archivos originales con su nombre canónico, una carpeta
    por familia documental. Las nóminas confidenciales nunca entran.
    """
    buffer = io.BytesIO()
    used_names = set()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for entry in _with_epi_entries(entries, epi_deliveries):
            if entry.is_confidential:
                continue
            folder = (
                slugify(entry.document_type.get_person_family_display())
                if entry.document_type_id else "sin-familia"
            )
            arcname = f"{folder}/{entry.name}"
            if "." in entry.name:
                base_name, extension = entry.name.rsplit(".", 1)
            else:
                base_name, extension = entry.name, ""
            suffix = 2
            while arcname in used_names:
                arcname = (
                    f"{folder}/{base_name}_{suffix}.{extension}"
                    if extension else f"{folder}/{base_name}_{suffix}"
                )
                suffix += 1
            used_names.add(arcname)
            zf.writestr(arcname, _entry_bytes(entry))
    _lines, token = _subject_texts(subject)
    return (
        buffer.getvalue(),
        f"Dossier_{token}_{timezone.localdate().isoformat()}.zip",
    )


# ------------------------------------------------------------- plantillas
def _entry_date(entry):
    """
    Date that orders a document of a cumulative type.

    ---

    Fecha con la que se ordena un documento de un tipo acumulable: la de
    emisión; sin ella, la del nombre normalizado (..._AAAAMMDD.pdf); sin
    ninguna, el día en que se subió.
    """
    if entry.issue_date:
        return entry.issue_date
    match = _NAME_DATE_RE.search(entry.name or "")
    if match:
        try:
            return datetime.strptime(match.group(1), "%Y%m%d").date()
        except ValueError:
            pass
    if entry.indexed_at:
        return timezone.localtime(entry.indexed_at).date()
    return date.min


def _latest_per_cumulative_type(entries):
    """
    Keep only the newest document of each cumulative type.

    ---

    De cada tipo acumulable (entregas de EPIs, formaciones...) solo los
    de la fecha más reciente; varios del mismo día van todos.
    """
    newest = {}
    for entry in entries:
        if entry.document_type_id and entry.document_type.is_cumulative:
            day = _entry_date(entry)
            newest[entry.document_type_id] = max(
                day, newest.get(entry.document_type_id, day))
    return [
        entry for entry in entries
        if not (entry.document_type_id and entry.document_type.is_cumulative)
        or _entry_date(entry) == newest[entry.document_type_id]
    ]


def template_entries(subject, template):
    """
    Current document of each template type for this subject, now.

    ---

    El vigente de cada tipo de la plantilla para esta persona o
    máquina, calculado en este momento con las reglas de la ficha.
    """
    ct = ContentType.objects.get_for_model(subject)
    type_ids = list(template.document_types.values_list("pk", flat=True))
    entries = DocumentIndexEntry.objects.filter(
        bucket=BUCKET, domain_content_type=ct, domain_object_id=subject.pk,
        entry_kind=DocumentIndexEntry.KIND_FILE,
        deleted_at__isnull=True, purged_at__isnull=True,
        document_type_id__in=type_ids,
    ).select_related("document_type")
    current, _obsolete = _split_current_obsolete(
        list(entries), get_required_type_ids(subject),
    )
    current = _latest_per_cumulative_type(current)
    current.sort(key=lambda e: (e.document_type.family, e.document_type.label))
    return current


def template_epi_deliveries(person, template):
    """
    Latest delivery of each EPI of the template for this person.

    ---

    La última entrega de cada EPI marcado en la plantilla; su documento
    real va en el dosier como uno más.
    """
    epi_ids = list(template.epi_items.values_list("pk", flat=True))
    if not epi_ids or not isinstance(person, PersonIdentity):
        return []
    latest = {}
    for delivery in EpiDelivery.objects.filter(
        person=person, epi_id__in=epi_ids,
    ).select_related("epi", "source_entry").order_by("-delivery_date"):
        latest.setdefault(delivery.epi_id, delivery)
    return list(latest.values())


def missing_types(subject, template):
    """
    Labels of the template types with no current document now.

    ---

    Los tipos de la plantilla que esta persona o máquina no tiene hoy
    vigentes.
    """
    found = {e.document_type_id for e in template_entries(subject, template)}
    return [
        dt.label for dt in template.document_types.order_by("label")
        if dt.pk not in found
    ]


# ------------------------------------------------- correo / descarga juntos
def attachments(subjects, output_format):
    """
    Attachments as (bytes, maintype, subtype, filename).

    ---

    Los adjuntos en el formato elegido (ver arriba).
    """
    today = timezone.localdate().isoformat()
    result = []
    if output_format == FORMAT_ZIP:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as outer:
            for subject, _label, entries, epi in subjects:
                data, name = build_zip(subject, entries, epi)
                folder = name.rsplit(".", 1)[0]
                with zipfile.ZipFile(io.BytesIO(data)) as inner:
                    for info in inner.infolist():
                        outer.writestr(
                            "%s/%s" % (folder, info.filename),
                            inner.read(info.filename),
                        )
        result.append((
            buffer.getvalue(), "application", "zip",
            "Documentacion_%s.zip" % today,
        ))
        return result
    pdf_parts = []
    for subject, _label, entries, epi in subjects:
        try:
            data, name = build_pdf(subject, entries, epi)
        except DossierError:
            data, name = build_zip(subject, entries, epi)
            result.append((data, "application", "zip", name))
            continue
        if output_format == FORMAT_COMBINED:
            pdf_parts.append(data)
        else:
            result.append((data, "application", "pdf", name))
    if len(pdf_parts) == 1 and len(subjects) == 1:
        _subject = subjects[0][0]
        _lines, token = _subject_texts(_subject)
        result.insert(0, (
            pdf_parts[0], "application", "pdf",
            f"Dossier_{token}_{today}.pdf",
        ))
    elif pdf_parts:
        result.insert(0, (
            merge_pdfs(pdf_parts), "application", "pdf",
            "Documentacion_%s.pdf" % today,
        ))
    return result


def download(subjects, output_format):
    """
    (bytes, content_type, filename): the file, or all in one ZIP.

    ---

    Los mismos adjuntos que el correo, para descargar: el archivo tal
    cual si es uno; si son varios, todos en un ZIP.
    """
    files = attachments(subjects, output_format)
    if len(files) == 1:
        data, maintype, subtype, filename = files[0]
        return data, "%s/%s" % (maintype, subtype), filename
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for data, _m, _s, name in files:
            zf.writestr(name, data)
    return (
        buffer.getvalue(), "application/zip",
        "Documentacion_%s.zip" % timezone.localdate().isoformat(),
    )


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


def build_eml(subjects, output_format, body_html, sender_company_user):
    """
    Outlook draft `.eml` (X-Unsent). Returns (bytes, attachments size).

    ---

    Borrador `.eml` de Outlook: sin destinatario, cuerpo por defecto con
    lo que va adjunto (o el escrito), la firma de quien envía y los
    adjuntos. Devuelve (bytes, tamaño de los adjuntos).
    """
    files = attachments(subjects, output_format)
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
    logo_path = find_static("new_ui/img/grupo_alvarez_logo_color.png")
    if logo_path:
        with open(logo_path, "rb") as logo_file:
            msg.get_payload()[1].add_related(
                logo_file.read(), "image", "png", cid=logo_cid,
            )
    size = 0
    for data, maintype, subtype, filename in files:
        msg.add_attachment(
            data, maintype=maintype, subtype=subtype, filename=filename,
        )
        size += len(data)
    return eml_bytes(msg), size
