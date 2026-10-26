# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/fleet/signals.py
"""
H30 (S137). Signals of the fleet app.

---

H30 (S137). Señales de la app fleet: al guardar un bloque de parte, o
el parte (puede cambiar su fecha), se rehace su lectura de km y horas
(`fleet/work_order_readings.py`). Señales y no llamadas en las vistas,
porque los bloques se guardan desde muchos sitios del parte digital.
"""
from django.db.models.signals import post_save
from django.dispatch import receiver

from fleet.work_order_readings import sync_line_reading
from work_order_processor.models import WorkOrderEntry
from work_order_processor.models import WorkOrderEntryLine


@receiver(post_save, sender=WorkOrderEntryLine,
          dispatch_uid="fleet_work_order_line_reading")
def work_order_line_saved(sender, instance, **kwargs):
    """
    Redo the reading of a saved work order block.

    ---

    Rehace la lectura del bloque de parte guardado.
    """
    sync_line_reading(instance)


@receiver(post_save, sender=WorkOrderEntry,
          dispatch_uid="fleet_work_order_entry_reading")
def work_order_entry_saved(sender, instance, **kwargs):
    """
    Redo the readings of a saved work order page (its date may change).

    ---

    Rehace las lecturas de los bloques de una página de parte guardada:
    si cambia la fecha, cambia la de sus lecturas.
    """
    if kwargs.get("created"):
        return
    for line in instance.lines.select_related("entry", "machine_asset"):
        sync_line_reading(line)
