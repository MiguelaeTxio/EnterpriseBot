# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/fleet/migrations/0009_active_from_owner_pdf_s117.py
"""
S117 (H30). Máquinas ACTIVAS según el listado oficial del programa de
gestión de la empresa entregado por uno de los dueños (Alejandro Sergio
Álvarez Díaz): "Maquinaria de Empresas", filtro "Bajas: No", 24/09/2026
-- 319 códigos, todos con ficha en Centros de gasto.

Decisión de Miguel Ángel: "el PDF manda, a excepción de empresa y
personal [...] hay dos códigos o cuatro códigos de EMP que no están en
la familia de empresa, están en móviles, están en plataformas [...] se
deben de quedar también. Porque son donde van los gastos de los
mecánicos [...] Y luego lo que es residuos, ventas, documentarios [...]
pilotes, reparación, eso lo dejamos inactivos, que lo he puesto yo
inactivo hoy."

1. Código del PDF -> activa, SALVO las fichas administrativas que el
   programa de gestión trae como "máquinas" y Miguel Ángel dejó
   inactivas hoy (RESIDUOS, VENTA, C, DOCUMEN, E.M., LARIOS, M01, NB,
   PILOTES, REPARACI, U) y ASIS-VAR (dada de baja por él hoy).
2. Código que NO está en el PDF -> inactiva, SALVO los centros de coste
   internos: cualquier código que empieza por "EMPRESA_" (sea cual sea
   su familia: EMPRESA_TALLER_MECANICO en MOVILES,
   EMPRESA_TALLER_ELEVACION en PLATAFOR...) y "PERSONAL".
Sustituye a las reglas anteriores del día (Excel de Yolanda, listado
del parque, reglas de carpetas), cuyos comandos se retiran en el mismo
commit. Irreversible a propósito (la reversa no hace nada).
"""
import re

from django.db import migrations

OWNER_ACTIVE = {
    "0168DZS", "0268JWD", "1123HWG", "1245LJB", "1884JBM", "2030JVK",
    "2034JVK", "2488HRS", "2655KSF", "2667LMK", "3968HWN", "4089LDP",
    "4400JTD", "4542KGD", "5462FJP", "6397HHL", "6399KFF", "6951HZS",
    "7308BWM", "8029BZV", "8197HSG", "8401NDM", "9656", "9843KBZ",
    "A29", "A30", "A33", "A34", "A35", "A36", "A39", "A43", "A44",
    "A45", "A46", "A49", "A50", "A52", "A53", "A55", "A56", "A57",
    "A58", "A59", "A60", "A61", "A62", "A63", "A64", "A65", "A66",
    "A67", "A68", "A69", "ADOLFO", "ADOLFO2", "ALE", "ASISVAR", "B12",
    "B23", "B24", "B26", "B27", "B28", "B29", "B30", "B31", "B32",
    "B33", "B34", "B35", "B36", "B37", "B38", "B39", "B40", "B41",
    "B42", "B43", "B44", "B45", "B46", "B47", "B48", "C", "C20",
    "CONT1", "CONT2", "CONT3", "CONT4", "CUBA1", "DOCUMEN", "E.M.",
    "FURGLAR", "G01", "G02", "G03", "G07", "G08", "G09", "G10", "G11",
    "G12", "G14", "G15", "G16", "H01", "H02", "H04", "H06", "H07",
    "H08", "H09", "H11", "JUANITA", "JUMPER", "LARIOS", "LILI", "M01",
    "NB", "NEMO", "P09", "P14", "P16", "P17", "P18", "P19", "P20",
    "P21", "P22", "P23", "P24", "P25", "P26", "P27", "PAOLA", "PILOTES",
    "R06", "R08", "R11", "R12", "R14", "R16", "R17", "R19", "R20",
    "R21", "R22", "REPARACI", "RESIDUOS", "S01", "S02", "S03", "S04",
    "S05", "S06", "S07", "S08", "S09", "S10", "S11", "S12", "S13",
    "S14", "S15", "S18", "S19", "T05", "T08", "T09", "T10", "T11",
    "T13", "T14", "T15", "T16", "T17", "T18", "T20", "T21", "T22",
    "T23", "T24", "T25", "T26", "T27", "T28", "T29", "T30", "TANQUETA",
    "U", "V02", "V03", "V04", "V05", "V07", "V08", "V09", "V11",
    "VENTA", "X01", "X02", "X06", "X07", "X08", "X09", "X10", "X11",
    "X12", "X14", "X15", "Z03", "Z04", "Z06", "Z08", "Z09", "Z100",
    "Z101", "Z102", "Z103", "Z104", "Z105", "Z106", "Z107", "Z108",
    "Z109", "Z110", "Z111", "Z112", "Z113", "Z114", "Z115", "Z116",
    "Z117", "Z118", "Z119", "Z120", "Z121", "Z122", "Z123", "Z124",
    "Z125", "Z126", "Z127", "Z128", "Z129", "Z130", "Z131", "Z132",
    "Z133", "Z134", "Z135", "Z136", "Z137", "Z138", "Z14", "Z15", "Z17",
    "Z19", "Z20", "Z22", "Z24", "Z25", "Z26", "Z28", "Z29", "Z31",
    "Z32", "Z37", "Z39", "Z40", "Z42", "Z43", "Z44", "Z45", "Z46",
    "Z47", "Z48", "Z49", "Z50", "Z51", "Z52", "Z53", "Z54", "Z55",
    "Z56", "Z57", "Z58", "Z59", "Z60", "Z61", "Z62", "Z63", "Z64",
    "Z65", "Z66", "Z68", "Z69", "Z71", "Z72", "Z73", "Z77", "Z78",
    "Z79", "Z82", "Z83", "Z84", "Z85", "Z88", "Z89", "Z91", "Z92",
    "Z93", "Z94", "Z95", "Z96", "Z97", "Z98", "Z99"
}
ALWAYS_INACTIVE = {
    "RESIDUOS", "VENTA", "C", "DOCUMEN", "E.M.", "LARIOS", "M01", "NB",
    "PILOTES", "REPARACI", "U", "ASISVAR",
}


def _norm(code):
    return re.sub(r"[\s\-]", "", str(code or "")).upper()


def _is_internal_cost_centre(code):
    upper = str(code or "").strip().upper()
    return upper.startswith("EMPRESA_") or upper == "PERSONAL"


def apply_owner_pdf(apps, schema_editor):
    MachineAsset = apps.get_model("fleet", "MachineAsset")
    for asset in MachineAsset.objects.all():
        key = _norm(asset.code)
        if _is_internal_cost_centre(asset.code):
            should_be_active = True
        elif key in ALWAYS_INACTIVE:
            should_be_active = False
        else:
            should_be_active = key in OWNER_ACTIVE
        if asset.is_active != should_be_active:
            asset.is_active = should_be_active
            asset.save(update_fields=["is_active"])


class Migration(migrations.Migration):

    dependencies = [
        ("fleet", "0008_asistencia_from_excel_s117"),
    ]

    operations = [
        migrations.RunPython(apply_owner_pdf, migrations.RunPython.noop),
    ]
