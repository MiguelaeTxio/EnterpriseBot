# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/fleet/manual_counters_service.py
"""
S154 (invasora, 28/11) -- machine models and where their counters are.

---

S154 (invasora, 28/11) -- modelos de máquina y dónde están sus
contadores, sacado de los manuales.

Miguel Ángel: «los manuales de los vehículos deben estar linkados a sus
modelos [...] Necesitamos indicar en el link del QR, mirando los
manuales de los vehículos, con fotos o diagramas, preferentemente
fotos, el lugar donde se encuentran los horómetros y cuenta km o los
botones que permutan la información en los displays». Decidió que lo
que saque la IA se revise antes de publicarse y empezar por un modelo
(el de la A29).

Cómo se buscan las páginas: se lee el texto de cada página del manual
(PyMuPDF, sin OCR) y se eligen las que hablan de contadores o del
display; si el manual es escaneado (casi sin texto), se miran sus
primeras páginas por tandas. Esas páginas van a Gemini, que dice cuál
enseña cada contador y lo explica en una frase. Cada página elegida se
guarda como imagen, pendiente de revisar.
"""
import json
import logging
import re
import unicodedata

logger = logging.getLogger(__name__)

# Palabras que delatan una página con contadores o el display.
COUNTER_WORDS = (
    "horometro", "cuentahoras", "contador de horas", "horas de servicio",
    "horas de funcionamiento", "horas de trabajo", "horas motor",
    "cuentakilometros", "odometro", "kilometraje", "totalizador",
    "hour meter", "hourmeter", "hour counter", "operating hours",
    "service hours", "odometer", "mileage", "betriebsstunden",
    "kilometerzahler",
)
DISPLAY_WORDS = (
    "display", "pantalla", "cuadro de instrumentos", "instrument panel",
    "instrument cluster", "tablero", "salpicadero", "dashboard",
    "visualizador", "indicador", "menu",
)
MAX_CANDIDATE_PAGES = 24
SCANNED_CHUNK_PAGES = 20
# S154 (28/11): el manual entero (los de la A29 tienen hasta 568).
SCANNED_MAX_PAGES = 800
MAX_SUBSET_BYTES = 15 * 1024 * 1024
MAX_PER_KIND = 2
# S154 (28/11), Miguel Ángel: «las imágenes se ven realmente mal»: la
# página entera a 110 ppp no se leía en el móvil. Ahora se recorta el
# dibujo (recuadro que da Gemini) y se saca a más resolución.
RENDER_DPI = 220
CROP_MARGIN = 0.03
JPEG_QUALITY = 90
GEMINI_TIMEOUT_MS = 240_000

_PROMPT = """Eres un mecánico de maquinaria pesada. Te paso páginas del
manual de la máquina «{model}». Busca las que enseñan al conductor o al
gruista DÓNDE leer:
- KM: el cuentakilómetros (odómetro, kilometraje total);
- MOTOR: el horómetro del motor (horas de funcionamiento del motor o de
  la máquina);
- GRUA: el horómetro de la grúa o de la superestructura;
- DISPLAY: los botones o el menú que cambian lo que sale en el display
  para ver esos contadores.
Solo vale la página donde SE VE el dibujo o la foto del contador, de la
pantalla o de los botones. Las páginas de solo texto, las listas
numeradas de mandos (leyendas) y las tablas NO valen: si la leyenda está
en una página y el dibujo en otra, devuelve la del dibujo. Prefiere
fotos. Cada página es la número `n` del orden en que te las paso (la
primera es 1).
Para cada página útil da: n, kind (KM, MOTOR, GRUA o DISPLAY), caption
(una frase en castellano para el conductor: dónde está y cómo verlo, sin
inventar nada que no salga en la página), is_photo (true si es una foto
real, false si es un dibujo), confidence (0 a 1) y box: el recuadro del
dibujo o la foto en la página, [ymin, xmin, ymax, xmax] de 0 a 1000,
que abarque el dibujo con sus números y flechas pero no el texto de
alrededor. Si ninguna sirve, devuelve una lista vacía."""

_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "pages": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "n": {"type": "INTEGER"},
                    "kind": {"type": "STRING",
                             "enum": ["KM", "MOTOR", "GRUA", "DISPLAY"]},
                    "caption": {"type": "STRING"},
                    "is_photo": {"type": "BOOLEAN"},
                    "confidence": {"type": "NUMBER"},
                    "box": {"type": "ARRAY",
                            "items": {"type": "INTEGER"}},
                },
                "required": ["n", "kind", "caption", "is_photo",
                             "confidence"],
            },
        },
    },
    "required": ["pages"],
}


class ManualCountersError(Exception):
    """Something the office can fix / Algo que la oficina puede arreglar."""


def _plain(text):
    text = unicodedata.normalize("NFKD", text or "").lower()
    return "".join(c for c in text if not unicodedata.combining(c))


def _machine_content_type():
    from django.contrib.contenttypes.models import ContentType

    from fleet.models import MachineAsset

    return ContentType.objects.get_for_model(MachineAsset)


def machine_manuals(machines):
    """
    Use manuals linked to the machines, one per identical file.

    ---

    Los manuales de uso enlazados a esas máquinas, sin repetir: cada
    máquina tenía su copia del mismo PDF; se queda uno por tamaño.
    """
    from document_explorer.models import DocumentIndexEntry

    rows = DocumentIndexEntry.objects.filter(
        domain_content_type=_machine_content_type(),
        domain_object_id__in=[m.pk for m in machines],
        document_type__label__icontains="manual",
        deleted_at__isnull=True,
        manual_discard__isnull=True,
    ).order_by("name")
    seen, unique = set(), []
    for entry in rows:
        if entry.size_bytes in seen:
            continue
        seen.add(entry.size_bytes)
        unique.append(entry)
    return unique


def build_model(company, name):
    """
    Create or refresh the model `name` from the machines' Marca/Modelo.

    ---

    Crea (o completa) el modelo con las máquinas cuya Marca / Modelo es
    exactamente `name`. No quita nada de lo que ya tuviera. El manual se
    elige aparte (set_model_manual).
    """
    from fleet.models import MachineAsset, MachineModel

    machines = list(MachineAsset.objects.filter(
        company=company, brand_model__iexact=name.strip()))
    if not machines:
        raise ManualCountersError(
            "Ninguna máquina tiene «%s» en Marca / Modelo." % name)
    model, _created = MachineModel.objects.get_or_create(
        company=company, name=machines[0].brand_model.strip())
    model.machines.add(*machines)
    return model


def set_model_manual(model, entry, company_user=None):
    """
    Make `entry` the model's only manual; discard the other copies.

    ---

    S154 (28/11), Miguel Ángel: un modelo, un manual. `entry` pasa a
    ser el manual del modelo y las demás copias de las máquinas del
    modelo quedan descartadas en la BD (siguen en el cubo y en
    Microsoft 365, no se borra nada). Devuelve cuántas se descartan.
    """
    from fleet.models import DiscardedManual

    machines = list(model.machines.all())
    if entry.domain_object_id not in {m.pk for m in machines}:
        raise ManualCountersError(
            "Ese manual no es de ninguna máquina del modelo.")
    model.manual = entry
    model.save(update_fields=["manual"])
    others = [e for e in machine_manuals(machines) if e.pk != entry.pk]
    for other in others:
        DiscardedManual.objects.get_or_create(
            entry=other, defaults={"machine_model": model,
                                   "kept_manual": entry,
                                   "discarded_by": company_user})
    return len(others)


def _candidate_pages(document):
    """
    Page numbers (0-based) that talk about counters or the display.

    ---

    Las páginas (desde 0) cuyo texto habla de contadores o del display,
    de más a menos palabras encontradas. Si el manual casi no tiene
    texto (escaneado), devuelve None.
    """
    scores, text_chars = [], 0
    for index in range(document.page_count):
        text = _plain(document[index].get_text("text"))
        text_chars += len(text)
        score = 3 * sum(text.count(w) for w in COUNTER_WORDS)
        if score:
            score += sum(text.count(w) for w in DISPLAY_WORDS)
        if score:
            scores.append((score, index))
    if text_chars < 200 * max(document.page_count, 1) // 10:
        return None
    scores.sort(key=lambda x: (-x[0], x[1]))
    return sorted(index for _score, index in scores[:MAX_CANDIDATE_PAGES])


def _subset(document, pages):
    import fitz

    target = fitz.open()
    for index in pages:
        target.insert_pdf(document, from_page=index, to_page=index)
    return target.tobytes(garbage=3, deflate=True)


def _ask_gemini(model_name, pdf_bytes):
    from google.genai.types import (
        GenerateContentConfig, HttpOptions, Part, ThinkingConfig,
    )

    from ai_services.document_vision_service import (
        _generate_content_with_retry,
    )
    from ai_services.gemini_client import DEFAULT_MODEL, get_gemini_client

    response = _generate_content_with_retry(
        get_gemini_client(),
        model=DEFAULT_MODEL,
        contents=[Part.from_bytes(data=pdf_bytes,
                                  mime_type="application/pdf"),
                  _PROMPT.format(model=model_name)],
        config=GenerateContentConfig(
            http_options=HttpOptions(timeout=GEMINI_TIMEOUT_MS),
            response_mime_type="application/json",
            response_schema=_SCHEMA,
            thinking_config=ThinkingConfig(thinking_level="low"),
            temperature=0.0,
        ),
    )
    try:
        return json.loads(response.text.strip()).get("pages") or []
    except (ValueError, AttributeError):
        return []


def _batches(document, pages):
    """
    Split the pages in subsets that fit one Gemini request.

    ---

    Reparte las páginas en tandas que caben en una petición.
    """
    # S154 (28/11): el tamaño de cada página una vez (rehacer la tanda
    # entera en cada página era cuadrático con manuales de 568 páginas).
    batch, size = [], 0
    for index in pages:
        page_size = len(_subset(document, [index]))
        if batch and size + page_size > MAX_SUBSET_BYTES:
            yield batch
            batch, size = [], 0
        batch.append(index)
        size += page_size
    if batch:
        yield batch


def find_counter_pages(model_name, entry, log=print, page_counts=None):
    """
    Pages of one manual that show where the counters are.

    ---

    Las páginas de un manual que enseñan dónde están los contadores:
    lista de (página desde 0, kind, caption, is_photo, confidence, box).
    """
    import fitz

    from spare_parts.gcs_service import download_bytes

    data = download_bytes(entry.bucket, entry.blob_name)
    try:
        document = fitz.open(stream=data, filetype="pdf")
    except Exception:  # noqa: BLE001 -- PDF dañado
        log("   %s: no se puede abrir, se salta." % entry.name)
        return []
    if page_counts is not None:
        page_counts[entry.pk] = document.page_count
    pages = _candidate_pages(document)
    if pages is None:
        pages = list(range(min(document.page_count, SCANNED_MAX_PAGES)))
        log("   %s: escaneado (%s páginas), se miran las primeras %s."
            % (entry.name, document.page_count, len(pages)))
    else:
        log("   %s: %s páginas, %s hablan de contadores o del display."
            % (entry.name, document.page_count, len(pages)))
    if not pages:
        return []
    found = []
    for batch in _batches(document, pages):
        try:
            answer = _ask_gemini(model_name, _subset(document, batch))
        except Exception as exc:  # noqa: BLE001
            log("   %s: Gemini falló (%s), se sigue." % (
                entry.name, str(exc)[:120]))
            continue
        for item in answer:
            n = item.get("n") or 0
            if 1 <= n <= len(batch):
                found.append((batch[n - 1], item["kind"],
                              (item.get("caption") or "")[:300],
                              bool(item.get("is_photo")),
                              float(item.get("confidence") or 0),
                              _valid_box(item.get("box"))))
    return found


def _valid_box(box):
    """
    The box as 4 numbers 0-1000 (ymin, xmin, ymax, xmax), or None.

    ---

    El recuadro si tiene sentido (4 números de 0 a 1000, con alto y
    ancho); si no, None y se saca la página entera.
    """
    if not isinstance(box, (list, tuple)) or len(box) != 4:
        return None
    try:
        ymin, xmin, ymax, xmax = (max(0, min(1000, int(v))) for v in box)
    except (TypeError, ValueError):
        return None
    if ymax - ymin < 50 or xmax - xmin < 50:
        return None
    return ymin, xmin, ymax, xmax


def _render_page(data, page_index, box=None):
    """
    JPEG of the page (or of the box in it) at RENDER_DPI.

    ---

    La página en JPEG a RENDER_DPI; con recuadro, solo el dibujo con
    un pequeño margen.
    """
    import fitz

    with fitz.open(stream=data, filetype="pdf") as document:
        page = document[page_index]
        clip = None
        if box:
            ymin, xmin, ymax, xmax = box
            rect = page.rect
            clip = fitz.Rect(
                rect.x0 + rect.width * max(xmin / 1000 - CROP_MARGIN, 0),
                rect.y0 + rect.height * max(ymin / 1000 - CROP_MARGIN, 0),
                rect.x0 + rect.width * min(xmax / 1000 + CROP_MARGIN, 1),
                rect.y0 + rect.height * min(ymax / 1000 + CROP_MARGIN, 1))
        pixmap = page.get_pixmap(dpi=RENDER_DPI, clip=clip)
        return pixmap.tobytes("jpeg", jpg_quality=JPEG_QUALITY)


def extract_for_model(model, log=print):
    """
    Look for the counters in all the model's manuals; store pending.

    ---

    Busca los contadores en todos los manuales del modelo y guarda las
    mejores páginas (hasta 2 por contador, primero las fotos) como
    imágenes pendientes de revisar. No repite una página ya guardada.
    Devuelve cuántas se han guardado.
    """
    from fleet.models import ManualCounterImage
    from spare_parts.gcs_service import (
        TASK_PHOTOS_BUCKET, download_bytes, upload_bytes,
    )

    if model.manual is None:
        raise ManualCountersError("El modelo no tiene manual elegido.")
    manuals = [model.manual]
    found, page_counts = [], {}
    for position, entry in enumerate(manuals, 1):
        log("[%s/%s] %s" % (position, len(manuals), entry.name))
        for page, kind, caption, is_photo, confidence, box in \
                find_counter_pages(model.name, entry, log, page_counts):
            found.append((kind, not is_photo, -confidence, entry, page,
                          caption, is_photo, box))
    found.sort(key=lambda x: x[:3])
    saved, per_kind, seen, pdf_cache = 0, {}, set(), {}
    for kind, _p, _c, entry, page, caption, is_photo, box in found:
        if per_kind.get(kind, 0) >= MAX_PER_KIND:
            continue
        # S154 (28/11): manuales que son copia uno de otro (mismas
        # páginas, otro tamaño) daban la misma página dos veces.
        same = (kind, page, page_counts.get(entry.pk))
        if same in seen:
            continue
        seen.add(same)
        if ManualCounterImage.objects.filter(
                machine_model=model, manual=entry, page=page + 1,
                kind=kind).exists():
            per_kind[kind] = per_kind.get(kind, 0) + 1
            continue
        blob_name = "fichas_qr/modelos/%s/%s_p%s_%s.jpg" % (
            model.pk, entry.pk, page + 1, kind.lower())
        if entry.pk not in pdf_cache:
            pdf_cache[entry.pk] = download_bytes(entry.bucket,
                                                 entry.blob_name)
        upload_bytes(TASK_PHOTOS_BUCKET, blob_name,
                     _render_page(pdf_cache[entry.pk], page, box),
                     content_type="image/jpeg")
        ManualCounterImage.objects.create(
            machine_model=model, kind=kind, caption=caption, manual=entry,
            page=page + 1, is_photo=is_photo, bucket=TASK_PHOTOS_BUCKET,
            blob_name=blob_name)
        per_kind[kind] = per_kind.get(kind, 0) + 1
        saved += 1
        log("   Guardada: %s, %s página %s (%s)." % (
            dict(ManualCounterImage.KIND_CHOICES)[kind], entry.name,
            page + 1, "foto" if is_photo else "dibujo"))
    return saved


def manual_rows(machine):
    """
    The manuals to leaf through from the QR page, with a signed URL.

    ---

    S154 (28/11), Miguel Ángel: «enlazar el propio manual desde el QR
    para tener acceso para hojearlo». El manual de sus modelos y los
    suyos propios no descartados (sin repetir copias), con su tamaño
    para que se sepa lo que pesa antes de abrirlo con datos del móvil.
    """
    from spare_parts.gcs_service import generate_signed_url

    entries = machine_manuals([machine])
    ids = {e.pk for e in entries}
    for model in machine.machine_models.select_related("manual"):
        entry = model.manual
        if entry is not None and entry.deleted_at is None and (
                entry.pk not in ids):
            ids.add(entry.pk)
            entries.append(entry)
    return [{"name": entry.name,
             "mb": round((entry.size_bytes or 0) / 1048576, 1),
             "url": generate_signed_url(entry.bucket, entry.blob_name)}
            for entry in sorted(entries, key=lambda e: e.name)]


def clear_pending(model):
    """
    Delete the model's images still pending review (and their files).

    ---

    Borra las imágenes del modelo que siguen pendientes de revisar (y su
    archivo), para volver a buscar. Las publicadas y las quitadas se
    quedan. Devuelve cuántas.
    """
    from fleet.models import ManualCounterImage
    from spare_parts.gcs_service import delete_file

    pending = list(model.counter_images.filter(
        status=ManualCounterImage.STATUS_PENDING))
    for image in pending:
        delete_file(image.bucket, image.blob_name)
        image.delete()
    return len(pending)


def image_rows(machine, published_only=True):
    """
    The counter images of the machine's models, with a signed URL.

    ---

    Las imágenes de contadores de los modelos de la máquina, con su URL
    firmada. `published_only=False` incluye las pendientes (revisión).
    """
    from fleet.models import ManualCounterImage
    from spare_parts.gcs_service import generate_signed_url

    images = ManualCounterImage.objects.filter(
        machine_model__machines=machine).select_related(
        "machine_model", "manual")
    if published_only:
        images = images.filter(status=ManualCounterImage.STATUS_PUBLISHED)
    else:
        images = images.exclude(status=ManualCounterImage.STATUS_REJECTED)
    return [{"image": image,
             "url": generate_signed_url(image.bucket, image.blob_name)}
            for image in images.distinct()]


def review_image(machine, image_id, decision, caption, company_user):
    """
    Publish or remove a counter image; optionally fix its caption.

    ---

    Publica o quita una imagen de contador de un modelo de la máquina;
    con `caption`, cambia antes su explicación. Devuelve el mensaje.
    """
    from django.utils import timezone

    from fleet.models import ManualCounterImage

    image = ManualCounterImage.objects.filter(
        pk=image_id, machine_model__machines=machine).first()
    if image is None:
        raise ManualCountersError("Esa imagen no es de este modelo.")
    if caption is not None:
        image.caption = re.sub(r"\s+", " ", caption).strip()[:300]
    if decision == "publish":
        image.status = ManualCounterImage.STATUS_PUBLISHED
        message = "Publicada en el QR de las máquinas del modelo."
    elif decision == "remove":
        image.status = ManualCounterImage.STATUS_REJECTED
        message = "Quitada."
    else:
        message = "Explicación guardada."
    image.reviewed_by = company_user
    image.reviewed_at = timezone.now()
    image.save(update_fields=["caption", "status", "reviewed_by",
                              "reviewed_at"])
    return message
