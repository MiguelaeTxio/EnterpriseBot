# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/driving_licence_service.py
"""
H30 (S125). Reads the class matrix (reverse, columns 9-12) of ONE
driving licence card when it enters, by any route.

---

H30 (S125). Lee la matriz de clases (reverso, columnas 9 a 12) de UN
permiso de conducción al entrar, venga por donde venga (ficha,
cuarentena, WhatsApp). Hasta ahora solo la rellenaba el comando de lote
`harvest_driving_licence_classes` (S120), lanzado una vez sobre los
carnés que ya existían: un carné nuevo salía en la ficha con "Este
archivo no tiene matriz de clases registrada" (captura real de Miguel
Ángel, S125, carné entrado por WhatsApp).

Reutiliza EXACTAMENTE el comando de S120 -- mismo prompt, mismo esquema,
misma traducción de clases (modelo antiguo, clases suprimidas, fechas
inverosímiles) y misma escritura (`DrivingLicenceGrant` + caducidad más
lejana en el documento). Solo cambia de dónde sale el tipo del archivo:
de sus bytes, no del índice.
"""
import logging

from django.utils import timezone
from google.genai.types import Part

from ai_services.gemini_client import get_gemini_client
from document_explorer.management.commands import (
    harvest_driving_licence_classes as harvest,
)
from document_explorer.models import (
    DocumentIndexEntry, DrivingLicenceCategory,
)
from document_explorer.subject_upload_service import content_type_of
from spare_parts.gcs_service import download_bytes

logger = logging.getLogger(__name__)

CARD_CODE = harvest.CARD_CODE


class _OneCard(harvest.Command):
    """
    The S120 harvester, for one card, with the MIME type from bytes.

    ---

    El recolector de S120 para un solo carné, con el tipo sacado de
    los propios bytes (el índice puede decir application/octet-stream).
    """

    def __init__(self):
        super().__init__()
        self._categories = {
            category.code: category
            for category in DrivingLicenceCategory.objects.all()
        }

    def _file_parts(self, entry, render_dpi):
        data = download_bytes(entry.bucket, entry.blob_name)
        return [Part.from_bytes(
            data=data, mime_type=content_type_of(data, entry.name),
        )]


def harvest_card(entry_pk):
    """
    Read and store the class matrix of one card. Returns a short text.

    ---

    Lee y guarda la matriz de clases de un carné. Devuelve un texto
    corto con el resultado. Con las mismas reglas que el lote de S120:
    si no es un permiso, no se ve el reverso o la confianza es BAJA, no
    se escribe nada.
    """
    entry = DocumentIndexEntry.objects.select_related(
        "document_type",
    ).filter(pk=entry_pk).first()
    if entry is None or entry.document_type is None:
        return "sin documento"
    if entry.document_type.code != CARD_CODE:
        return "no es un permiso de conducción"
    card = _OneCard()
    answer = card._ask_gemini(get_gemini_client(), entry)
    if not answer.get("is_driving_licence"):
        result = "no es un permiso de conducción según Gemini"
    elif not answer.get("reverse_visible") or not answer.get("rows"):
        result = "sin reverso/matriz visible"
    elif answer.get("confidence") == "BAJA":
        result = "confianza BAJA, no se escribe"
    else:
        grants, issues = card._translate_rows(answer, timezone.localdate())
        if grants:
            card._apply(entry, grants)
            result = "matriz guardada: %s" % ", ".join(sorted(grants))
        else:
            result = "ninguna clase utilizable"
        if issues:
            result += " (incidencias: %s)" % "; ".join(issues)
    logger.info("# [DRIVING] Carné %s: %s", entry.pk, result)
    return result


def queue_harvest(entry):
    """
    Queue the reading of a card after the current transaction.

    ---

    Encola la lectura de un carné al confirmar la transacción en curso
    (Gemini tarda: nunca dentro de la petición web). Solo para
    permisos de conducción; cualquier otro tipo se ignora.
    """
    from django.db import transaction

    from document_explorer.tasks import harvest_driving_licence_task

    if entry is None or not entry.document_type_id:
        return
    if entry.document_type.code != CARD_CODE:
        return
    transaction.on_commit(
        lambda: harvest_driving_licence_task.delay(entry.pk),
    )
