# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0032_add_family_otros_documentos.py
"""
H30 (S51). Añade la familia catch-all "Otros documentos"
(OTROS_DOCUMENTOS) a los choices de `DocumentTypeCatalog.family`.

Origen real: al construir el atajo de alta de tipo documental desde
el propio flujo de subida del panel (para cuando el supervisor no
encuentre el tipo en el desplegable), surgió la pregunta de qué
familia asignar a un tipo nuevo que no encajase en ninguna de las 10
existentes (S49). Miguel Angel confirmo que la lista de familias
sigue siendo fija en codigo, no editable en caliente (decision de
S49 sin revertir) -- pero propuso anadir una 11a familia fija,
"Otros documentos", como cajon de sastre explicito para ese caso,
en vez de bloquear el alta o dejar el campo en blanco. Miguel Angel,
verbatim: "mi propuesta seria anadir una familia mas, que seria
otros documentos [...] si en un futuro viesemos que otros documentos
se esta llenando de muchos tipos diferentes del mismo tipo, si se
podria crear una familia mas."

Sin backfill de datos -- ningun tipo existente cambia de familia,
solo se anade la opcion nueva al choices para uso futuro.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0031_merge_ipo_itc"),
    ]

    operations = [
        migrations.AlterField(
            model_name="documenttypecatalog",
            name="family",
            field=models.CharField(
                blank=True,
                choices=[
                    ("CIRCULACION", "Circulación"),
                    ("TECNICA_SEGURIDAD", "Técnica y seguridad"),
                    ("SEGUROS", "Seguros"),
                    ("FINANCIERO", "Financiero y compraventa"),
                    ("BAJAS_MAQUINA", "Bajas de máquina"),
                    ("ADMINISTRATIVO", "Administrativo"),
                    ("IDENTIDAD_PERSONAL", "Identidad y personal (base)"),
                    ("LABORAL", "Laboral"),
                    ("SALUD_BAJAS_PERSONA", "Salud y bajas de persona"),
                    ("PRL_FORMACION", "PRL y formación"),
                    ("OTROS_DOCUMENTOS", "Otros documentos"),
                ],
                max_length=32,
                help_text=(
                    "H30 (S49). Agrupación del acordeón de la ficha "
                    "(en vez de solo Vigentes/Histórico) y base de la "
                    "búsqueda granular ('ver el seguro de esta "
                    "máquina'). Lista fija de choices en código (a "
                    "diferencia de tracks_expiry/ocr_unreliable) "
                    "porque las familias son un puñado estable de "
                    "categorías, no crecen sesión a sesión como los "
                    "tipos documentales -- decisión explícita de "
                    "Miguel Ángel (S49). Distinta de la familia "
                    "normativa de máquina (A/B/Z/H/MK/P/T/V/S de "
                    "fleet.MachineAsset): esta agrupa TIPOS "
                    "DOCUMENTALES para la interfaz, esa otra dice qué "
                    "documentos son obligatorios por tipo de máquina. "
                    "S51: se añade 'Otros documentos' como familia "
                    "catch-all fija número 11 -- Miguel Ángel confirmó "
                    "que la lista sigue cerrada por código (no "
                    "editable en caliente desde el panel), pero si "
                    "aparece un tipo nuevo que no encaje en ninguna de "
                    "las 10 originales, entra aquí en vez de bloquear "
                    "el alta; revisar periódicamente el volumen de "
                    "esta familia -- una acumulación real de un mismo "
                    "tipo dentro de 'Otros documentos' es la señal "
                    "para decidir en sesión, explícitamente, una "
                    "familia nueva de verdad (nunca creación libre "
                    "por un supervisor)."
                ),
                verbose_name="Familia de documento",
            ),
        ),
    ]
