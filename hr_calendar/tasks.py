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


@shared_task(name="hr_calendar.tasks.read_payslip_batch_task")
def read_payslip_batch_task(batch_id):
    """
    S149. Reads the PDFs of a payslip delivery and notifies who started it.

    ---

    Lee en segundo plano los PDF de una entrega de nóminas
    (hr_calendar/payslip_delivery.read_batch) y avisa por WhatsApp a
    quien la inició.
    """
    from hr_calendar.models import PayslipBatch
    from hr_calendar.payslip_delivery import read_batch

    batch = PayslipBatch.objects.filter(
        pk=batch_id, status=PayslipBatch.Status.READING).first()
    if batch is None:
        return "sin entrega que leer"
    read_batch(batch)
    return "leída %s" % batch_id


@shared_task(name="hr_calendar.tasks.send_payslip_batch_task")
def send_payslip_batch_task(batch_id):
    """
    S149. Files and sends by WhatsApp the approved payslips of a batch.

    ---

    Archiva en la ficha de cada trabajador y le manda por WhatsApp las
    nóminas con visto bueno de una entrega
    (hr_calendar/payslip_delivery.send_batch).
    """
    from hr_calendar.models import PayslipBatch
    from hr_calendar.payslip_delivery import send_batch

    batch = PayslipBatch.objects.filter(
        pk=batch_id, status=PayslipBatch.Status.SENDING).first()
    if batch is None:
        return "sin entrega que enviar"
    send_batch(batch)
    return "enviada %s" % batch_id


@shared_task(name="hr_calendar.tasks.retry_payslip_whatsapp_task")
def retry_payslip_whatsapp_task(batch_id):
    """
    S149. Sends again the WhatsApp of the payslips filed without it.

    ---

    Reintenta el WhatsApp de las nóminas de una entrega que se
    archivaron sin que saliera (p. ej. la plantilla aún sin aprobar).
    """
    from hr_calendar.models import PayslipBatch
    from hr_calendar.payslip_delivery import retry_whatsapp

    batch = PayslipBatch.objects.filter(pk=batch_id).first()
    if batch is None:
        return "sin entrega"
    return "reenviadas %s" % retry_whatsapp(batch)


@shared_task(name="hr_calendar.tasks.read_albaran_batch_task")
def read_albaran_batch_task(batch_id):
    """
    S149. Reads a worker's albaranes with Gemini and compares each day.

    ---

    Lee con Gemini los albaranes de una carga y compara cada día con
    los fichajes (hr_calendar/albaran_check.read_batch).
    """
    from hr_calendar.albaran_check import read_batch
    from hr_calendar.models import AlbaranBatch

    batch = AlbaranBatch.objects.filter(
        pk=batch_id, status=AlbaranBatch.Status.READING).select_related(
        "person", "company", "created_by").first()
    if batch is None:
        return "sin carga que leer"
    try:
        read_batch(batch)
    except Exception as exc:  # noqa: BLE001 -- queda anotado en la carga
        logger.exception("# Albaranes %s: fallo al leer", batch_id)
        AlbaranBatch.objects.filter(pk=batch_id).update(
            status=AlbaranBatch.Status.READY, error=str(exc)[:500])
    return "leída %s" % batch_id


@shared_task(name="hr_calendar.tasks.resume_albaran_batches_task")
def resume_albaran_batches_task():
    """
    S149. Resumes the albarán readings cut half way (e.g. a deploy).

    ---

    Reanuda las lecturas de albaranes que se cortaron a medias (un
    reinicio de Celery en un despliegue): albaran_check.resume_stalled.
    """
    from hr_calendar.albaran_check import resume_stalled

    resumed = resume_stalled()
    return "reanudadas %s" % (resumed or "ninguna")
