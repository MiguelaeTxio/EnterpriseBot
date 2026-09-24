# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/fleet/migrations/0007_merge_huelva_logistica_into_dependencias_s117.py
"""
S117 (H30). Decisión de Miguel Ángel: "la familia Huelva la vamos a meter
dentro de dependencias. Anulamos Huelva y la ponemos dentro de
dependencias y sus activos los pasamos a dependencias. La familia
logística la pasamos también a dependencias."

Valores reales antes de la migración (consulta de solo lectura S117):
HUELVA 2 máquinas, LOGÍSTICA 1, DEPENDENCIAS 2. Tras ella, DEPENDENCIAS
5 y las dos familias desaparecen (ya no les queda ninguna máquina).
Comparación sin distinguir mayúsculas y con y sin tilde (LOGÍSTICA /
LOGISTICA).

Irreversible a propósito: una vez fusionadas no hay forma fiable de
saber qué máquina venía de qué familia (la reversa no hace nada).
"""
from django.db import migrations
from django.db.models import Q


def merge_into_dependencias(apps, schema_editor):
    MachineAsset = apps.get_model("fleet", "MachineAsset")
    MachineAsset.objects.filter(
        Q(family__iexact="HUELVA")
        | Q(family__iexact="LOGÍSTICA")
        | Q(family__iexact="LOGISTICA")
    ).update(family="DEPENDENCIAS")


class Migration(migrations.Migration):

    dependencies = [
        ("fleet", "0006_machineasset_excel_fields"),
    ]

    operations = [
        migrations.RunPython(merge_into_dependencias, migrations.RunPython.noop),
    ]
