# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/dossier_service.py
"""
H30 (S127). Documents hidden inside a dossier are extracted, never lost.

---

H30 (S127). Los documentos que viajan dentro de un dossier se sacan a
su propio archivo; nunca se pierden.

Causa de raíz (S127, verificada con el historial): la regla S041 del
H28 ("dossier con certeza -> papelera") daba por hecho que todo lo que
lleva un dossier ya estaba archivado por separado. Con los escaneos y
fotos de tarjetas (DNI + permiso + tacógrafo + CAP en una hoja) no es
así: el dossier era la única copia. Caso real: el escaneo de Gutiérrez
Mateo Cristhian fue a la papelera como "[DOSSIER ELIMINADO] ... DNI,
Tarjeta de Conductor, Permiso de Conducción y CAP", y sus avisos daban
esos documentos por inexistentes. Y cuando Gemini sí ponía un tipo al
dossier (el "carnet de conducir" de Campos Román, el "NIE" de Correa),
solo se archivaba ese tipo: el DNI y la tarjeta de conductor que iban
en la misma hoja quedaban escondidos.

Regla nueva, aprobada por Miguel Ángel (S127):
- Gemini enumera en la misma llamada (`contained_documents`, sin coste
  extra) cada documento del dossier: tipo, páginas y fechas.
- Por cada uno que la persona no tenga ya archivado y vivo, se crea un
  archivo propio con su tipo (`extract_document`), cortado por páginas;
  si varias tarjetas comparten hoja, cada tipo lleva una copia de esa
  hoja. Mismo flujo que una subida desde la ficha
  (`subject_upload_service.upload_subject_document`): texto, fecha,
  sustitución del vigente y colas de contrato/permiso.
- El dossier original solo va a la papelera cuando todo lo que lleva
  ya queda archivado. Si queda algo sin poder sacar (tipo desconocido,
  persona sin resolver), va a NO CONFORMES para revisión humana.
"""
import datetime
import logging

import fitz
from django.contrib.contenttypes.models import ContentType

from document_explorer.models import (
    DocumentIndexEntry, DocumentTypeCatalog, PersonIdentity,
)
from spare_parts.gcs_service import download_bytes

logger = logging.getLogger(__name__)

# Tipos de un dominio que una persona puede tener (los del dominio
# PERSONAL y los comunes).
_PERSON_DOMAINS = ("PERSONAL", "BOTH")


def parse_date(value):
    """
    ISO date (AAAA-MM-DD) or None.

    ---

    Fecha ISO (AAAA-MM-DD) o None si viene vacía o mal formada.
    """
    try:
        return datetime.date.fromisoformat((value or "").strip()[:10])
    except ValueError:
        return None


def person_type(type_code):
    """
    Catalog type a person can own, or None.

    ---

    Tipo del catálogo, activo y de persona, o None.
    """
    return DocumentTypeCatalog.objects.filter(
        code=(type_code or "").strip(), is_active=True,
        domain__in=_PERSON_DOMAINS,
    ).first()


def already_filed(person, document_type, expiry_date=None):
    """
    Live document of this type on the person that covers the one found.

    ---

    Documento vivo de ese tipo en la ficha de la persona que ya cubre
    el encontrado en el dossier: con fecha de caducidad igual o
    posterior, o cualquiera si el del dossier no trae caducidad. Un
    vigente sin caducidad no cubre a uno que sí la trae (se extrae: es
    mejor un duplicado que un documento escondido).
    """
    live = DocumentIndexEntry.objects.filter(
        document_type=document_type,
        domain_content_type=ContentType.objects.get_for_model(person),
        domain_object_id=person.pk,
        entry_kind=DocumentIndexEntry.KIND_FILE,
        deleted_at__isnull=True, purged_at__isnull=True,
    )
    if expiry_date is None:
        return live.order_by("-id").first()
    return live.filter(expiry_date__gte=expiry_date).order_by("-id").first()


def page_subset(data, filename, pages):
    """
    Bytes and extension of the given pages (1-based) of a PDF.

    ---

    Bytes y extensión de las páginas pedidas (numeradas desde 1) de un
    PDF. Si no es un PDF, no hay páginas o alguna no existe, el archivo
    entero tal cual: nunca se recorta a ciegas.
    """
    extension = (
        filename.rsplit(".", 1)[-1].lower() if "." in filename else "pdf"
    )
    if extension != "pdf" or not pages:
        return data, extension
    try:
        source = fitz.open(stream=data, filetype="pdf")
    except Exception:
        return data, extension
    try:
        wanted = sorted({int(page) for page in pages})
        if wanted[0] < 1 or wanted[-1] > source.page_count:
            return data, extension
        if len(wanted) == source.page_count:
            return data, extension
        subset = fitz.open()
        for page in wanted:
            subset.insert_pdf(source, from_page=page - 1, to_page=page - 1)
        return subset.tobytes(), "pdf"
    finally:
        source.close()


def extract_document(
    source, person, document_type, pages=None, issue_date=None,
    expiry_date=None, data=None,
):
    """
    New typed file on the person with the given pages of `source`.

    ---

    Crea en la ficha de la persona un archivo nuevo con su tipo, con
    las páginas indicadas de `source` (todo el archivo si no se dan), y
    las fechas leídas en el propio documento. El original no se toca.
    Devuelve la `DocumentIndexEntry` nueva.
    """
    from document_explorer.subject_upload_service import (
        upload_subject_document,
    )

    if data is None:
        data = download_bytes(source.bucket, source.blob_name)
    content, extension = page_subset(data, source.name, pages)
    stem = source.name.rsplit(".", 1)[0] if "." in source.name else (
        source.name
    )
    outcome = upload_subject_document(
        subject=person,
        domain_content_type=ContentType.objects.get_for_model(person),
        document_type=document_type,
        data=content,
        original_filename="%s.%s" % (stem, extension),
        typed_date=expiry_date if document_type.tracks_expiry else None,
        subject_label=str(person),
        typed_issue_date=issue_date,
        filename_date=expiry_date or issue_date,
    )
    entry = outcome["entry"]
    note = "Sacado del dossier %s (#%d)%s." % (
        source.name, source.pk,
        ", página(s) %s" % ", ".join(str(page) for page in pages)
        if pages else "",
    )
    entry.curator_note = (
        "%s\n%s" % (entry.curator_note, note) if entry.curator_note
        else note
    )
    entry.save(update_fields=["curator_note"])
    logger.info(
        "# [dossier_service] %s -> #%d %s (%s)",
        source.name, entry.pk, entry.name, document_type.code,
    )
    return entry


def extract_contained(source, person, contained, skip_codes=(), data=None):
    """
    Extract every document of a dossier the person does not have yet.

    ---

    Recorre `contained` (lista de Gemini: `document_type_code`,
    `pages`, `issue_date`, `expiry_date`) y saca a su propio archivo
    cada documento que la persona no tenga ya archivado. `skip_codes`:
    tipos que no se sacan (el que se le da al propio original).

    Devuelve `(extracted, covered, unknown)`: listas de textos cortos
    para el historial -- extraídos, ya archivados, y sin tipo de
    persona reconocible (estos impiden mandar el original a la
    papelera).
    """
    extracted, covered, unknown = [], [], []
    seen = set()
    for item in contained or []:
        code = (item.get("document_type_code") or "").strip()
        document_type = person_type(code)
        if document_type is None:
            unknown.append(code or "?")
            continue
        expiry = parse_date(item.get("expiry_date"))
        key = (code, expiry)
        if code in skip_codes or key in seen:
            continue
        seen.add(key)
        existing = already_filed(person, document_type, expiry)
        if existing is not None:
            covered.append("%s (ya archivado #%d)" % (code, existing.pk))
            continue
        if data is None:
            data = download_bytes(source.bucket, source.blob_name)
        new_entry = extract_document(
            source, person, document_type,
            pages=item.get("pages") or None,
            issue_date=parse_date(item.get("issue_date")),
            expiry_date=expiry, data=data,
        )
        extracted.append("%s -> #%d" % (code, new_entry.pk))
    return extracted, covered, unknown


def dossier_note(extracted, covered, unknown):
    """
    One-line summary for the operation log.

    ---

    Resumen de una línea para el historial de operaciones.
    """
    parts = []
    if extracted:
        parts.append("Sacados del dossier: %s" % ", ".join(extracted))
    if covered:
        parts.append("Ya archivados: %s" % ", ".join(covered))
    if unknown:
        parts.append("Sin tipo de persona: %s" % ", ".join(unknown))
    return " -- ".join(parts)


def resolve_dossier_person(entry, result):
    """
    Owner of a personal dossier, or None.

    ---

    Dueño de un dossier personal, con el mismo resolvedor que el resto
    del H28 (DNI, nombre único, lectura con errores; crea al trabajador
    nuevo con las mismas reglas).
    """
    from document_explorer.classification_service import (
        resolve_or_create_person_identity,
    )

    person = resolve_or_create_person_identity(result, entry)
    return person if isinstance(person, PersonIdentity) else None
