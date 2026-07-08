# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/delivery_notes/apps.py
"""
App configuration for delivery_notes.

CRUD de administración de albaranes de proveedor (H10, gap señalado
por Miguel Ángel 2026-07-08): listado, vista/edición y borrado de
DeliveryNote para ADMIN, SUPERVISOR y WORKSHOPBOSS, vividendo en
"Administración" del panel -- separado del flujo de subida/revisión
pre-confirmación de spare_parts (Mecánicos) para no seguir engordando
spare_parts/views.py. Sin modelos propios -- reutiliza
DeliveryNote/DeliveryNoteLine de spare_parts, mismo patrón que
workorder_spare_parts.
---
Configuración de la app delivery_notes.

Admin CRUD for supplier delivery notes (H10, gap flagged by Miguel
Ángel 2026-07-08): list, view/edit and delete DeliveryNote for ADMIN,
SUPERVISOR and WORKSHOPBOSS, living in the panel's "Administración"
section -- separate from spare_parts' (Mecánicos) upload/pre-confirm
review flow to avoid further bloating spare_parts/views.py. No models
of its own -- reuses DeliveryNote/DeliveryNoteLine from spare_parts,
same pattern as workorder_spare_parts.
"""
from django.apps import AppConfig


class DeliveryNotesConfig(AppConfig):
    """
    App configuration for delivery_notes.
    ---
    Configuración de la app delivery_notes.
    """

    default_auto_field = 'django.db.models.BigAutoField'
    name = 'delivery_notes'
    verbose_name = 'Administración de Albaranes'
