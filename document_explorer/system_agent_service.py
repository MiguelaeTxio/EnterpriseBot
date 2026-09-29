# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/system_agent_service.py
"""
H30 (S123). Heartbeat of system agents running outside PythonAnywhere
(the H28 migration agent) and the WhatsApp alert when one stops.

---

H30 (S123), punto 7 de la hoja de ruta. Latido de los agentes de
sistema que corren fuera de PythonAnywhere (el agente de migración H28
en una máquina Windows) y alerta por WhatsApp cuando uno se para.
Miguel Ángel lo pidió tras un corte de luz que dejó el agente parado
sin que nadie se enterase.

- `record_heartbeat()`: lo llama `AgentHeartbeatView` cada vez que el
  agente da señales (cada 5 minutos).
- `check_agents()`: lo llama `check_system_agents_task` cada 5 minutos
  desde Celery Beat. Un agente con más de `STALE_AFTER` sin latido
  recibe UNA alerta de caída (`system_agent_down_alert`); cuando vuelve
  a latir tras una alerta, UN aviso de recuperación
  (`system_agent_recovered_alert`). Cada envío queda registrado en su
  fila (`SystemAgentHeartbeat`: hora y SID de Twilio).

Destinatarios: las personas de `settings.SYSTEM_AGENT_ALERT_PERSON_IDS`
(por defecto, Miguel Ángel). Nunca lanza: un fallo de Twilio se
registra y se reintenta en la siguiente pasada, porque la marca de
"avisado" solo se escribe si al menos un envío tuvo éxito.
"""
import json
import logging
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from .models import PersonIdentity, SystemAgentHeartbeat
from .person_phone_service import mobile_of

logger = logging.getLogger(__name__)

STALE_AFTER = timedelta(minutes=15)
DOWN_TEMPLATE = "system_agent_down_alert"
RECOVERED_TEMPLATE = "system_agent_recovered_alert"
FALLBACK_COMPANY_SLUG = "grupo-alvarez"
AGENT_LABELS = {"h28_migration_agent": "de migracion H28"}


def record_heartbeat(agent_name, host=""):
    """
    Upsert the agent's last heartbeat to now.

    ---

    Anota ahora como último latido del agente (lo crea si no existía).
    """
    heartbeat, _created = SystemAgentHeartbeat.objects.update_or_create(
        agent_name=agent_name,
        defaults={"last_beat_at": timezone.now(), "host": host[:255]},
    )
    return heartbeat


def _agent_label(heartbeat):
    label = AGENT_LABELS.get(heartbeat.agent_name, heartbeat.agent_name)
    if heartbeat.host:
        label = "%s (%s)" % (label, heartbeat.host)
    return label


def _send_to_recipients(template_name, heartbeat, moment):
    """
    Send one template to every configured recipient; return the first
    Twilio SID, or "" if none could be sent.

    ---

    Envía una plantilla a cada destinatario configurado; devuelve el
    primer SID de Twilio, o "" si no se pudo enviar ninguna.
    """
    from ivr_config.models import Company
    from whatsapp.models import WhatsAppTemplate
    from whatsapp.services import _build_twilio_client
    from whatsapp.tasks import _get_whatsapp_sender

    sender = _get_whatsapp_sender()
    if not sender:
        logger.error("# [AGENT HEARTBEAT] Sin TWILIO_WHATSAPP_SENDER.")
        return ""
    fallback_company = Company.objects.filter(
        slug=FALLBACK_COMPANY_SLUG,
    ).first()
    person_ids = getattr(settings, "SYSTEM_AGENT_ALERT_PERSON_IDS", [])
    first_sid = ""
    for person in PersonIdentity.objects.filter(pk__in=person_ids):
        phone = mobile_of(person) or ""  # S125: E.164 (+34...)
        company = person.company or fallback_company
        template = WhatsAppTemplate.objects.filter(
            company=company, name=template_name, is_active=True,
        ).first()
        if not phone or template is None:
            logger.error(
                "# [AGENT HEARTBEAT] %s: sin teléfono o sin plantilla %s.",
                person, template_name,
            )
            continue
        variables = {
            "1": person.given_name or str(person),
            "2": _agent_label(heartbeat),
            "3": timezone.localtime(moment).strftime("%d/%m/%Y %H:%M"),
        }
        try:
            message = _build_twilio_client().messages.create(
                from_="whatsapp:%s" % sender,
                to="whatsapp:%s" % phone,
                content_sid=template.content_sid,
                content_variables=json.dumps(variables),
            )
        except Exception as exc:  # noqa: BLE001 -- se reintenta luego
            logger.error(
                "# [AGENT HEARTBEAT] Error enviando %s a %s: %s",
                template_name, phone, exc,
            )
            continue
        logger.info(
            "# [AGENT HEARTBEAT] %s enviado a %s -- SID %s",
            template_name, phone, message.sid,
        )
        first_sid = first_sid or message.sid
    return first_sid


def check_agents():
    """
    Alert once per outage and once per recovery.

    ---

    Avisa una vez por caída y una vez por recuperación.
    """
    now = timezone.now()
    for heartbeat in SystemAgentHeartbeat.objects.all():
        stale = now - heartbeat.last_beat_at > STALE_AFTER
        if stale and heartbeat.down_alerted_at is None:
            sid = _send_to_recipients(
                DOWN_TEMPLATE, heartbeat, heartbeat.last_beat_at,
            )
            if sid:
                heartbeat.down_alerted_at = now
                heartbeat.down_alert_sid = sid
                heartbeat.save(
                    update_fields=["down_alerted_at", "down_alert_sid"],
                )
        elif not stale and heartbeat.down_alerted_at is not None:
            sid = _send_to_recipients(
                RECOVERED_TEMPLATE, heartbeat, heartbeat.last_beat_at,
            )
            if sid:
                heartbeat.down_alerted_at = None
                heartbeat.recovered_alerted_at = now
                heartbeat.recovered_alert_sid = sid
                heartbeat.save(update_fields=[
                    "down_alerted_at", "recovered_alerted_at",
                    "recovered_alert_sid",
                ])
