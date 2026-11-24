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
import re
import unicodedata

from django.contrib.contenttypes.models import ContentType

from document_explorer.buckets import PRIMARY_BUCKET
from document_explorer.models import DocumentIndexEntry

# Estados de cada documento pedido en la pantalla.
FOUND = "found"
EXPIRED = "expired"
NEEDS_NEW = "needs_new"
MISSING = "missing"
NO_TYPE = "no_type"
NO_HOLDER = "no_holder"

STATUS_LABELS = {
    FOUND: "Lo tenemos",
    EXPIRED: "Lo tenemos, caducado",
    NEEDS_NEW: "Falta el nuevo",
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


_MONTHS = {
    "ENERO": 1, "FEBRERO": 2, "MARZO": 3, "ABRIL": 4, "MAYO": 5,
    "JUNIO": 6, "JULIO": 7, "AGOSTO": 8, "SEPTIEMBRE": 9,
    "SETIEMBRE": 9, "OCTUBRE": 10, "NOVIEMBRE": 11, "DICIEMBRE": 12,
}
# «TC1 ... (Septiembre 2026)»: el documento de un mes concreto.
_PERIOD_RE = re.compile(r"\(\s*([A-Z]+)\s+(20\d{2})\s*\)")


def demand_period(demand):
    """(year, month) a monthly demand is for, or None.
    ---
    Mes concreto que pide un documento mensual («TC1 (Septiembre
    2026)», «Certificado ... (Agosto 2023)»), o None.
    """
    text = unicodedata.normalize("NFKD", demand.document or "")
    text = "".join(c for c in text if not unicodedata.combining(c))
    for name, year in _PERIOD_RE.findall(text.upper()):
        if name in _MONTHS:
            return int(year), _MONTHS[name]
    return None


def _in_period(entry, period):
    day = entry.issue_date or entry.expiry_date
    return day is not None and (day.year, day.month) == period


def current_document(holder, document_type, period=None):
    """Most recent live document of a type for a holder, or None.
    ---
    El documento vivo más reciente de un tipo para un titular: primero
    los no obsoletos; por caducidad y, si no tiene, por emisión. Con
    `period` (año, mes), solo el de ese mes.
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
    if period is not None:
        entries = [entry for entry in entries if _in_period(entry, period)]
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
    cuando lo tenemos (vigente, caducado o el mismo que la plataforma
    ya tiene y caduca en la fecha del aviso).
    """
    today = today or datetime.date.today()
    if demand.document_type_id is None:
        return NO_TYPE, None
    holder = holder_of(demand)
    if holder is None:
        return NO_HOLDER, None
    period = demand_period(demand)
    entry = current_document(holder, demand.document_type, period)
    if entry is None:
        return MISSING, None
    # El de un mes concreto no caduca: es ese o no lo es.
    if period is not None:
        return FOUND, entry
    if entry.expiry_date and entry.expiry_date < today:
        return EXPIRED, entry
    # S156: el aviso dice hasta cuándo vale lo que tiene la plataforma
    # («próximo a caducar el 15/12»). Si lo nuestro no pasa de esa
    # fecha, es el mismo documento: hace falta el nuevo.
    if (demand.due_date and entry.expiry_date
            and entry.expiry_date <= demand.due_date):
        return NEEDS_NEW, entry
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
