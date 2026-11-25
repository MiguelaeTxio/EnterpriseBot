# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/hr_calendar/payslip_delivery.py
"""
H24 (S149 invasora). Payslip delivery: read, review and send.

---

Entrega de nóminas. Miguel Ángel (S149): "cuando pulse el botón de
entrega de nóminas, elija una carpeta, cargue todos los documentos PDF
que haya en esa carpeta y el sistema tiene que leer cada nómina y
enviarla por WhatsApp a los destinatarios [...] lectura en segundo
plano [...] cuando se hayan terminado de leer, se avisa por WhatsApp al
supervisor que haya iniciado la entrega [...] se presenta un listado
con las nóminas que se van a enviar para dar el visto bueno [...] una
vez se acepta el listado, se envía."

1. Subida (`stage_file`): cada PDF se guarda cifrado (la misma llave de
   los documentos confidenciales) en una carpeta privada del servidor,
   fuera del cubo y de la carpeta del trabajador, hasta el envío.
2. Lectura (`read_batch`, en Celery): solo el texto que lleva el propio
   PDF, aquí mismo (PyMuPDF). Las nóminas son confidenciales (S147): no
   pasan por Cloud Vision ni Gemini y el texto no se guarda. Por cada
   página, el DNI/NIE con letra válida de un trabajador de la empresa;
   las páginas seguidas del mismo trabajador son una nómina (un PDF
   puede traer las de toda la plantilla) y una página sin DNI sigue a
   la anterior. El mes, del periodo de la nómina. Lo que no se puede
   asignar queda "Sin trabajador" para ponerlo a mano. Al acabar, aviso
   por WhatsApp a quien inició la entrega.
3. Visto bueno: el supervisor revisa el listado (cambia el trabajador o
   deja una nómina fuera) y acepta.
4. Envío (`send_batch`, en Celery): cada nómina se archiva en la ficha
   del trabajador como cualquier nómina (tipo NOMINA, confidencial,
   cifrada, con quien da el visto bueno como remitente) y se le manda
   el PDF por WhatsApp. Twilio recoge el PDF de un enlace temporal
   (`media_token`, caduca a las pocas horas) que solo sirve esa nómina.

S153 -- quién la ve y no son efímeras (Miguel Ángel: "no pueden ser
efímeras [...] la persona que recibe las nóminas puede tenerlas como
archivo, buscarlas por fecha, por periodos"): quien sube la entrega la
comparte con los supervisores que deban enviarla
(hr_calendar/payslip_access.py), a los que se avisa por WhatsApp en
cuanto está leída; la copia cifrada de la subida ya NO se borra al
enviar (solo al anular la entrega), para poder descargar cualquier
nómina más adelante, también las que se dejaron fuera.
"""
import datetime
import io
import logging
import os
import re
import secrets
import unicodedata

from django.conf import settings
from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)

STAGING_DIR = os.path.join(settings.BASE_DIR, "private", "payslips")
MAX_FILE_BYTES = 40 * 1024 * 1024
MEDIA_HOURS = 6
BATCH_READY_TEMPLATE = "payslip_batch_ready"
DELIVERY_TEMPLATE = "payslip_delivery"
PAYSLIP_TYPE_CODE = "NOMINA"

DNI_LETTERS = "TRWAGMYFPDXBNJZSQVHLCKE"
_DNI_RE = re.compile(r"(?<![A-Z0-9])([XYZ]?\d{7,8})[ -]?([A-Z])(?![A-Z0-9])")
MONTHS = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
          "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
_MONTH_ABBR = {"ENE": 1, "FEB": 2, "MAR": 3, "ABR": 4, "MAY": 5, "JUN": 6,
               "JUL": 7, "AGO": 8, "SEP": 9, "SET": 9, "OCT": 10,
               "NOV": 11, "DIC": 12}
_NUM_RANGE = re.compile(
    r"(\d{1,2})[/.-](\d{1,2})[/.-](\d{2,4})\s*(?:A|AL|HASTA|-)\s*"
    r"(\d{1,2})[/.-](\d{1,2})[/.-](\d{2,4})")
_ABBR_RANGE = re.compile(
    r"(\d{1,2})\s+(ENE|FEB|MAR|ABR|MAY|JUN|JUL|AGO|SEP|SET|OCT|NOV|DIC)"
    r"[A-Z]*\.?\s+(\d{2,4})\s*(?:A|AL|HASTA|-)\s*(\d{1,2})\s+"
    r"(ENE|FEB|MAR|ABR|MAY|JUN|JUL|AGO|SEP|SET|OCT|NOV|DIC)[A-Z]*\.?\s+"
    r"(\d{2,4})")
_MONTH_YEAR = re.compile(
    r"(ENERO|FEBRERO|MARZO|ABRIL|MAYO|JUNIO|JULIO|AGOSTO|SEPTIEMBRE|"
    r"SETIEMBRE|OCTUBRE|NOVIEMBRE|DICIEMBRE)\s+(?:DE\s+)?(\d{4})")
_EXTRA = re.compile(r"PAGA\s+EXTRA|P\.\s*EXTRA|PAGA\s+EXTRAORDINARIA")


class PayslipError(Exception):
    """
    A delivery step cannot be done (message for the supervisor).
    ---
    No se puede hacer un paso de la entrega (mensaje para el supervisor).
    """


# ----------------------------------------------------------------------
# Lectura
# ----------------------------------------------------------------------

def _plain(text):
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(c for c in text if not unicodedata.combining(c))
    # 12.345.678-Z -> 12345678-Z
    text = re.sub(r"(?<=\d)\.(?=\d)", "", text.upper())
    return text


def normalize_dni(raw):
    """
    The DNI/NIE as stored in PersonIdentity (upper, no separators).
    ---
    El DNI/NIE como se guarda en la ficha: mayúsculas, sin espacios ni
    guiones ni puntos.
    """
    return re.sub(r"[^A-Z0-9]", "", (raw or "").upper())


def valid_dni(number, letter):
    """
    True if the control letter of a DNI/NIE is right.
    ---
    True si la letra de control del DNI/NIE es la buena (así no se
    confunde con otros números de la nómina).
    """
    if number[0] in "XYZ":
        if len(number) != 8:
            return False
        number = str("XYZ".index(number[0])) + number[1:]
    elif len(number) != 8:
        return False
    return DNI_LETTERS[int(number) % 23] == letter


def dnis_in(text):
    """
    The valid DNI/NIE numbers in a text, in order, without repeats.
    ---
    Los DNI/NIE con letra válida que aparecen en un texto.
    """
    found = []
    for number, letter in _DNI_RE.findall(_plain(text)):
        dni = number + letter
        if valid_dni(number, letter) and dni not in found:
            found.append(dni)
    return found


def _year(raw):
    year = int(raw)
    return year + 2000 if year < 100 else year


def _safe_date(year, month, day):
    try:
        return datetime.date(year, month, day)
    except ValueError:
        return None


def _month_end(year, month):
    following = datetime.date(year + month // 12, month % 12 + 1, 1)
    return following - datetime.timedelta(days=1)


def find_period(text):
    """
    (start, end, label) of the payslip period, or (None, None, "").
    ---
    El periodo de la nómina: un intervalo de fechas ("01/10/2026 a
    31/10/2026", "01 OCT 26 a 31 OCT 26") o un mes con su año
    ("OCTUBRE 2026"). La etiqueta es el mes del final del periodo
    ("Octubre 2026"), con "Paga extra" delante si lo pone.
    """
    plain = _plain(text)
    start = end = None
    match = _NUM_RANGE.search(plain)
    if match:
        d1, m1, y1, d2, m2, y2 = match.groups()
        start = _safe_date(_year(y1), int(m1), int(d1))
        end = _safe_date(_year(y2), int(m2), int(d2))
    if end is None:
        match = _ABBR_RANGE.search(plain)
        if match:
            d1, m1, y1, d2, m2, y2 = match.groups()
            start = _safe_date(_year(y1), _MONTH_ABBR[m1], int(d1))
            end = _safe_date(_year(y2), _MONTH_ABBR[m2], int(d2))
    if end is None:
        match = _MONTH_YEAR.search(plain)
        if match:
            name, year = match.groups()
            month = (9 if name == "SETIEMBRE"
                     else MONTHS.index(name.lower()) + 1)
            start = datetime.date(int(year), month, 1)
            end = _month_end(int(year), month)
    if end is None:
        return None, None, ""
    label = "%s %s" % (MONTHS[end.month - 1].capitalize(), end.year)
    if _EXTRA.search(plain):
        label = "Paga extra " + label
    return start, end, label


def _people_by_dni(company):
    from document_explorer.models import PersonIdentity

    people = PersonIdentity.objects.filter(company=company).exclude(dni="")
    return {normalize_dni(p.dni): p for p in people}


def split_pages(page_texts, people):
    """
    The payslips of one PDF: [(first page, last page, person, dni, text)].
    ---
    Reparte las páginas de un PDF en nóminas (páginas 1-based): una
    página con el DNI/NIE de un trabajador empieza la nómina de ese
    trabajador (o sigue la suya si es el mismo); una página sin ninguno
    sigue a la anterior. Si una página trae DNI/NIE válidos pero de
    nadie de la empresa, se guarda el primero para que el supervisor
    sepa cuál era.
    """
    groups = []
    for number, text in enumerate(page_texts, start=1):
        dnis = dnis_in(text)
        known = [d for d in dnis if d in people]
        key = known[0] if known else (dnis[0] if dnis else None)
        if groups and (key is None or key == groups[-1]["dni"]):
            groups[-1]["last"] = number
            groups[-1]["text"] += "\n" + text
            continue
        groups.append({"first": number, "last": number, "dni": key or "",
                       "person": people.get(key) if key else None,
                       "text": text})
    return [(g["first"], g["last"], g["person"], g["dni"], g["text"])
            for g in groups]


# ----------------------------------------------------------------------
# Copias cifradas hasta el envío
# ----------------------------------------------------------------------

def _staged_abs(relative):
    path = os.path.realpath(os.path.join(STAGING_DIR, relative))
    if not path.startswith(os.path.realpath(STAGING_DIR) + os.sep):
        raise PayslipError("Ruta de la copia no válida.")
    return path


def stage_file(batch, filename, data):
    """
    Keeps an uploaded PDF encrypted until it is sent. Returns its item.
    ---
    Guarda cifrado uno de los PDF de la carpeta y crea su nómina "Por
    leer" (la lectura la reparte luego en una o varias).
    """
    from document_explorer.confidential import ConfidentialError, encrypt
    from hr_calendar.models import PayslipItem

    if not data:
        raise PayslipError("%s está vacío." % filename)
    if len(data) > MAX_FILE_BYTES:
        raise PayslipError("%s pasa de 40 MB." % filename)
    if not data.startswith(b"%PDF"):
        raise PayslipError("%s no es un PDF." % filename)
    try:
        sealed = encrypt(data)
    except ConfidentialError as exc:
        raise PayslipError(str(exc)) from exc
    relative = os.path.join(str(batch.pk), "%s.bin" % secrets.token_hex(12))
    path = _staged_abs(relative)
    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    with open(path, "wb") as handle:
        handle.write(sealed)
    return PayslipItem.objects.create(
        batch=batch, original_name=filename[:255], staged_path=relative,
    )


def staged_bytes(item):
    """
    The original bytes of the uploaded PDF of an item.
    ---
    Los bytes del PDF subido de una nómina (descifrados).
    """
    from document_explorer.confidential import decrypt

    with open(_staged_abs(item.staged_path), "rb") as handle:
        return decrypt(handle.read())


def item_pdf(item):
    """
    The PDF of just this payslip (its pages of the uploaded file).
    ---
    El PDF de esta nómina sola: sus páginas del PDF subido.
    """
    import fitz

    data = staged_bytes(item)
    with fitz.open(stream=data, filetype="pdf") as source:
        if item.page_from == 1 and item.page_to in (0, source.page_count):
            return data
        out = fitz.open()
        out.insert_pdf(source, from_page=item.page_from - 1,
                       to_page=(item.page_to or source.page_count) - 1)
        buffer = io.BytesIO()
        out.save(buffer, garbage=3, deflate=True)
        out.close()
        return buffer.getvalue()


# ----------------------------------------------------------------------
# Paso 2: lectura en segundo plano
# ----------------------------------------------------------------------

def read_batch(batch):
    """
    Reads every uploaded PDF of the batch and notifies who started it.
    ---
    Lee todos los PDF subidos de la entrega (texto del propio PDF, sin
    servicios externos), los reparte en nóminas con su trabajador y su
    mes, deja la entrega "Para el visto bueno" y avisa por WhatsApp a
    quien la inició.
    """
    import fitz

    from hr_calendar.models import PayslipBatch, PayslipItem

    people = _people_by_dni(batch.company)
    for item in list(batch.items.filter(status=PayslipItem.Status.PENDING)):
        try:
            data = staged_bytes(item)
            with fitz.open(stream=data, filetype="pdf") as pdf:
                texts = [page.get_text() for page in pdf]
        except Exception as exc:  # PDF roto o cifrado: queda anotado.
            logger.warning("[nominas] lectura %s: %s", item.pk, exc)
            item.status = PayslipItem.Status.UNMATCHED
            item.note = "No se ha podido leer el PDF."
            item.page_to = item.page_to or 1
            item.save(update_fields=["status", "note", "page_to"])
            continue
        parts = split_pages(texts, people)
        with transaction.atomic():
            for index, (first, last, person, dni, text) in enumerate(parts):
                target = item if index == 0 else PayslipItem(
                    batch=batch, original_name=item.original_name,
                    staged_path=item.staged_path)
                start, end, label = find_period(text)
                target.page_from, target.page_to = first, last
                target.person = person
                target.dni_found = dni
                target.match_source = (PayslipItem.MatchSource.DNI
                                       if person else "")
                target.period_start, target.period_end = start, end
                target.period_label = label
                target.status = (PayslipItem.Status.READY if person
                                 else PayslipItem.Status.UNMATCHED)
                if person is not None:
                    target.note = ""
                elif not text.strip():
                    target.note = ("Sin texto (¿escaneada?): asígnala a "
                                   "mano.")
                elif dni:
                    target.note = ("El DNI/NIE %s no es de nadie de la "
                                   "empresa." % dni)
                else:
                    target.note = "No se ha encontrado ningún DNI/NIE."
                target.save()
    batch.status = PayslipBatch.Status.READY
    batch.read_at = timezone.now()
    batch.save(update_fields=["status", "read_at"])
    if batch.notify_whatsapp:
        notify_ready(batch)
    # S153: aviso a cada supervisor con acceso a la entrega.
    from hr_calendar.payslip_access import notify_share

    for share in batch.shares.select_related("company_user__user"):
        notify_share(share)
    return batch


def _user_phone(company_user):
    from document_explorer.models import PersonIdentity
    from document_explorer.person_phone_service import mobile_of
    from document_explorer.person_phone_service import whatsapp_address

    person = PersonIdentity.objects.filter(company_user=company_user).first()
    if person is not None:
        phone = mobile_of(person)
        if phone:
            return phone
    return whatsapp_address(company_user.phone)


def worker_phone(person):
    """
    The worker's WhatsApp number (E.164), or None.
    ---
    El móvil de WhatsApp del trabajador: el de empresa de su ficha y, si
    no tiene, el de su cuenta del panel (como los avisos del fichaje).
    """
    from document_explorer.person_phone_service import mobile_of
    from document_explorer.person_phone_service import whatsapp_address

    phone = mobile_of(person)
    if phone:
        return phone
    if person.company_user_id:
        return whatsapp_address(person.company_user.phone)
    return None


def _template(company, name):
    from whatsapp.models import WhatsAppTemplate

    return WhatsAppTemplate.objects.filter(company=company, name=name).first()


def _first_name(company_user=None, person=None):
    name = ""
    if person is not None:
        name = person.given_name or ""
    if not name and company_user is not None:
        name = company_user.user.first_name or ""
    return (name.strip() or "trabajador").title()


def notify_ready(batch):
    """
    WhatsApp to who started the batch: the payslips have been read.
    ---
    Avisa por WhatsApp a quien inició la entrega de que la lectura ha
    terminado. Si no se puede (sin móvil, sin plantilla aprobada y fuera
    de la ventana de 24 h, error de Twilio), queda anotado en la entrega
    y se ve en la pantalla.
    """
    from fleet.refuel_questions import template_approved
    from whatsapp.services import _build_twilio_client
    from whatsapp.window_service import send_notification, window_open

    from document_explorer.models import PersonIdentity

    by = batch.created_by
    error = ""
    if by is None:
        error = "La entrega no tiene supervisor."
    phone = _user_phone(by) if by is not None else None
    if not error and not phone:
        error = "El supervisor no tiene móvil en su ficha ni en su cuenta."
    template = _template(batch.company, BATCH_READY_TEMPLATE)
    if not error and template is None:
        error = ("Falta la plantilla de WhatsApp %s." % BATCH_READY_TEMPLATE)
    if not error and not (template_approved(template.content_sid)
                          or window_open(batch.company, phone)):
        error = "La plantilla de WhatsApp aún no está aprobada por Meta."
    if not error:
        counts = batch.items.values_list("status", flat=True)
        variables = {
            "1": _first_name(by, PersonIdentity.objects.filter(
                company_user=by).first()),
            "2": str(len(counts)),
            # Botón "Ver el listado": /panel/nominas/?batch=<id>.
            "3": "?batch=%d" % batch.pk,
        }
        try:
            send_notification(
                _build_twilio_client(),
                os.environ.get("TWILIO_WHATSAPP_SENDER", ""),
                batch.company, phone, template.content_sid, variables,
            )
        except Exception as exc:  # Twilio: se anota y se ve en pantalla.
            error = ("No se ha podido enviar el aviso: %s" % exc)[:255]
    if error:
        batch.notify_error = error[:255]
        batch.save(update_fields=["notify_error"])
        logger.warning("[nominas] aviso de la entrega %s: %s", batch.pk,
                       error)
        return False
    batch.notified_at = timezone.now()
    batch.notify_error = ""
    batch.save(update_fields=["notified_at", "notify_error"])
    return True


# ----------------------------------------------------------------------
# Paso 3: visto bueno
# ----------------------------------------------------------------------

def assign(item, person):
    """
    The supervisor sets (or clears) the worker of a payslip.
    ---
    El supervisor pone a mano el trabajador de una nómina (o lo quita).
    """
    from hr_calendar.models import PayslipBatch, PayslipItem

    if item.batch.status != PayslipBatch.Status.READY:
        raise PayslipError("La entrega ya no se puede cambiar.")
    if item.status not in (PayslipItem.Status.READY,
                           PayslipItem.Status.UNMATCHED,
                           PayslipItem.Status.EXCLUDED):
        raise PayslipError("Esa nómina ya no se puede cambiar.")
    item.person = person
    item.match_source = (PayslipItem.MatchSource.MANUAL if person
                         else "")
    if item.status != PayslipItem.Status.EXCLUDED:
        item.status = (PayslipItem.Status.READY if person
                       else PayslipItem.Status.UNMATCHED)
    item.save(update_fields=["person", "match_source", "status"])
    return item


def set_excluded(item, excluded):
    """
    Leaves a payslip out of the delivery, or puts it back.
    ---
    Deja una nómina fuera de la entrega, o la vuelve a meter.
    """
    from hr_calendar.models import PayslipBatch, PayslipItem

    if item.batch.status != PayslipBatch.Status.READY:
        raise PayslipError("La entrega ya no se puede cambiar.")
    if excluded:
        if item.status not in (PayslipItem.Status.READY,
                               PayslipItem.Status.UNMATCHED):
            raise PayslipError("Esa nómina ya no se puede dejar fuera.")
        item.status = PayslipItem.Status.EXCLUDED
    elif item.status == PayslipItem.Status.EXCLUDED:
        item.status = (PayslipItem.Status.READY if item.person_id
                       else PayslipItem.Status.UNMATCHED)
    item.save(update_fields=["status"])
    return item


def approve(batch, by):
    """
    The supervisor accepts the list: the batch goes out.
    ---
    El supervisor da el visto bueno al listado: la entrega pasa a
    "Enviando" (el envío lo hace Celery). No puede quedar ninguna nómina
    sin trabajador: o se asigna o se deja fuera.
    """
    from hr_calendar.models import PayslipBatch, PayslipItem

    with transaction.atomic():
        batch = PayslipBatch.objects.select_for_update().get(pk=batch.pk)
        if batch.status != PayslipBatch.Status.READY:
            raise PayslipError("La entrega no está para el visto bueno.")
        if batch.items.filter(status=PayslipItem.Status.UNMATCHED).exists():
            raise PayslipError(
                "Hay nóminas sin trabajador: asígnalas o déjalas fuera.")
        if not batch.items.filter(status=PayslipItem.Status.READY).exists():
            raise PayslipError("No hay ninguna nómina que enviar.")
        batch.status = PayslipBatch.Status.SENDING
        batch.approved_by = by
        batch.approved_at = timezone.now()
        batch.save(update_fields=["status", "approved_by", "approved_at"])
    return batch


def cancel(batch):
    """
    Cancels a batch not yet sent; its encrypted copies are deleted.
    ---
    Anula una entrega que no se ha enviado y borra sus copias cifradas.
    """
    import shutil

    from hr_calendar.models import PayslipBatch, PayslipItem

    if batch.status not in (PayslipBatch.Status.UPLOADING,
                            PayslipBatch.Status.READING,
                            PayslipBatch.Status.READY):
        raise PayslipError("Esa entrega ya no se puede anular.")
    batch.status = PayslipBatch.Status.CANCELLED
    batch.save(update_fields=["status"])
    batch.items.exclude(status__in=[PayslipItem.Status.SENT,
                                    PayslipItem.Status.FILED]).update(
        status=PayslipItem.Status.EXCLUDED)
    shutil.rmtree(_staged_abs(str(batch.pk)), ignore_errors=True)
    return batch


# ----------------------------------------------------------------------
# Paso 4: envío
# ----------------------------------------------------------------------

def _payslip_type():
    from document_explorer.models import DocumentTypeCatalog

    found = DocumentTypeCatalog.objects.filter(
        code=PAYSLIP_TYPE_CODE, is_active=True).first()
    if found is None:
        raise PayslipError("Falta el tipo NOMINA en el catálogo.")
    return found


def _file_payslip(item, by):
    """
    Files the payslip in the worker's folder (confidential, encrypted).
    ---
    Archiva la nómina en la carpeta del trabajador, como una subida
    desde su ficha: tipo NOMINA (confidencial: cifrada, sin lectura
    automática, solo para él y quien la envía).
    """
    from django.contrib.contenttypes.models import ContentType

    from document_explorer.models import PersonIdentity
    from document_explorer.subject_upload_service import (
        SubjectUploadError, upload_subject_document,
    )
    from hr_calendar.worker_requests import person_label

    name = "Nomina_%s.pdf" % re.sub(
        r"[^A-Za-z0-9]+", "_", _plain(item.period_label or "")).strip("_")
    try:
        result = upload_subject_document(
            subject=item.person,
            domain_content_type=ContentType.objects.get_for_model(
                PersonIdentity),
            document_type=_payslip_type(), data=item_pdf(item),
            original_filename=name if item.period_label else "Nomina.pdf",
            typed_date=None, typed_issue_date=item.period_end,
            subject_label=person_label(item.person), uploaded_by=by,
            filename_date=item.period_end,
        )
    except SubjectUploadError as exc:
        raise PayslipError(str(exc)) from exc
    return result["entry"]


# S163 (25/11): muestra pública (sin datos) que Meta descarga para
# aprobar payslip_delivery; las nóminas reales van a «<token>.pdf».
SAMPLE_MEDIA_NAME = "ejemplo-nomina.pdf"


def sample_pdf():
    """
    A one-page sample PDF with no personal data (template approval).

    ---

    Un PDF de una página sin ningún dato personal: la muestra de la
    plantilla de WhatsApp de la nómina que Meta descarga para aprobarla.
    """
    import fitz

    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((72, 110), "Grupo Alvarez", fontsize=20)
    page.insert_text((72, 150), "Nomina de ejemplo", fontsize=16)
    page.insert_text((72, 185), "Documento de muestra sin datos "
                     "personales.", fontsize=11)
    data = doc.tobytes()
    doc.close()
    return data


def media_url(item):
    """
    The temporary public link Twilio fetches the payslip from.
    ---
    El enlace temporal (sin sesión) del que Twilio recoge el PDF para
    mandarlo por WhatsApp. Solo sirve esa nómina y caduca a las
    MEDIA_HOURS horas.
    """
    from django.urls import reverse

    return "%s%s" % (settings.PLATFORM_BASE_URL, reverse(
        "panel:payslip_media", args=[item.media_token + ".pdf"]))


def _whatsapp(item):
    """
    Sends the payslip PDF to the worker. Returns (sid, error).
    ---
    Manda el PDF de la nómina al trabajador: dentro de la ventana de
    24 h, mensaje con el PDF; fuera, la plantilla aprobada (con el PDF).
    """
    from fleet.refuel_questions import template_approved
    from whatsapp.services import _build_twilio_client
    from whatsapp.window_service import send_notification, window_open

    phone = worker_phone(item.person)
    item.phone = phone or ""
    if not phone:
        return "", "Sin móvil en su ficha ni en su cuenta."
    template = _template(item.batch.company, DELIVERY_TEMPLATE)
    inside = window_open(item.batch.company, phone)
    if template is None and not inside:
        return "", "Falta la plantilla de WhatsApp %s." % DELIVERY_TEMPLATE
    if not inside and not template_approved(template.content_sid):
        return "", "La plantilla de WhatsApp aún no está aprobada por Meta."
    item.media_token = secrets.token_urlsafe(32)
    item.media_expires = timezone.now() + datetime.timedelta(
        hours=MEDIA_HOURS)
    item.save(update_fields=["media_token", "media_expires", "phone"])
    name = _first_name(person=item.person)
    month = item.period_label or "este mes"
    text = ("Hola %s. Le enviamos su nomina de %s. Es un documento "
            "personal y confidencial." % (name, month))
    try:
        message = send_notification(
            _build_twilio_client(),
            os.environ.get("TWILIO_WHATSAPP_SENDER", ""),
            item.batch.company, phone,
            template.content_sid if template else None,
            {"1": name, "2": month, "3": item.media_token + ".pdf"},
            text=text, media_url=media_url(item),
        )
    except Exception as exc:  # Twilio: se anota en la nómina.
        return "", ("WhatsApp: %s" % exc)[:255]
    return getattr(message, "sid", "") or "", ""


def send_item(item, by):
    """
    Files one payslip and sends it by WhatsApp. Updates the item.
    ---
    Archiva una nómina en la ficha del trabajador (si no lo estaba) y se
    la manda por WhatsApp. "Enviada" si llega el WhatsApp; "Archivada,
    sin WhatsApp" si se archiva pero el WhatsApp no sale (se puede
    reintentar); "Error" si ni se archiva.
    """
    from hr_calendar.models import PayslipItem

    if item.entry_id is None:
        try:
            item.entry = _file_payslip(item, by)
        except Exception as exc:  # cualquier fallo: queda en la nómina.
            logger.exception("[nominas] archivo de %s", item.pk)
            item.status = PayslipItem.Status.ERROR
            item.note = str(exc)[:255] or "No se ha podido archivar."
            item.save(update_fields=["status", "note"])
            return item
    sid, error = _whatsapp(item)
    item.message_sid = sid
    item.sent_at = timezone.now() if sid else None
    item.status = (PayslipItem.Status.SENT if sid
                   else PayslipItem.Status.FILED)
    item.note = error
    item.save(update_fields=["entry", "message_sid", "sent_at", "status",
                             "note", "phone"])
    return item


def send_batch(batch):
    """
    Sends every approved payslip of the batch.
    ---
    Envía todas las nóminas con visto bueno de la entrega. S153: las
    copias cifradas se quedan (no son efímeras).
    """
    from hr_calendar.models import PayslipBatch, PayslipItem

    by = batch.approved_by
    for item in batch.items.filter(
            status=PayslipItem.Status.READY).select_related("person"):
        send_item(item, by)
    batch.status = PayslipBatch.Status.SENT
    batch.finished_at = timezone.now()
    batch.save(update_fields=["status", "finished_at"])
    return batch


def retry_whatsapp(batch):
    """
    Sends again the WhatsApp of the payslips filed without it.
    ---
    Vuelve a mandar por WhatsApp las nóminas archivadas que no llegaron
    a salir (sin plantilla aprobada, sin móvil, error de Twilio).
    """
    from hr_calendar.models import PayslipItem

    sent = 0
    for item in batch.items.filter(
            status__in=[PayslipItem.Status.FILED, PayslipItem.Status.ERROR]
    ).select_related("person", "batch__company"):
        before = item.status
        send_item(item, batch.approved_by)
        if item.status == PayslipItem.Status.SENT != before:
            sent += 1
    return sent
