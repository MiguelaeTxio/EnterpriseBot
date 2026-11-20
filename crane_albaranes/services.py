# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/crane_albaranes/services.py
"""
Crane work delivery notes: preparing, notice, clock times, PDF and
delivery (H11, S162).

---

Albaranes de trabajo de las grúas (H11, S162): preparar el albarán con
los datos de la obra, avisar al gruista por WhatsApp, sacar las horas de
sus fichajes del día, generar el PDF, guardarlo en el cubo y entregarlo
al cliente por correo o WhatsApp.
"""
import datetime
import logging
import os
import re
import unicodedata
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone

from crane_albaranes.models import CraneAlbaran

logger = logging.getLogger(__name__)

NOTICE_TEMPLATE_NAME = "crane_albaran_notice"
NUMBER_PREFIX = "D"


class CraneAlbaranError(Exception):
    """
    Expected failure shown to the user.
    ---
    Fallo esperado que se enseña tal cual al usuario.
    """


# ---------------------------------------------------------------------
# Preparar
# ---------------------------------------------------------------------

def next_number(company):
    """
    Next number of the digital series (D000001, D000002...).
    ---
    Siguiente número de la serie digital. Se calcula dentro de la misma
    transacción que crea el albarán (bloqueo de la fila más alta).
    """
    last = (CraneAlbaran.objects.select_for_update()
            .filter(company=company, number__startswith=NUMBER_PREFIX)
            .order_by("-number").values_list("number", flat=True)
            .first())
    value = int(last[len(NUMBER_PREFIX):]) + 1 if last else 1
    return "%s%06d" % (NUMBER_PREFIX, value)


def person_label(person):
    """
    "Name Surname Surname" of a worker.
    ---
    Nombre y apellidos del trabajador, como en el papel.
    """
    if person is None:
        return ""
    return " ".join(p for p in (person.given_name, person.first_surname,
                                person.second_surname) if p)


def default_issuer(machine=None, person=None):
    """
    Issuing company: the machine's, else the worker's employer.
    ---
    Empresa emisora: la de la máquina; si no, la del gruista.
    """
    from document_explorer.epi_delivery_document_service import (
        resolve_company_fiscal_profile,
    )

    for text in ((machine.company_name if machine else ""),
                 (person.employer_company if person else "")):
        profile = resolve_company_fiscal_profile(text)
        if profile is not None:
            return profile
    return None


def apply_worksite(albaran, worksite):
    """
    Copy the site and client data onto the albarán.
    ---
    Copia al albarán la obra y los datos de su cliente (cliente, N.I.F.,
    domicilio, teléfono, lugar de trabajo, nº de pedido y horas
    mínimas). Lo ya escrito en el albarán no se pisa.
    """
    albaran.worksite = worksite
    if worksite is None:
        return albaran
    client = worksite.client
    albaran.client = client
    albaran.client_name = albaran.client_name or worksite.client_label
    if client is not None:
        albaran.client_tax_id = albaran.client_tax_id or client.tax_id
        albaran.client_address = albaran.client_address or client.address
        albaran.client_locality = (albaran.client_locality
                                   or client.locality)
        albaran.client_province = (albaran.client_province
                                   or client.province)
        albaran.client_phone = albaran.client_phone or client.phone
    albaran.work_place = (albaran.work_place or worksite.address
                          or worksite.name)
    albaran.work_locality = albaran.work_locality or worksite.locality
    albaran.order_number = albaran.order_number or worksite.order_number
    if albaran.min_hours is None:
        albaran.min_hours = worksite.min_hours
    return albaran


def last_tonnage(machine):
    """
    Tonnage written on the last albarán of the machine.
    ---
    Toneladas del último albarán de esa máquina (la ficha de la máquina
    no las tiene).
    """
    if machine is None:
        return ""
    return (CraneAlbaran.objects.filter(machine=machine)
            .exclude(tonnage="").order_by("-day", "-pk")
            .values_list("tonnage", flat=True).first() or "")


def create_albaran(company, *, day, worksite=None, machine=None,
                   person=None, origin=CraneAlbaran.ORIGIN_OFFICE,
                   created_by=None, **fields):
    """
    Create a prepared albarán with its number and the site data.
    ---
    Crea un albarán preparado, con su número, la obra y su cliente, la
    empresa emisora y las toneladas de la máquina.
    """
    with transaction.atomic():
        albaran = CraneAlbaran(
            company=company, number=next_number(company), day=day,
            machine=machine, person=person, origin=origin,
            created_by=created_by, **fields)
        apply_worksite(albaran, worksite)
        if albaran.issuer_id is None:
            albaran.issuer = default_issuer(machine, person)
        if not albaran.tonnage:
            albaran.tonnage = last_tonnage(machine)
        albaran.save()
    return albaran


# ---------------------------------------------------------------------
# Horas desde los fichajes
# ---------------------------------------------------------------------

def _local_time(value):
    return timezone.localtime(value).time().replace(second=0,
                                                    microsecond=0)


def clock_times(person, day):
    """
    The four times of the production sheet, from the day's clock events.
    ---
    Las horas del parte de producción a partir de los fichajes del
    gruista (fichaje por tipos):
    - Salida de base: la entrada de la jornada.
    - Llegada al trabajo: el primer tramo que no es desplazamiento ni
      pausa (trabajo efectivo, presencia...).
    - Salida del trabajo: el final del último de esos tramos.
    - Llegada a base: la salida de la jornada.
    Horas trabajadas: la suma de esos tramos (sin desplazamientos ni
    pausas). Se usa la hora redondeada del parte si la hay. Devuelve {}
    si ese día no fichó.
    """
    from hr_calendar.models import ClockEvent, ClockType

    company_user = getattr(person, "company_user", None)
    if company_user is None:
        return {}
    start = timezone.make_aware(datetime.datetime.combine(
        day, datetime.time.min))
    end = start + datetime.timedelta(hours=36)
    events = list(
        ClockEvent.objects.current()
        .filter(company_user=company_user, pressed_at__gte=start,
                pressed_at__lt=end)
        .select_related("clock_type").order_by("pressed_at", "pk"))
    first_in = next((i for i, e in enumerate(events)
                     if e.kind == ClockEvent.Kind.IN
                     and timezone.localtime(e.pressed_at).date() == day),
                    None)
    if first_in is None:
        return {}
    shift = []
    for event in events[first_in:]:
        if shift and event.kind == ClockEvent.Kind.IN:
            break
        shift.append(event)
        if event.kind == ClockEvent.Kind.OUT:
            break

    def when(event):
        return event.rounded_at or event.pressed_at

    not_work = (ClockType.ROLE_TRAVEL, ClockType.ROLE_MEAL)
    work = []
    for index, event in enumerate(shift):
        if event.kind == ClockEvent.Kind.OUT:
            continue
        role = event.clock_type.role if event.clock_type_id else ""
        if role in not_work:
            continue
        stop = shift[index + 1] if index + 1 < len(shift) else None
        work.append((when(event), when(stop) if stop else None))
    result = {"base_out": _local_time(when(shift[0]))}
    last = shift[-1]
    if last.kind == ClockEvent.Kind.OUT:
        result["base_in"] = _local_time(when(last))
    if work:
        result["work_in"] = _local_time(work[0][0])
        if work[-1][1] is not None:
            result["work_out"] = _local_time(work[-1][1])
        seconds = sum((b - a).total_seconds() for a, b in work if b)
        if seconds:
            result["hours_worked"] = (
                Decimal(seconds) / Decimal(3600)).quantize(Decimal("0.01"))
    return result


def fill_from_clock(albaran, overwrite=False):
    """
    Put the clock times on the albarán (only empty ones by default).
    ---
    Pone en el albarán las horas sacadas de los fichajes. Por defecto
    solo rellena lo vacío (lo que haya corregido el gruista se respeta);
    con `overwrite` las vuelve a poner todas.
    """
    times = clock_times(albaran.person, albaran.day)
    changed = []
    for field, value in times.items():
        if overwrite or getattr(albaran, field) in (None, ""):
            setattr(albaran, field, value)
            changed.append(field)
    if changed:
        albaran.times_from_clock = True
    return changed


# ---------------------------------------------------------------------
# Aviso al gruista
# ---------------------------------------------------------------------

def worker_url(albaran):
    """
    Link the worker opens (inside the clock-in app).
    ---
    Enlace que abre el gruista, dentro de la aplicación de fichaje.
    """
    return settings.PLATFORM_BASE_URL + reverse(
        "crane_albaranes:worker_albaran", kwargs={"token": albaran.token})


def worker_phone(person):
    """
    Worker mobile: his sheet's, else his panel contact's.
    ---
    Móvil del gruista: el de su ficha; si no, el de su contacto.
    """
    if person is None:
        return ""
    return person.phone or person.phone_secondary or ""


def notice_text(albaran):
    """
    WhatsApp text of the work order notice.
    ---
    Texto del aviso de orden de trabajo por WhatsApp.
    """
    when = albaran.day.strftime("%d/%m/%Y")
    if albaran.planned_time:
        when += " a las %s" % albaran.planned_time.strftime("%H:%M")
    lines = [
        "\U0001f3d7️ Orden de trabajo — albarán %s" % albaran.number,
        "Fecha: %s" % when,
        "Obra: %s" % (albaran.worksite.name if albaran.worksite_id
                      else albaran.work_place or "sin indicar"),
        "Cliente: %s" % (albaran.client_name or "sin indicar"),
        "Lugar: %s" % (", ".join(p for p in (albaran.work_place,
                                             albaran.work_locality) if p)
                       or "sin indicar"),
        "Máquina: %s" % (albaran.machine.code if albaran.machine_id
                         else "sin indicar"),
    ]
    if albaran.task:
        lines.append("Trabajo: %s" % albaran.task)
    lines.append("Abre el albarán aquí: %s" % worker_url(albaran))
    return "\n".join(lines)


def send_worker_notice(albaran):
    """
    Send the albarán to the worker by WhatsApp.
    ---
    Envía el albarán al gruista por WhatsApp: la plantilla
    crane_albaran_notice si está aprobada; dentro de la ventana de 24 h,
    el mismo texto libre (whatsapp.window_service). Sin plantilla y
    fuera de la ventana no se puede enviar y se dice. Deja el albarán en
    SENT o SEND_FAILED con el motivo.
    """
    from fleet.refuel_questions import template_approved
    from whatsapp.models import WhatsAppTemplate
    from whatsapp.services import _build_twilio_client
    from whatsapp.window_service import (
        send_notification,
        to_e164,
        window_open,
    )

    phone = worker_phone(albaran.person)
    error = ""
    if albaran.person is None:
        error = "Sin gruista asignado."
    elif not phone:
        error = "El gruista no tiene móvil en su ficha."
    sender = os.environ.get("TWILIO_WHATSAPP_SENDER", "")
    if not error and not sender:
        error = "Falta TWILIO_WHATSAPP_SENDER en el servidor."
    if not error:
        template = WhatsAppTemplate.objects.filter(
            company=albaran.company, name=NOTICE_TEMPLATE_NAME,
            is_active=True).first()
        sid = template.content_sid if template else ""
        approved = bool(sid) and template_approved(sid)
        if not approved and not window_open(albaran.company,
                                            to_e164(phone)):
            error = ("La plantilla de WhatsApp del aviso está pendiente de "
                     "aprobación y el gruista no ha escrito al bot en las "
                     "últimas 24 h.")
    if not error:
        try:
            send_notification(
                _build_twilio_client(), sender, albaran.company, phone,
                sid if approved else None,
                variables=_notice_variables(albaran) if approved else None,
                text=notice_text(albaran))
        except Exception as exc:  # noqa: BLE001 -- se informa al usuario
            logger.exception("# [ALBARÁN GRÚA] Aviso de %s no enviado",
                             albaran.number)
            error = "Twilio no aceptó el envío: %s" % exc
    albaran.notice_error = error[:255]
    if error:
        albaran.status = CraneAlbaran.Status.SEND_FAILED
    else:
        albaran.status = CraneAlbaran.Status.SENT
        albaran.notified_at = timezone.now()
    albaran.save(update_fields=["notice_error", "status", "notified_at",
                                "updated_at"])
    logger.info("# [ALBARÁN GRÚA] %s aviso a %s: %s", albaran.number,
                phone, error or "enviado")
    return not error


def _notice_variables(albaran):
    """
    Variables of the crane_albaran_notice template.
    ---
    Variables de la plantilla crane_albaran_notice: {{1}} gruista,
    {{2}} número, {{3}} fecha y hora, {{4}} obra y cliente, {{5}}
    máquina, {{6}} el final del enlace del botón.
    """
    when = albaran.day.strftime("%d/%m/%Y")
    if albaran.planned_time:
        when += " %s" % albaran.planned_time.strftime("%H:%M")
    site = albaran.worksite.name if albaran.worksite_id else (
        albaran.work_place or "-")
    return {
        "1": albaran.person.given_name if albaran.person_id else "-",
        "2": albaran.number,
        "3": when,
        "4": "%s (%s)" % (site, albaran.client_name or "-"),
        "5": albaran.machine.code if albaran.machine_id else "-",
        "6": "%s/" % albaran.token,
    }


# ---------------------------------------------------------------------
# PDF, cubo y entrega
# ---------------------------------------------------------------------

def pdf_bytes(albaran):
    """
    The albarán as PDF (weasyprint), like the paper one.
    ---
    El albarán en PDF, con la misma disposición que el de papel.
    """
    import weasyprint

    from django.contrib.staticfiles import finders

    logo = finders.find("panel/img/grupo_alvarez_logo.png")
    html = render_to_string("crane_albaranes/pdf.html", {
        "a": albaran,
        "logo_uri": ("file://%s" % logo) if logo else "",
        "operator": person_label(albaran.person),
    })
    return weasyprint.HTML(string=html).write_pdf()


def pdf_name(albaran):
    """
    File name of the PDF.
    ---
    Nombre del PDF: ALBARAN_D000001_20261120_A-65.pdf.
    """
    machine = albaran.machine.code if albaran.machine_id else ""
    stem = "ALBARAN_%s_%s_%s" % (albaran.number,
                                 albaran.day.strftime("%Y%m%d"), machine)
    stem = unicodedata.normalize("NFKD", stem).encode(
        "ascii", "ignore").decode()
    return re.sub(r"[^0-9A-Za-z._-]+", "_", stem).strip("_") + ".pdf"


def archive_pdf(albaran, data):
    """
    Keep the signed PDF in the worker's ALBARANES DE TRABAJO folder.
    ---
    Guarda el PDF firmado en el cubo, en la carpeta ALBARANES DE TRABAJO
    del gruista (la misma que los albaranes de papel, S153).
    """
    from hr_calendar.albaran_check import archive_in_bucket

    if albaran.person is None:
        return ""
    return archive_in_bucket(None, pdf_name(albaran), data,
                             "application/pdf", "pdf",
                             person=albaran.person)


def email_configured():
    """
    Whether the server can send e-mail.
    ---
    Si el servidor tiene buzón de salida configurado (EMAIL_HOST en el
    .env) o un backend que no es SMTP (pruebas).
    """
    backend = getattr(settings, "EMAIL_BACKEND", "")
    return bool(getattr(settings, "EMAIL_HOST", "")) or (
        not backend.endswith("smtp.EmailBackend"))


def _email_html(albaran):
    return render_to_string("crane_albaranes/email.html", {
        "a": albaran, "operator": person_label(albaran.person)})


def send_by_email(albaran, data, recipients):
    """
    E-mail the signed PDF to the client.
    ---
    Envía el PDF firmado al cliente por correo, con un resumen en el
    cuerpo.
    """
    from django.core.mail import EmailMultiAlternatives

    issuer = albaran.issuer.legal_name if albaran.issuer_id else (
        "Grupo Álvarez")
    subject = "Albarán de trabajo %s — %s — %s" % (
        albaran.number, albaran.day.strftime("%d/%m/%Y"),
        albaran.worksite.name if albaran.worksite_id else (
            albaran.work_place or albaran.client_name))
    text = ("Adjuntamos el albarán de trabajo %s firmado.\n\n%s"
            % (albaran.number, issuer))
    message = EmailMultiAlternatives(
        subject=subject, body=text,
        from_email=settings.DEFAULT_FROM_EMAIL, to=recipients)
    message.attach_alternative(_email_html(albaran), "text/html")
    message.attach(pdf_name(albaran), data, "application/pdf")
    message.send(fail_silently=False)


def deliver(albaran, data):
    """
    Deliver the signed albarán to the client as the site says.
    ---
    Entrega el albarán firmado según diga la obra: por correo (lo
    recomendado) o por WhatsApp. Deja DELIVERED o DELIVERY_FAILED con el
    motivo.
    """
    from worksites.models import Worksite

    worksite = albaran.worksite
    channel = worksite.delivery_channel if worksite else (
        Worksite.DELIVERY_EMAIL)
    errors, done = [], []
    if channel in (Worksite.DELIVERY_EMAIL, Worksite.DELIVERY_BOTH):
        emails = worksite.emails() if worksite else []
        if not emails and albaran.client_id and albaran.client.email:
            emails = [e.strip() for e in albaran.client.email.split(",")
                      if "@" in e]
        if not emails:
            errors.append("la obra y el cliente no tienen correo")
        elif not email_configured():
            errors.append("el servidor no tiene buzón de salida "
                          "configurado")
        else:
            try:
                send_by_email(albaran, data, emails)
                done.append(", ".join(emails))
            except Exception as exc:  # noqa: BLE001 -- motivo al usuario
                logger.exception("# [ALBARÁN GRÚA] Correo de %s",
                                 albaran.number)
                errors.append("el correo falló (%s)" % exc)
    if channel in (Worksite.DELIVERY_WHATSAPP, Worksite.DELIVERY_BOTH):
        errors.append("la entrega por WhatsApp necesita su plantilla "
                      "aprobada")
    albaran.delivery_channel = channel
    albaran.delivered_to = "; ".join(done)[:300]
    albaran.delivery_error = ("Sin entregar: %s." % "; ".join(errors)
                              if errors else "")[:255]
    if done:
        albaran.delivered_at = timezone.now()
    if channel == Worksite.DELIVERY_NONE:
        albaran.status = CraneAlbaran.Status.SIGNED
    else:
        albaran.status = (CraneAlbaran.Status.DELIVERED if done
                          and not errors else
                          CraneAlbaran.Status.DELIVERY_FAILED)
    albaran.save(update_fields=[
        "delivery_channel", "delivered_to", "delivery_error",
        "delivered_at", "status", "updated_at"])
    return not errors


def finish_signed(albaran):
    """
    After the client signs: PDF, bucket copy and delivery.
    ---
    Tras la firma del cliente: genera el PDF, lo guarda en el cubo y lo
    entrega. Un fallo del cubo no impide la entrega (queda anotado).
    """
    data = pdf_bytes(albaran)
    try:
        albaran.pdf_blob = archive_pdf(albaran, data)
        albaran.save(update_fields=["pdf_blob", "updated_at"])
    except Exception as exc:  # noqa: BLE001 -- la entrega sigue
        logger.exception("# [ALBARÁN GRÚA] %s sin copia en el cubo",
                         albaran.number)
        albaran.delivery_error = ("Sin copia en el cubo: %s" % exc)[:255]
        albaran.save(update_fields=["delivery_error", "updated_at"])
    return deliver(albaran, data)
