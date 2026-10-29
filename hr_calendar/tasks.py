# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/hr_calendar/tasks.py
"""
H24 (S141). Periodic tasks of the hr_calendar app.

---

H24 (S141). Tareas periódicas de la app hr_calendar: recordatorios por
WhatsApp de fichajes olvidados.
"""
import logging

from celery import shared_task

logger = logging.getLogger(__name__)

COMPANY_SLUG = "grupo-alvarez"


@shared_task(name="hr_calendar.tasks.send_clock_reminders_task")
def send_clock_reminders_task():
    """
    Send the forgotten clock-in/out reminders due now (idempotent).

    ---

    Envía los recordatorios de entrada/salida sin fichar que tocan
    ahora. Idempotente: un recordatorio ya enviado no se repite
    (ClockReminder).
    """
    from hr_calendar.clock_reminders import send_clock_reminders
    from ivr_config.models import Company

    company = Company.objects.filter(slug=COMPANY_SLUG).first()
    if company is None:
        logger.warning("Recordatorios de fichaje: no existe la empresa "
                       "%s.", COMPANY_SLUG)
        return {}
    return send_clock_reminders(company, log=logger.info)
