# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/document_audit_service.py
"""
H30 (S127). Does this file contain THAT person's document? -- read whole.

---

H30 (S127). Auditoría sin heurísticas, pedida por Miguel Ángel: "una
persona que le falta el DNI, que tiene una carpeta, vamos a comprobar
todos los documentos de esa persona. Cuando hayamos comprobado que en
todos los documentos no es el DNI, entonces podremos decir: a esta
persona le falta el DNI". Origen: su segundo contrato se daba por
inexistente "con total seguridad" y estaba en su carpeta con un nombre
que no casaba.

- `candidate_files(person)`: TODOS los archivos que pueden ser de la
  persona -- vinculados a ella (cualquier tipo), los de su carpeta, los
  de cualquier carpeta con su nombre, y los de la papelera vinculados o
  en esas carpetas.
- `find_in_file(entry, person, wanted)`: Gemini lee el archivo ENTERO
  (los PDF largos por tramos, sin el recorte de bordes del H28: un DNI
  en la página 17 de un dossier es justo lo que se busca) y responde a
  una pregunta cerrada: ¿contiene el `wanted` de esta persona?

Solo lectura: no escribe nada en la BD.
"""
import io
import json
import logging
import re

from django.db.models import Q
from google.genai.types import GenerateContentConfig, HttpOptions, Part

from ai_services.gemini_client import DEFAULT_MODEL, get_gemini_client
from document_explorer.classification_service import (
    _LIBREOFFICE_CONVERTIBLE_EXTENSIONS, _TEXT_EXTENSIONS, _convert_to_pdf,
    _document_text, _generate_content_with_retry,
)
from document_explorer.models import DocumentIndexEntry, PersonIdentity
from spare_parts.gcs_service import download_bytes

logger = logging.getLogger(__name__)

# Qué se busca, en palabras para Gemini.
WANTED_LABELS = {
    "IDENTIDAD": "su DNI o su NIE / permiso de residencia (cualquier cara)",
    "PERMISO_CONDUCIR": (
        "su permiso de conducción (carnet de conducir, cualquier cara)"
    ),
    "CONTRATO": (
        "su contrato de trabajo, o una conversión de contrato temporal en "
        "indefinido, o una carta de subrogación de su relación laboral"
    ),
}
_IMAGE_MIME = {
    "jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
    "webp": "image/webp", "heic": "image/heic", "heif": "image/heif",
    "gif": "image/gif", "bmp": "image/bmp", "tif": "image/tiff",
    "tiff": "image/tiff",
}
# PDF largos: tramos de este número de páginas (un dossier escaneado de
# 30 páginas va en dos llamadas).
_CHUNK_PAGES = 20

_RESPONSE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "found": {"type": "BOOLEAN"},
        "pages": {"type": "ARRAY", "items": {"type": "INTEGER"}},
        "what": {"type": "STRING"},
        "holder_name": {"type": "STRING"},
        "holder_id": {"type": "STRING"},
        "key_date": {"type": "STRING"},
        "evidence": {"type": "STRING"},
        "file_owner": {"type": "STRING"},
        "is_this_person": {"type": "BOOLEAN"},
    },
    "required": ["found", "what", "evidence"],
}


def _prompt(person, wanted, first_page=1):
    return (
        "Eres auditor de documentación laboral de una empresa española. "
        "Lee TODAS las páginas del archivo adjunto, sin saltarte ninguna.\n"
        "Pregunta: ¿contiene este archivo %s de esta persona: %s %s, %s "
        "(DNI/NIE registrado: %s)? Puede venir dentro de un dossier con "
        "otros documentos, con el nombre abreviado o el DNI con algún "
        "dígito mal escaneado.\n"
        "Responde SOLO JSON:\n"
        "- found: true solo si el documento buscado de ESA persona está "
        "en el archivo.\n"
        "- pages: páginas donde aparece (la primera de este archivo es la "
        "%d).\n"
        "- what: qué es exactamente lo que contiene el archivo (aunque no "
        "sea lo buscado), en pocas palabras.\n"
        "- holder_name / holder_id: titular y número de documento leídos.\n"
        "- key_date: AAAA-MM-DD -- caducidad para DNI/NIE/permiso; para "
        "un contrato, la fecha de inicio (para una conversión, la de "
        "celebración del contrato original; para una subrogación, la de "
        "efectos).\n"
        "- evidence: una frase con lo que lo demuestra.\n"
        "- file_owner: de quién es el archivo (nombre que aparece como "
        "titular o interesado), aunque no sea lo buscado.\n"
        "- is_this_person: false si el archivo es claramente de OTRA "
        "persona distinta de la indicada; true si es suyo o no se puede "
        "saber."
        % (
            WANTED_LABELS[wanted], person.first_surname,
            person.second_surname or "", person.given_name,
            person.dni or "desconocido", first_page,
        )
    )


def candidate_files(person, include_trash=True):
    """
    Every file that may belong to the person.

    ---

    Todos los archivos que pueden ser de la persona: vinculados a ella
    (cualquier tipo), en su carpeta actual, en cualquier carpeta cuya
    ruta lleve su nombre (carpetas antiguas), y -- si `include_trash` --
    los de la papelera en esos mismos sitios. Sin carpetas.
    """
    from django.contrib.contenttypes.models import ContentType

    person_ct = ContentType.objects.get_for_model(PersonIdentity)
    where = Q(domain_content_type=person_ct, domain_object_id=person.pk)
    if person.folder_path:
        where |= Q(parent_path=person.folder_path) | Q(
            parent_path__startswith=person.folder_path + "/",
        )
    surnames = " ".join(
        part for part in (person.first_surname, person.second_surname)
        if part
    ).strip()
    if surnames and person.given_name:
        # Carpetas antiguas: "OPERARIOS/DIAZ QUINTERO, ANTONIO JESUS (GR)",
        # "RENOVACION CARNE/DIAZ QUINTERO ANTONIO"...
        where |= Q(parent_path__icontains=surnames) & Q(
            parent_path__icontains=person.given_name.split()[0],
        )
    files = DocumentIndexEntry.objects.filter(where).filter(
        entry_kind=DocumentIndexEntry.KIND_FILE, purged_at__isnull=True,
    )
    if not include_trash:
        files = files.filter(deleted_at__isnull=True)
    return list(files.select_related("document_type").order_by(
        "deleted_at", "pk",
    ))


def content_key(entry):
    """
    Identity of a file's content (CRC32C + size), or None.

    ---

    Identidad del CONTENIDO (huella CRC32C y tamaño): dos archivos con la
    misma son el mismo contenido byte a byte, así que una sola lectura
    vale para los dos (S127: Álvarez Serrano tenía ~360 copias exactas en
    la papelera de la cuarentena). None si falta la huella: se lee.
    """
    if not entry.crc32c or entry.size_bytes is None:
        return None
    return "%s:%s" % (entry.crc32c, entry.size_bytes)


def _pdf_chunks(data):
    """PDF -> list of (first_page, bytes) chunks of _CHUNK_PAGES pages."""
    import fitz

    try:
        source = fitz.open(stream=data, filetype="pdf")
    except Exception:
        return [(1, data)]
    if source.page_count <= _CHUNK_PAGES:
        source.close()
        return [(1, data)]
    chunks = []
    for start in range(0, source.page_count, _CHUNK_PAGES):
        part = fitz.open()
        part.insert_pdf(
            source, from_page=start,
            to_page=min(start + _CHUNK_PAGES, source.page_count) - 1,
        )
        buffer = io.BytesIO()
        part.save(buffer)
        part.close()
        chunks.append((start + 1, buffer.getvalue()))
    source.close()
    return chunks


def _spreadsheet_text(data, max_chars=60_000):
    """Text of an .xlsx (every sheet, cell values), or ""."""
    try:
        import openpyxl

        book = openpyxl.load_workbook(
            io.BytesIO(data), read_only=True, data_only=True,
        )
        lines = []
        for sheet in book.worksheets:
            lines.append("# Hoja: %s" % sheet.title)
            for row in sheet.iter_rows(values_only=True):
                cells = [str(value) for value in row if value is not None]
                if cells:
                    lines.append(" | ".join(cells))
                if sum(len(line) for line in lines) > max_chars:
                    break
        return "\n".join(lines)[:max_chars]
    except Exception as exc:
        logger.warning("# [audit] Excel ilegible: %s", exc)
        return ""


def _parts_for(entry):
    """
    Gemini parts for the WHOLE file: [(first_page, Part)] or an error.

    ---

    Partes para Gemini del archivo ENTERO: PDF (por tramos), imágenes,
    documentos de oficina (convertidos o por texto), .html/.xml/.msg por
    texto. ([], "motivo") si no se puede leer.
    """
    extension = (
        entry.name.rsplit(".", 1)[-1].lower() if "." in entry.name else ""
    )
    data = download_bytes(entry.bucket, entry.blob_name)
    if not data:
        return [], "archivo vacío"
    if extension == "pdf":
        return [
            (first, Part.from_bytes(data=chunk, mime_type="application/pdf"))
            for first, chunk in _pdf_chunks(data)
        ], None
    if extension in _IMAGE_MIME:
        return [(1, Part.from_bytes(
            data=data, mime_type=_IMAGE_MIME[extension],
        ))], None
    if extension in ("xlsx", "xlsm"):
        # S127: un Excel convertido a PDF hacía caer a Gemini (504 tres
        # veces); su texto basta para saber qué es.
        text = _spreadsheet_text(data)
        if text:
            return [(1, Part.from_text(text=text))], None
    if extension in _LIBREOFFICE_CONVERTIBLE_EXTENSIONS:
        converted = _convert_to_pdf(data, extension)
        if converted:
            return [
                (first, Part.from_bytes(
                    data=chunk, mime_type="application/pdf",
                ))
                for first, chunk in _pdf_chunks(converted)
            ], None
    if extension in _TEXT_EXTENSIONS or extension == "docx":
        text = _document_text(data, extension)
        if text:
            return [(1, Part.from_text(text=text))], None
    if extension == "msg":
        from document_explorer.date_verification_service import msg_to_text

        text = msg_to_text(data)
        if text:
            return [(1, Part.from_text(text=text))], None
    return [], "formato .%s no legible" % extension


def _normalized_id(value):
    return re.sub(r"[^0-9A-Z]", "", (value or "").upper())


def _pages_of(ocr_text):
    """ocr_text with FULL_OCR_MARKER -> [(page_number, text)]."""
    pages = []
    for block in re.split(r"^=== Página (\d+) ===$", ocr_text, flags=re.M)[1:]:
        if block.strip().isdigit() and len(block.strip()) < 5:
            pages.append([int(block.strip()), ""])
        elif pages:
            pages[-1][1] = block
    return [(number, text) for number, text in pages]


_IDENTITY_CARD_RE = re.compile(
    r"DOCUMENTO NACIONAL DE IDENTIDAD|NATIONAL IDENTITY CARD|IDESP|"
    r"PERMISO DE RESIDENCIA|RESIDENCE PERMIT|TARJETA DE IDENTIDAD DE "
    r"EXTRANJERO|N\.?I\.?E\b.*CERTIFICADO|CERTIFICADO DE REGISTRO DE "
    r"CIUDADANO",
    re.IGNORECASE,
)


def _identity_by_number(person, pages):
    """
    Exact check: the person's DNI/NIE number printed in a page.

    ---

    Comprobación exacta (no heurística): el número de DNI/NIE registrado
    de la persona aparece en la página, con o sin letra, con o sin
    separadores, o en la zona legible por máquina (IDESP...). Devuelve
    las páginas donde aparece.
    """
    number = _normalized_id(person.dni)
    # Solo el número COMPLETO con su letra de control: los 8 dígitos
    # sueltos aparecen en otras cosas (una cuenta "2510-0961" casaba con
    # el DNI 25100961A en la prueba). La zona legible por máquina
    # (IDESP...25100961A<<<) también lo trae completo.
    if len(number) < 9 or not number[-1].isalpha():
        return []
    # S127: el número sale también en un alta, un contrato o una
    # autorización (falsos positivos reales: Gutiérrez Mateo, Gutiérrez
    # Santiago). Solo cuenta si en ESA página hay además las marcas de un
    # documento de identidad.
    return [
        page_number for page_number, text in pages
        if number in _normalized_id(text)
        and _IDENTITY_CARD_RE.search(text or "")
    ]


def find_in_text(entry, person, wanted):
    """
    Same question as find_in_file, answered on the stored full OCR text.

    ---

    H30 (S127). La misma pregunta que `find_in_file`, pero sobre el texto
    completo guardado por `ocr_full_text` (Cloud Vision / texto
    incrustado): Gemini sobre texto, rápido y sin saturar la cuota. None
    si el archivo aún no tiene OCR completo (el llamador usa la imagen).
    """
    from document_explorer.cloud_vision_service import FULL_OCR_MARKER

    text = entry.ocr_text or ""
    if not text.startswith(FULL_OCR_MARKER):
        return None
    pages = _pages_of(text)
    if not any(page_text.strip() for _, page_text in pages):
        return None
    client = get_gemini_client()
    try:
        response = _generate_content_with_retry(
            client, model=DEFAULT_MODEL,
            contents=[
                "Texto completo del archivo, página a página, obtenido por "
                "OCR:\n\n" + text[:120_000],
                _prompt(person, wanted),
            ],
            config=GenerateContentConfig(
                http_options=HttpOptions(timeout=90_000),
                response_mime_type="application/json",
                response_schema=_RESPONSE_SCHEMA, temperature=0.0,
            ),
        )
        result = json.loads(response.text)
    except Exception as exc:
        return {"error": "Gemini (texto): %s" % exc}
    result["source"] = "texto OCR"
    result["gemini_found"] = bool(result.get("found"))
    if wanted == "IDENTIDAD":
        exact = _identity_by_number(person, pages)
        if exact:
            # El número exacto de la persona está impreso: es suyo,
            # diga lo que diga la lectura (que queda como contexto).
            result.update(
                found=True, pages=exact,
                evidence="Número de documento %s impreso en la(s) "
                         "página(s) %s. %s" % (
                             person.dni, exact, result.get("evidence", "")),
            )
    return result


def find_in_file(entry, person, wanted):
    """
    Read the whole file and say whether it holds the wanted document.

    ---

    Lee el archivo entero y dice si contiene el documento buscado de la
    persona. Devuelve el dict de Gemini (found, pages, what, holder_*,
    key_date, evidence) o {"error": ...}. Nunca lanza.
    """
    from_text = find_in_text(entry, person, wanted)
    if from_text is not None and not from_text.get("error"):
        return from_text
    try:
        parts, problem = _parts_for(entry)
    except Exception as exc:
        return {"error": "no se pudo descargar/preparar: %s" % exc}
    if problem:
        return {"error": problem}
    client = get_gemini_client()
    merged = {
        "found": False, "pages": [], "what": [], "evidence": [],
        "is_this_person": True, "file_owner": "",
    }
    for first_page, part in parts:
        try:
            response = _generate_content_with_retry(
                client, model=DEFAULT_MODEL,
                contents=[part, _prompt(person, wanted, first_page)],
                config=GenerateContentConfig(
                    http_options=HttpOptions(timeout=120_000),
                    response_mime_type="application/json",
                    response_schema=_RESPONSE_SCHEMA, temperature=0.0,
                ),
            )
            data = json.loads(response.text)
        except Exception as exc:
            return {"error": "Gemini: %s" % exc}
        merged["what"].append(data.get("what", ""))
        if data.get("is_this_person") is False:
            merged["is_this_person"] = False
        if data.get("file_owner") and not merged["file_owner"]:
            merged["file_owner"] = data["file_owner"]
        if data.get("found"):
            merged["found"] = True
            merged["pages"].extend(data.get("pages") or [first_page])
            merged["evidence"].append(data.get("evidence", ""))
            for key in ("holder_name", "holder_id", "key_date"):
                if data.get(key) and not merged.get(key):
                    merged[key] = data[key]
    merged["what"] = " / ".join(text for text in merged["what"] if text)
    merged["evidence"] = " / ".join(
        text for text in merged["evidence"] if text
    )
    return merged
