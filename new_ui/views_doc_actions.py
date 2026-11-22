# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/new_ui/views_doc_actions.py
"""
Document actions of the new interface (S163).

---

Acciones sobre documentos de personas y máquinas en la nueva interfaz
(S163), desde el panel Acciones de Personal / Centros de gasto ›
Documentos:
- Subir o actualizar (nueva versión de un tipo: sustituye a la
  anterior, con la comprobación del contenido de siempre).
- Cambiar el tipo de los marcados (nombre canónico y sustituciones
  rehechas, como en la ficha antigua).
- Mandar a la papelera los marcados (borrado blando; el cubo no se
  toca).
- Separar las páginas de un PDF de una persona en documentos (copia de
  panel/views_document_split.py).
El historial de un tipo y la descarga van por el propio listado y la
fila (new_ui.js). Nada llama a la interfaz antigua.
"""
import base64
import json
import re
import unicodedata

import fitz
from django.contrib.contenttypes.models import ContentType
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views import View

from document_explorer import dossier_service
from document_explorer.models import (
    DocumentIndexEntry, DocumentTypeCatalog, PersonIdentity,
)
from document_explorer.personal_content_classification import (
    resolve_type_from_content,
)
from document_explorer.subject_upload_service import change_document_type
from new_ui.docs_core import BUCKET
from new_ui.mixins import SuperuserRequiredMixin
from new_ui.views_docs import SubjectUploadView
from spare_parts.gcs_service import download_bytes

MAX_PAGES = 30
DOSSIER_CODE = "DOSSIER"
_PAGE_SPLIT = re.compile(r"=== P[áa]gina (\d+) ===")


def _ok(message, **extra):
    return JsonResponse({"ok": True, "message": message, **extra})


def _error(message):
    return JsonResponse({"ok": False, "message": message}, status=400)


def _marked_entries(request):
    ids = [v for v in request.POST.getlist("selected") if v.isdigit()]
    return DocumentIndexEntry.objects.filter(
        pk__in=ids, bucket=BUCKET, entry_kind=DocumentIndexEntry.KIND_FILE,
        deleted_at__isnull=True, purged_at__isnull=True,
    ).select_related("document_type")


def doc_types_context(section):
    """
    Active document types of the section, grouped by family.

    ---

    Los tipos activos de la sección (Personal: de persona y de los dos;
    Centros de gasto: de máquina y de los dos), por familia, para elegir
    el tipo al subir o al cambiarlo.
    """
    if section not in ("per", "cdg"):
        return {}
    for_person = section == "per"
    domains = ["PERSONAL", "BOTH"] if for_person else ["MACHINE", "BOTH"]
    groups = {}
    order = []
    for dt in DocumentTypeCatalog.objects.filter(
        is_active=True, domain__in=domains,
    ).exclude(code=DOSSIER_CODE).order_by("family", "label"):
        title = DocumentTypeCatalog.family_label(
            dt.family, for_person=for_person) if dt.family else "Sin familia"
        if title not in groups:
            groups[title] = []
            order.append(title)
        groups[title].append((dt.code, dt.label))
    return {
        "nui_doc_types": [(title, groups[title]) for title in order],
        "nui_doc_domain": "personal" if for_person else "machine",
    }


class DocumentUploadView(SuperuserRequiredMixin, View):
    """
    POST: upload documents of one person or machine, with a summary.

    ---

    POST: sube uno o varios documentos (o la nueva versión de uno) de la
    persona o máquina indicada (`domain`, `subject_pk`). La subida es la
    copiada de la ficha (views_docs.SubjectUploadView); aquí se resume
    en un aviso: qué quedó, con qué fecha, qué sustituyó y lo que la
    comprobación del contenido vio raro.
    """

    def post(self, request):
        domain = request.POST.get("domain", "")
        subject_pk = request.POST.get("subject_pk", "")
        if domain not in ("personal", "machine") or not subject_pk.isdigit():
            return _error("Elige primero de quién es (abre su ficha o usa "
                          "«Actualizar» en una fila).")
        response = SubjectUploadView().post(request, domain, int(subject_pk))
        data = json.loads(response.content or b"{}")
        if "uploaded" not in data:
            return _error(data.get("error") or "No se ha podido subir.")
        lines = []
        for item in data["uploaded"]:
            text = "Guardado %s" % item["entry_name"]
            if item.get("date_label"):
                text += " (%s %s)" % (item["date_kind"], item["date_label"])
            elif item.get("needs_date"):
                text += " (sin fecha: revísala)"
            if item.get("superseded_count"):
                text += "; sustituye a %d anterior(es)" % (
                    item["superseded_count"])
            mismatch = item.get("type_mismatch")
            if mismatch:
                text += "; ojo, el contenido parece otro tipo: %s" % (
                    mismatch.get("label") or mismatch.get("code")
                    if isinstance(mismatch, dict) else mismatch)
            if item.get("different"):
                text += "; datos distintos a los de la ficha: %s" % ", ".join(
                    "%s (ficha %s, leído %s)" % (
                        label, pair["current"], pair["read"])
                    for label, pair in item["different"].items())
            if item.get("warning"):
                text += "; la fecha escrita no coincide con la leída (%s)" % (
                    item["warning"]["system_date"])
            lines.append(text + ".")
        for item in data.get("errors") or []:
            lines.append("No subido %s: %s." % (item["file"], item["error"]))
        message = " ".join(lines) or "Nada que subir."
        if data.get("errors") and not data["uploaded"]:
            return _error(message)
        return _ok(message)


class DocumentChangeTypeView(SuperuserRequiredMixin, View):
    """
    POST: change the type of the marked documents.

    ---

    POST: cambia el tipo de los documentos marcados: nombre canónico del
    tipo nuevo, la sustitución deshecha en el viejo y hecha en el nuevo
    y, en máquinas, los datos que acredita (change_document_type). El
    archivo del cubo no se toca.
    """

    def post(self, request):
        new_type = DocumentTypeCatalog.objects.filter(
            code=request.POST.get("document_type_code", "").strip(),
            is_active=True).first()
        if new_type is None:
            return _error("Elige el tipo nuevo.")
        entries = list(_marked_entries(request))
        if not entries:
            return _error("Marca primero los documentos.")
        changed = 0
        for entry in entries:
            change_document_type(entry, new_type)
            changed += 1
        return _ok("%d documento(s) pasan a %s." % (changed, new_type.label))


class DocumentTrashView(SuperuserRequiredMixin, View):
    """
    POST: send the marked documents to the trash.

    ---

    POST: manda a la papelera los documentos marcados (solo
    deleted_at/deleted_by; el cubo no se toca, directriz 4.12).
    """

    def post(self, request):
        entries = _marked_entries(request)
        count = entries.update(deleted_at=timezone.now(),
                               deleted_by=request.user.company_user)
        if not count:
            return _error("Marca primero los documentos.")
        return _ok("%d documento(s) a la papelera." % count)


# --------------------------------------------------------------- separar
def _upper(value):
    value = unicodedata.normalize("NFKD", value or "")
    return "".join(
        c for c in value if not unicodedata.combining(c)).upper()


def _page_texts(ocr_text):
    parts = _PAGE_SPLIT.split(ocr_text or "")
    return {
        int(parts[i]): parts[i + 1] for i in range(1, len(parts) - 1, 2)
    }


def _person_entry(pk):
    person_ct = ContentType.objects.get_for_model(PersonIdentity)
    entry = get_object_or_404(
        DocumentIndexEntry, pk=pk, deleted_at__isnull=True,
        entry_kind=DocumentIndexEntry.KIND_FILE,
        domain_content_type=person_ct, is_confidential=False,
    )
    person = get_object_or_404(PersonIdentity, pk=entry.domain_object_id)
    return entry, person


def _already_extracted(source, person, document_type, numbers):
    note = "(#%d), página(s) %s." % (
        source.pk, ", ".join(map(str, sorted(numbers))))
    return DocumentIndexEntry.objects.filter(
        domain_content_type=ContentType.objects.get_for_model(person),
        domain_object_id=person.pk, document_type=document_type,
        deleted_at__isnull=True, curator_note__contains=note,
    ).exists()


def _mark_as_dossier(entry, created):
    """
    The split file becomes a "Dossier", visible in the file.

    ---

    El archivo separado pasa a ser un "Dossier" y sigue a la vista para
    volver a entrar y separar; con el cambio de tipo completo, deja el
    sitio del tipo que tenía y lo que había sustituido vuelve a contar.
    """
    if not entry.document_type_id or entry.document_type.code != (
            DOSSIER_CODE):
        dossier = DocumentTypeCatalog.objects.get(code=DOSSIER_CODE)
        change_document_type(entry, dossier)
    note = "Separado: %s." % "; ".join(created)
    entry.is_obsolete = False
    entry.curator_note = (
        "%s\n%s" % (entry.curator_note, note)
        if entry.curator_note else note)
    entry.save(update_fields=["is_obsolete", "curator_note"])


class DocumentSplitView(SuperuserRequiredMixin, View):
    """
    GET: pages with their suggested type. POST: take the documents out.

    ---

    GET: el formulario de Separar para Acciones (cada página en
    miniatura con el tipo que sugiere su texto ya leído); ?page=N, esa
    página en grande. POST: las páginas con el mismo tipo forman un
    documento nuevo en la ficha de la persona (mismo flujo que una
    subida); el original pasa a ser un Dossier.
    """

    def get(self, request, pk):
        entry, person = _person_entry(pk)
        data = download_bytes(entry.bucket, entry.blob_name)
        page_number = request.GET.get("page", "")
        try:
            pdf = fitz.open(stream=data, filetype="pdf")
        except Exception:
            if page_number:
                raise Http404("No es un PDF.")
            return render(request, "new_ui/_document_split.html",
                          {"error": "Este archivo no es un PDF."})
        if page_number.isdigit():
            number = int(page_number)
            if not 1 <= number <= pdf.page_count:
                pdf.close()
                raise Http404("No existe esa página.")
            png = pdf[number - 1].get_pixmap(dpi=130).tobytes("png")
            pdf.close()
            return HttpResponse(png, content_type="image/png")
        texts = _page_texts(entry.ocr_text)
        current = entry.document_type.code if entry.document_type_id else ""
        pages = []
        for index in range(min(pdf.page_count, MAX_PAGES)):
            pix = pdf[index].get_pixmap(dpi=45)
            code, ambiguous, matched = resolve_type_from_content(
                _upper(texts.get(index + 1, "")), current)
            pages.append({
                "number": index + 1,
                "image": base64.b64encode(pix.tobytes("png")).decode(),
                "suggested": code or "",
                "hint": ", ".join(sorted(matched)) if ambiguous else "",
            })
        context = {
            "entry": entry, "person": person, "pages": pages,
            "page_count": pdf.page_count,
            "too_many": pdf.page_count > MAX_PAGES,
            "all_document_types": DocumentTypeCatalog.objects.filter(
                is_active=True, domain__in=["PERSONAL", "BOTH"],
            ).exclude(code=DOSSIER_CODE).order_by("family", "label"),
        }
        pdf.close()
        return render(request, "new_ui/_document_split.html", context)

    def post(self, request, pk):
        entry, person = _person_entry(pk)
        groups, dates = {}, {}
        for key, code in request.POST.items():
            match = re.fullmatch(r"page_type_(\d+)", key)
            if not match or not code:
                continue
            number = int(match.group(1))
            groups.setdefault(code, []).append(number)
            typed = dossier_service.parse_date(
                request.POST.get("page_date_%d" % number))
            if typed and code not in dates:
                dates[code] = typed
        if not groups:
            return _error("No has elegido el tipo de ninguna página.")
        data = download_bytes(entry.bucket, entry.blob_name)
        created, skipped = [], []
        for code, numbers in groups.items():
            document_type = dossier_service.person_type(code)
            if document_type is None or code == DOSSIER_CODE:
                return _error("Tipo desconocido: %s" % code)
            pages = ", ".join(map(str, sorted(numbers)))
            if _already_extracted(entry, person, document_type, numbers):
                skipped.append("%s (páginas %s)" % (
                    document_type.label, pages))
                continue
            typed = dates.get(code)
            dossier_service.extract_document(
                entry, person, document_type, pages=sorted(numbers),
                issue_date=None if document_type.tracks_expiry else typed,
                expiry_date=typed if document_type.tracks_expiry else None,
                data=data,
            )
            created.append("%s (páginas %s)" % (document_type.label, pages))
        if created:
            _mark_as_dossier(entry, created)
        message = []
        if created:
            message.append("Sacados: %s." % "; ".join(created))
        if skipped:
            message.append("Ya estaban sacados: %s." % "; ".join(skipped))
        return _ok(" ".join(message))
