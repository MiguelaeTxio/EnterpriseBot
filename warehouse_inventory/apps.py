# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/warehouse_inventory/apps.py
"""
App configuration for warehouse_inventory.

---

H10 (S151, sesión invasora). Inventario del almacén por fotos: se baja
al taller con el móvil, se fotografía cada estantería o cajón (etiquetas,
cajas y piezas sueltas), Gemini lee lo que hay y se cruza con el stock
del almacén digital. Las diferencias no tocan el stock hasta que Miguel
Ángel las confirma una a una. App propia para que sus migraciones no
choquen con las de las sesiones en paralelo.
"""
from django.apps import AppConfig


class WarehouseInventoryConfig(AppConfig):
    """
    App configuration for warehouse_inventory.

    ---

    Configuración de la app warehouse_inventory.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "warehouse_inventory"
    verbose_name = "Inventario del almacén por fotos"
