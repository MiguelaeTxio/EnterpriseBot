# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/notice_delivery_service.py
"""
H30 (S122). Daily WhatsApp delivery of the document notices.

---

H30 (S122). Envío diario por WhatsApp de los avisos de documentación:
exactamente lo que se ve en Avisos > Pendientes, a cada supervisor
según su ámbito (`notice_recipients`), con las plantillas nuevas
`document_expiry_notice` / `document_missing_notice`. Sustituye al
envío de las filas antiguas de `DocumentAlert` (30/15/7 automáticas).

Solo para empresas con el interruptor encendido
(`DocumentAlertSettings`). Sin repeticiones (`NoticeDelivery`):
- Próximo a caducar: una vez por cada aviso alcanzado.
- Caducado y falta: al aparecer y después un recordatorio cada 7
  días mientras sigan sin resolverse (decisión de Miguel Ángel, S122).
"""
import json
import logging
from datetime import timedelta

from django.utils import timezone

from document_explorer import document_notice_service as notices
from document_explorer.notice_recipients import load_scopes, recipients_for

logger = logging.getLogger(__name__)

EXPIRY_TEMPLATE_NAME = "document_expiry_notice"
MISSING_TEMPLATE_NAME = "document_missing_notice"
REMINDER_INTERVAL = timedelta(days=7)


def _is_due(notice, delivery, now):
    """
    True if this notice has to be sent now to this supervisor.

    ---

    True si toca enviar el aviso ahora a este supervisor.
    """
    if delivery is None:
        return True
    if notice.kind == notices.KIND_UPCOMING:
        return False
    return delivery.last_sent_at <= now - REMINDER_INTERVAL


def _content_variables(notice, company_user):
    """
    Template variables for this notice.

    ---

    Variables de la plantilla: {{1}} destinatario, {{2}} documento,
    {{3}} sujeto y, en caducidad, {{4}} fecha.
    """
    variables = {
        "1": company_user.user.get_full_name() or company_user.user.username,
        "2": notice.document_label,
        "3": notice.subject_label,
    }
    if notice.kind != notices.KIND_MISSING:
        variables["4"] = notice.expiry_date.strftime("%d/%m/%Y")
    return variables


def _phone_of(company_user):
    """
    WhatsApp phone of an internal contact, or "".

    ---

    Teléfono del contacto interno del usuario (mismo criterio que el
    envío manual de alertas), o "".
    """
    from ivr_config.models import Contact

    contact = Contact.objects.filter(
        company_user=company_user, is_internal=True,
    ).first()
    return contact.phone_number if contact and contact.phone_number else ""


def send_due_notices():
    """
    Send today's due notices of every company with the switch on.

    ---

    Envía los avisos que tocan hoy en cada empresa con el interruptor
    encendido. Nunca deja que un fallo aborte el resto. Devuelve un
    resumen legible para el log de la tarea.
    """
    from document_explorer.models import NoticeDelivery
    from document_management.alert_service import (
        _build_twilio_client, _get_whatsapp_sender,
    )
    from document_management.models import DocumentAlertSettings
    from whatsapp.models import WhatsAppTemplate

    enabled = DocumentAlertSettings.objects.filter(
        whatsapp_enabled=True,
    ).select_related("company")
    if not enabled:
        return "Envío automático por WhatsApp apagado en todas las empresas."

    pending = []
    for domain in (notices.DOMAIN_PERSONAL, notices.DOMAIN_MACHINE):
        domain_pending, _scheduled, _calendar = notices.compute_notices(
            domain,
        )
        pending.extend(domain_pending)

    now = timezone.now()
    sent = skipped = errors = 0
    for settings_row in enabled:
        company = settings_row.company
        templates = {
            t.name: t for t in WhatsAppTemplate.objects.filter(
                company=company, is_active=True,
                name__in=(EXPIRY_TEMPLATE_NAME, MISSING_TEMPLATE_NAME),
            )
        }
        if len(templates) < 2:
            logger.error(
                "# [send_due_notices] %s: faltan plantillas activas (%s) "
                "-- no se envía nada.", company, sorted(templates),
            )
            continue
        try:
            client = _build_twilio_client()
            sender = _get_whatsapp_sender()
        except KeyError as exc:
            logger.error(
                "# [send_due_notices] Variable de entorno de Twilio "
                "ausente: %s -- no se envía nada.", exc,
            )
            continue

        scopes = load_scopes(company)
        deliveries = {
            (d.company_user_id, d.notice_key): d
            for d in NoticeDelivery.objects.filter(
                company_user__in=[s.company_user for s in scopes],
            )
        }
        for notice in pending:
            for company_user in recipients_for(notice, scopes):
                key = notice.notice_key
                delivery = deliveries.get((company_user.pk, key))
                if not _is_due(notice, delivery, now):
                    continue
                phone = _phone_of(company_user)
                if not phone:
                    skipped += 1
                    logger.warning(
                        "# [send_due_notices] %s sin teléfono de "
                        "WhatsApp -- aviso no enviado: %s", company_user,
                        key,
                    )
                    continue
                template = templates[
                    MISSING_TEMPLATE_NAME
                    if notice.kind == notices.KIND_MISSING
                    else EXPIRY_TEMPLATE_NAME
                ]
                try:
                    client.messages.create(
                        from_="whatsapp:%s" % sender,
                        to="whatsapp:%s" % phone,
                        content_sid=template.content_sid,
                        content_variables=json.dumps(
                            _content_variables(notice, company_user),
                        ),
                    )
                except Exception as exc:
                    errors += 1
                    logger.error(
                        "# [send_due_notices] Error de Twilio enviando a "
                        "%s (%s): %s", company_user, key, exc,
                    )
                    continue
                sent += 1
                if delivery is None:
                    deliveries[(company_user.pk, key)] = (
                        NoticeDelivery.objects.create(
                            company_user=company_user, notice_key=key,
                            kind=notice.kind, first_sent_at=now,
                            last_sent_at=now,
                        )
                    )
                else:
                    delivery.last_sent_at = now
                    delivery.send_count += 1
                    delivery.save(
                        update_fields=["last_sent_at", "send_count"],
                    )

    return (
        "Avisos enviados: %d; sin teléfono: %d; con error: %d."
        % (sent, skipped, errors)
    )
