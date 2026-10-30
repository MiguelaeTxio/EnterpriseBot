# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/budgets/tasks.py
"""
Celery tasks of the budgets application.

H37 (S142): evaluation of the services uploaded from a folder.

---

Tareas Celery de la aplicación de presupuestos.

H37 (S142): valoración de los servicios subidos desde una carpeta en
la pestaña Servicios (lectura del documento con Gemini, ruta con
Google y presupuesto), una tarea por documento para no bloquear la
página.
"""
from celery import shared_task


@shared_task(name="budgets.tasks.evaluate_service_task")
def evaluate_service_task(evaluation_pk):
    """
    Evaluate one uploaded service.

    ---

    Valora un servicio subido (`budgets.service_evaluation.evaluate`).
    """
    from budgets.service_evaluation import evaluate

    evaluate(evaluation_pk)
