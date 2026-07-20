# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/machine_documents/markdown_service.py
"""
Conversión de un MachineDocument (PDF ya persistido en GCS) a
Markdown -- petición explícita de Miguel Ángel (S025): "los manuales
son muy pesados... interesaría poder convertirlos a Markdown...
tener un botón de conversión en la documentación para convertirlos a
Markdown y poder descargarlos en Markdown para enviarlos
posteriormente por correo. Podríamos persistir la copia Markdown y
dejarla en Google Cloud Storage para reutilizarla cuando se necesite."

Verificado en línea (directriz 4.4, 2026-07-20) antes de elegir
librería: pymupdf4llm (pypi.org/project/pymupdf4llm,
github.com/pymupdf/pymupdf4llm) -- extensión OFICIAL de PyMuPDF
(mismo fabricante, ya instalado en el proyecto para
pdf_merge_service), "No GPU, no Cloud, no Tokens required", corre
sobre el motor C de MuPDF. Preferida frente a marker-pdf (requiere
PyTorch/GPU, inviable en PythonAnywhere sin GPU) y frente a servicios
cloud de pago (ConvertAPI y similares, coste por conversión +
dependencia de red externa) -- instalación real verificada en
producción (S025, pip-compile/pip-sync confirmados por Miguel Ángel).

Síncrono a propósito, sin Celery: pymupdf4llm procesa localmente
sobre el motor C de MuPDF, sin llamadas de red ni límite de cuota --
a diferencia de Gemini Vision, no hay motivo real para sacarlo del
hilo de la petición salvo que un manual muy extremo demuestre
timeout real (a vigilar, no asumido).

Domain-agnostic a propósito, mismo principio que ai_services/
document_management: no importa nada de machine_documents.models más
allá del propio MachineDocument que recibe como argumento, para
poder reutilizarse en personal_documents cuando se retome H25 sin
duplicar esta lógica.
"""
import logging

import pymupdf
import pymupdf4llm

from spare_parts.gcs_service import (
    MACHINE_DOCUMENTS_BUCKET,
    download_bytes,
    upload_bytes,
)

logger = logging.getLogger(__name__)


class MarkdownConversionError(Exception):
    """
    Fallo real de conversión (documento sin PDF en GCS todavía, o
    error del propio motor de conversión) -- el llamador (vista) lo
    traduce a un mensaje legible para el usuario, nunca deja que
    reviente como un 500 sin capturar (mismo criterio que
    document_management.alert_service.send_alert_now, S025).
    """


def convert_document_to_markdown(document) -> str:
    """
    Descarga el PDF de `document` desde GCS, lo convierte a Markdown
    con pymupdf4llm, y sube el resultado al MISMO bucket con
    extensión .md -- reutilizando la ruta ya sanitizada del PDF
    original (mismo directorio/nombre, solo cambia la extensión), sin
    necesidad de generar una ruta nueva.

    Actualiza document.markdown_blob_name y lo persiste. Devuelve el
    blob_name del Markdown generado.

    Lanza MarkdownConversionError si el documento no tiene PDF en GCS
    todavía (gcs_blob_name vacío) o si la conversión falla.
    """
    if not document.gcs_blob_name:
        raise MarkdownConversionError(
            "Este documento todavía no tiene un PDF persistido en "
            "Google Cloud Storage -- espera a que termine de "
            "clasificarse antes de convertirlo."
        )

    try:
        pdf_bytes = download_bytes(
            MACHINE_DOCUMENTS_BUCKET, document.gcs_blob_name,
        )
    except Exception as exc:
        logger.error(
            "# [convert_document_to_markdown] #%d: error descargando "
            "el PDF original (blob=%s): %s",
            document.pk, document.gcs_blob_name, exc, exc_info=True,
        )
        raise MarkdownConversionError(
            "No se pudo descargar el PDF original desde Google Cloud "
            "Storage."
        ) from exc

    pdf_doc = None
    try:
        pdf_doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
        markdown_text = pymupdf4llm.to_markdown(pdf_doc)
    except Exception as exc:
        logger.error(
            "# [convert_document_to_markdown] #%d: error convirtiendo "
            "a Markdown: %s",
            document.pk, exc, exc_info=True,
        )
        raise MarkdownConversionError(
            "La conversión a Markdown falló -- puede que el PDF esté "
            "dañado o en un formato no soportado."
        ) from exc
    finally:
        if pdf_doc is not None:
            pdf_doc.close()

    if not markdown_text or not markdown_text.strip():
        raise MarkdownConversionError(
            "La conversión no produjo ningún texto -- puede que el "
            "PDF sea solo imágenes escaneadas sin capa de texto."
        )

    markdown_bytes = markdown_text.encode("utf-8")
    markdown_blob_name = (
        document.gcs_blob_name.rsplit(".", 1)[0] + ".md"
    )

    try:
        upload_bytes(
            MACHINE_DOCUMENTS_BUCKET, markdown_blob_name, markdown_bytes,
            content_type="text/markdown; charset=utf-8",
        )
    except Exception as exc:
        logger.error(
            "# [convert_document_to_markdown] #%d: error subiendo el "
            "Markdown generado (blob=%s): %s",
            document.pk, markdown_blob_name, exc, exc_info=True,
        )
        raise MarkdownConversionError(
            "El Markdown se generó correctamente pero no se pudo "
            "subir a Google Cloud Storage."
        ) from exc

    document.markdown_blob_name = markdown_blob_name
    document.save(update_fields=["markdown_blob_name"])

    logger.info(
        "# [convert_document_to_markdown] #%d convertido a Markdown "
        "(%d bytes) -- blob=%s.",
        document.pk, len(markdown_bytes), markdown_blob_name,
    )
    return markdown_blob_name
