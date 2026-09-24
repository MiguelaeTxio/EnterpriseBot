# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/fleet/migrations/0008_asistencia_from_excel_s117.py
"""
S117 (H30). La delegación de ASISTENCIA según su lista real
(MAQUINAS_ASISTENCIA.xlsx, "MAQUINAS DE ASISTENCIA Y GRUAS GRANADA",
entregada por Miguel Ángel; 34 códigos, P23 repetido en el original).

Reglas, verbatim de Miguel Ángel: "Este Excel contiene todas las
máquinas activas de asistencia. Si en nuestra base de datos tenemos una
máquina de la familia asistencia que no se encuentra en el Excel,
tenemos que darla de baja. Si una máquina de nuestra base de datos no
figura en la familia de asistencia, pero aparece en el Excel de
asistencia, hay que pasarla a la familia de asistencia."

1. Máquina del Excel -> family="ASISTENC" (valor real de la familia en
   Centros de gasto) y activa.
2. Máquina con family="ASISTENC" que NO está en el Excel -> inactiva.

Decisiones de Miguel Ángel tras la revisión (5 de ASISTENC fuera del
Excel): "A50, es de asistencia y está activa, confirmado por
Asistencia, A60 es de asistencia, delegación de Loja y está activa" (se
añaden a la lista); "B38, no es de asistencia, la dejamos activa y la
ponemos en las autocargantes" (AUTOCARG, activa); ASIS-VAR ya la dio de
baja él; 3848BZW es la A50 duplicada y se fusiona en su ficha con
merge_machine_duplicate (comando aparte: necesita los modelos reales de
todas las apps que apuntan a una máquina).

Códigos comparados sin guion ni espacios. Irreversible a propósito (la
reversa no hace nada): no hay forma fiable de restaurar la familia y el
estado anteriores de cada máquina.
"""
import re

from django.db import migrations

ASISTENCIA_CODES = {
    "A30", "A39", "A50", "A55", "A60", "A66",
    "B30", "B31", "B35", "B37", "B39", "B40", "B44",
    "G09", "G11", "G12", "G14", "G15", "G16", "G18",
    "P18", "P19", "P20", "P22", "P23", "P24", "P25", "P27",
    "X02", "X06", "X07", "X08", "X09", "X11", "X12", "X14",
}
FAMILY = "ASISTENC"


def _norm(code):
    return re.sub(r"[\s\-.]", "", str(code or "")).upper()


def apply_asistencia(apps, schema_editor):
    MachineAsset = apps.get_model("fleet", "MachineAsset")
    for asset in MachineAsset.objects.all():
        if _norm(asset.code) == "B38":
            asset.family = "AUTOCARG"
            asset.is_active = True
            asset.save(update_fields=["family", "is_active"])
            continue
        in_list = _norm(asset.code) in ASISTENCIA_CODES
        if in_list:
            if asset.family != FAMILY or not asset.is_active:
                asset.family = FAMILY
                asset.is_active = True
                asset.save(update_fields=["family", "is_active"])
        elif (asset.family or "").upper() == FAMILY and asset.is_active:
            asset.is_active = False
            asset.save(update_fields=["is_active"])


class Migration(migrations.Migration):

    dependencies = [
        ("fleet", "0007_merge_huelva_logistica_into_dependencias_s117"),
    ]

    operations = [
        migrations.RunPython(apply_asistencia, migrations.RunPython.noop),
    ]
