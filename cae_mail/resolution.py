# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/cae_mail/resolution.py
"""
What to send for each document a CAE notice asks for (S156).

For every CaeDemand linked to a catalogue type and to its holder
(group company, worker or machine), finds the current document in the
bucket: the most recent one of that type for that holder, by expiry
date or, failing that, by issue date. The screen shows it ready to
download, or says what is missing to know it.

---

Qué mandar por cada documento que pide un aviso CAE. Para cada
documento pedido ya enlazado a un tipo del catálogo y a su titular
(empresa del grupo, trabajador o centro de gasto), busca en el cubo el
vigente: el más reciente de ese tipo y titular, por caducidad o, si no
tiene, por fecha de emisión. La pantalla lo ofrece para descargar o
dice qué falta para saberlo.
"""
import datetime

from django.contrib.contenttypes.models import ContentType

from document_explorer.buckets import PRIMARY_BUCKET
from document_explorer.models import DocumentIndexEntry

# Estados de cada documento pedido en la pantalla.
FOUND = "found"
EXPIRED = "expired"
MISSING = "missing"
NO_TYPE = "no_type"
NO_HOLDER = "no_holder"

STATUS_LABELS = {
    FOUND: "Lo tenemos",
    EXPIRED: "Lo tenemos, caducado",
    MISSING: "No lo tenemos",
    NO_TYPE: "Sin tipo",
    NO_HOLDER: "Sin titular",
}


def holder_of(demand):
    """Company, worker or machine the demand is about, or None.
    ---
    Empresa, trabajador o centro de gasto del documento pedido, o None.
    Un documento de un trabajador o de una máquina nunca se busca en la
    empresa, aunque el aviso diga cuál es.
    """
    if demand.subject_type == demand.SUBJECT_WORKER:
        return demand.person
    if demand.subject_type == demand.SUBJECT_MACHINE:
        return demand.machine
    return demand.company


def current_document(holder, document_type):
    """Most recent live document of a type for a holder, or None.
    ---
    El documento vivo más reciente de un tipo para un titular: primero
    los no obsoletos; por caducidad y, si no tiene, por emisión.
    """
    entries = list(DocumentIndexEntry.objects.filter(
        bucket=PRIMARY_BUCKET,
        entry_kind=DocumentIndexEntry.KIND_FILE,
        deleted_at__isnull=True,
        purged_at__isnull=True,
        domain_content_type=ContentType.objects.get_for_model(
            type(holder)),
        domain_object_id=holder.pk,
        document_type=document_type,
    ))
    if not entries:
        return None
    return max(entries, key=lambda entry: (
        not entry.is_obsolete,
        entry.expiry_date or entry.issue_date or datetime.date.min,
        entry.pk,
    ))


def resolve_demand(demand, today=None):
    """(status, entry) for one demand.
    ---
    (estado, documento) de un documento pedido: el documento solo
    cuando lo tenemos (vigente o caducado).
    """
    today = today or datetime.date.today()
    if demand.document_type_id is None:
        return NO_TYPE, None
    holder = holder_of(demand)
    if holder is None:
        return NO_HOLDER, None
    entry = current_document(holder, demand.document_type)
    if entry is None:
        return MISSING, None
    if entry.expiry_date and entry.expiry_date < today:
        return EXPIRED, entry
    return FOUND, entry


def resolve_mail(mail):
    """Rows for the detail of one notice, plus a status count.
    ---
    Filas del detalle de un aviso (documento pedido, estado y
    documento nuestro) y el recuento por estado.
    """
    today = datetime.date.today()
    rows = []
    counts = dict.fromkeys(STATUS_LABELS, 0)
    for demand in mail.demands.select_related(
            "document_type", "company", "person", "machine"):
        status, entry = resolve_demand(demand, today)
        counts[status] += 1
        rows.append({
            "demand": demand,
            "holder": holder_of(demand),
            "status": status,
            "status_label": STATUS_LABELS[status],
            "entry": entry,
        })
    return rows, counts
