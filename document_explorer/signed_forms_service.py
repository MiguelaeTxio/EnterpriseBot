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
Si un PDF no tiene alguna de las dos, no se genera y se dice por qué
(nunca se pone la firma en un sitio adivinado).
"""
import io
import os

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


def company_text(profile):
    """
    The subcontractor text: legal name and tax ID.
    ---
    El texto de la empresa subcontratista: razón social y CIF.
    """
    name = (profile.legal_name or "").upper()
    return "%s (CIF %s)" % (name, profile.tax_id) if profile.tax_id \
        else name


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


def fill_form(pdf_bytes, text, png):
    """
    The form filled with the company and signed. Returns PDF bytes.
    ---
    Devuelve el PDF con la empresa escrita a la derecha de su etiqueta
    y la firma debajo de la suya. SignedFormError si no es un PDF o no
    se encuentra alguna de las dos etiquetas.
    """
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception as exc:
        raise SignedFormError("no es un PDF que se pueda abrir") from exc
    if doc.page_count == 0:
        raise SignedFormError("el PDF no tiene páginas")
    page, label = _first_hit(doc, COMPANY_LABELS)
    if page is None:
        raise SignedFormError(
            "no se encuentra \"Empresa Subcontratista:\" en el texto")
    x = label.x1 + 4
    room = page.rect.x1 - 40 - x
    size = FONT_SIZE
    while size > MIN_FONT_SIZE and fitz.get_text_length(
            text, fontname="helv", fontsize=size) > room:
        size -= 0.5
    page.insert_text((x, label.y1 - 3), text, fontname="helv",
                     fontsize=size, color=(0, 0, 0))

    page, label = _last_hit(doc, SIGNATURE_LABELS)
    if page is None:
        raise SignedFormError(
            "no se encuentra \"REPRESENTANTE DE LA SUBCONTRATA\" para la "
            "firma")
    top = label.y1 + SIGNATURE_GAP
    bottom = min(top + SIGNATURE_HEIGHT, page.rect.y1 - FOOTER_MARGIN)
    if bottom - top < 30:
        raise SignedFormError("no queda sitio para la firma bajo su "
                              "etiqueta")
    box = fitz.Rect(label.x0, top, label.x0 + SIGNATURE_WIDTH, bottom)
    page.insert_image(box, stream=png, keep_proportion=True)
    out = doc.tobytes(garbage=3, deflate=True)
    doc.close()
    return out


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
