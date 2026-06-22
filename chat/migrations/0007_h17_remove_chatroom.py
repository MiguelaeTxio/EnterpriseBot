# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/chat/migrations/0007_h17_remove_chatroom.py
"""
H17 — Paso 1: Eliminate ChatRoom, ChatMessage and BreakdownConversationTurn.
Replace BreakdownTicket.room (FK → ChatRoom) with BreakdownTicket.company
(FK → Company) for direct company scoping.

Steps:
  1. Add BreakdownTicket.company (nullable, populated from room.company).
  2. Populate company from room__company for all existing tickets.
  3. Remove BreakdownTicket.room FK.
  4. Alter BreakdownTicket.company to NOT NULL.
  5. Drop BreakdownConversationTurn table.
  6. Drop ChatMessage table (CASCADE from ChatRoom drop covers messages,
     but explicit removal is safer and documents intent).
  7. Drop ChatRoom M2M tables and constraints, then the table itself.
---
H17 — Paso 1: Eliminar ChatRoom, ChatMessage y BreakdownConversationTurn.
Sustituir BreakdownTicket.room (FK → ChatRoom) por BreakdownTicket.company
(FK → Company) para acceso directo a la empresa.
"""

import django.db.models.deletion
from django.db import migrations, models


def populate_company_from_room(apps, schema_editor):
    """
    Copies company_id from the related ChatRoom to each BreakdownTicket.
    ---
    Copia company_id de la ChatRoom relacionada a cada BreakdownTicket.
    """
    BreakdownTicket = apps.get_model("chat", "BreakdownTicket")
    for ticket in BreakdownTicket.objects.select_related("room__company").all():
        if ticket.room_id and ticket.room.company_id:
            ticket.company_id = ticket.room.company_id
            ticket.save(update_fields=["company_id"])


class Migration(migrations.Migration):

    dependencies = [
        ("chat", "0006_breakdownticket_fault_location_and_more"),
        ("ivr_config", "0033_companyuser_is_intensive_override"),
    ]

    operations = [
        # Step 1 — Add company FK as nullable first.
        # Paso 1 — Añadir FK company como nullable primero.
        migrations.AddField(
            model_name="breakdownticket",
            name="company",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="breakdown_tickets",
                to="ivr_config.company",
                verbose_name="Empresa",
                help_text="Empresa a la que pertenece este ticket de avería.",
            ),
        ),

        # Step 2 — Populate company_id from room__company for all existing tickets.
        # Paso 2 — Rellenar company_id desde room__company en todos los tickets.
        migrations.RunPython(
            populate_company_from_room,
            reverse_code=migrations.RunPython.noop,
        ),

        # Step 3 — Remove room FK from BreakdownTicket.
        # Paso 3 — Eliminar FK room de BreakdownTicket.
        migrations.RemoveField(
            model_name="breakdownticket",
            name="room",
        ),

        # Step 4 — Make company NOT NULL now that all rows are populated.
        # Paso 4 — Hacer company NOT NULL ahora que todas las filas están pobladas.
        migrations.AlterField(
            model_name="breakdownticket",
            name="company",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="breakdown_tickets",
                to="ivr_config.company",
                verbose_name="Empresa",
                help_text="Empresa a la que pertenece este ticket de avería.",
            ),
        ),

        # Step 5 — Drop BreakdownConversationTurn (FK to BreakdownTicket).
        # Paso 5 — Eliminar BreakdownConversationTurn (FK a BreakdownTicket).
        migrations.DeleteModel(
            name="BreakdownConversationTurn",
        ),

        # Step 6 — Drop ChatMessage (FK to ChatRoom).
        # Paso 6 — Eliminar ChatMessage (FK a ChatRoom).
        migrations.DeleteModel(
            name="ChatMessage",
        ),

        # Step 7 — Drop ChatRoom (M2M tables are dropped automatically by Django).
        # Paso 7 — Eliminar ChatRoom (las tablas M2M las elimina Django automáticamente).
        migrations.DeleteModel(
            name="ChatRoom",
        ),
    ]
