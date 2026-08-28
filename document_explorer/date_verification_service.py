# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/date_verification_service.py
"""
H30 (S48). Servicio compartido de extraccion/contraste de fecha para
dos consumidores reales:

1. `run_fase_b1_ocr_dates` (comando de gestion, recorrido masivo por
   lotes sobre el histórico ya indexado).
2. El flujo de subida desde ficha (panel, S48 en adelante): el
   supervisor escribe la fecha a mano al subir un documento nuevo, y
   este servicio la CONTRASTA contra lo que dice el propio documento
   -- nunca decide por su cuenta, solo avisa si no coinciden. Miguel
   Ángel, verbatim (S48): "Contraste nunca va a estar por encima del
   supervisor, pero contrasta la información y avisa."

Dos vias de lectura, decididas por dato de catalogo (nunca lista fija
en codigo -- mismo principio que tracks_expiry):

- `DocumentTypeCatalog.ocr_unreliable=False` (la mayoria de tipos):
  OCR local con Tesseract, gratis.
- `DocumentTypeCatalog.ocr_unreliable=True` (verificado con datos
  reales -- hoy solo ITV, tarjetas manuscritas con fondo de seguridad
  que domina la lectura de Tesseract, ver anexo H30 "COMPLETADAS EN
  S48"): Gemini como ultimo recurso, acotado a este subconjunto
  concreto -- nunca se usa Gemini para tipos que ya resuelve OCR o
  que el propio supervisor ya introduce a mano.
"""
import io
import json
import re
import unicodedata
from datetime import date

import fitz
import pytesseract
from google.genai.types import GenerateContentConfig, HttpOptions, Part
from PIL import Image

from ai_services.gemini_client import DEFAULT_MODEL, get_gemini_client
from ai_services.gemini_rate_limiter import acquire_gemini_slot

_EXPIRY_CONTEXT = [
    "CADUCA", "CADUCIDAD", "VALIDO HASTA", "VALIDA HASTA", "VENCE",
    "VENCIMIENTO", "HASTA EL", "PROXIMA REVISION", "PROXIMA INSPECCION",
    "FECHA LIMITE",
]
_ISSUE_CONTEXT = [
    "EXPEDICION", "EXPEDIDO", "EXPEDIDA", "EMISION", "EMITIDO",
    "EMITIDA", "CON FECHA", "SOMETIDO EL DIA", "MALAGA A",
]

_DATE_RE = re.compile(r"(\d{1,2})[-./](\d{1,2})[-./](\d{2,4})")
_CONTEXT_WINDOW = 70

# H30 (S78). Fecha en formato largo espanol -- "7 de marzo de 2018",
# "12 de noviembre de 2022", "6 de septiembre del 2014". Miguel Angel,
# hallazgo real de sesion: la mayoria de certificados/comunicaciones
# oficiales (reconocimiento medico, contrato, formacion, carnet de
# gruista...) escriben la fecha asi en el cuerpo del texto, nunca en
# formato numerico -- el patron numerico de arriba nunca las
# reconocia, aunque el documento SI trajera fecha real y legible.
_MESES_LARGO = {
    "ENERO": 1, "FEBRERO": 2, "MARZO": 3, "ABRIL": 4, "MAYO": 5,
    "JUNIO": 6, "JULIO": 7, "AGOSTO": 8, "SEPTIEMBRE": 9, "OCTUBRE": 10,
    "NOVIEMBRE": 11, "DICIEMBRE": 12,
}
_DATE_LARGO_RE = re.compile(
    r"(\d{1,2})\s+DE\s+(" + "|".join(_MESES_LARGO.keys()) + r")\s+DEL?\s+(\d{4})",
)

_GEMINI_DATE_SCHEMA = {
    "type": "object",
    "properties": {
        "expiry_date": {"type": "string"},
        "found": {"type": "boolean"},
    },
    "required": ["expiry_date", "found"],
}

_GEMINI_DATE_PROMPT = (
    "Eres un asistente que lee documentos administrativos españoles "
    "de maquinaria/personal (tarjetas ITV, certificados, permisos). "
    "Busca la fecha de CADUCIDAD o VALIDEZ (\"valedera hasta\", "
    "\"fecha de la próxima inspección\") escrita en el documento -- "
    "puede ser manuscrita. Devuelve SOLO la más reciente/última "
    "anotada, en formato AAAA-MM-DD. Si no encuentras ninguna fecha "
    "de caducidad legible, found=false."
)


def _strip_accents(value):
    return "".join(
        c for c in unicodedata.normalize("NFD", value)
        if unicodedata.category(c) != "Mn"
    )


def _parse_date(day_s, month_s, year_s):
    try:
        day, month, year = int(day_s), int(month_s), int(year_s)
    except ValueError:
        return None
    if year < 100:
        year += 2000
    if not (1 <= day <= 31 and 1 <= month <= 12 and 1900 <= year <= 2100):
        return None
    try:
        return date(year, month, day)
    except ValueError:
        return None


def classify_dates_in_text(text):
    """
    Devuelve (expiry_date o None, issue_date o None, [otras fechas])
    a partir de texto plano -- busca cada fecha (numerica DD/MM/AAAA
    y en formato largo "DD de MES de AAAA") y mira el contexto a
    ambos lados (_CONTEXT_WINDOW caracteres) por palabras de
    caducidad/emision.
    """
    norm = _strip_accents(text).upper()
    expiry_candidates = []
    issue_candidates = []
    other_dates = []

    matches = list(_DATE_RE.finditer(norm))
    for match in matches:
        parsed = _parse_date(*match.groups())
        if not parsed:
            continue
        window_start = max(0, match.start() - _CONTEXT_WINDOW)
        window_end = min(len(norm), match.end() + _CONTEXT_WINDOW)
        context = norm[window_start:match.start()] + \
            norm[match.end():window_end]
        if any(word in context for word in _EXPIRY_CONTEXT):
            expiry_candidates.append(parsed)
        elif any(word in context for word in _ISSUE_CONTEXT):
            issue_candidates.append(parsed)
        else:
            other_dates.append(parsed)

    for match in _DATE_LARGO_RE.finditer(norm):
        day_s, mes_s, year_s = match.groups()
        month = _MESES_LARGO.get(mes_s)
        parsed = _parse_date(day_s, month, year_s) if month else None
        if not parsed:
            continue
        window_start = max(0, match.start() - _CONTEXT_WINDOW)
        window_end = min(len(norm), match.end() + _CONTEXT_WINDOW)
        context = norm[window_start:match.start()] + \
            norm[match.end():window_end]
        if any(word in context for word in _EXPIRY_CONTEXT):
            expiry_candidates.append(parsed)
        elif any(word in context for word in _ISSUE_CONTEXT):
            issue_candidates.append(parsed)
        else:
            other_dates.append(parsed)

    expiry = max(expiry_candidates) if expiry_candidates else None
    issue = min(issue_candidates) if issue_candidates else None
    return expiry, issue, other_dates


def ocr_pdf_to_text(data, max_pages=2, dpi=300):
    text_parts = []
    doc = fitz.open(stream=data, filetype="pdf")
    for page_index in range(min(max_pages, doc.page_count)):
        page = doc.load_page(page_index)
        pix = page.get_pixmap(dpi=dpi)
        img = Image.open(io.BytesIO(pix.tobytes("png")))
        text_parts.append(pytesseract.image_to_string(img, lang="spa"))
    doc.close()
    return "\n".join(text_parts)


def ocr_image_to_text(data):
    img = Image.open(io.BytesIO(data))
    return pytesseract.image_to_string(img, lang="spa")


def docx_to_text(data):
    import docx
    doc = docx.Document(io.BytesIO(data))
    return "\n".join(p.text for p in doc.paragraphs)


def extract_text(filename, data):
    """
    Devuelve el texto legible de `data` segun la extension de
    `filename`, o None si la extension no esta soportada (nunca se
    fuerza OCR sobre un tipo de archivo que no se sabe leer).
    """
    name_lower = filename.lower()
    if name_lower.endswith(".pdf"):
        return ocr_pdf_to_text(data)
    if name_lower.endswith((".jpg", ".jpeg", ".png")):
        return ocr_image_to_text(data)
    if name_lower.endswith(".docx"):
        return docx_to_text(data)
    return None


def extract_expiry_via_gemini(data, filename):
    """
    Ultimo recurso, acotado a document_type.ocr_unreliable=True
    (verificado con datos reales, ver docstring del modulo). Solo pide
    una fecha de caducidad, nunca reclasifica el tipo documental ni
    el sujeto -- eso ya lo sabe el llamador por contexto (viene de la
    ficha del sujeto). Devuelve un `date` o None si Gemini no
    encuentra ninguna fecha legible.
    """
    if filename.lower().endswith(".pdf"):
        part = Part.from_bytes(data=data, mime_type="application/pdf")
    elif filename.lower().endswith((".jpg", ".jpeg", ".png")):
        mime = "image/png" if filename.lower().endswith(".png") else "image/jpeg"
        part = Part.from_bytes(data=data, mime_type=mime)
    else:
        return None

    client = get_gemini_client()
    acquire_gemini_slot()
    response = client.models.generate_content(
        model=DEFAULT_MODEL,
        contents=[part, _GEMINI_DATE_PROMPT],
        config=GenerateContentConfig(
            http_options=HttpOptions(timeout=90_000),
            response_mime_type="application/json",
            response_schema=_GEMINI_DATE_SCHEMA,
            temperature=0.0,
        ),
    )
    result = json.loads(response.text.strip())
    if not result.get("found"):
        return None
    try:
        year, month, day = (int(x) for x in result["expiry_date"].split("-"))
        return date(year, month, day)
    except (ValueError, KeyError, AttributeError):
        return None


def verify_typed_date(document_type, filename, data, typed_date):
    """
    Contrasta `typed_date` (lo que el supervisor escribió a mano)
    contra lo que el propio documento dice de verdad -- nunca decide,
    solo avisa. Devuelve None si coincide o si no se pudo leer nada
    (silencio, no bloquea la subida); devuelve un dict de aviso si hay
    discrepancia real:
        {"system_date": date, "typed_date": date, "source": "OCR"|"Gemini"}

    Via de lectura decidida por `document_type.ocr_unreliable` (dato
    de catalogo, nunca lista fija en codigo).
    """
    if document_type.ocr_unreliable:
        system_date = extract_expiry_via_gemini(data, filename)
        source = "Gemini"
    else:
        text = extract_text(filename, data)
        if text is None:
            return None
        expiry, issue, other = classify_dates_in_text(text)
        system_date = expiry or issue or (
            other[0] if len(other) == 1 else None
        )
        source = "OCR"

    if system_date is None:
        return None
    if system_date == typed_date:
        return None
    return {
        "system_date": system_date,
        "typed_date": typed_date,
        "source": source,
    }
