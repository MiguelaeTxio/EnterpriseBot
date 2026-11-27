# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/fleet/qr_sheet_service.py
"""
H23 (S154, invasora) -- QR sheet of each cost centre.

---

H23 (S154, invasora) -- ficha QR de cada centro de gasto. Miguel Ángel:
"Código QR por cada uno de los centros de gasto [...] una especie de
ficha técnica donde nos va a decir si el camión pasa la revisión por
hora [...] algún tipo de observación escrita [...] algún vídeo o varios
vídeos explicativos, fotos". Aquí: crear la ficha, subir y quitar fotos
y vídeos (cubo de fotos de tareas, prefijo fichas_qr/), el contexto de
la página pública y la imagen del QR (segno).
"""
import io
import logging
import os
import uuid

from django.urls import reverse

from fleet.models import MachineQrMedia, MachineQrSheet

logger = logging.getLogger(__name__)

MEDIA_PREFIX = "fichas_qr"
MAX_PHOTO_BYTES = 25 * 1024 * 1024
MAX_VIDEO_BYTES = 150 * 1024 * 1024


class QrSheetError(Exception):
    """
    Error handling a QR sheet (message for the user).

    ---

    Error al tratar una ficha QR (mensaje para el usuario).
    """


def sheet_for(machine):
    """
    The QR sheet of the machine, created if it does not exist.

    ---

    La ficha QR del centro de gasto; se crea si no existe (su
    identificador, y por tanto el QR, ya no cambia).
    """
    sheet, _created = MachineQrSheet.objects.get_or_create(machine=machine)
    return sheet


def public_url(request, sheet):
    """
    Absolute URL the QR points to.

    ---

    La dirección completa a la que lleva el QR.
    """
    return request.build_absolute_uri(
        reverse("fleet_qr_public", kwargs={"token": sheet.token}))


def qr_image(url, kind="svg", scale=10):
    """
    The QR code of a URL as SVG text or PNG bytes.

    ---

    El código QR de una dirección, en SVG (para la pantalla) o PNG (para
    imprimir), con corrección de errores alta (resiste pegatinas sucias).
    """
    import segno

    qr = segno.make(url, error="h")
    buffer = io.BytesIO()
    if kind == "png":
        qr.save(buffer, kind="png", scale=scale, border=2)
        return buffer.getvalue()
    qr.save(buffer, kind="svg", scale=scale, border=2, xmldecl=False,
            svgns=True)
    return buffer.getvalue().decode("utf-8")


def sticker_png(url, code):
    """
    The QR sticker as PNG: the QR with the vehicle code below it.

    ---

    S163 (25/11, Miguel Ángel: «debe de verse en la pegatina el código
    del vehículo»): la pegatina en PNG, el QR y debajo el código del
    centro de gasto en grande, sobre blanco.
    """
    from PIL import Image, ImageDraw, ImageFont

    qr_img = Image.open(io.BytesIO(qr_image(url, "png", scale=20))).convert(
        "RGB")
    width = qr_img.width
    size = max(40, width // 7)
    font = None
    for path in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                 "/usr/share/fonts/truetype/liberation/"
                 "LiberationSans-Bold.ttf"):
        try:
            font = ImageFont.truetype(path, size)
            break
        except OSError:
            continue
    if font is None:
        font = ImageFont.load_default(size=size)
    draw = ImageDraw.Draw(qr_img)
    box = draw.textbbox((0, 0), code, font=font)
    text_w, text_h = box[2] - box[0], box[3] - box[1]
    while text_w > width * 0.92 and size > 12:
        size -= 4
        font = font.font_variant(size=size) if hasattr(
            font, "font_variant") else font
        box = draw.textbbox((0, 0), code, font=font)
        text_w, text_h = box[2] - box[0], box[3] - box[1]
    pad = size // 2
    sticker = Image.new("RGB", (width, qr_img.height + text_h + pad * 2),
                        "white")
    sticker.paste(qr_img, (0, 0))
    ImageDraw.Draw(sticker).text(
        ((width - text_w) // 2 - box[0], qr_img.height + pad - box[1]),
        code, fill="black", font=font)
    out = io.BytesIO()
    sticker.save(out, format="PNG")
    return out.getvalue()


def add_media(sheet, upload, caption, user):
    """
    Store an uploaded photo or video in GCS and register it.

    ---

    Guarda en GCS una foto o un vídeo subido y lo apunta en la ficha, al
    final. Solo imágenes y vídeos; fotos hasta 25 MB y vídeos hasta
    150 MB.
    """
    from spare_parts.gcs_service import TASK_PHOTOS_BUCKET, upload_bytes

    content_type = (upload.content_type or "").lower()
    if content_type.startswith("image/"):
        kind, limit = MachineQrMedia.KIND_PHOTO, MAX_PHOTO_BYTES
    elif content_type.startswith("video/"):
        kind, limit = MachineQrMedia.KIND_VIDEO, MAX_VIDEO_BYTES
    else:
        raise QrSheetError(
            "«%s» no es una foto ni un vídeo." % upload.name)
    if upload.size > limit:
        raise QrSheetError("«%s» pasa de %d MB." % (
            upload.name, limit // (1024 * 1024)))
    extension = os.path.splitext(upload.name)[1].lower()[:10]
    blob_name = "%s/%s/%s%s" % (
        MEDIA_PREFIX, sheet.machine.code, uuid.uuid4().hex, extension)
    upload_bytes(TASK_PHOTOS_BUCKET, blob_name, upload.read(),
                 content_type=content_type)
    last = sheet.media.order_by("-position").first()
    media = MachineQrMedia.objects.create(
        sheet=sheet, kind=kind, caption=(caption or "").strip()[:300],
        bucket=TASK_PHOTOS_BUCKET, blob_name=blob_name,
        content_type=content_type, size=upload.size,
        position=(last.position + 1) if last else 0, created_by=user,
    )
    logger.info("# [qr_sheet] %s: %s subido (%s, %d bytes)",
                sheet.machine.code, kind, blob_name, upload.size)
    return media


def delete_media(media):
    """
    Remove a photo or video from the sheet and from GCS.

    ---

    Quita una foto o un vídeo de la ficha y de GCS.
    """
    from spare_parts.gcs_service import delete_file

    try:
        delete_file(media.bucket, media.blob_name)
    except Exception:  # noqa: BLE001 -- el registro se quita igual
        logger.exception("# [qr_sheet] no se pudo borrar %s",
                         media.blob_name)
    media.delete()


def media_rows(sheet):
    """
    The sheet's photos and videos with a temporary URL to show them.

    ---

    Las fotos y vídeos de la ficha con una dirección temporal (30 min)
    para verlos.
    """
    from spare_parts.gcs_service import generate_signed_url

    rows = []
    for media in sheet.media.all():
        rows.append({
            "media": media,
            "is_video": media.kind == MachineQrMedia.KIND_VIDEO,
            "url": generate_signed_url(media.bucket, media.blob_name),
        })
    return rows


def service_lines(machine):
    """
    How the machine's service is counted, in plain words.

    ---

    Cómo se cuenta la revisión del centro de gasto, en palabras: por
    horas de motor, por km y, si tiene, por horas de grúa (plan de
    revisiones de la ficha, H30).
    """
    lines = []
    # S154 (27/11): qué contadores tiene que anotar quien reposta o hace
    # el parte, según la toma de datos del QR.
    counters = [name for flag, name in (
        (machine.has_odometer, "kilómetros"),
        (machine.has_engine_hours, "horas de motor"),
        (machine.has_crane_hours, "horas de grúa"),
    ) if flag]
    if counters:
        text = (", ".join(counters[:-1]) + " y " + counters[-1]
                if len(counters) > 1 else counters[0])
        lines.append("Contadores que se anotan: %s." % text)
    if machine.service_hours_interval:
        lines.append("Revisión por horas de motor: cada %d h." %
                     machine.service_hours_interval)
    if machine.service_every_km:
        lines.append("Revisión por kilómetros: cada %s km." % (
            "{:,}".format(machine.service_every_km).replace(",", ".")))
    if machine.has_crane_hours and machine.service_crane_hours_interval:
        lines.append("Revisión de la grúa por horas: cada %d h." %
                     machine.service_crane_hours_interval)
    if not lines:
        lines.append("Sin plan de revisiones en la ficha.")
    return lines


def _hours_interval(raw):
    """
    800, 1200 or None from a form value; QrSheetError if invalid.

    ---

    800, 1200 o nada a partir de lo marcado.
    """
    raw = (raw or "").strip()
    if not raw:
        return None
    if raw not in ("800", "1200"):
        raise QrSheetError("La revisión por horas es a las 800 o a las "
                           "1200.")
    return int(raw)


def _whole_number(raw, label):
    """
    A positive whole number from a form value, or None if empty.

    ---

    Un número entero positivo (admite puntos de miles) o nada.
    """
    raw = (raw or "").strip().replace(".", "").replace(" ", "")
    if not raw:
        return None
    if not raw.isdigit() or int(raw) <= 0:
        raise QrSheetError("%s: pon un número entero." % label)
    return int(raw)


def save_service_setup(machine, data):
    """
    Save counters and service plan from the QR data form.

    ---

    S154 (27/11), Miguel Ángel: «casilleros para indicar si pasa la
    revisión a las 800 horas, a las 1200, si la pasa por X kilómetros
    [...] dependiendo si tiene grúas». Guarda en la ficha del centro de
    gasto qué contadores tiene (km, horas de motor, horas de grúa) y su
    revisión: horas (800/1200), cada N km y, con grúa, la de la grúa.
    Lo mismo que se cambia en la pestaña Ficha. `data`: request.POST.
    """
    has_odometer = data.get("has_odometer") == "1"
    has_engine_hours = data.get("has_engine_hours") == "1"
    has_crane_hours = data.get("has_crane_hours") == "1"
    hours = _hours_interval(data.get("service_hours"))
    crane = _hours_interval(data.get("service_crane_hours"))
    every_km = _whole_number(data.get("service_km"),
                             "Revisión por kilómetros")
    if not has_crane_hours:
        crane = None
    machine.has_odometer = has_odometer
    machine.has_engine_hours = has_engine_hours
    machine.has_crane_hours = has_crane_hours
    machine.service_hours_interval = hours
    machine.service_crane_hours_interval = crane
    machine.service_every_km = every_km
    machine.save(update_fields=[
        "has_odometer", "has_engine_hours", "has_crane_hours",
        "service_hours_interval", "service_crane_hours_interval",
        "service_every_km",
    ])


def set_real_counters(machine, data, company_user):
    """
    Store the machine's real counters now; refuels count from them.

    ---

    S154 (27/11), Miguel Ángel: «un botón para actualizar los
    contadores [...] los valores reales que tiene ahora mismo para que
    conste como la lectura real y correcta, y a partir de ahí se
    controlen los repostajes». Guarda una lectura «Contadores
    actualizados» con lo que marcan ahora (km, horas de motor, horas de
    grúa) y rehace la serie de sus repostajes desde ella: los de antes
    ya no cuentan. Devuelve el mensaje.
    """
    from django.utils import timezone

    from fleet.gasoges_sync import recheck_series
    from fleet.models import GasoGesVehicle, MachineMeterReading

    km = _whole_number(data.get("km"), "Kilómetros")
    hours = _whole_number(data.get("hours"), "Horas de motor")
    crane = _whole_number(data.get("crane_hours"), "Horas de grúa")
    if km is None and hours is None and crane is None:
        raise QrSheetError("Pon lo que marca ahora al menos un contador.")
    MachineMeterReading.objects.create(
        machine=machine,
        reading_date=timezone.localdate(),
        km=km, hours=hours, crane_hours=crane,
        source=MachineMeterReading.SOURCE_REAL,
        created_by=company_user,
    )
    units = set(GasoGesVehicle.objects.filter(machine=machine).exclude(
        unit=GasoGesVehicle.UNIT_UNKNOWN).values_list("unit", flat=True))
    for unit in units:
        if (unit == GasoGesVehicle.UNIT_KM and km is not None) or (
                unit == GasoGesVehicle.UNIT_HOURS and hours is not None):
            recheck_series(machine, unit)
    parts = []
    if km is not None:
        parts.append("{:,} km".format(km).replace(",", "."))
    if hours is not None:
        parts.append("{:,} h de motor".format(hours).replace(",", "."))
    if crane is not None:
        parts.append("{:,} h de grúa".format(crane).replace(",", "."))
    return ("Contadores actualizados: %s. Los repostajes se controlan a "
            "partir de aquí." % ", ".join(parts))


def last_real_counters(machine):
    """
    The machine's last real counters reading, or None.

    ---

    La última lectura de contadores actualizados del centro de gasto.
    """
    from fleet.models import MachineMeterReading

    return MachineMeterReading.objects.filter(
        machine=machine, source=MachineMeterReading.SOURCE_REAL,
    ).order_by("-created_at").first()


def spec_rows(machine):
    """
    The technical specifications to show, only those with a value.

    ---

    Las especificaciones técnicas que se muestran, solo las que tienen
    dato.
    """
    def metres(value):
        return ("%.2f m" % (value / 1000)).replace(".", ",")

    rows = [
        ("Marca y modelo", machine.brand_model),
        ("Matrícula", machine.plate),
        ("Capacidad de elevación", (
            "%s t" % ("%g" % machine.capacity_tonnes).replace(".", ",")
            if machine.capacity_tonnes is not None else "")),
        ("Momento de carga", (
            "%s t·m" % ("%g" % machine.capacity_tm).replace(".", ",")
            if machine.capacity_tm is not None else "")),
        ("Masa máxima autorizada", (
            "%s kg" % "{:,}".format(machine.max_authorized_mass_kg)
            .replace(",", ".") if machine.max_authorized_mass_kg else "")),
        ("Masa", (
            "%s kg" % "{:,}".format(machine.mass_kg).replace(",", ".")
            if machine.mass_kg else "")),
        ("Ejes", machine.axle_count or ""),
        ("Largo", metres(machine.length_mm) if machine.length_mm else ""),
        ("Ancho", metres(machine.width_mm) if machine.width_mm else ""),
        ("Alto", metres(machine.height_mm) if machine.height_mm else ""),
        ("Año", machine.manufacture_year or ""),
    ]
    return [(label, value) for label, value in rows if value]


# ------------------------------------------------------------------------
# S154: editor de fichas QR dentro de la aplicación de fichaje, con una
# contraseña propia (no la del usuario).
# ------------------------------------------------------------------------
EDITOR_SESSION_KEY = "qr_editor_until"
EDITOR_SESSION_HOURS = 8
EDITOR_MAX_ATTEMPTS = 5
EDITOR_ATTEMPTS_KEY = "qr_editor_attempts"
# S154 (27/11): huella de la contraseña con la que se entró; si la
# oficina la cambia, deja de valer y se vuelve a pedir.
EDITOR_FINGERPRINT_KEY = "qr_editor_fingerprint"
MIN_PASSWORD_LENGTH = 6


def set_editor_password(company, raw_password, user):
    """
    Set (or change) the QR editor password of the company.

    ---

    Fija o cambia la contraseña del editor de fichas QR de la empresa
    (se guarda cifrada). Al cambiarla, quien ya estaba dentro tiene que
    volver a meterla (S154, 27/11: `editor_unlocked` compara la huella).
    """
    from django.contrib.auth.hashers import make_password

    from fleet.models import QrEditorSettings

    raw_password = (raw_password or "").strip()
    if len(raw_password) < MIN_PASSWORD_LENGTH:
        raise QrSheetError("La contraseña necesita al menos %d caracteres."
                           % MIN_PASSWORD_LENGTH)
    settings_row, _created = QrEditorSettings.objects.get_or_create(
        company=company)
    from document_explorer.confidential import encrypt

    settings_row.password_hash = make_password(raw_password)
    settings_row.password_encrypted = encrypt(
        raw_password.encode()).decode()
    settings_row.updated_by = user
    settings_row.save()
    return settings_row


def editor_password_plain(company):
    """
    The QR editor password, readable (S163), or "" if unknown.

    ---

    La contraseña del editor QR en claro, para la nueva interfaz. Las
    puestas antes de S163 solo tienen el hash: "" (hay que volver a
    ponerla para poder verla).
    """
    from document_explorer.confidential import ConfidentialError, decrypt

    from fleet.models import QrEditorSettings

    row = QrEditorSettings.objects.filter(company=company).first()
    if row is None or not row.password_encrypted:
        return ""
    try:
        return decrypt(row.password_encrypted.encode()).decode()
    except ConfidentialError:
        return ""


def editor_password_set(company):
    """
    Whether the company has a QR editor password.

    ---

    Si la empresa tiene contraseña para el editor de fichas QR.
    """
    from fleet.models import QrEditorSettings

    return QrEditorSettings.objects.filter(
        company=company).exclude(password_hash="").exists()


def _password_fingerprint(company):
    """
    A short fingerprint of the current editor password ("" if none).

    ---

    Huella de la contraseña actual del editor (no la contraseña): sirve
    para saber si ha cambiado desde que se entró.
    """
    import hashlib

    from fleet.models import QrEditorSettings

    row = QrEditorSettings.objects.filter(company=company).first()
    if row is None or not row.password_hash:
        return ""
    return hashlib.sha256(row.password_hash.encode()).hexdigest()[:16]


def editor_unlocked(request, company):
    """
    Whether this browser entered the current QR editor password.

    ---

    Si este navegador metió la contraseña del editor hace menos de 8 h y
    sigue siendo la misma (S154, 27/11: si la oficina la cambia, se
    vuelve a pedir).
    """
    from django.utils import timezone

    until = request.session.get(EDITOR_SESSION_KEY)
    if not until or until <= timezone.now().timestamp():
        return False
    current = _password_fingerprint(company)
    return bool(current) and (
        request.session.get(EDITOR_FINGERPRINT_KEY) == current)


def lock_editor(request):
    """
    Close the QR editor in this browser.

    ---

    Cierra el editor en este navegador: hay que volver a meter la
    contraseña (S154, 27/11: se pide cada vez que se entra desde el
    fichaje).
    """
    request.session.pop(EDITOR_SESSION_KEY, None)
    request.session.pop(EDITOR_FINGERPRINT_KEY, None)


def unlock_editor(request, company, raw_password):
    """
    Check the password and open the editor for 8 hours.

    ---

    Comprueba la contraseña y abre el editor 8 horas en este navegador.
    Tras 5 intentos fallidos seguidos queda bloqueado en esta sesión.
    Devuelve (abierto, mensaje).
    """
    from django.contrib.auth.hashers import check_password
    from django.utils import timezone

    from fleet.models import QrEditorSettings

    attempts = request.session.get(EDITOR_ATTEMPTS_KEY, 0)
    if attempts >= EDITOR_MAX_ATTEMPTS:
        return False, ("Demasiados intentos fallidos. Pide la contraseña "
                       "a la oficina.")
    settings_row = QrEditorSettings.objects.filter(company=company).first()
    if settings_row is None or not settings_row.password_hash:
        return False, "La oficina todavía no ha puesto la contraseña."
    if not check_password((raw_password or "").strip(),
                          settings_row.password_hash):
        request.session[EDITOR_ATTEMPTS_KEY] = attempts + 1
        return False, "Contraseña incorrecta."
    request.session[EDITOR_ATTEMPTS_KEY] = 0
    request.session[EDITOR_SESSION_KEY] = (
        timezone.now().timestamp() + EDITOR_SESSION_HOURS * 3600)
    request.session[EDITOR_FINGERPRINT_KEY] = _password_fingerprint(company)
    return True, ""
