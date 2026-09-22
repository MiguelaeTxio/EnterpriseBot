# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/worksites/apps.py
"""
App configuration for worksites (H31 -- S115).

Modelo de Obra, pensado desde el origen para ser el centro de una
red de modelos relacionados (Cliente, Proveedor, facturación,
albaranes, DECA) que todavía no existen -- ver deuda técnica 4.23 del
documento maestro para el contexto completo y la decisión explícita
de Miguel Ángel de crear ya esta tabla, con vistas a esa expansión
futura, en vez de esperar al diseño completo.

Por eso los campos de "cliente" y "empresa gestora" empiezan como
texto libre / FK a lo que ya existe (mismo patrón que
`PersonIdentity.employer_company` antes de tener `CompanyFiscalProfile`
real) -- se sustituirán por FKs a modelos Cliente/Proveedor reales
cuando esos se diseñen, sin tener que rehacer Worksite desde cero.

---

Configuración de la app worksites (H31 -- S115).
"""
from django.apps import AppConfig


class WorksitesConfig(AppConfig):
    """
    AppConfig for the worksites application.
    ---
    AppConfig de la aplicación worksites.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "worksites"
    verbose_name = "Obras"
