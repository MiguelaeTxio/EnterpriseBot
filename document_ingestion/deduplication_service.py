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
    Busca un documento con el mismo content_hash para `company`, en
    dos sitios:
    1. YA persistido (MachineDocument o PersonalDocument, cualquiera
       de los dos dominios).
    2. TODAVÍA EN COLA de enrutado (IngestedFile con
       status=PENDING_ROUTING) -- añadido S024-bis tras un caso real:
       Miguel Ángel subió la misma carpeta dos veces con 34 segundos
       de diferencia, y el segundo lote no se detectó como duplicado
       porque en ese momento el primer lote todavía no se había
       enrutado a MachineDocument (cada lote puede tardar varios
       minutos en procesarse -- confirmado con el log real del worker
       Celery, ~5-13s por llamada a Gemini y ~20+ documentos en fila).
       Sin esta comprobación, dos subidas rápidas del mismo archivo
       generan trabajo duplicado real (dos llamadas de enrutado + dos
       de clasificación por archivo) antes de que la comprobación
       contra documentos ya persistidos tuviera ninguna posibilidad de
       detectarlo.

    Devuelve la instancia encontrada (para poder informar de qué
    documento es duplicado), o None si no hay ninguno.

    ---

    Looks up a document with the same content_hash for `company`, in
    two places: already persisted (MachineDocument/PersonalDocument),
    or still queued for routing (IngestedFile, PENDING_ROUTING) --
    added S024-bis after a real case where two uploads of the same
    folder 34 seconds apart weren't caught, because the first batch
    hadn't been routed into MachineDocument yet (batches can take
    several minutes to process).
    """
    from document_ingestion.models import IngestedFile
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

    personal_match = (
        PersonalDocument.objects
        .filter(company=company, content_hash=content_hash)
        .first()
    )
    if personal_match:
        return personal_match

    return (
        IngestedFile.objects
        .filter(
            company=company,
            content_hash=content_hash,
            status=IngestedFile.Status.PENDING_ROUTING,
        )
        .first()
    )
