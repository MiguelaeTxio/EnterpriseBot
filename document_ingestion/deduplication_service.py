# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_ingestion/deduplication_service.py
"""
Deduplicación por hash de contenido (S024, a petición explícita de
Miguel Ángel: "hay que añadir el hash de archivos y controlar que
nunca se nos cuele un archivo que ya tenemos subido"). SHA-256 sobre
los bytes crudos del archivo -- si dos PDFs son byte-a-byte idénticos,
mismo hash, sin importar el nombre de archivo con el que se suban.

Domain-agnostic a propósito, mismo motivo que entity_matching_service
y el resto de este paquete: la comprobación cruza MachineDocument y
PersonalDocument (un mismo PDF no debería colarse dos veces sin
importar en qué dominio caiga cada intento), así que no puede vivir
dentro de ninguna de las dos apps de dominio sin acoplarlas.

La comprobación se hace lo antes posible en cada flujo de subida
(antes de crear cualquier fila, antes de gastar ninguna llamada a
Gemini) -- ver panel/views_documentation.py
(DocumentationFolderUploadView) y machine_documents/views.py
(MachineDocumentBatchUploadView), ambas llaman a find_duplicate()
dentro de su propio bucle de archivos subidos.
"""
import hashlib
import logging

logger = logging.getLogger(__name__)


def compute_content_hash(file_bytes: bytes) -> str:
    """
    SHA-256 hexdigest de los bytes crudos de un archivo.
    ---
    SHA-256 hexdigest of a file's raw bytes.
    """
    return hashlib.sha256(file_bytes).hexdigest()


def find_duplicate(company, content_hash: str):
    """
    Busca un documento YA persistido (MachineDocument o
    PersonalDocument, cualquiera de los dos dominios) con el mismo
    content_hash para `company`. Devuelve la instancia encontrada
    (para poder informar de qué documento es duplicado), o None si no
    hay ninguno.

    NUNCA compara contra IngestedFile -- esas filas son staging
    transitorio (su source_file se borra al enrutar, ver
    document_ingestion.tasks.route_ingested_files) y no representan
    documentos ya persistidos de verdad.

    ---

    Looks up an ALREADY persisted document (MachineDocument or
    PersonalDocument, either domain) with the same content_hash for
    `company`. Returns the found instance, or None.
    """
    from machine_documents.models import MachineDocument
    from personal_documents.models import PersonalDocument

    if not content_hash:
        return None

    machine_match = (
        MachineDocument.objects
        .filter(company=company, content_hash=content_hash)
        .first()
    )
    if machine_match:
        return machine_match

    return (
        PersonalDocument.objects
        .filter(company=company, content_hash=content_hash)
        .first()
    )
