# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/budgets/signals.py
"""
Signals of the budgets app.

H37 (S138): after every save of a work order, the pickup and the
destination are geocoded again if their address changed
(budgets.service_geocode). It runs after the commit and never breaks
the save; with the address unchanged it does not call Google.

---

Señales de la app budgets. Tras cada guardado de una orden, se
vuelven a geocodificar la recogida y el destino si cambió su dirección.
Corre tras el commit y nunca rompe el guardado; con la dirección igual
no llama a Google.
"""
from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver


@receiver(post_save, sender="budgets.WorkOrderAssistance")
def geocode_work_order(sender, instance, raw=False, **kwargs):
    """
    Geocode the changed points of a saved work order.

    ---

    Geocodifica los puntos cambiados de una orden guardada.
    """
    if raw:
        return
    from budgets.service_geocode import ensure_points_by_pk

    work_order_pk = instance.pk
    transaction.on_commit(lambda: ensure_points_by_pk(work_order_pk))
