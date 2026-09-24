# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/fleet/family_service.py
"""
S117 -- familias de máquinas (texto libre de MachineAsset.family).

Decisión de Miguel Ángel: "las familias que no tengan ningún activo, las
vamos a desactivar". No hay tabla de familias, así que "desactivar" una
familia es que deja de ofrecerse en los desplegables (filtro del listado
de Centros de gasto y campo Familia de la ficha): la lista se construye
solo con familias que tienen AL MENOS UNA máquina activa. En cuanto una
máquina de esa familia vuelve a estar activa, la familia reaparece sola.
Punto único para el filtro y el formulario, para que nunca diverjan.
"""
from fleet.models import MachineAsset


def active_families(company):
    """
    Sorted distinct non-empty families with at least one active machine.
    ---
    Familias distintas no vacías, ordenadas, con al menos una máquina
    activa.
    """
    return list(
        MachineAsset.objects
        .filter(company=company, is_active=True)
        .exclude(family="")
        .values_list("family", flat=True)
        .distinct()
        .order_by("family")
    )
