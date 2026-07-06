# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/workorder_spare_parts/apps.py
"""
App configuration for workorder_spare_parts.

Puente entre los partes digitales de trabajo (work_order_processor) y
el almacén digital de repuestos (spare_parts). Aloja el CRUD del
catálogo de SparePartEntry fuera del circuito de albaranes, y (H10
Paso 4, siguiente bloque) los endpoints de consumo que sustituirán la
entrada de texto libre de repuestos en el formulario de parte de
trabajo. Sin modelos propios -- reutiliza SparePartEntry/StockMovement
de spare_parts, igual que ai_services no tiene modelos propios.
---
Configuración de la app workorder_spare_parts.

Bridge between digital work orders (work_order_processor) and the
digital spare parts warehouse (spare_parts). Hosts the SparePartEntry
catalog CRUD outside the delivery-note circuit, and (H10 Paso 4, next
block) the consumption endpoints that will replace the free-text
spare-part entry in the work order form. No models of its own --
reuses SparePartEntry/StockMovement from spare_parts, same pattern as
ai_services.
"""
from django.apps import AppConfig


class WorkorderSparePartsConfig(AppConfig):
    """
    App configuration for workorder_spare_parts.
    ---
    Configuración de la app workorder_spare_parts.
    """

    default_auto_field = 'django.db.models.BigAutoField'
    name = 'workorder_spare_parts'
    verbose_name = 'Repuestos en Partes de Trabajo'
