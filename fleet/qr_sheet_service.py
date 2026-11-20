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
MIN_PASSWORD_LENGTH = 6


def set_editor_password(company, raw_password, user):
    """
    Set (or change) the QR editor password of the company.

    ---

    Fija o cambia la contraseña del editor de fichas QR de la empresa
    (se guarda cifrada). Al cambiarla, quien ya estaba dentro sigue
    hasta que caduque su acceso (8 h).
    """
    from django.contrib.auth.hashers import make_password

    from fleet.models import QrEditorSettings

    raw_password = (raw_password or "").strip()
    if len(raw_password) < MIN_PASSWORD_LENGTH:
        raise QrSheetError("La contraseña necesita al menos %d caracteres."
                           % MIN_PASSWORD_LENGTH)
    settings_row, _created = QrEditorSettings.objects.get_or_create(
        company=company)
    settings_row.password_hash = make_password(raw_password)
    settings_row.updated_by = user
    settings_row.save()
    return settings_row


def editor_password_set(company):
    """
    Whether the company has a QR editor password.

    ---

    Si la empresa tiene contraseña para el editor de fichas QR.
    """
    from fleet.models import QrEditorSettings

    return QrEditorSettings.objects.filter(
        company=company).exclude(password_hash="").exists()


def editor_unlocked(request):
    """
    Whether this browser entered the QR editor password recently.

    ---

    Si este navegador metió la contraseña del editor hace menos de 8 h.
    """
    from django.utils import timezone

    until = request.session.get(EDITOR_SESSION_KEY)
    return bool(until) and until > timezone.now().timestamp()


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
    return True, ""
