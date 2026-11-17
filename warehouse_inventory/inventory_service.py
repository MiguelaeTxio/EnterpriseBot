# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/warehouse_inventory/inventory_service.py
"""
Photo-based warehouse inventory: upload, Gemini reading, matching
against the digital warehouse and differences.

---

H10 (S151, sesión invasora). Inventario del almacén por fotos, a
petición de Miguel Ángel: "bajar a taller, al almacén, ir haciendo
fotos, ir subiéndolas y ver qué es lo que tenemos en taller".
Decisiones suyas (17/11/2026):

- Se fotografían etiquetas y cajas con referencia y también piezas
  sueltas.
- Las diferencias solo se informan: el stock no cambia hasta que él
  confirma cada una (o la descarta).
- Se guarda la ubicación de cada cosa (estantería, balda, cajón).
- De momento solo lo usa él (superusuario).

Flujo:
1. `register_photo`: la foto va al cubo, a ALMACEN/INVENTARIO POR
   FOTOS/<recuento>/, se indexa (se ve en el explorador) y se encola.
2. `process_photo` (tarea Celery): Gemini lee cada artículo visible, se
   cruza con el almacén digital (referencia del proveedor o interna;
   si no, descripción normalizada) y se recalculan las diferencias.
3. `recompute_differences`: agrupa lo contado de todas las fotos del
   recuento y lo compara con el stock. Al cerrar el recuento aparece
   además lo que el sistema tiene y no se ha visto en ninguna foto.
4. `resolve_differences`: lo que Miguel Ángel confirma ajusta el stock
   (movimiento ADJUST con nota del recuento); lo que descarta no toca
   nada.
"""
import json
import logging
import re
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
from document_explorer.subject_upload_service import (
    BUCKET, content_type_of,
)
from spare_parts.gcs_service import (
    download_bytes, get_storage_client, upload_bytes,
)
from spare_parts.models import SparePartEntry, StockMovement
from spare_parts.services import (
    _normalise_description, register_uninventoried_warehouse_stock,
)

from .models import (
    InventoryCount, InventoryDifference, InventoryItem, InventoryLocation,
    InventoryPhoto,
)

logger = logging.getLogger(__name__)

PHOTOS_ROOT = "ALMACEN/INVENTARIO POR FOTOS"
GEMINI_MIME_TYPES = {
    "image/jpeg", "image/png", "image/webp", "image/heic", "image/heif",
}
MAX_PHOTO_BYTES = 25 * 1024 * 1024
EMPTY_LEVEL = "EMPTY"

_PHOTO_SCHEMA = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "source": {"type": "string", "enum": ["LABEL", "PART"]},
                    "reference": {"type": "string"},
                    "brand": {"type": "string"},
                    "description": {"type": "string"},
                    "quantity": {"type": "string"},
                    "quantity_is_estimate": {"type": "boolean"},
                },
                "required": [
                    "source", "reference", "brand", "description",
                    "quantity", "quantity_is_estimate",
                ],
            },
        },
    },
    "required": ["items"],
}

_PROMPT = (
    "Eres el encargado del almacén de repuestos de un taller de grúas, "
    "camiones y maquinaria. Esta foto es de una estantería, balda, "
    "cajón o zona del almacén. Enumera cada artículo distinto que se "
    "vea, uno por elemento de 'items':\n"
    "- source: LABEL si lo identificas por una etiqueta, caja o envase "
    "con texto legible; PART si es una pieza suelta que reconoces por su "
    "forma.\n"
    "- reference: la referencia o código del artículo tal cual se lee en "
    "la etiqueta o la pieza (sin inventar), o cadena vacía.\n"
    "- brand: la marca si se lee, o cadena vacía.\n"
    "- description: qué es, en castellano y breve (p. ej. 'Filtro de "
    "aceite', 'Rodamiento 6205', 'Aceite hidráulico 20 L').\n"
    "- quantity: cuántas unidades hay de ese artículo, como número con "
    "punto decimal. Si una caja cerrada indica cuántas lleva, usa ese "
    "número por caja y multiplica por las cajas. Cadena vacía si no se "
    "puede saber.\n"
    "- quantity_is_estimate: true si la cantidad es aproximada (piezas "
    "tapadas, montón, caja abierta sin poder contar).\n"
    "Agrupa en un solo elemento las unidades iguales del mismo artículo. "
    "No incluyas herramientas del taller, estanterías, ni objetos que no "
    "sean repuestos o material del almacén. Si no se ve ningún artículo, "
    "devuelve items vacío."
)


class TransientInventoryError(Exception):
    """
    Gemini saturated/unavailable: try again later.

    ---

    Gemini saturado o caído: se reintenta más tarde desde la tarea.
    """


class InventoryUploadError(Exception):
    """
    The uploaded file cannot be accepted.

    ---

    La foto subida no se puede aceptar (mensaje para la pantalla).
    """


# ---------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------

def _norm_code(value):
    """
    Reference for matching: upper case, letters and digits only.

    ---

    Referencia para cruzar: mayúsculas, solo letras y cifras.
    """
    return re.sub(r"[^0-9A-Z]", "", (value or "").upper())


def _parse_decimal(value):
    """
    "12.5" -> Decimal; empty or unreadable -> None.

    ---

    "12.5" -> Decimal; vacío o ilegible -> None.
    """
    text = str(value or "").strip().replace(",", ".")
    if not text:
        return None
    try:
        number = Decimal(text)
    except InvalidOperation:
        return None
    return number if number >= 0 else None


def _safe_name(text):
    """
    Name usable inside a blob path.

    ---

    Nombre utilizable dentro de la ruta del objeto en el cubo.
    """
    cleaned = re.sub(r"[^\w\- ]+", " ", text or "", flags=re.UNICODE)
    return re.sub(r"\s+", " ", cleaned).strip()[:60] or "SIN UBICACION"


def _quantity_text(value):
    """
    Decimal -> short text without useless decimals.

    ---

    Decimal -> texto corto, sin decimales inútiles.
    """
    if value is None:
        return "?"
    return ("%f" % value).rstrip("0").rstrip(".")


# ---------------------------------------------------------------------
# Recuento, ubicaciones y subida
# ---------------------------------------------------------------------

def open_count(company):
    """
    The open stocktake of the company, or None.

    ---

    El recuento abierto de la empresa, o None.
    """
    return InventoryCount.objects.filter(
        company=company, closed_at__isnull=True,
    ).first()


def start_count(company_user):
    """
    Open a stocktake (or return the one already open).

    ---

    Abre un recuento (o devuelve el que ya está abierto: solo hay uno a
    la vez).
    """
    company = company_user.company
    with transaction.atomic():
        current = open_count(company)
        if current is not None:
            return current
        return InventoryCount.objects.create(
            company=company, started_by=company_user,
        )


def location_for(company, name):
    """
    Get or create the location with this name.

    ---

    Busca o crea la ubicación con ese nombre (sin distinguir mayúsculas).
    """
    name = re.sub(r"\s+", " ", (name or "").strip())[:120]
    if not name:
        raise InventoryUploadError("Escribe la ubicación de la foto.")
    existing = InventoryLocation.objects.filter(
        company=company, name__iexact=name,
    ).first()
    if existing is not None:
        return existing
    return InventoryLocation.objects.create(company=company, name=name)


def _queue(photo_pk):
    """
    Queue the Gemini reading after the commit.

    ---

    Encola la lectura con Gemini cuando la transacción se confirma.
    """
    from .tasks import process_inventory_photo_task

    transaction.on_commit(
        lambda: process_inventory_photo_task.delay(photo_pk),
    )


def register_photo(count, location, data, filename, uploaded_by):
    """
    Store one photo in the bucket, index it and queue its reading.

    ---

    Guarda la foto en el cubo (ALMACEN/INVENTARIO POR FOTOS/<recuento>/),
    la indexa para verla en el explorador, la registra y encola su
    lectura. Devuelve la InventoryPhoto.
    """
    if not count.is_open:
        raise InventoryUploadError("El recuento ya está cerrado.")
    if not data:
        raise InventoryUploadError("La foto está vacía.")
    if len(data) > MAX_PHOTO_BYTES:
        raise InventoryUploadError("La foto pasa de 25 MB.")
    content_type = content_type_of(data, filename or "")
    if content_type not in GEMINI_MIME_TYPES:
        raise InventoryUploadError(
            "No es una foto que se pueda leer (JPG, PNG, WEBP o HEIC).",
        )
    extension = {
        "image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp",
        "image/heic": ".heic", "image/heif": ".heif",
    }[content_type]
    folder = "%s/RECUENTO %s %s" % (
        PHOTOS_ROOT, count.pk,
        timezone.localtime(count.started_at).strftime("%d-%m-%Y"),
    )
    stamp = timezone.localtime().strftime("%H%M%S")
    sequence = InventoryPhoto.objects.filter(count=count).count() + 1
    blob_name = "%s/%s %s-%03d%s" % (
        folder, _safe_name(location.name), stamp, sequence, extension,
    )
    upload_bytes(BUCKET, blob_name, data, content_type=content_type)
    blob = get_storage_client().bucket(BUCKET).get_blob(blob_name)
    with transaction.atomic():
        index_writer.ensure_folder_chain(BUCKET, folder)
        if blob is not None:
            index_writer.persist_rows(BUCKET, [index_writer.file_row(blob)])
            index_writer.recount_children(
                BUCKET, folder_paths=index_writer.ancestors_of(folder),
            )
        entry = DocumentIndexEntry.objects.filter(
            bucket=BUCKET, blob_name=blob_name,
            deleted_at__isnull=True, purged_at__isnull=True,
        ).first()
        photo = InventoryPhoto.objects.create(
            count=count,
            location=location,
            entry=entry,
            blob_name=blob_name,
            content_type=content_type,
            uploaded_by=uploaded_by,
        )
        _queue(photo.pk)
    return photo


# ---------------------------------------------------------------------
# Lectura con Gemini y cruce con el almacén
# ---------------------------------------------------------------------

def _read_with_gemini(data, content_type):
    """
    Ask Gemini for the articles visible in the photo.

    ---

    Pide a Gemini los artículos que se ven en la foto.
    """
    response = _generate_content_with_retry(
        get_gemini_client(),
        model=DEFAULT_MODEL,
        contents=[Part.from_bytes(data=data, mime_type=content_type), _PROMPT],
        config=GenerateContentConfig(
            http_options=HttpOptions(timeout=180_000),
            response_mime_type="application/json",
            response_schema=_PHOTO_SCHEMA,
            temperature=0.0,
        ),
    )
    return json.loads(response.text.strip())


def _warehouse_index(company):
    """
    Warehouse entries by normalised reference and by description.

    ---

    Repuestos en almacén de la empresa, indexados por referencia
    normalizada (del proveedor y la interna) y por descripción
    normalizada. Si hay varios con la misma clave, el más reciente.
    """
    by_code, by_description = {}, {}
    entries = SparePartEntry.objects.filter(
        company=company, status=SparePartEntry.STATUS_WAREHOUSE,
    ).order_by("updated_at")
    for entry in entries:
        for code in (entry.reference, entry.internal_reference):
            key = _norm_code(code)
            if len(key) >= 3:
                by_code[key] = entry
        description = _normalise_description(entry.description)
        if description:
            by_description[description] = entry
    return by_code, by_description


def _match(raw, by_code, by_description):
    """
    (entry, match_kind) of one article read in a photo.

    ---

    (repuesto, tipo de cruce) de un artículo leído: primero por
    referencia; si no tiene referencia o no casa, por descripción.
    """
    code = _norm_code(raw.get("reference"))
    if len(code) >= 3 and code in by_code:
        return by_code[code], InventoryItem.MATCH_REFERENCE
    description = _normalise_description(raw.get("description"))
    if description and description in by_description:
        return by_description[description], InventoryItem.MATCH_DESCRIPTION
    return None, InventoryItem.MATCH_NONE


def _finish(photo, status, reason, extraction=None):
    """
    Close the reading of a photo.

    ---

    Cierra la lectura de una foto con su estado y su resultado.
    """
    photo.status = status
    photo.reason = reason[:4000]
    photo.processed_at = timezone.now()
    if extraction is not None:
        photo.extraction = extraction
    photo.save()
    return status


def process_photo(photo_id, final=False):
    """
    Read one photo with Gemini and match it against the warehouse.

    ---

    Lee una foto con Gemini, guarda cada artículo con su cruce con el
    almacén digital y recalcula las diferencias del recuento. Con
    `final`, un fallo transitorio de Gemini ya no se reintenta.
    """
    claimed = InventoryPhoto.objects.filter(
        pk=photo_id, status=InventoryPhoto.STATUS_PENDING,
    ).update(status=InventoryPhoto.STATUS_PROCESSING)
    photo = InventoryPhoto.objects.select_related(
        "count__company", "location",
    ).get(pk=photo_id)
    if not claimed:
        return photo.status
    try:
        data = download_bytes(BUCKET, photo.blob_name)
    except Exception as exc:
        return _finish(
            photo, InventoryPhoto.STATUS_ERROR,
            "No se pudo leer la foto del cubo: %s" % exc,
        )
    try:
        extraction = _read_with_gemini(data, photo.content_type)
    except Exception as exc:
        if not final:
            photo.status = InventoryPhoto.STATUS_PENDING
            photo.save(update_fields=["status"])
            raise TransientInventoryError(str(exc)) from exc
        logger.exception("# [INVENTARIO] Gemini falló (%s)", photo.pk)
        return _finish(
            photo, InventoryPhoto.STATUS_ERROR,
            "Gemini no pudo leer la foto: %s" % exc,
        )
    by_code, by_description = _warehouse_index(photo.count.company)
    with transaction.atomic():
        photo.items.all().delete()
        matched = 0
        raw_items = extraction.get("items") or []
        for raw in raw_items:
            description = (raw.get("description") or "").strip()[:255]
            reference = (raw.get("reference") or "").strip()[:100]
            if not description and not reference:
                continue
            entry, kind = _match(raw, by_code, by_description)
            matched += entry is not None
            InventoryItem.objects.create(
                photo=photo,
                location=photo.location,
                source=(
                    InventoryItem.SOURCE_LABEL
                    if raw.get("source") == "LABEL"
                    else InventoryItem.SOURCE_PART
                ),
                reference=reference,
                brand=(raw.get("brand") or "").strip()[:100],
                description=description or reference,
                quantity=_parse_decimal(raw.get("quantity")),
                quantity_is_estimate=bool(raw.get("quantity_is_estimate")),
                spare_part_entry=entry,
                match_kind=kind,
            )
        count = photo.items.count()
        _finish(
            photo, InventoryPhoto.STATUS_DONE,
            (
                "%d artículo(s) vistos, %d en el almacén digital."
                % (count, matched)
            ) if count else "No se ve ningún artículo del almacén.",
            extraction=extraction,
        )
        recompute_differences(photo.count)
    return photo.status


# ---------------------------------------------------------------------
# Diferencias
# ---------------------------------------------------------------------

def _system_quantity(entry):
    """
    Stock the system says there is (None for uncountable parts).

    ---

    Lo que el sistema dice que hay (None si el repuesto es incontable).
    """
    if entry.is_uncountable:
        return None
    return entry.stock_quantity or Decimal("0")


def _group_key(item):
    """
    Grouping key of an article: its warehouse entry, else its code or
    description.

    ---

    Clave para agrupar lo contado: el repuesto con el que casa; si no
    casa, su referencia normalizada o, sin referencia, su descripción.
    """
    if item.spare_part_entry_id:
        return "entry:%s" % item.spare_part_entry_id
    code = _norm_code(item.reference)
    if len(code) >= 3:
        return ("ref:%s" % code)[:255]
    return ("desc:%s" % (
        _normalise_description(item.description) or item.description.upper()
    ))[:255]


def _desired_differences(count):
    """
    {group_key: fields} of what does not match right now.

    ---

    {clave: campos} de lo que ahora mismo no cuadra: lo contado en todas
    las fotos leídas del recuento, agrupado por repuesto (o, si no casa,
    por referencia/descripción), comparado con el stock. Con el recuento
    cerrado, además lo que el sistema tiene y no se ha visto.
    """
    groups = {}
    items = InventoryItem.objects.filter(
        photo__count=count, photo__status=InventoryPhoto.STATUS_DONE,
    ).select_related("spare_part_entry", "location")
    for item in items:
        key = _group_key(item)
        group = groups.setdefault(key, {
            "entry": item.spare_part_entry,
            "reference": item.reference,
            "description": item.description,
            "locations": [],
            "quantity": None,
            "estimate": False,
        })
        if item.location.name not in group["locations"]:
            group["locations"].append(item.location.name)
        if item.quantity is not None:
            group["quantity"] = (group["quantity"] or 0) + item.quantity
        group["estimate"] = group["estimate"] or item.quantity_is_estimate
        if not group["reference"] and item.reference:
            group["reference"] = item.reference

    desired = {}
    for key, group in groups.items():
        entry = group["entry"]
        fields = {
            "spare_part_entry": entry,
            "reference": (group["reference"] or "")[:100],
            "description": group["description"][:255],
            "locations": ", ".join(group["locations"])[:500],
            "counted_quantity": group["quantity"],
            "counted_is_estimate": group["estimate"],
            "system_quantity": None,
        }
        if entry is None:
            fields["kind"] = InventoryDifference.KIND_NEW
            desired[key] = fields
            continue
        system = _system_quantity(entry)
        if system is None or group["quantity"] is None:
            continue
        if group["quantity"] != system:
            fields["kind"] = InventoryDifference.KIND_QUANTITY
            fields["system_quantity"] = system
            fields["reference"] = (
                entry.reference or entry.internal_reference
            )[:100]
            fields["description"] = entry.description[:255]
            desired[key] = fields

    if not count.is_open:
        warehouse = SparePartEntry.objects.filter(
            company=count.company, status=SparePartEntry.STATUS_WAREHOUSE,
        )
        for entry in warehouse:
            key = "entry:%s" % entry.pk
            if key in groups:
                continue
            system = _system_quantity(entry)
            in_stock = (
                entry.stock_level not in ("", EMPTY_LEVEL)
                if system is None else system > 0
            )
            if not in_stock:
                continue
            desired[key] = {
                "kind": InventoryDifference.KIND_NOT_SEEN,
                "spare_part_entry": entry,
                "reference": (
                    entry.reference or entry.internal_reference
                )[:100],
                "description": entry.description[:255],
                "locations": "",
                "counted_quantity": None,
                "counted_is_estimate": False,
                "system_quantity": system,
            }
    return desired


def recompute_differences(count):
    """
    Bring the pending differences of a stocktake up to date.

    ---

    Pone al día las diferencias pendientes del recuento. Las ya
    confirmadas o descartadas no se tocan nunca.
    """
    with transaction.atomic():
        desired = _desired_differences(count)
        existing = {
            diff.group_key: diff
            for diff in InventoryDifference.objects.select_for_update()
            .filter(count=count)
        }
        for key, diff in existing.items():
            if (
                diff.status == InventoryDifference.STATUS_PENDING
                and key not in desired
            ):
                diff.delete()
        for key, fields in desired.items():
            diff = existing.get(key)
            if diff is None:
                InventoryDifference.objects.create(
                    count=count, group_key=key, **fields,
                )
            elif diff.status == InventoryDifference.STATUS_PENDING:
                for name, value in fields.items():
                    setattr(diff, name, value)
                diff.save()


def close_count(count):
    """
    Close the stocktake: what was not seen shows up as a difference.

    ---

    Cierra el recuento: desde ahora aparece también lo que el sistema
    tiene en almacén y no se ha visto en ninguna foto.
    """
    if count.closed_at is None:
        count.closed_at = timezone.now()
        count.save(update_fields=["closed_at"])
    recompute_differences(count)


def _apply_one(diff, company_user):
    """
    Adjust the stock for one confirmed difference.

    ---

    Ajusta el stock por una diferencia confirmada. Devuelve el
    movimiento creado o lanza ValueError con el motivo.
    """
    note = "recuento %s del almacén por fotos (%s)." % (
        diff.count_id, diff.locations or "sin ubicación",
    )
    if diff.kind == InventoryDifference.KIND_NEW:
        quantity = diff.counted_quantity
        if quantity is None or quantity <= 0:
            raise ValueError(
                "No se sabe cuántas hay: no se puede dar de alta.",
            )
        entry = register_uninventoried_warehouse_stock(
            diff.count.company, company_user, diff.description,
            stock_quantity=quantity,
        )
        if diff.reference:
            entry.reference = diff.reference
            entry.save(update_fields=["reference"])
        movement = entry.movements.order_by("-created_at").first()
        movement.notes = "Alta por el %s" % note
        movement.save(update_fields=["notes"])
        diff.spare_part_entry = entry
        # Lo contado de este grupo pasa a casar con el repuesto nuevo:
        # al recalcular ya no sale como "no se ha visto".
        for item in InventoryItem.objects.filter(
            photo__count=diff.count, spare_part_entry__isnull=True,
        ):
            if _group_key(item) == diff.group_key:
                item.spare_part_entry = entry
                item.save(update_fields=["spare_part_entry"])
        return movement

    entry = diff.spare_part_entry
    if entry is None:
        raise ValueError("El repuesto ya no existe.")
    entry = SparePartEntry.objects.select_for_update().get(pk=entry.pk)
    if entry.is_uncountable:
        before = entry.stock_level
        entry.stock_level = EMPTY_LEVEL
        entry.save(update_fields=["stock_level"])
        return StockMovement.objects.create(
            spare_part_entry=entry,
            movement_type=StockMovement.MOVEMENT_ADJUST,
            quantity=Decimal("0"),
            level_before=before,
            level_after=EMPTY_LEVEL,
            created_by=company_user,
            notes="No se ha visto en el %s" % note,
        )
    before = entry.stock_quantity or Decimal("0")
    after = (
        Decimal("0") if diff.kind == InventoryDifference.KIND_NOT_SEEN
        else diff.counted_quantity
    )
    if after is None:
        raise ValueError("No se sabe cuántas hay.")
    entry.stock_quantity = after
    entry.save(update_fields=["stock_quantity"])
    return StockMovement.objects.create(
        spare_part_entry=entry,
        movement_type=StockMovement.MOVEMENT_ADJUST,
        quantity=after - before,
        created_by=company_user,
        notes="Stock de %s a %s por el %s" % (
            _quantity_text(before), _quantity_text(after), note,
        ),
    )


def resolve_differences(ids, company_user, apply):
    """
    Confirm (adjusting the stock) or discard the given differences.

    Returns (done, skipped_messages).

    ---

    Confirma (ajustando el stock) o descarta las diferencias marcadas.
    Solo actúa sobre las pendientes. Devuelve (hechas, avisos).
    """
    done, warnings = 0, []
    diffs = InventoryDifference.objects.filter(
        pk__in=ids, status=InventoryDifference.STATUS_PENDING,
        count__company=company_user.company,
    ).select_related("count__company", "spare_part_entry")
    for diff in diffs:
        try:
            with transaction.atomic():
                if apply:
                    diff.stock_movement = _apply_one(diff, company_user)
                    diff.status = InventoryDifference.STATUS_APPLIED
                else:
                    diff.status = InventoryDifference.STATUS_DISCARDED
                diff.resolved_by = company_user
                diff.resolved_at = timezone.now()
                diff.save()
        except ValueError as exc:
            warnings.append("%s: %s" % (diff.description, exc))
            continue
        done += 1
    return done, warnings
