# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_management/pdf_merge_service.py
"""
Servicio de fusion de PDF bajo demanda (Hito 26, anexo seccion 2.2).
Palabras de Miguel Angel: "la documentacion normalmente se aglutina en
un solo PDF para enviarla por correo" -- accion bajo demanda (el
usuario pulsa "generar dossier"), NUNCA automatica ni disparada por
ningun evento (confirmado explicitamente en S022).

Verificacion online (directriz 4.4, S023): PyMuPDF ya esta instalado
en el proyecto (usado por
machine_documents.document_classification_service.extract_pages()) y
su metodo Document.insert_pdf() es suficiente para combinar varios
PDFs en uno solo -- sin dependencia nueva, sin pasar por pip-tools.

Este modulo trabaja sobre bytes crudos de PDF, nunca sobre modelos de
dominio (MachineDocument, el futuro modelo de H25) ni sobre GCS
directamente -- el llamador (vista de panel de H23/H25) es quien
resuelve que documentos concretos combinar y descarga sus bytes desde
GCS antes de llamar a esta funcion.

---

On-demand PDF merge service (Milestone 26, annex section 2.2). Works
on raw PDF bytes only -- never on domain models or GCS directly; the
caller (H23/H25 panel view) resolves which concrete documents to
combine and downloads their bytes from GCS before calling this
function.
"""
import io

import pymupdf

# H31 (S103). Extensiones de imagen rasterizada que PyMuPDF sabe
# convertir a PDF de una pagina via Document.convert_to_pdf() --
# verificado en frio (sandbox de desarrollo, pymupdf 1.28.2, misma
# API que la version fijada 1.27.2.2 del proyecto): abrir los bytes
# con `filetype=<extension>` y llamar a convert_to_pdf() basta, sin
# libreria nueva. "jpeg" se normaliza a "jpg" -- PyMuPDF no reconoce
# el nombre largo como filetype. Los formatos de oficina (.doc/.docx/
# .xlsx) quedan FUERA a proposito: la conversion real de esos
# formatos en este proyecto vive en VMs de GCE dedicadas (libreoffice-
# writer, ver H30 S83), nunca confirmada como instalada en el propio
# servidor de PythonAnywhere -- intentarlo aqui seria una suposicion,
# no un hecho verificado. Un documento con una extension fuera de
# esta lista (y que no sea "pdf") se reporta como "no incluido" en el
# indice, nunca se descarta en silencio.
SUPPORTED_IMAGE_EXTENSIONS = (
    "jpg", "jpeg", "png", "gif", "bmp", "tif", "tiff", "webp",
)


class EmptyDocumentListError(ValueError):
    """Se lanza si se pide fusionar una lista vacia de documentos."""


def convert_to_pdf_bytes(data: bytes, extension: str) -> bytes | None:
    """
    H31 (S103). Convierte los bytes de un documento a PDF de cara al
    dossier unico: si `extension` ya es "pdf" devuelve `data` tal
    cual; si es una imagen rasterizada soportada (SUPPORTED_IMAGE_
    EXTENSIONS) la convierte a un PDF de una pagina; en cualquier otro
    caso (Word, Excel, o cualquier extension no reconocida) devuelve
    None -- el llamador debe entonces excluir ese documento del PDF
    fusionado y anotarlo como "no incluido" en el indice, nunca
    fusionarlo a ciegas ni lanzar un error que tumbe todo el dossier
    por un solo archivo no soportado.

    ---

    Converts a document's bytes to PDF for the single-file dossier:
    if `extension` is already "pdf", returns `data` unchanged; if
    it's a supported raster image, converts it to a one-page PDF;
    otherwise (Word, Excel, or any unrecognised extension) returns
    None -- the caller must then exclude that document from the
    merged PDF and note it as "not included" in the index, never
    silently merge it nor raise an error that would bring down the
    whole dossier over a single unsupported file.
    """
    ext = (extension or "").lower().lstrip(".")
    if ext == "pdf":
        return data
    if ext == "jpeg":
        ext = "jpg"
    if ext not in SUPPORTED_IMAGE_EXTENSIONS:
        return None
    try:
        with pymupdf.open(stream=data, filetype=ext) as image_doc:
            return image_doc.convert_to_pdf()
    except Exception:
        return None


def build_index_page(
    header_lines: list[tuple],
    item_lines: list[str],
    footer_note: str = None,
) -> bytes:
    """
    H31 (S103). Construye la portada/indice del dossier (una o mas
    paginas A4) con PyMuPDF puro -- sin reportlab ni ninguna
    dependencia nueva. Paginacion manual linea a linea (nunca
    insert_textbox con ajuste automatico): con un indice de decenas
    de documentos seleccionados, el desbordamiento silencioso de
    insert_textbox perderia lineas del indice sin que nadie se diera
    cuenta -- verificado en frio (sandbox) que este bucle salta de
    pagina correctamente con 45 lineas de item.

    `header_lines`: lista de tuplas (texto, tamano_fuente, negrita).
    `item_lines`: una linea de texto por documento incluido en el PDF
    fusionado, ya formateada por el llamador (tipo, familia,
    caducidad).
    `footer_note`: nota final opcional (p. ej. documentos NO incluidos
    por formato no soportado) -- nunca se omite si el llamador la
    pasa, aunque obligue a abrir una pagina mas.

    ---

    Builds the dossier's cover/index (one or more A4 pages) with pure
    PyMuPDF -- no reportlab, no new dependency. Manual line-by-line
    pagination (never auto-wrapping insert_textbox): with an index of
    dozens of selected documents, insert_textbox's silent overflow
    would drop index lines without anyone noticing -- verified cold
    (sandbox) that this loop breaks pages correctly with 45 item
    lines.
    """
    doc = pymupdf.open()
    page_width, page_height = 595, 842  # A4 en puntos (72 dpi)
    margin_top = 72
    margin_bottom = 56
    margin_left = 56
    line_height = 16

    def new_page():
        return doc.new_page(width=page_width, height=page_height)

    page = new_page()
    y = margin_top
    for text, fontsize, bold in header_lines:
        page.insert_text(
            (margin_left, y), text, fontsize=fontsize,
            fontname="hebo" if bold else "helv",
        )
        y += line_height * (1.6 if fontsize > 12 else 1.2)

    y += line_height * 0.5
    for text in item_lines:
        if y > page_height - margin_bottom:
            page = new_page()
            y = margin_top
        page.insert_text((margin_left, y), text, fontsize=10, fontname="helv")
        y += line_height

    if footer_note:
        if y > page_height - margin_bottom - line_height * 2:
            page = new_page()
            y = margin_top
        y += line_height
        page.insert_text(
            (margin_left, y), footer_note, fontsize=9, fontname="helv",
        )

    output = io.BytesIO()
    doc.save(output)
    doc.close()
    return output.getvalue()


def merge_pdfs(pdf_bytes_list: list[bytes]) -> bytes:
    """
    Combina una lista de PDFs (bytes crudos, en el orden dado) en un
    unico PDF, devuelto tambien como bytes. Pensado para el boton
    "generar dossier" del panel: el usuario selecciona documentos ya
    persistidos, la vista descarga sus bytes desde GCS y llama a esta
    funcion para producir el PDF combinado que luego se ofrece para
    descargar/adjuntar a un email.

    Lanza EmptyDocumentListError si la lista esta vacia -- nunca
    genera un PDF de 0 paginas silenciosamente.

    ---

    Combines a list of PDFs (raw bytes, in the given order) into a
    single PDF, also returned as bytes. Intended for the panel's
    "generate dossier" button: the user selects already-persisted
    documents, the view downloads their bytes from GCS and calls this
    function to produce the combined PDF, later offered for download/
    attaching to an email.

    Raises EmptyDocumentListError if the list is empty -- never
    silently produces a 0-page PDF.
    """
    if not pdf_bytes_list:
        raise EmptyDocumentListError(
            "No se puede generar un dossier sin ningun documento "
            "seleccionado."
        )

    merged = pymupdf.open()
    try:
        for pdf_bytes in pdf_bytes_list:
            with pymupdf.open(stream=pdf_bytes, filetype="pdf") as source:
                merged.insert_pdf(source)

        output = io.BytesIO()
        merged.save(output)
        return output.getvalue()
    finally:
        merged.close()
