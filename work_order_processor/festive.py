# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/work_order_processor/festive.py
"""
Festive hours of a parte (S133).

---

Horas festivas de un parte (S133). Miguel Ángel: "no son ni horas
extras ni horas ordinarias, son horas festivas y las pagan a otro
precio" (caso real: Sampaio trabajó un domingo). Un parte es festivo
con el mismo criterio que ya permite cerrarlo con menos de 8 horas
(H07, S133): sábado, domingo o festivo del calendario laboral de la
base del trabajador (budgets.services._is_holiday). Todas sus horas son
festivas y ninguna cuenta como hora extra.
"""
from decimal import Decimal

STANDARD_DAY_HOURS = Decimal("8")


def is_festive(work_date, company_user):
    """
    Whether the parte's day is festive for its worker.

    ---

    Si el día del parte es festivo para su trabajador (sábado, domingo
    o festivo de su base).
    """
    if work_date is None:
        return False
    from budgets.services import _is_holiday

    return _is_holiday(work_date, getattr(company_user, "base", None))


def split_hours(total_hours, festive):
    """
    (extra hours, festive hours) of a day with total_hours worked.

    ---

    (horas extra, horas festivas) de un día con total_hours trabajadas:
    en festivo todas son festivas y no hay extra; si no, extra es lo que
    pasa de 8.
    """
    total = total_hours or Decimal("0")
    if festive:
        return Decimal("0"), total
    return max(Decimal("0"), total - STANDARD_DAY_HOURS), Decimal("0")
