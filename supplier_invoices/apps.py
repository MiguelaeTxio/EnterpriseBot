# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/supplier_invoices/apps.py
"""
App configuration for supplier_invoices.

---

H28 (S151, sesión invasora). Pipeline del almacén para las facturas de
proveedor que el agente del PC de Ani sube al cubo, a FACTURACION
PROVEEDORES: se leen, se cotejan con los albaranes del taller, ponen
al día el almacén y se cruzan con los partes de trabajo. En el panel:
Almacén > Facturas de proveedor. App propia (y no dentro de
document_explorer) para que sus migraciones no choquen con las de las
sesiones en paralelo.
"""
from django.apps import AppConfig


class SupplierInvoicesConfig(AppConfig):
    """
    App configuration for supplier_invoices.

    ---

    Configuración de la app supplier_invoices.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "supplier_invoices"
    verbose_name = "Facturas de proveedor"
