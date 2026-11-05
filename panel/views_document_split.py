# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/views_document_split.py
"""
H24 (S145). "Separar": take documents out of a dossier from the file.

---

H24 (S145). "Separar": sacar documentos de un dossier desde la ficha.
Miguel Ángel, con el DNI de Berenguer Gómez, que es un dossier con el
certificado del CAP, la tarjeta CAP, la de tacógrafo, el permiso y el
DNI: "deberíamos de dotar al sistema de una herramienta para poder
extraer únicamente el DNI. Y si alguno de los documentos que te he
dicho no los tiene, también extraerlos y colocarlos en su sitio."

- GET ?page=N: esa página en grande (PNG), para verla bien antes de
  elegir su tipo (S145, Miguel Ángel: "había un documento que en la
  miniatura yo no llegaba a ver bien lo que era").
- GET: el contenido del modal: cada página en miniatura con el tipo
  que su texto ya leído sugiere (`resolve_type_from_content`, sin
  Gemini), un selector de tipo y una fecha opcional.
- POST: las páginas con el mismo tipo forman un documento nuevo en la
  ficha de la persona (`dossier_service.extract_document`, el mismo
  flujo que una subida: nombre, fecha, sustitución). El original pasa
  a ser un "Dossier" (tipo propio, S145) y sigue en la ficha para
  volver a entrar y separar; nunca se borra.
"""
import base64
import re
import unicodedata

import fitz
from django.contrib.contenttypes.models import ContentType
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views import View

from document_explorer import dossier_service
from document_explorer.models import (
    DocumentIndexEntry, DocumentTypeCatalog, PersonIdentity,
)
from document_explorer.personal_content_classification import (
    resolve_type_from_content,
)
from panel.mixins import DocsUploadAccessMixin
from spare_parts.gcs_service import download_bytes

MAX_PAGES = 30
DOSSIER_CODE = "DOSSIER"
_PAGE_SPLIT = re.compile(r"=== P[áa]gina (\d+) ===")


def _upper(value):
    value = unicodedata.normalize("NFKD", value or "")
    return "".join(
        c for c in value if not unicodedata.combining(c)).upper()


def _page_texts(ocr_text):
    """{page number: text} from the cached OCR ("=== Página N ===")."""
    parts = _PAGE_SPLIT.split(ocr_text or "")
    return {
        int(parts[i]): parts[i + 1] for i in range(1, len(parts) - 1, 2)
    }


def _page_image(data, number):
    """One page in large size (PNG), for the zoom of the modal."""
    try:
        pdf = fitz.open(stream=data, filetype="pdf")
    except Exception:
        raise Http404("No es un PDF.")
    if not 1 <= number <= pdf.page_count:
        pdf.close()
        raise Http404("No existe esa página.")
    png = pdf[number - 1].get_pixmap(dpi=130).tobytes("png")
    pdf.close()
    return HttpResponse(png, content_type="image/png")


def _person_entry(pk):
    person_ct = ContentType.objects.get_for_model(PersonIdentity)
    entry = get_object_or_404(
        DocumentIndexEntry, pk=pk, deleted_at__isnull=True,
        entry_kind=DocumentIndexEntry.KIND_FILE,
        domain_content_type=person_ct,
    )
    person = get_object_or_404(PersonIdentity, pk=entry.domain_object_id)
    return entry, person


class DocumentSplitView(DocsUploadAccessMixin, View):
    """GET: páginas con su tipo sugerido. POST: sacar los documentos."""

    def get(self, request, pk):
        entry, person = _person_entry(pk)
        data = download_bytes(entry.bucket, entry.blob_name)
        page_number = request.GET.get("page", "")
        if page_number.isdigit():
            return _page_image(data, int(page_number))
        try:
            pdf = fitz.open(stream=data, filetype="pdf")
        except Exception:
            return render(request, "panel/documentation_h30/"
                          "_document_split_body.html",
                          {"error": "Este archivo no es un PDF."})
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
            "entry": entry,
            "person": person,
            "pages": pages,
            "page_count": pdf.page_count,
            "too_many": pdf.page_count > MAX_PAGES,
            "all_document_types": DocumentTypeCatalog.objects.filter(
                is_active=True, domain__in=["PERSONAL", "BOTH"],
            ).exclude(code=DOSSIER_CODE).order_by("family", "label"),
        }
        pdf.close()
        return render(
            request, "panel/documentation_h30/_document_split_body.html",
            context)

    def post(self, request, pk):
        entry, person = _person_entry(pk)
        groups = {}
        dates = {}
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
            return JsonResponse(
                {"ok": False, "error": "No has elegido ninguna página."},
                status=400)
        data = download_bytes(entry.bucket, entry.blob_name)
        created = []
        for code, numbers in groups.items():
            document_type = dossier_service.person_type(code)
            if document_type is None or code == DOSSIER_CODE:
                return JsonResponse(
                    {"ok": False, "error": "Tipo desconocido: %s" % code},
                    status=400)
            typed = dates.get(code)
            dossier_service.extract_document(
                entry, person, document_type, pages=sorted(numbers),
                issue_date=None if document_type.tracks_expiry else typed,
                expiry_date=typed if document_type.tracks_expiry else None,
                data=data,
            )
            created.append("%s (páginas %s)" % (
                document_type.label, ", ".join(map(str, sorted(numbers)))))
        _mark_as_dossier(entry, created)
        return JsonResponse({"ok": True, "created": created})


def _mark_as_dossier(entry, created):
    """
    The split file becomes a "Dossier", visible in the file.
    ---
    El archivo separado pasa a ser un "Dossier" y sigue a la vista en
    la ficha, con su botón Separar (S145, Miguel Ángel: "un tipo para
    dossier que aparezca y que se pueda entrar y separar"). Con el
    cambio de tipo completo del panel: deja de ocupar el sitio del
    tipo que tenía (el DNI de Berenguer) y lo que había sustituido
    vuelve a contar.
    """
    from document_explorer.subject_upload_service import (
        change_document_type,
    )

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
