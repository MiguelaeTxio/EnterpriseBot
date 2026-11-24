# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/cae_mail/tasks.py
"""
Celery tasks of the CAE notices read from the mail agent uploads.

---

H31 (S156). Tareas Celery de los avisos de plataformas CAE: el barrido
de CORREOS DOCUMENTACION/NUEVOS y la lectura de cada aviso (Gemini).
"""
import logging

from celery.contrib.django.task import DjangoTask

from enterprise_core.celery import app

logger = logging.getLogger(__name__)

CAE_MAIL_FINAL_ATTEMPT = 5
CAE_MAIL_RETRY_BASE = 60


@app.task(base=DjangoTask, bind=True, max_retries=CAE_MAIL_FINAL_ATTEMPT)
def process_cae_mail_task(self, mail_id: int) -> str:
    """
    Read one CAE notice with Gemini.

    ---

    Lee un aviso CAE con Gemini. Gemini saturado se reintenta con
    espera creciente; en el último intento queda como error visible.
    """
    from ai_services.gemini_client import backoff_delay

    from .mail_service import TransientMailError, process_mail

    final = self.request.retries >= CAE_MAIL_FINAL_ATTEMPT
    try:
        return process_mail(mail_id, final=final)
    except TransientMailError:
        raise self.retry(countdown=backoff_delay(
            self.request.retries + 1, CAE_MAIL_RETRY_BASE))


@app.task(base=DjangoTask, bind=True, max_retries=0)
def sweep_cae_mails_task(self) -> int:
    """
    Register the mails the mail agent left in CORREOS DOCUMENTACION.

    ---

    Registra los correos que el agente de correos ha dejado en
    CORREOS DOCUMENTACION/NUEVOS y los manda a leer.
    """
    from .mail_service import sweep_new_mails

    registered = sweep_new_mails()
    if registered:
        logger.info("# [CAE] %d aviso(s) nuevos registrados.", registered)
    return registered
