# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/company_local_folder_service.py
"""
A group company's document uploaded from the panel, down to OneDrive
(S156).

Miguel Ángel (25/11/2026), on resolving CAE notices from the app: the
document goes to its folder in the bucket "¿y en local?" -- to the same
local folder its kind came from: a Transgrual TC1 to the folder of the
Transgrual TC1s, an RC receipt to the RC policy folder.

The local folder is the one of the most recent document of the same
type and company that came up from OneDrive (its object name is its
local path, behind _CUARENTENA/). With none, there is no local folder
to use and nothing is downloaded. The H28 agent does the download, the
same way as for people and machines (LocalDownloadJob).

---

Un documento de una empresa del grupo subido desde el panel baja a su
carpeta de OneDrive: la del documento más reciente del mismo tipo y
empresa que subió de OneDrive (el nombre del objeto es su ruta en
local, tras _CUARENTENA/). Si no hay ninguno, no hay carpeta y no se
baja. Lo baja el agente H28 (LocalDownloadJob), como lo de personas y
máquinas.
"""
import logging

from django.contrib.contenttypes.models import ContentType
from django.db.models import F

from .buckets import QUARANTINE_PREFIX
from .models import CompanyFiscalProfile, DocumentIndexEntry, LocalDownloadJob

logger = logging.getLogger(__name__)


def source_local_folder(entry):
    """Local folder of the latest document of the same type and company.
    ---
    Carpeta local del documento más reciente (por caducidad o emisión)
    del mismo tipo y empresa que subió de OneDrive, o "".
    """
    source = DocumentIndexEntry.objects.filter(
        bucket=entry.bucket,
        entry_kind=DocumentIndexEntry.KIND_FILE,
        deleted_at__isnull=True, purged_at__isnull=True,
        domain_content_type=entry.domain_content_type,
        domain_object_id=entry.domain_object_id,
        document_type=entry.document_type,
        blob_name__startswith=QUARANTINE_PREFIX,
    ).exclude(pk=entry.pk).order_by(
        F("expiry_date").desc(nulls_last=True),
        F("issue_date").desc(nulls_last=True), "-pk",
    ).first()
    if source is None:
        return ""
    return source.blob_name[len(QUARANTINE_PREFIX):].rpartition("/")[0]


def create_for_company_entry(entry, requested_by=None):
    """Job that brings one company document to its local folder.
    ---
    Crea el trabajo que baja el documento a su carpeta local. None si
    no es de una empresa del grupo o no hay carpeta local de su clase.
    """
    fiscal_ct = ContentType.objects.get_for_model(CompanyFiscalProfile)
    if entry.domain_content_type_id != fiscal_ct.pk or (
            entry.document_type_id is None):
        return None
    folder = source_local_folder(entry)
    if not folder:
        logger.info("# [company_local] %s: sin carpeta local de su clase; "
                    "no se baja.", entry.name)
        return None
    return LocalDownloadJob.objects.create(
        requested_by=requested_by, folder=folder,
        files=[{"blob": entry.blob_name,
                "path": "%s/%s" % (folder, entry.name)}],
    )
