# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/warehouse_inventory/tasks.py
"""
Celery task of the photo-based warehouse inventory.

---

H10 (S151, sesión invasora). Lectura con Gemini de cada foto del
inventario del almacén (tarda): se hace en segundo plano para que
Miguel Ángel siga haciendo fotos sin esperar.
"""
from celery.contrib.django.task import DjangoTask

from enterprise_core.celery import app

PHOTO_FINAL_ATTEMPT = 5


@app.task(base=DjangoTask, bind=True, max_retries=PHOTO_FINAL_ATTEMPT)
def process_inventory_photo_task(self, photo_id: int) -> str:
    """
    Read one inventory photo with Gemini.

    ---

    Lee una foto del inventario con Gemini y la cruza con el almacén.
    Gemini saturado se reintenta al minuto; en el último intento queda
    como error visible, nunca en silencio.
    """
    from .inventory_service import TransientInventoryError, process_photo

    final = self.request.retries >= PHOTO_FINAL_ATTEMPT
    try:
        return process_photo(photo_id, final=final)
    except TransientInventoryError:
        raise self.retry(countdown=60)
