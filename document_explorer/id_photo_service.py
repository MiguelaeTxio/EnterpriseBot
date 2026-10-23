# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/id_photo_service.py
"""
ID photo of a person, cropped from his ID card or driving licence.

The face is found with Cloud Vision face detection on the document
(image, or the first pages of a PDF), cropped like an ID photo (3:4,
head and shoulders) and stored in the person record. The platform
photo is a PNG under 128 KB made from it on download.

---

Foto de carné de una persona, recortada de su DNI o de su permiso de
conducir. H31 (S134), Miguel Ángel: *"un pipeline en los DNI y
permisos con foto para extraer la foto y colocarla como foto de la
persona"*, y poder descargarla *"para plataforma [...] con el nombre
de la persona en formato PNG y con menos de 128K"*.

- Documentos de los que sale: DNI, NIE, pasaporte, permiso de
  conducir y las imágenes que se suben como foto (tipo IMAGEN). Manda
  el más reciente: una foto subida a mano después de un DNI gana; un
  DNI nuevo, después de la foto, también.
- La cara se busca con la detección de caras de Cloud Vision (la misma
  cuenta que el OCR de la plataforma). En el DNI hay una foto grande y
  otra pequeña de seguridad: se toma la más grande.
- Nunca toca el documento ni su blob en GCS (directriz 4.12): el
  recorte se guarda en `PersonIdPhoto`, uno por persona.
"""
import io
import logging

from django.contrib.contenttypes.models import ContentType
from django.utils import timezone

from document_explorer.models import (
    DocumentIndexEntry,
    PersonIdentity,
    PersonIdPhoto,
)

logger = logging.getLogger(__name__)

SOURCE_TYPES = ("DNI", "NIE", "PASAPORTE", "CARNET_CONDUCIR", "IMAGEN")
IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp")
PDF_PAGES = 2
PDF_DPI = 200
MIN_CONFIDENCE = 0.6
# ID photo proportions: 3 wide by 4 high, face about half the width.
# Proporción de foto de carné: 3 de ancho por 4 de alto.
CROP_WIDTH_PER_FACE = 1.9
CROP_TOP_PER_FACE = 0.55
MAX_STORED_HEIGHT = 800
STORED_JPEG_QUALITY = 92
PLATFORM_MAX_BYTES = 128 * 1024


class IdPhotoError(Exception):
    """
    No photo could be cropped.

    ---

    No se ha podido sacar la foto (documento ilegible, sin cara, sin
    credenciales de Google...).
    """


def _person_ct():
    return ContentType.objects.get_for_model(PersonIdentity)


def candidates(person):
    """
    Documents of the person a photo can come from, newest first.

    ---

    Documentos de la persona de los que puede salir la foto, del más
    reciente al más antiguo (por fecha de indexado).
    """
    return DocumentIndexEntry.objects.filter(
        domain_content_type=_person_ct(),
        domain_object_id=person.pk,
        entry_kind=DocumentIndexEntry.KIND_FILE,
        document_type__code__in=SOURCE_TYPES,
        deleted_at__isnull=True,
        purged_at__isnull=True,
    ).select_related("document_type").order_by("-indexed_at", "-pk")


def _pages(entry, data):
    """
    PIL images of the document: the image, or the first PDF pages.

    ---

    Imágenes del documento: la propia imagen, o las primeras páginas
    del PDF renderizadas.
    """
    from PIL import Image, ImageOps

    name = entry.name.lower()
    if name.endswith(".pdf"):
        import fitz

        pages = []
        with fitz.open(stream=data, filetype="pdf") as pdf:
            for index in range(min(PDF_PAGES, pdf.page_count)):
                pixmap = pdf[index].get_pixmap(dpi=PDF_DPI)
                pages.append(Image.open(
                    io.BytesIO(pixmap.tobytes("png")),
                ).convert("RGB"))
        return pages
    if name.endswith(IMAGE_EXTENSIONS):
        image = Image.open(io.BytesIO(data))
        return [ImageOps.exif_transpose(image).convert("RGB")]
    raise IdPhotoError("Formato no admitido: %s." % entry.name)


def _faces(image):
    """
    Faces found by Cloud Vision: (confidence, x0, y0, x1, y1).

    ---

    Caras que encuentra Cloud Vision en la imagen, con la caja ajustada
    a la cara (`fd_bounding_poly`).
    """
    from google.cloud import vision

    from ai_services.gemini_client import ensure_gcp_credentials

    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=90)
    ensure_gcp_credentials()
    client = vision.ImageAnnotatorClient()
    response = client.face_detection(
        image=vision.Image(content=buffer.getvalue()),
    )
    if response.error.message:
        raise IdPhotoError("Cloud Vision: %s" % response.error.message)
    faces = []
    for face in response.face_annotations:
        xs = [v.x for v in face.fd_bounding_poly.vertices]
        ys = [v.y for v in face.fd_bounding_poly.vertices]
        if xs and ys:
            faces.append((
                face.detection_confidence, min(xs), min(ys), max(xs),
                max(ys),
            ))
    return faces


def crop_box(face, width, height):
    """
    ID-photo box around a face, inside the image.

    ---

    Caja de foto de carné (3:4, cabeza y hombros) alrededor de la cara,
    sin salirse de la imagen.
    """
    _conf, x0, y0, x1, y1 = face
    face_w, face_h = x1 - x0, y1 - y0
    crop_w = min(face_w * CROP_WIDTH_PER_FACE, width)
    crop_h = min(crop_w * 4 / 3, height)
    crop_w = min(crop_w, crop_h * 3 / 4)
    left = (x0 + x1) / 2 - crop_w / 2
    top = y0 - face_h * CROP_TOP_PER_FACE
    left = max(0, min(left, width - crop_w))
    top = max(0, min(top, height - crop_h))
    return (
        int(left), int(top), int(left + crop_w), int(top + crop_h),
    )


def crop_photo(entry, data):
    """
    JPEG bytes of the ID photo cropped from a document.

    ---

    Foto de carné recortada del documento, en JPEG: la cara más grande
    con confianza suficiente de las páginas leídas.
    """
    best = None
    for image in _pages(entry, data):
        for face in _faces(image):
            if face[0] < MIN_CONFIDENCE:
                continue
            area = (face[3] - face[1]) * (face[4] - face[2])
            if best is None or area > best[0]:
                best = (area, image, face)
    if best is None:
        raise IdPhotoError("No se ve ninguna cara en %s." % entry.name)
    _area, image, face = best
    photo = image.crop(crop_box(face, *image.size))
    if photo.height > MAX_STORED_HEIGHT:
        photo = photo.resize((
            round(photo.width * MAX_STORED_HEIGHT / photo.height),
            MAX_STORED_HEIGHT,
        ))
    buffer = io.BytesIO()
    photo.save(buffer, format="JPEG", quality=STORED_JPEG_QUALITY)
    return buffer.getvalue()


def extract_from_entry(person, entry, data=None, manual=False):
    """
    Crop the photo of one document and store it as the person photo.

    ---

    Saca la foto de un documento concreto y la guarda como foto de la
    persona. Lanza IdPhotoError si no se puede.
    """
    from spare_parts.gcs_service import download_bytes

    if data is None:
        data = download_bytes(entry.bucket, entry.blob_name)
    image = crop_photo(entry, data)
    PersonIdPhoto.objects.update_or_create(
        person=person,
        defaults={"image": image, "source": entry, "is_manual": manual},
    )
    person.photo_attempted_at = timezone.now()
    person.save(update_fields=["photo_attempted_at"])
    logger.info(
        "# [ID-PHOTO] Foto de %s sacada de %s (%s).",
        person.pk, entry.pk, entry.name,
    )


def extract_for_person(person, limit=5):
    """
    Crop the photo from the newest document that has a face.

    ---

    Saca la foto del documento más reciente que tenga cara (DNI, NIE,
    pasaporte, permiso de conducir o imagen), probando como mucho
    `limit`. Devuelve el documento usado, o None si ninguno sirve; en
    los dos casos queda apuntada la fecha de búsqueda.
    """
    for entry in candidates(person)[:limit]:
        try:
            extract_from_entry(person, entry)
            return entry
        except IdPhotoError as exc:
            logger.info("# [ID-PHOTO] %s: %s", person.pk, exc)
        except Exception:  # noqa: BLE001 -- un documento roto no para
            logger.exception(
                "# [ID-PHOTO] Error con el documento %s.", entry.pk,
            )
    person.photo_attempted_at = timezone.now()
    person.save(update_fields=["photo_attempted_at"])
    return None


def box_pixels(box, width, height):
    """
    Pixel box of a fractional box, inside the image.

    ---

    Caja en píxeles de una caja en fracciones (x, y, ancho, alto),
    recortada a la imagen; IdPhotoError si queda vacía.
    """
    x, y, w, h = (min(max(float(v), 0.0), 1.0) for v in box)
    left, top = round(x * width), round(y * height)
    right = min(width, round((x + w) * width))
    bottom = min(height, round((y + h) * height))
    if right - left < 8 or bottom - top < 8:
        raise IdPhotoError("El recuadro marcado es demasiado pequeño.")
    return left, top, right, bottom


def persons_to_check(limit):
    """
    Persons with a source document indexed after their last search.

    ---

    Personas con algún documento del que puede salir la foto indexado
    después de su última búsqueda (o nunca buscadas), activas primero.
    """
    from django.db.models import Exists, F, OuterRef, Q

    newer = candidates_for_any_person().filter(
        domain_object_id=OuterRef("pk"),
        indexed_at__gt=OuterRef("photo_attempted_at"),
    )
    pending = PersonIdentity.objects.annotate(
        has_newer=Exists(newer),
        has_any=Exists(candidates_for_any_person().filter(
            domain_object_id=OuterRef("pk"),
        )),
    ).filter(
        Q(photo_attempted_at__isnull=True, has_any=True)
        | Q(has_newer=True),
    ).exclude(
        # A photo put by hand is never replaced automatically.
        # Una foto puesta a mano nunca se cambia sola.
        id_photo__is_manual=True,
    ).order_by(F("is_active_employee").desc(), "pk")
    return list(pending[:limit])


def candidates_for_any_person():
    """
    Source documents of any person.

    ---

    Documentos de los que puede salir la foto, de cualquier persona.
    """
    return DocumentIndexEntry.objects.filter(
        domain_content_type=_person_ct(),
        entry_kind=DocumentIndexEntry.KIND_FILE,
        document_type__code__in=SOURCE_TYPES,
        deleted_at__isnull=True,
        purged_at__isnull=True,
    )


def save_uploaded(person, data):
    """
    Store an uploaded profile photo as it is, without reading it.

    ---

    Guarda una foto de perfil subida a mano tal cual, sin leerla ni
    buscar la cara (Miguel Ángel, S134: *"La foto no tiene por qué
    leerla [...] lo que queremos es que sea lo más rápido posible"*).
    Solo se endereza (EXIF), se pasa a JPEG y se limita su tamaño. Queda
    marcada como puesta a mano: la búsqueda automática ya no la cambia.
    """
    from PIL import Image, ImageOps, UnidentifiedImageError

    try:
        image = ImageOps.exif_transpose(Image.open(io.BytesIO(data)))
    except (UnidentifiedImageError, OSError) as exc:
        raise IdPhotoError("El archivo no es una imagen.") from exc
    image = image.convert("RGB")
    if image.height > MAX_STORED_HEIGHT:
        image = image.resize((
            round(image.width * MAX_STORED_HEIGHT / image.height),
            MAX_STORED_HEIGHT,
        ))
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=STORED_JPEG_QUALITY)
    PersonIdPhoto.objects.update_or_create(
        person=person, defaults={
            "image": buffer.getvalue(), "source": None, "is_manual": True,
        },
    )
    person.photo_attempted_at = timezone.now()
    person.save(update_fields=["photo_attempted_at"])


def platform_png(image_bytes, box=None, max_bytes=PLATFORM_MAX_BYTES):
    """
    PNG of the photo (or of a box of it) under `max_bytes`.

    ---

    PNG de la foto de menos de `max_bytes` (128 KB), para subirla a
    otras plataformas: se reduce de tamaño y, si hace falta, se pasa a
    256 colores hasta que cabe. `box` = (x, y, ancho, alto) en
    fracciones de 0 a 1 de la foto tal como se ve: el recuadro que
    marca el usuario para que la cara ocupe la mayor parte (Miguel
    Ángel, S134: *"la plataforma pide que salga la cara principalmente
    y que la cara ocupe la máxima cantidad posible en la foto"*).
    """
    from PIL import Image, ImageOps

    image = ImageOps.exif_transpose(
        Image.open(io.BytesIO(image_bytes)),
    ).convert("RGB")
    if box is not None:
        image = image.crop(box_pixels(box, *image.size))
    width, height = image.size
    scale = 1.0
    for _attempt in range(30):
        size = (max(1, round(width * scale)), max(1, round(height * scale)))
        candidate = image.resize(size) if scale < 1 else image
        for quantize in (False, True):
            frame = candidate.quantize(256) if quantize else candidate
            buffer = io.BytesIO()
            frame.save(buffer, format="PNG", optimize=True)
            if buffer.tell() <= max_bytes:
                return buffer.getvalue()
        scale *= 0.85
    raise IdPhotoError("No se ha podido dejar la foto en menos de 128 KB.")
