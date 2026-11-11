# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/supplier_invoices/invoice_service.py
"""
Invoice agent: FACTURACIÓN folder of the inbox -> warehouse -> work
orders.

---

H28 (S151, sesión invasora). Agente de facturas de la carpeta
FACTURACIÓN de la bandeja de entrada. Tarea de Miguel Ángel, tal cual:

1. Cada factura que entra en "Facturas nuevas" (subida desde la
   bandeja o dejada en la carpeta por cualquier otra vía) se lee con
   Gemini: proveedor, número, fecha y sus líneas (referencia,
   descripción, cantidad, precio y el albarán que cita, si lo cita).
2. Cada repuesto se coteja con los albaranes que ya tenemos (mismo
   proveedor, por número de albarán si la factura lo cita o por fecha
   si no, y por referencia o descripción): si ya tiene albarán, no se
   duplica nada en el almacén.
3. Los que no tienen albarán se dan por comprados: entran en el
   almacén (mismas reglas de emparejamiento que la entrada por
   albarán, `spare_parts.services.confirm_delivery_note`), con su
   movimiento de entrada.
4. El almacén se coteja con los partes de trabajo: una línea de
   repuesto de un parte con la misma referencia (o, sin referencia, la
   misma descripción), posterior a la compra y todavía sin vincular a
   ningún repuesto del almacén, se da por colocada: salida de almacén
   hacia su máquina. Cada línea de parte se usa una sola vez. Muchos
   partes antiguos se digitalizaron sin repuestos: el almacén
   resultante es un punto de partida, no la realidad.
5. Al terminar, la factura pasa a "Facturas procesadas" (movimiento
   virtual del índice, directriz 4.12: el objeto de GCS no se toca).

Lo que no es una factura o falla se queda en "Facturas nuevas" con su
motivo, para volver a procesarlo.
"""
import hashlib
import json
import logging
import re
import unicodedata
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone
from google.genai.types import GenerateContentConfig, HttpOptions, Part

from ai_services.gemini_client import DEFAULT_MODEL, get_gemini_client
from document_explorer import index_writer
from document_explorer.classification_service import (
    _generate_content_with_retry,
)
from document_explorer.models import DocumentIndexEntry
from document_explorer.move_service import move_entry
from document_explorer.subject_upload_service import (
    BUCKET, content_type_of,
)
from ivr_config.models import Company, CompanyUser
from spare_parts.gcs_service import (
    download_bytes, get_storage_client, upload_bytes,
)
from spare_parts.models import (
    DeliveryNote, DeliveryNoteLine, SparePartEntry, StockMovement,
)
from spare_parts.services import (
    _normalise_description, _normalise_tax_id, generate_internal_reference,
    resolve_or_create_supplier,
)
from work_order_processor.models import SparePartLine

from .models import (
    SupplierInvoice, SupplierInvoiceLine, SupplierInvoicePlacement,
)

logger = logging.getLogger(__name__)

# Carpetas virtuales de FACTURACIÓN en el cubo histórico. Sin tilde en
# la ruta, como el resto de carpetas del cubo (DOC. MAQUINAS, NO
# CONFORMES...); en pantalla se llama FACTURACIÓN.
INVOICES_ROOT = "FACTURACION"
NEW_FOLDER = INVOICES_ROOT + "/FACTURAS NUEVAS"
PROCESSED_FOLDER = INVOICES_ROOT + "/FACTURAS PROCESADAS"

ALLOWED_EXTENSIONS = {"pdf", "jpg", "jpeg", "png", "webp", "heic"}
GEMINI_MIME_TYPES = {
    "application/pdf", "image/jpeg", "image/png", "image/webp",
    "image/heic",
}
# Un albarán que cubre una línea de factura es de, como mucho, estos
# días antes de la fecha de referencia (la del albarán citado o la de
# la factura). Las facturas de proveedor suelen agrupar los albaranes
# de uno a tres meses.
DELIVERY_LOOKBACK_DAYS = 120
# Un repuesto se da por colocado en partes de estos días antes de la
# fecha de referencia en adelante: el parte puede ser anterior a la
# factura (el repuesto llegó con el albarán y la factura vino después).
PLACEMENT_LOOKBACK_DAYS = 60

_INVOICE_SCHEMA = {
    "type": "object",
    "properties": {
        "is_invoice": {"type": "boolean"},
        "document_description": {"type": "string"},
        "supplier_name": {"type": "string"},
        "supplier_tax_id": {"type": "string"},
        "invoice_number": {"type": "string"},
        "invoice_date": {"type": "string"},
        "total_amount": {"type": "string"},
        "lines": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "reference": {"type": "string"},
                    "description": {"type": "string"},
                    "quantity": {"type": "string"},
                    "unit_price": {"type": "string"},
                    "total_price": {"type": "string"},
                    "delivery_number": {"type": "string"},
                    "delivery_date": {"type": "string"},
                    "is_spare_part": {"type": "boolean"},
                },
                "required": [
                    "reference", "description", "quantity", "unit_price",
                    "total_price", "delivery_number", "delivery_date",
                    "is_spare_part",
                ],
            },
        },
    },
    "required": [
        "is_invoice", "document_description", "supplier_name",
        "supplier_tax_id", "invoice_number", "invoice_date",
        "total_amount", "lines",
    ],
}

_PROMPT = (
    "Eres un asistente que lee facturas de proveedores de repuestos "
    "para un grupo de empresas de grúas, plataformas y vehículos "
    "industriales (el grupo es el CLIENTE de la factura, nunca el "
    "proveedor). Responde:\n"
    "- is_invoice: true si el documento es una factura (o factura "
    "rectificativa) de un proveedor; false si es otra cosa (albarán, "
    "presupuesto, pedido...).\n"
    "- document_description: qué es el documento, en pocas palabras.\n"
    "- supplier_name y supplier_tax_id: nombre y NIF/CIF de quien EMITE "
    "la factura, o cadena vacía.\n"
    "- invoice_number: número de la factura, o cadena vacía.\n"
    "- invoice_date: fecha de la factura en formato AAAA-MM-DD, o cadena "
    "vacía.\n"
    "- total_amount: importe total de la factura como número con punto "
    "decimal, sin símbolo de moneda, o cadena vacía.\n"
    "- lines: cada línea facturada, en orden, con: reference (referencia "
    "o código del artículo, o cadena vacía), description (descripción "
    "tal cual), quantity, unit_price y total_price (números con punto "
    "decimal, sin símbolo de moneda, o cadena vacía si no figuran), "
    "delivery_number y delivery_date (número y fecha AAAA-MM-DD del "
    "albarán al que pertenece la línea, si la factura los indica en la "
    "línea o en un encabezado de grupo de líneas tipo 'Albarán nº ... "
    "de fecha ...'; si no, cadena vacía) e is_spare_part (true si es un "
    "repuesto, pieza o material físico; false si es mano de obra, "
    "portes, transporte, desplazamiento, recargos, tasas, servicios o "
    "una línea de texto sin artículo).\n"
    "No incluyas filas de subtotal, impuestos ni totales. No inventes "
    "ningún dato que no se lea en el documento."
)


class InvoiceUploadError(Exception):
    """
    A file the FACTURACIÓN folder does not accept.

    ---

    Archivo que la carpeta FACTURACIÓN no admite (mensaje para quien
    lo sube).
    """


class TransientInvoiceError(Exception):
    """
    Gemini saturated/unavailable: try again later.

    ---

    Gemini saturado o caído: se reintenta más tarde desde la tarea.
    """


# ---------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------

def _extension_of(name):
    """
    Lowercase extension of a file name ("" if none).

    ---

    Extensión en minúsculas del nombre ("" si no tiene).
    """
    return name.rsplit(".", 1)[-1].lower() if "." in name else ""


def _safe_name(name):
    """
    File name safe for a GCS object (no slashes, no control chars).

    ---

    Nombre apto para un objeto de GCS: sin barras ni caracteres de
    control, en NFC (S036: los acentos descompuestos generan
    duplicados fantasma).
    """
    name = unicodedata.normalize("NFC", name)
    name = re.sub(r"[\x00-\x1f/\\]", "_", name).strip() or "factura"
    return name[:180]


def _norm_code(value):
    """
    Reference/number for comparison: uppercase letters and digits only.

    ---

    Referencia o número para comparar: solo letras y cifras, en
    mayúsculas y sin tildes ("A-123.4" == "a1234").
    """
    text = unicodedata.normalize("NFKD", value or "")
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"[^A-Z0-9]", "", text.upper())


def _parse_iso(value):
    """
    Parse an AAAA-MM-DD string, or None.

    ---

    Convierte AAAA-MM-DD en fecha, o None.
    """
    try:
        year, month, day = (int(p) for p in (value or "").split("-"))
        return date(year, month, day)
    except (ValueError, TypeError):
        return None


def _parse_decimal(value):
    """
    Parse a numeric string read by Gemini, or None.

    ---

    Convierte un número leído por Gemini en Decimal, o None.
    """
    text = (value or "").strip().replace(",", ".")
    if not text:
        return None
    try:
        return Decimal(text).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return None


def _quantity_text(value):
    """
    Quantity without trailing zeros ("2", "1.5").

    ---

    Cantidad sin ceros sobrantes ("2", "1.5").
    """
    if value == value.to_integral_value():
        return str(int(value))
    return str(value).rstrip("0")


def _default_company():
    """
    The platform's only Company (same rule as subject_upload_service).

    ---

    La única fila Company de la plataforma (misma regla que
    `subject_upload_service._resolve_company`).
    """
    return Company.objects.order_by("pk").first()


def _movement_author(invoice):
    """
    CompanyUser recorded on stock movements of this invoice.

    ---

    Usuario que figura en los movimientos de stock de la factura: quien
    la subió o, si llegó a la carpeta por otra vía, el primer
    administrador de la empresa (`StockMovement.created_by` es
    obligatorio).
    """
    if invoice.uploaded_by_id:
        return invoice.uploaded_by
    return CompanyUser.objects.filter(
        company=invoice.company, role=CompanyUser.ROLE_ADMIN,
    ).order_by("pk").first()


# ---------------------------------------------------------------------
# Entrada en la carpeta
# ---------------------------------------------------------------------

def _queue(invoice_pk):
    """
    Queue the agent for one invoice once the transaction commits.

    ---

    Encola el agente para una factura al confirmar la transacción.
    """
    from .tasks import process_supplier_invoice_task

    transaction.on_commit(
        lambda: process_supplier_invoice_task.delay(invoice_pk),
    )


def _index_new_blob(blob_name, display_name):
    """
    Index a just-uploaded object of "Facturas nuevas" under its name.

    ---

    Indexa un objeto recién subido a "Facturas nuevas" y le pone, en
    el índice, el nombre original (el del objeto lleva delante el
    principio de la huella para no pisar nunca otro objeto).
    """
    blob = get_storage_client().bucket(BUCKET).get_blob(blob_name)
    with transaction.atomic():
        index_writer.ensure_folder_chain(BUCKET, NEW_FOLDER)
        index_writer.ensure_folder_chain(BUCKET, PROCESSED_FOLDER)
        index_writer.persist_rows(BUCKET, [index_writer.file_row(blob)])
        index_writer.recount_children(
            BUCKET,
            folder_paths=index_writer.ancestors_of(NEW_FOLDER)
            + [PROCESSED_FOLDER],
        )
    entry = DocumentIndexEntry.objects.get(
        bucket=BUCKET, blob_name=blob_name,
        deleted_at__isnull=True, purged_at__isnull=True,
    )
    if entry.name != display_name:
        entry.name = display_name
        move_entry(entry, NEW_FOLDER)
    return entry


def register_upload(name, data, uploaded_by):
    """
    Store one uploaded invoice in "Facturas nuevas" and queue it.

    Returns (invoice, created, note). Raises InvoiceUploadError for a
    file type not accepted.

    ---

    Guarda una factura subida desde la bandeja en "Facturas nuevas" y
    la encola. El mismo archivo (huella SHA-256) ya subido no se
    guarda otra vez: vuelve con una nota. Devuelve (factura, creada,
    nota).
    """
    extension = _extension_of(name)
    if extension not in ALLOWED_EXTENSIONS:
        raise InvoiceUploadError(
            "%s: solo se admiten PDF e imágenes (JPG, PNG, WEBP, HEIC)."
            % name
        )
    sha256 = hashlib.sha256(data).hexdigest()
    previous = SupplierInvoice.objects.filter(sha256=sha256).order_by(
        "-pk",
    ).first()
    if previous is not None and previous.entry_id:
        return previous, False, "Ya se había subido (%s)." % (
            previous.get_status_display()
        )
    content_type = content_type_of(data, name)
    if content_type == "application/octet-stream" and extension == "heic":
        content_type = "image/heic"
    display_name = _safe_name(name)
    blob_name = "%s/%s_%s" % (NEW_FOLDER, sha256[:12], display_name)
    upload_bytes(BUCKET, blob_name, data, content_type=content_type)
    entry = _index_new_blob(blob_name, display_name)
    with transaction.atomic():
        invoice = SupplierInvoice.objects.create(
            entry=entry,
            sha256=sha256,
            original_name=name[:255],
            content_type=content_type,
            company=uploaded_by.company,
            uploaded_by=uploaded_by,
        )
        _queue(invoice.pk)
    return invoice, True, ""


def sweep_new_folder():
    """
    Register files that reached "Facturas nuevas" by any other route.

    ---

    Registra y encola los archivos que han llegado a "Facturas nuevas"
    por cualquier otra vía (explorador, agente de OneDrive...) y que
    todavía no tienen factura. Devuelve cuántos ha encolado.
    """
    entries = DocumentIndexEntry.objects.filter(
        bucket=BUCKET,
        parent_path=NEW_FOLDER,
        entry_kind=DocumentIndexEntry.KIND_FILE,
        deleted_at__isnull=True,
        purged_at__isnull=True,
        supplier_invoice__isnull=True,
    )
    company = _default_company()
    queued = 0
    for entry in entries:
        try:
            data = download_bytes(BUCKET, entry.blob_name)
        except Exception:
            logger.exception(
                "# [FACTURAS] No se pudo leer %s", entry.blob_name,
            )
            continue
        with transaction.atomic():
            invoice = SupplierInvoice.objects.create(
                entry=entry,
                sha256=hashlib.sha256(data).hexdigest(),
                original_name=entry.name[:255],
                content_type=(
                    entry.content_type or content_type_of(data, entry.name)
                ),
                company=company,
            )
            _queue(invoice.pk)
        queued += 1
    return queued


def requeue_invoices(invoices, uploaded_by):
    """
    Process again the "not an invoice" / failed ones.

    Returns (requeued, skipped).

    ---

    Vuelve a procesar las que salieron "no es una factura" o con
    error (siguen en "Facturas nuevas"). El resto se salta. Devuelve
    (encoladas, saltadas).
    """
    requeued = skipped = 0
    for invoice in invoices:
        if invoice.status not in SupplierInvoice.RETRYABLE_STATUSES or (
            invoice.entry_id is None
        ):
            skipped += 1
            continue
        with transaction.atomic():
            invoice.status = SupplierInvoice.STATUS_PENDING
            invoice.reason = ""
            invoice.processed_at = None
            if invoice.uploaded_by_id is None:
                invoice.uploaded_by = uploaded_by
            invoice.save(update_fields=[
                "status", "reason", "processed_at", "uploaded_by",
            ])
            _queue(invoice.pk)
        requeued += 1
    return requeued, skipped


# ---------------------------------------------------------------------
# Lectura con Gemini
# ---------------------------------------------------------------------

def _read_with_gemini(data, content_type):
    """
    Ask Gemini for the invoice header and its lines.

    ---

    Pide a Gemini la cabecera de la factura y sus líneas.
    """
    response = _generate_content_with_retry(
        get_gemini_client(),
        model=DEFAULT_MODEL,
        contents=[Part.from_bytes(data=data, mime_type=content_type), _PROMPT],
        config=GenerateContentConfig(
            http_options=HttpOptions(timeout=180_000),
            response_mime_type="application/json",
            response_schema=_INVOICE_SCHEMA,
            temperature=0.0,
        ),
    )
    return json.loads(response.text.strip())


# ---------------------------------------------------------------------
# Cotejo con los albaranes
# ---------------------------------------------------------------------

def _same_supplier(note, supplier, tax_id, supplier_name):
    """
    Whether a delivery note is from the invoice's supplier.

    ---

    Si el albarán es del proveedor de la factura: por el proveedor
    resuelto, por CIF y, solo si la factura no trae CIF, por nombre.
    """
    if supplier is not None and note.supplier_id == supplier.pk:
        return True
    if tax_id:
        return _normalise_tax_id(note.supplier_tax_id) == tax_id
    return bool(supplier_name) and _norm_code(
        note.supplier_name,
    ) == _norm_code(supplier_name)


def _delivery_candidates(invoice, supplier, ref_dates):
    """
    Purchase delivery note lines of the supplier not yet invoiced.

    ---

    Líneas de albaranes de compra del proveedor de la factura que
    ninguna otra línea de factura ha cubierto todavía, dentro de la
    ventana de fechas de la factura.
    """
    tax_id = _normalise_tax_id(invoice.supplier_tax_id)
    qs = DeliveryNoteLine.objects.select_related("delivery_note").filter(
        delivery_note__company=invoice.company,
        delivery_note__note_type=DeliveryNote.NOTE_TYPE_PURCHASE,
        invoice_lines__isnull=True,
    )
    if ref_dates:
        qs = qs.filter(
            delivery_note__delivery_date__gte=min(ref_dates) - timedelta(
                days=DELIVERY_LOOKBACK_DAYS,
            ),
            delivery_note__delivery_date__lte=max(ref_dates),
        )
    return [
        line for line in qs
        if _same_supplier(
            line.delivery_note, supplier, tax_id, invoice.supplier_name,
        )
    ]


def _match_delivery_line(line, candidates, used):
    """
    The delivery note line that already covers an invoice line, or None.

    ---

    Línea de albarán que ya cubre la línea de factura, o None. Si la
    factura cita el albarán, solo se mira ese albarán; si no, cualquier
    albarán del proveedor anterior a la fecha de referencia. Manda la
    referencia; sin referencia en alguno de los dos, la descripción.
    Con varias, la de la misma cantidad.
    """
    ref_date = line.delivery_date or line.invoice.invoice_date
    wanted_number = _norm_code(line.delivery_number_raw)
    pool = []
    for candidate in candidates:
        if candidate.pk in used:
            continue
        note = candidate.delivery_note
        if wanted_number:
            if _norm_code(note.delivery_number) != wanted_number:
                continue
        elif ref_date and note.delivery_date and (
            not ref_date - timedelta(days=DELIVERY_LOOKBACK_DAYS)
            <= note.delivery_date <= ref_date
        ):
            continue
        pool.append(candidate)
    reference = _norm_code(line.reference)
    description = _normalise_description(line.description)
    matches = []
    for candidate in pool:
        candidate_ref = _norm_code(candidate.reference)
        if reference and candidate_ref:
            if reference == candidate_ref:
                matches.append(candidate)
        elif description and (
            _normalise_description(candidate.description) == description
        ):
            matches.append(candidate)
    if not matches:
        return None
    same_quantity = [m for m in matches if m.quantity == line.quantity]
    return (same_quantity or matches)[0]


# ---------------------------------------------------------------------
# Entrada en almacén (comprado sin albarán)
# ---------------------------------------------------------------------

def _warehouse_intake(invoice, line, supplier, author):
    """
    Put a part bought without delivery note into the warehouse.

    ---

    Da entrada en almacén a un repuesto comprado sin albarán, con las
    mismas reglas que la entrada por albarán
    (`confirm_delivery_note`, rama WAREHOUSE): se suma a la entrada de
    almacén con su misma referencia; si no, a una entrada rápida sin
    proveedor con la misma descripción; si no, entrada nueva con su
    referencia interna. Movimiento IN con la factura en la nota.
    """
    company = invoice.company
    entry = None
    if line.reference:
        wanted = _norm_code(line.reference)
        for candidate in SparePartEntry.objects.filter(
            company=company,
            status=SparePartEntry.STATUS_WAREHOUSE,
            is_uncountable=False,
        ).exclude(reference=""):
            if _norm_code(candidate.reference) == wanted:
                entry = candidate
                break
    if entry is None:
        description = _normalise_description(line.description)
        if description:
            for candidate in SparePartEntry.objects.filter(
                company=company,
                status=SparePartEntry.STATUS_WAREHOUSE,
                is_uncountable=False,
                reference="",
                supplier__isnull=True,
            ):
                if _normalise_description(
                    candidate.description,
                ) == description:
                    entry = candidate
                    break
    if entry is None:
        entry = SparePartEntry(
            company=company,
            reference=line.reference,
            internal_reference=generate_internal_reference(company),
            description=(line.description or line.reference)[:255],
            is_uncountable=False,
            status=SparePartEntry.STATUS_WAREHOUSE,
            origin_type=SparePartEntry.ORIGIN_SUPPLIER,
            supplier_name=invoice.supplier_name,
            supplier_tax_id=invoice.supplier_tax_id,
        )
    elif not entry.reference and line.reference:
        entry.reference = line.reference
    entry.stock_quantity = (entry.stock_quantity or Decimal("0")) + (
        line.quantity
    )
    entry.supplier = supplier
    entry.purchase_unit_price = line.unit_price
    entry.purchase_total_price = line.total_price
    entry.save()
    movement = StockMovement.objects.create(
        spare_part_entry=entry,
        movement_type=StockMovement.MOVEMENT_IN,
        quantity=line.quantity,
        created_by=author,
        notes=(
            "Entrada por factura %s de %s (sin albarán registrado)." % (
                invoice.invoice_number or invoice.pk,
                invoice.supplier_name or "proveedor sin nombre",
            )
        ),
    )
    return entry, movement


# ---------------------------------------------------------------------
# Cotejo con los partes de trabajo
# ---------------------------------------------------------------------

def _work_order_pool(company, since):
    """
    Work-order spare part lines still unlinked to the warehouse.

    ---

    Líneas de repuesto de partes de la empresa desde `since`, todavía
    sin vincular a ningún repuesto del almacén ni dadas por colocadas
    con otra factura, indexadas por referencia y por descripción.
    """
    qs = SparePartLine.objects.select_related(
        "entry_line__entry", "entry_line__machine_asset", "vehicle",
    ).filter(
        spare_part_entry__isnull=True,
        invoice_placement__isnull=True,
        entry_line__entry__work_order__company=company,
        entry_line__entry__work_date__gte=since,
    ).order_by("entry_line__entry__work_date", "pk")
    by_reference, by_description = {}, {}
    for spare_line in qs:
        reference = _norm_code(spare_line.reference)
        if reference:
            by_reference.setdefault(reference, []).append(spare_line)
        description = _normalise_description(spare_line.material)
        if description:
            by_description.setdefault(description, []).append(spare_line)
    return by_reference, by_description


def _place_from_work_orders(line, entry, pool, used, author):
    """
    Take as fitted the work-order lines that used this part.

    ---

    Da por colocadas las líneas de parte que usaron este repuesto (por
    referencia; si la factura no trae referencia, por descripción),
    posteriores a la fecha de referencia menos PLACEMENT_LOOKBACK_DAYS,
    hasta la cantidad de la línea de factura y el stock que quede. Cada
    una: salida de almacén hacia su máquina, la línea del parte queda
    vinculada al repuesto y se anota la colocación. Un parte sin
    unidades cuenta 1. Devuelve la cantidad colocada.
    """
    if entry is None or entry.is_uncountable or (
        entry.status != SparePartEntry.STATUS_WAREHOUSE
    ):
        return Decimal("0")
    by_reference, by_description = pool
    reference = _norm_code(line.reference)
    if reference:
        candidates, kind = by_reference.get(reference, []), (
            SupplierInvoicePlacement.MATCH_REFERENCE
        )
    else:
        candidates, kind = by_description.get(
            _normalise_description(line.description), [],
        ), SupplierInvoicePlacement.MATCH_DESCRIPTION
    ref_date = line.delivery_date or line.invoice.invoice_date
    since = (
        ref_date - timedelta(days=PLACEMENT_LOOKBACK_DAYS)
        if ref_date else None
    )
    remaining = min(line.quantity or Decimal("0"), entry.stock_quantity)
    placed = Decimal("0")
    for spare_line in candidates:
        if remaining <= 0:
            break
        if spare_line.pk in used:
            continue
        work_date = spare_line.entry_line.entry.work_date
        if since and work_date and work_date < since:
            continue
        assumed = not spare_line.quantity
        quantity = min(
            spare_line.quantity or Decimal("1"), remaining,
        )
        entry_line = spare_line.entry_line
        entry.stock_quantity -= quantity
        if entry.stock_quantity <= 0:
            entry.stock_quantity = Decimal("0")
            entry.status = SparePartEntry.STATUS_CONSUMED
            entry.consumed_at = timezone.now()
        entry.save(update_fields=[
            "stock_quantity", "status", "consumed_at", "updated_at",
        ])
        movement = StockMovement.objects.create(
            spare_part_entry=entry,
            movement_type=StockMovement.MOVEMENT_OUT,
            quantity=quantity,
            machine=spare_line.vehicle or entry_line.machine_asset,
            work_order_entry_line=entry_line,
            spare_part_line=spare_line,
            created_by=author,
            notes=(
                "Colocado según el parte del %s (cruce automático con la "
                "factura %s)." % (
                    work_date.strftime("%d/%m/%Y") if work_date else "?",
                    line.invoice.invoice_number or line.invoice.pk,
                )
            ),
        )
        spare_line.spare_part_entry = entry
        spare_line.save(update_fields=["spare_part_entry"])
        SupplierInvoicePlacement.objects.create(
            invoice_line=line,
            spare_part_line=spare_line,
            quantity=quantity,
            quantity_assumed=assumed,
            match_kind=kind,
            stock_movement=movement,
        )
        used.add(spare_line.pk)
        remaining -= quantity
        placed += quantity
        if entry.status != SparePartEntry.STATUS_WAREHOUSE:
            break
    return placed


# ---------------------------------------------------------------------
# Proceso de una factura
# ---------------------------------------------------------------------

def _finish(invoice, status, reason, **fields):
    """
    Close an invoice; done ones move to "Facturas procesadas".

    ---

    Cierra la factura con su estado y motivo. Las procesadas y las
    repetidas pasan a "Facturas procesadas" (movimiento virtual del
    índice); las demás se quedan en "Facturas nuevas".
    """
    invoice.status = status
    invoice.reason = reason[:4000]
    invoice.processed_at = timezone.now()
    for name, value in fields.items():
        setattr(invoice, name, value)
    invoice.save()
    if status in SupplierInvoice.DONE_STATUSES and invoice.entry_id:
        entry = DocumentIndexEntry.objects.filter(
            pk=invoice.entry_id, deleted_at__isnull=True,
            purged_at__isnull=True,
        ).first()
        if entry is not None:
            move_entry(entry, PROCESSED_FOLDER)
    return status


def _find_duplicate(invoice):
    """
    An already processed invoice with the same supplier and number.

    ---

    Factura ya procesada del mismo proveedor (CIF) y número, o None.
    """
    number = _norm_code(invoice.invoice_number)
    tax_id = _normalise_tax_id(invoice.supplier_tax_id)
    if not number or not tax_id:
        return None
    for other in SupplierInvoice.objects.filter(
        company=invoice.company,
        status=SupplierInvoice.STATUS_PROCESSED,
    ).exclude(pk=invoice.pk).only(
        "pk", "invoice_number", "supplier_tax_id",
    ):
        if _norm_code(other.invoice_number) == number and (
            _normalise_tax_id(other.supplier_tax_id) == tax_id
        ):
            return other
    return None


def _store_lines(invoice, extraction):
    """
    Replace the invoice lines with the ones just read.

    ---

    Sustituye las líneas de la factura por las recién leídas.
    """
    invoice.lines.all().delete()
    lines = []
    for number, raw in enumerate(extraction.get("lines") or [], start=1):
        lines.append(SupplierInvoiceLine.objects.create(
            invoice=invoice,
            line_number=number,
            reference=(raw.get("reference") or "").strip()[:100],
            description=(raw.get("description") or "").strip()[:255],
            quantity=_parse_decimal(raw.get("quantity")),
            unit_price=_parse_decimal(raw.get("unit_price")),
            total_price=_parse_decimal(raw.get("total_price")),
            delivery_number_raw=(
                raw.get("delivery_number") or ""
            ).strip()[:100],
            delivery_date=_parse_iso(raw.get("delivery_date")),
            is_spare_part=bool(raw.get("is_spare_part")),
        ))
    return lines


def _summary(counts):
    """
    Human summary of what the agent did with the invoice.

    ---

    Resumen para la pantalla de lo que ha hecho el agente.
    """
    parts = ["%d línea(s)" % counts["lines"]]
    for key, label in (
        ("covered", "ya con albarán"),
        ("purchased", "compradas sin albarán, entradas en almacén"),
        ("no_quantity", "sin cantidad legible"),
        ("not_part", "no son repuestos"),
    ):
        if counts[key]:
            parts.append("%d %s" % (counts[key], label))
    text = ", ".join(parts) + "."
    if counts["placed_lines"]:
        text += (
            " %d línea(s) con repuestos dados por colocados según los "
            "partes de trabajo (%s unidades)." % (
                counts["placed_lines"], _quantity_text(counts["placed"]),
            )
        )
    return text


def process_invoice(invoice_id, final=False):
    """
    Run the agent over one invoice.

    ---

    Ejecuta el agente sobre una factura (ver docstring del módulo).
    Con `final`, un fallo transitorio de Gemini ya no se reintenta:
    queda como error visible.
    """
    invoice = SupplierInvoice.objects.select_related(
        "entry", "company", "uploaded_by",
    ).get(pk=invoice_id)
    if invoice.status not in SupplierInvoice.OPEN_STATUSES:
        return invoice.status
    if invoice.entry is None:
        return _finish(
            invoice, SupplierInvoice.STATUS_ERROR,
            "El archivo de la factura ya no está en el índice.",
        )
    invoice.status = SupplierInvoice.STATUS_PROCESSING
    invoice.save(update_fields=["status"])
    try:
        data = download_bytes(BUCKET, invoice.entry.blob_name)
    except Exception as exc:
        return _finish(
            invoice, SupplierInvoice.STATUS_ERROR,
            "No se pudo leer el archivo: %s" % exc,
        )
    content_type = (invoice.content_type or "").split(";")[0].lower()
    if content_type not in GEMINI_MIME_TYPES:
        return _finish(
            invoice, SupplierInvoice.STATUS_NOT_INVOICE,
            "No es un PDF ni una imagen legible.",
        )
    try:
        extraction = _read_with_gemini(data, content_type)
    except Exception as exc:
        if not final:
            invoice.status = SupplierInvoice.STATUS_PENDING
            invoice.save(update_fields=["status"])
            raise TransientInvoiceError(str(exc)) from exc
        logger.exception("# [FACTURAS] Gemini falló (%s)", invoice.pk)
        return _finish(
            invoice, SupplierInvoice.STATUS_ERROR,
            "Gemini no pudo leer el archivo: %s" % exc,
        )
    if not extraction.get("is_invoice"):
        return _finish(
            invoice, SupplierInvoice.STATUS_NOT_INVOICE,
            "No es una factura: %s." % (
                (extraction.get("document_description") or "").strip()
                or "documento desconocido"
            ),
            extraction=extraction,
        )
    invoice.extraction = extraction
    invoice.supplier_name = (
        extraction.get("supplier_name") or ""
    ).strip()[:255]
    invoice.supplier_tax_id = (
        extraction.get("supplier_tax_id") or ""
    ).strip()[:50]
    invoice.invoice_number = (
        extraction.get("invoice_number") or ""
    ).strip()[:100]
    invoice.invoice_date = _parse_iso(extraction.get("invoice_date"))
    invoice.total_amount = _parse_decimal(extraction.get("total_amount"))
    invoice.save()

    original = _find_duplicate(invoice)
    if original is not None:
        return _finish(
            invoice, SupplierInvoice.STATUS_DUPLICATE,
            "La factura %s de %s ya se procesó (subida el %s): no se "
            "toca el almacén." % (
                invoice.invoice_number, invoice.supplier_name,
                timezone.localtime(original.created_at).strftime(
                    "%d/%m/%Y",
                ),
            ),
            duplicate_of=original,
        )
    author = _movement_author(invoice)
    if author is None:
        return _finish(
            invoice, SupplierInvoice.STATUS_ERROR,
            "No hay ningún usuario administrador al que atribuir los "
            "movimientos de almacén.",
        )
    try:
        with transaction.atomic():
            counts = _apply(invoice, extraction, author)
    except Exception as exc:
        logger.exception("# [FACTURAS] Fallo al aplicar %s", invoice.pk)
        return _finish(
            invoice, SupplierInvoice.STATUS_ERROR,
            "No se pudo poner al día el almacén (no se ha tocado nada): "
            "%s" % exc,
        )
    return _finish(
        invoice, SupplierInvoice.STATUS_PROCESSED, _summary(counts),
        lines_count=counts["lines"],
        covered_count=counts["covered"],
        purchased_count=counts["purchased"],
        placed_count=counts["placed_lines"],
    )


def _apply(invoice, extraction, author):
    """
    Lines -> delivery notes -> warehouse -> work orders (one atomic step).

    ---

    Líneas -> albaranes -> almacén -> partes, todo en una transacción:
    si algo falla no queda nada a medias.
    """
    supplier = resolve_or_create_supplier(
        invoice.company, invoice.supplier_tax_id, invoice.supplier_name,
    )
    invoice.supplier = supplier
    invoice.save(update_fields=["supplier"])
    lines = _store_lines(invoice, extraction)
    ref_dates = [
        d for d in [invoice.invoice_date] + [
            line.delivery_date for line in lines
        ] if d
    ]
    candidates = _delivery_candidates(invoice, supplier, ref_dates)
    pool = _work_order_pool(
        invoice.company,
        (
            min(ref_dates) - timedelta(days=PLACEMENT_LOOKBACK_DAYS)
            if ref_dates else date(2000, 1, 1)
        ),
    )
    used_delivery, used_work_order = set(), set()
    counts = {
        "lines": len(lines), "covered": 0, "purchased": 0,
        "no_quantity": 0, "not_part": 0, "placed": Decimal("0"),
        "placed_lines": 0,
    }
    for line in lines:
        if not line.is_spare_part:
            line.outcome = SupplierInvoiceLine.OUTCOME_NOT_PART
            line.save(update_fields=["outcome"])
            counts["not_part"] += 1
            continue
        covering = _match_delivery_line(line, candidates, used_delivery)
        if covering is not None:
            used_delivery.add(covering.pk)
            line.outcome = SupplierInvoiceLine.OUTCOME_COVERED
            line.delivery_note_line = covering
            line.spare_part_entry = covering.spare_part_entry
            counts["covered"] += 1
        elif not line.quantity or line.quantity <= 0:
            line.outcome = SupplierInvoiceLine.OUTCOME_NO_QUANTITY
            counts["no_quantity"] += 1
        else:
            entry, movement = _warehouse_intake(
                invoice, line, supplier, author,
            )
            line.outcome = SupplierInvoiceLine.OUTCOME_PURCHASED
            line.spare_part_entry = entry
            line.stock_movement = movement
            counts["purchased"] += 1
        if line.spare_part_entry is not None:
            line.spare_part_entry.refresh_from_db()
            line.placed_quantity = _place_from_work_orders(
                line, line.spare_part_entry, pool, used_work_order, author,
            )
            if line.placed_quantity:
                counts["placed"] += line.placed_quantity
                counts["placed_lines"] += 1
        line.save()
    return counts
