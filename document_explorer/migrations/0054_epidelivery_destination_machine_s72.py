# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0054_epidelivery_destination_machine_s72.py
"""
H30 (S72). Campo destination_machine en EpiDelivery -- FK nula a
fleet.MachineAsset ("Centro de Gasto"). Decisión de Miguel Ángel,
explicada primero en S69 y reconfirmada en S72 (verbatim, S69):
"tratarlos como EPIs y van a llevar una asignación a centro de
gasto... pueden ir hacia máquina, pueden ir hacia taller, pueden ir
hacia almacén, pueden ir hacia plataformas... así que van centro de
gasto y personal, a ambos, con su fecha de entrega."

Nulo para la inmensa mayoría de EPIs (entrega personal sin CdG de
destino) -- relleno solo para los que sí llevan asignación a CdG,
empezando por botiquines (ver 0055_seed_botiquin_catalog_item_s72).
"""
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0053_seed_epi_item_catalog_s71_s72"),
        ("fleet", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="epidelivery",
            name="destination_machine",
            field=models.ForeignKey(
                null=True,
                blank=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="epi_deliveries",
                to="fleet.machineasset",
                verbose_name="Centro de gasto de destino",
                help_text=(
                    "Nulo para la mayoría de EPIs (entrega personal "
                    "sin CdG de destino). Relleno cuando el EPI va "
                    "asignado a un Centro de Gasto además de a la "
                    "persona -- p. ej. botiquines, que pueden ir a "
                    "una máquina, un taller, un almacén o una "
                    "plataforma (Miguel Ángel, S69/S72)."
                ),
            ),
        ),
    ]
