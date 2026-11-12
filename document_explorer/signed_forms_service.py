# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/signed_forms_service.py
"""
S153. Company signatures and signed forms (e.g. the "Acta de adhesión
al Plan de Seguridad y Salud" a main contractor sends for each site).

---

S153. Firmas de las empresas del grupo y documentos firmados. Miguel
Ángel: los clientes envían varios documentos casi iguales (cambia la
obra), vacíos y sin firmar; aquí se elige qué empresa nuestra hace el
trabajo y con qué firma, y con un botón salen todos rellenos y firmados.

En cada PDF se buscan por texto dos sitios (sin distinguir mayúsculas):
- la etiqueta de la empresa subcontratista ("Empresa Subcontratista:"),
  y a su derecha se escribe la razón social y el CIF;
- la etiqueta de la firma ("REPRESENTANTE DE LA SUBCONTRATA"), y debajo
  se pone la imagen de la firma con su sello.
Si el PDF no las tiene (escaneado, sin texto, u otro modelo de
documento con otras palabras), S153 (Miguel Ángel: "Y si no, todo que
pase por Gemini"): se manda la página a Gemini, que dice qué datos pide
el documento y en qué hueco va cada uno (empresa, CIF, domicilio social,
trabajador y su DNI, firma de la empresa); allí se escriben. Los huecos
que ya vienen rellenos y las firmas que no son de la empresa (la del
trabajador, la del contratista) no se tocan.
"""
import io
import json
import logging
import os
from dataclasses import dataclass, field

import fitz
from PIL import Image

from document_explorer.confidential import decrypt, encrypt

# Etiquetas que se reconocen (PyMuPDF busca sin distinguir mayúsculas).
COMPANY_LABELS = (
    "Empresa Subcontratista:",
    "Empresa Subcontrata:",
)
SIGNATURE_LABELS = (
    "REPRESENTANTE DE LA SUBCONTRATA",
    "REPRESENTANTE DE LA EMPRESA SUBCONTRATISTA",
)
FONT_SIZE = 11
MIN_FONT_SIZE = 7
# Hueco de la firma bajo su etiqueta (puntos PDF; A4 = 595 x 842).
SIGNATURE_WIDTH = 190
SIGNATURE_HEIGHT = 80
SIGNATURE_GAP = 4
FOOTER_MARGIN = 50
# Píxeles casi blancos (fondo del escaneo) que pasan a transparentes.
WHITE_THRESHOLD = 225
MAX_SIGNATURE_PX = 1200

logger = logging.getLogger(__name__)

# Datos que Gemini puede pedir colocar (clave -> descripción para él).
FIELD_COMPANY = "empresa"
FIELD_TAX_ID = "cif"
FIELD_ADDRESS = "domicilio_social"
FIELD_WORKER = "trabajador"
FIELD_WORKER_DNI = "dni_trabajador"
FIELD_SIGNATURE = "firma_empresa"
FIELDS = {
    FIELD_COMPANY: "nombre o razón social de la empresa (la nuestra: "
                   "subcontratista, empresa del trabajador o empresa sin "
                   "más; nunca la contratista principal ni el cliente)",
    FIELD_TAX_ID: "CIF de esa empresa",
    FIELD_ADDRESS: "domicilio social de esa empresa",
    FIELD_WORKER: "nombre y apellidos del trabajador al que se refiere el "
                  "documento (D./Dª, nombrado, trabajador...)",
    FIELD_WORKER_DNI: "DNI de ese trabajador",
    FIELD_SIGNATURE: "firma y sello de la empresa (representante de la "
                     "subcontrata, de la empresa, \"por la empresa\"...); "
                     "NO la del trabajador ni la de la contratista",
}
FIELD_LABELS = {
    FIELD_COMPANY: "empresa", FIELD_TAX_ID: "CIF",
    FIELD_ADDRESS: "domicilio social", FIELD_WORKER: "trabajador",
    FIELD_WORKER_DNI: "DNI del trabajador",
    FIELD_SIGNATURE: "firma de la empresa",
}
GEMINI_MAX_PAGES = 4
GEMINI_DPI = 110
MIN_SIGNATURE_BOX_HEIGHT = 45
MIN_SIGNATURE_BOX_WIDTH = 150
METHOD_TEXT = "texto"
METHOD_GEMINI = "Gemini"


@dataclass
class FillResult:
    """
    A filled form: its bytes, how it was placed and the remarks.
    ---
    Un documento rellenado: sus bytes, cómo se colocaron los datos
    (texto o Gemini) y los avisos (lo que pedía y no se ha podido poner).
    """

    data: bytes
    method: str
    notes: list = field(default_factory=list)


class SignedFormError(ValueError):
    """
    A form cannot be filled (message for the user).
    ---
    No se puede rellenar un documento (mensaje para el usuario).
    """


def prepare_signature(raw):
    """
    PNG bytes of a signature: white background removed, cropped.
    ---
    La firma en PNG: el fondo blanco del escaneo pasa a transparente
    (así no tapa las líneas del documento), recortada a lo que tiene
    tinta y reducida si es enorme. SignedFormError si no es una imagen.
    """
    try:
        image = Image.open(io.BytesIO(raw))
        image.load()
    except Exception as exc:
        raise SignedFormError("El archivo de la firma no es una imagen.") \
            from exc
    image = image.convert("RGBA")
    pixels = [
        (r, g, b, 0) if min(r, g, b) >= WHITE_THRESHOLD else (r, g, b, a)
        for r, g, b, a in image.getdata()
    ]
    image.putdata(pixels)
    box = image.getbbox()
    if box is None:
        raise SignedFormError("La imagen de la firma está en blanco.")
    image = image.crop(box)
    image.thumbnail((MAX_SIGNATURE_PX, MAX_SIGNATURE_PX))
    out = io.BytesIO()
    image.save(out, format="PNG")
    return out.getvalue()


def store_signature(raw):
    """
    Encrypted PNG of a signature, ready for CompanySignature.
    ---
    La firma preparada y cifrada, para CompanySignature.image_encrypted.
    """
    return encrypt(prepare_signature(raw))


def signature_png(signature):
    """
    The PNG bytes of a stored CompanySignature.
    ---
    Los bytes PNG de una firma guardada.
    """
    return decrypt(bytes(signature.image_encrypted))


def _first_hit(doc, labels):
    for page in doc:
        for label in labels:
            hits = page.search_for(label)
            if hits:
                return page, hits[0]
    return None, None


def _last_hit(doc, labels):
    found = (None, None)
    for page in doc:
        for label in labels:
            for rect in page.search_for(label):
                found = (page, rect)
    return found


def _fit_size(text, width, size):
    while size > MIN_FONT_SIZE and fitz.get_text_length(
            text, fontname="helv", fontsize=size) > width:
        size -= 0.5
    return size


def _open(pdf_bytes):
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception as exc:
        raise SignedFormError("no es un PDF que se pueda abrir") from exc
    if not doc.is_pdf or doc.page_count == 0:
        raise SignedFormError("no es un PDF con páginas")
    return doc


def _fill_by_text(doc, text, png):
    """
    Text path: the two known labels; False if they are not there.
    ---
    Por texto: las dos etiquetas conocidas. False si no están (entonces
    va por Gemini) y no toca nada.
    """
    company_page, company_label = _first_hit(doc, COMPANY_LABELS)
    sign_page, sign_label = _last_hit(doc, SIGNATURE_LABELS)
    if company_page is None or sign_page is None:
        return False
    top = sign_label.y1 + SIGNATURE_GAP
    bottom = min(top + SIGNATURE_HEIGHT,
                 sign_page.rect.y1 - FOOTER_MARGIN)
    if bottom - top < 30:
        return False
    x = company_label.x1 + 4
    size = _fit_size(text, company_page.rect.x1 - 40 - x, FONT_SIZE)
    company_page.insert_text((x, company_label.y1 - 3), text,
                             fontname="helv", fontsize=size,
                             color=(0, 0, 0))
    box = fitz.Rect(sign_label.x0, top, sign_label.x0 + SIGNATURE_WIDTH,
                    bottom)
    sign_page.insert_image(box, stream=png, keep_proportion=True)
    return True


def _gemini_schema():
    return {
        "type": "OBJECT",
        "properties": {
            "fields": {
                "type": "ARRAY",
                "items": {
                    "type": "OBJECT",
                    "properties": {
                        "field": {"type": "STRING",
                                  "enum": list(FIELDS)},
                        "page": {"type": "INTEGER"},
                        "label": {"type": "STRING"},
                        "already_filled": {"type": "BOOLEAN"},
                        "box_2d": {"type": "ARRAY",
                                   "items": {"type": "INTEGER"}},
                    },
                    "required": ["field", "page", "already_filled",
                                 "box_2d"],
                },
            },
        },
        "required": ["fields"],
    }


def _gemini_prompt(pages):
    wanted = "\n".join("- %s: %s" % item for item in FIELDS.items())
    return (
        "Te paso %d página(s) de un documento (formulario de prevención "
        "de riesgos, coordinación de actividades, acta...) que una "
        "empresa cliente envía a nuestra empresa para que lo rellenemos "
        "y firmemos. Las imágenes van en orden: la primera es la página "
        "1.\n\n"
        "Localiza en él los huecos donde hay que escribir estos datos "
        "(solo los que el documento pide de verdad):\n%s\n\n"
        "Para cada hueco devuelve: field (la clave de arriba), page "
        "(1, 2...), label (el texto impreso junto al hueco, p. ej. "
        "\"Empresa:\" o \"D./Dª\"), already_filled (true si ya está "
        "escrito a máquina o a mano) y box_2d: la caja del ESPACIO EN "
        "BLANCO (o de la línea de puntos) donde va el dato, NO la de la "
        "etiqueta, como [ymin, xmin, ymax, xmax] normalizada de 0 a "
        "1000 sobre la página. Para la firma, la caja es el espacio "
        "libre donde se firma (debajo o a la derecha de su etiqueta), "
        "con sitio para una firma con sello. Si un dato aparece en "
        "varios sitios, devuelve todos. Si el documento no pide un "
        "dato, no lo devuelvas." % (pages, wanted)
    )


def _ask_gemini(doc):
    """
    Where each field goes, according to Gemini (list of dicts).
    ---
    Dónde va cada dato según Gemini, a partir de la imagen de las
    primeras páginas.
    """
    from google.genai.types import (
        GenerateContentConfig, HttpOptions, Part,
    )

    from ai_services.document_vision_service import (
        _generate_content_with_retry,
    )
    from ai_services.gemini_client import DEFAULT_MODEL, get_gemini_client

    count = min(doc.page_count, GEMINI_MAX_PAGES)
    parts = [
        Part.from_bytes(data=doc[i].get_pixmap(dpi=GEMINI_DPI).tobytes(
            "png"), mime_type="image/png")
        for i in range(count)
    ]
    try:
        response = _generate_content_with_retry(
            get_gemini_client(),
            model=DEFAULT_MODEL,
            contents=parts + [_gemini_prompt(count)],
            config=GenerateContentConfig(
                http_options=HttpOptions(timeout=90_000),
                response_mime_type="application/json",
                response_schema=_gemini_schema(),
                temperature=0.0,
            ),
        )
        result = json.loads(response.text.strip())
    except Exception as exc:
        logger.exception("# [FIRMAS] Fallo de Gemini al localizar huecos.")
        raise SignedFormError("Gemini no ha podido leer el documento "
                              "(%s)" % str(exc)[:200]) from exc
    logger.info("# [FIRMAS] Gemini: %s",
                json.dumps(result, ensure_ascii=False)[:2000])
    return [
        item for item in result.get("fields") or []
        if item.get("field") in FIELDS and len(item.get("box_2d") or []) == 4
        and 1 <= int(item.get("page") or 0) <= count
    ]


def _page_rect(page, box):
    ymin, xmin, ymax, xmax = (max(0, min(1000, v)) for v in box)
    width, height = page.rect.width, page.rect.height
    rect = fitz.Rect(xmin / 1000 * width, ymin / 1000 * height,
                     xmax / 1000 * width, ymax / 1000 * height)
    if page.rotation:
        rect = rect * page.derotation_matrix
    return rect


def _write_in_box(page, rect, text):
    height = max(rect.height, 8)
    size = _fit_size(text, max(rect.width - 4, 40),
                     min(FONT_SIZE, max(MIN_FONT_SIZE, height * 0.75)))
    baseline = rect.y0 + (height + size * 0.7) / 2
    page.insert_text((rect.x0 + 2, baseline), text, fontname="helv",
                     fontsize=size, color=(0, 0, 0))


def _sign_in_box(page, rect, png):
    if rect.height < MIN_SIGNATURE_BOX_HEIGHT:
        rect.y1 = min(rect.y0 + MIN_SIGNATURE_BOX_HEIGHT,
                      page.rect.y1 - 10)
    if rect.width < MIN_SIGNATURE_BOX_WIDTH:
        rect.x1 = min(rect.x0 + MIN_SIGNATURE_BOX_WIDTH, page.rect.x1 - 10)
    rect.y1 = min(rect.y1, rect.y0 + SIGNATURE_HEIGHT * 1.5)
    page.insert_image(rect, stream=png, keep_proportion=True)


def _fill_by_gemini(doc, values, png):
    """
    Gemini path: write each value where Gemini says. Returns notes.
    ---
    Por Gemini: escribe cada dato donde dice Gemini. Devuelve los
    avisos. SignedFormError si no encuentra ningún hueco.
    """
    items = _ask_gemini(doc)
    if not items:
        raise SignedFormError("Gemini no ha encontrado en el documento "
                              "ningún hueco para nuestros datos")
    found = {item["field"] for item in items}
    if FIELD_TAX_ID not in found and values.get(FIELD_TAX_ID) and (
            values.get(FIELD_COMPANY)):
        # Sin hueco propio para el CIF, va junto a la empresa.
        values = dict(values)
        values[FIELD_COMPANY] = "%s (CIF %s)" % (
            values[FIELD_COMPANY], values[FIELD_TAX_ID])
    notes, missing, placed = [], set(), 0
    for item in items:
        key = item["field"]
        if item.get("already_filled"):
            continue
        page = doc[int(item["page"]) - 1]
        rect = _page_rect(page, item["box_2d"])
        if rect.is_empty or rect.width < 5:
            continue
        if key == FIELD_SIGNATURE:
            _sign_in_box(page, rect, png)
            placed += 1
            continue
        value = values.get(key) or ""
        if not value:
            missing.add(key)
            continue
        _write_in_box(page, rect, value)
        placed += 1
    if not placed:
        raise SignedFormError("Gemini no ha encontrado ningún hueco libre "
                              "para nuestros datos")
    if FIELD_SIGNATURE not in found:
        notes.append("no se ha encontrado dónde va la firma de la empresa")
    for key in sorted(missing):
        notes.append("pide %s y no se ha indicado" % FIELD_LABELS[key])
    return notes


def fill_form(pdf_bytes, values, png):
    """
    The form filled and signed (FillResult).
    ---
    Rellena y firma un documento. `values`: {empresa, cif,
    domicilio_social, trabajador, dni_trabajador}. Primero por texto
    (las dos etiquetas conocidas); si no están, por Gemini. Devuelve un
    FillResult; SignedFormError si no se puede.
    """
    doc = _open(pdf_bytes)
    text = values.get(FIELD_COMPANY, "")
    if values.get(FIELD_TAX_ID):
        text = "%s (CIF %s)" % (text, values[FIELD_TAX_ID])
    if _fill_by_text(doc, text, png):
        method, notes = METHOD_TEXT, []
    else:
        method, notes = METHOD_GEMINI, _fill_by_gemini(doc, values, png)
    out = doc.tobytes(garbage=3, deflate=True)
    doc.close()
    return FillResult(out, method, notes)


def form_values(profile, person=None):
    """
    The values to fill for a company and, optionally, a worker.
    ---
    Los datos a escribir: los de la empresa (perfil fiscal) y, si se ha
    elegido, los del trabajador.
    """
    values = {
        FIELD_COMPANY: (profile.legal_name or "").upper(),
        FIELD_TAX_ID: profile.tax_id or "",
        FIELD_ADDRESS: (profile.fiscal_address or "").upper(),
    }
    if person is not None:
        values[FIELD_WORKER] = " ".join(
            part for part in (person.given_name, person.first_surname,
                              person.second_surname) if part).upper()
        values[FIELD_WORKER_DNI] = person.dni or ""
    return values


def output_name(original_name, profile):
    """
    File name of a generated form: original name plus the company.
    ---
    Nombre del documento generado: el original con la empresa al final.
    """
    stem = os.path.splitext(os.path.basename(original_name or "documento")
                            )[0]
    company = (profile.legal_name or "").replace(",", "").replace(
        ".", "").replace("/", "-").strip()
    return "%s - %s.pdf" % (stem, company)
