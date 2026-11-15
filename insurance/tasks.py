# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/insurance/tasks.py
"""
Celery task of the insurance reports.
---
Tarea de Celery de los informes de seguros.
"""
from celery import shared_task


@shared_task(name="insurance.tasks.run_insurance_report_task")
def run_insurance_report_task(report_id):
    """
    One step of a report; re-queues itself until it is done.
    ---
    Un paso del informe (insurance.service.run_step); se vuelve a encolar
    hasta terminar, para no ocupar el worker de seguido.
    """
    from insurance.service import run_step

    if run_step(report_id):
        run_insurance_report_task.apply_async((report_id,), countdown=2)
        return "sigue %s" % report_id
    return "fin %s" % report_id
