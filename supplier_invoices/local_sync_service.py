# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/supplier_invoices/local_sync_service.py
"""
Local FACTURACIÓN folder (OneDrive) kept in step by the H28 agent.

---

H28 (S151, sesión invasora). Miguel Ángel, al ver que en su OneDrive
no había nada: la carpeta FACTURACIÓN tiene que existir también en
local, dentro de ACCESO_BUZON_DOCUMENTACION, con sus subcarpetas
"FACTURAS NUEVAS" y "FACTURAS PROCESADAS". El agente H28 la mantiene
(`h28_migration_agent/invoice_folder.py`); aquí, lo que le dice el
servidor en cada ciclo:

- `upload`: facturas de la carpeta local de nuevas que el servidor no
  tiene -> el agente las sube (`register_upload(from_local=True)`).
- `move_to_processed`: facturas que están en local en nuevas y el
  agente ya ha procesado -> el agente las pasa a procesadas.
- `download`: facturas que entraron por otra vía (bandeja del panel,
  explorador) y nunca han estado en local -> el agente las baja a la
  subcarpeta que les toca. Una vez en local (`local_synced_at`), no se
  vuelven a bajar aunque se borren de allí.

Las facturas se reconocen por su huella SHA-256, nunca por el nombre.
"""
from django.utils import timezone

from .models import SupplierInvoice

FOLDER_NEW = "nuevas"
FOLDER_PROCESSED = "procesadas"


def _latest_by_sha():
    """
    Latest invoice of each fingerprint that still has its file.

    ---

    La factura más reciente de cada huella que conserva su archivo.
    """
    latest = {}
    for invoice in SupplierInvoice.objects.filter(
        entry__isnull=False,
    ).order_by("pk"):
        latest[invoice.sha256] = invoice
    return latest


def folder_of(invoice):
    """
    Local subfolder an invoice belongs in.

    ---

    Subcarpeta local que le toca a una factura.
    """
    if invoice.status in SupplierInvoice.DONE_STATUSES:
        return FOLDER_PROCESSED
    return FOLDER_NEW


def sync_plan(local_items):
    """
    What the agent has to do with the local folder this cycle.

    `local_items`: [{"sha256": ..., "folder": "nuevas"|"procesadas"}].

    ---

    Lo que el agente tiene que hacer en la carpeta local en este
    ciclo (ver docstring del módulo). Las facturas que ya están en
    local quedan marcadas como tales.
    """
    known = _latest_by_sha()
    local_shas = set()
    upload, move = [], []
    reached_local = []
    for item in local_items:
        sha = (item.get("sha256") or "").strip().lower()
        if len(sha) != 64:
            continue
        local_shas.add(sha)
        invoice = known.get(sha)
        if invoice is None:
            if item.get("folder") == FOLDER_NEW:
                upload.append(sha)
            continue
        if invoice.local_synced_at is None:
            reached_local.append(invoice.pk)
        if item.get("folder") == FOLDER_NEW and (
            folder_of(invoice) == FOLDER_PROCESSED
        ):
            move.append(sha)
    if reached_local:
        SupplierInvoice.objects.filter(pk__in=reached_local).update(
            local_synced_at=timezone.now(),
        )
    download = [
        {
            "id": invoice.pk,
            "sha256": invoice.sha256,
            "name": invoice.original_name,
            "folder": folder_of(invoice),
        }
        for sha, invoice in known.items()
        if sha not in local_shas and invoice.local_synced_at is None
        and invoice.pk not in reached_local
    ]
    return {
        "upload": sorted(set(upload)),
        "move_to_processed": sorted(set(move)),
        "download": download,
    }


def mark_local(invoice):
    """
    Record that the agent has put the invoice in the local folder.

    ---

    Anota que el agente ya ha dejado la factura en la carpeta local.
    """
    if invoice.local_synced_at is None:
        invoice.local_synced_at = timezone.now()
        invoice.save(update_fields=["local_synced_at"])
