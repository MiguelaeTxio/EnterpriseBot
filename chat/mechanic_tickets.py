# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/chat/mechanic_tickets.py
"""
H14 (desvío desde H30, S131). Open breakdown tickets of each mechanic.

---

H14 (desvío desde H30, S131). Tickets de avería abiertos de cada
mecánico. Miguel Ángel: un mecánico que ha trabajado en un ticket de
avería no cerrado sale como ocupado y con las máquinas en las que está;
lista por mecánico de sus tickets abiertos, y en cada uno cerrarlo a
mano sin pasar por el parte de trabajo ("Pablo, ocupado, con 4 tickets
abiertos, se repasan uno a uno").

Un ticket es de un mecánico si tiene alguna línea de parte suya
(`WorkOrderEntryLine.breakdown_ticket`, parte subido por él) o si está
asignado a él (`assigned_to`, lo que ya marcaba "Ocupado" antes de
S131). Solo cuentan los tickets no cerrados.
"""
from django.db.models import Count, Max


def open_tickets_by_mechanic(company):
    """
    {company_user_id: [ticket, ...]} of non-closed tickets.

    ---

    Tickets no cerrados de cada mecánico, del trabajo más reciente al
    más antiguo. Cada ticket lleva `last_work_date` (último día que
    trabajó en él ese mecánico, o None si solo está asignado),
    `worked_lines` y `is_assigned`. Tres consultas para toda la
    empresa, nunca una por mecánico.
    """
    from chat.models import BreakdownTicket
    from work_order_processor.models import WorkOrderEntryLine

    open_tickets = {
        ticket.pk: ticket
        for ticket in BreakdownTicket.objects.filter(
            company=company,
        ).exclude(
            status=BreakdownTicket.STATUS_CLOSED,
        ).select_related("machine")
    }
    if not open_tickets:
        return {}
    worked = (
        WorkOrderEntryLine.objects.filter(
            breakdown_ticket_id__in=open_tickets.keys(),
            entry__work_order__uploaded_by__isnull=False,
        )
        .values("entry__work_order__uploaded_by_id", "breakdown_ticket_id")
        .annotate(last=Max("entry__work_date"), lines=Count("id"))
    )
    by_mechanic = {}
    for row in worked:
        mechanic_id = row["entry__work_order__uploaded_by_id"]
        by_mechanic.setdefault(mechanic_id, {})[row["breakdown_ticket_id"]] = (
            row["last"], row["lines"],
        )
    for ticket in open_tickets.values():
        if ticket.assigned_to_id:
            by_mechanic.setdefault(ticket.assigned_to_id, {}).setdefault(
                ticket.pk, (None, 0),
            )

    result = {}
    for mechanic_id, tickets in by_mechanic.items():
        items = []
        for ticket_id, (last, lines) in tickets.items():
            source = open_tickets[ticket_id]
            # Copia por mecánico: el mismo ticket puede salir en varios.
            ticket = BreakdownTicket(**{
                field.attname: getattr(source, field.attname)
                for field in BreakdownTicket._meta.concrete_fields
            })
            ticket.machine = source.machine
            ticket.last_work_date = last
            ticket.worked_lines = lines
            ticket.is_assigned = source.assigned_to_id == mechanic_id
            ticket.machine_label = (
                source.machine.code if source.machine
                else (source.machine_raw or "Sin máquina")
            )
            items.append(ticket)
        items.sort(
            key=lambda t: (t.last_work_date is not None, t.last_work_date),
            reverse=True,
        )
        result[mechanic_id] = items
    return result
