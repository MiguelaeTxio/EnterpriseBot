# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/budgets/breadcrumbs.py
"""
H37 (S132). Breadcrumbs of the assistance service pages.

---

H37 (S132). Migas de pan de las páginas del servicio de asistencia.
Miguel Ángel, S132: los botones "Volver" con una URL fija mandaban
siempre a los presupuestos de asistencia, estuviera uno donde
estuviera; "los botones volver que construyamos que sean con
breadcrumb" (directriz 4.25 del documento maestro).

La miga raíz es la página Servicios para quien la puede ver (ADMIN y
supervisor de asistencia) y el asistente de presupuestos para el
operario de asistencia. El conductor no tiene ninguna: solo ve su
albarán.
"""
from django.urls import reverse

SERVICES_ROLES = ("ADMIN", "ASSIST_SUPERVISOR")
WORK_ORDER_ROLES = ("ADMIN", "ASSISTANCE", "ASSIST_SUPERVISOR")


def assistance_breadcrumbs(company_user, work_order=None, unit=None,
                           current=None):
    """
    Breadcrumb trail as a list of {"label", "url"} (last one without url).

    ---

    Migas como lista de {"label", "url"}; la última, la página actual,
    va sin enlace. `work_order` y `unit` añaden sus migas intermedias;
    `current` es el título de la página actual cuando no es la propia
    orden o unidad.
    """
    role = company_user.role
    crumbs = []
    if role in SERVICES_ROLES:
        crumbs.append({
            "label": "Servicios", "url": reverse("budgets:services_hub"),
        })
    elif role in WORK_ORDER_ROLES:
        crumbs.append({
            "label": "Presupuestos", "url": reverse("budgets:wizard"),
        })
    if work_order is not None and role in WORK_ORDER_ROLES:
        crumbs.append({
            "label": "Orden %s" % work_order.work_order_number,
            "url": reverse("budgets:work_order_detail", args=[work_order.pk]),
        })
    if unit is not None:
        crumbs.append({
            "label": "Albarán %s-%02d" % (
                unit.work_order.work_order_number, unit.unit_number,
            ),
            "url": reverse("budgets:work_order_albaran", args=[unit.pk]),
        })
    if current:
        crumbs.append({"label": current, "url": ""})
    elif crumbs:
        crumbs[-1] = {"label": crumbs[-1]["label"], "url": ""}
    return crumbs


def parent_url(crumbs):
    """
    URL of the page above the current one, or "".

    ---

    URL de la página de arriba de la actual (para "Cancelar"), o "".
    """
    linked = [crumb["url"] for crumb in crumbs if crumb["url"]]
    return linked[-1] if linked else ""
