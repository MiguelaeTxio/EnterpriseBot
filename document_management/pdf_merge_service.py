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


class EmptyDocumentListError(ValueError):
    """Se lanza si se pide fusionar una lista vacia de documentos."""


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
