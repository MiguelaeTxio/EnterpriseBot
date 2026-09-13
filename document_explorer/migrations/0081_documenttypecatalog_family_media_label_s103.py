# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0081_documenttypecatalog_family_media_label_s103.py
"""
H31 (S103). Corrige la etiqueta visible de la familia FAMILY_MEDIA:
"Media (imagen, vídeo, audio) — H30 S67" pasa a "Media (imagen,
vídeo, audio)". Detectado al revisar un PDF de dossier real generado
por PersonalDocumentSelectionPdfView: la anotación interna "— H30
S67" (referencia a cuándo se dio de alta la familia en código) se
colaba en un documento potencialmente compartido con un cliente o una
plataforma CAE externa. Es la única entrada de FAMILY_CHOICES con
este tipo de anotación -- las demás diez ya eran texto limpio.

Solo cambia el texto de una choice, nunca el código almacenado
("MEDIA") -- ningún dato existente se ve afectado, no hace falta
backfill.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0080_personidentity_ss_affiliation_number_s100"),
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
                    ("MEDIA", "Media (imagen, vídeo, audio)"),
                ],
                max_length=32,
                verbose_name="Familia de documento",
                help_text=(
                    "H30 (S49). Agrupación del acordeón de la ficha (en vez "
                    "de solo Vigentes/Histórico) y base de la búsqueda "
                    "granular ('ver el seguro de esta máquina'). Lista fija "
                    "de choices en código (a diferencia de tracks_expiry/"
                    "ocr_unreliable) porque las familias son un puñado "
                    "estable de categorías, no crecen sesión a sesión como "
                    "los tipos documentales -- decisión explícita de Miguel "
                    "Ángel (S49). Distinta de la familia normativa de "
                    "máquina (A/B/Z/H/MK/P/T/V/S de fleet.MachineAsset): "
                    "esta agrupa TIPOS DOCUMENTALES para la interfaz, esa "
                    "otra dice qué documentos son obligatorios por tipo de "
                    "máquina. S51: se añade 'Otros documentos' como familia "
                    "catch-all fija número 11 -- Miguel Ángel confirmó que la "
                    "lista sigue cerrada por código (no editable en caliente "
                    "desde el panel), pero si aparece un tipo nuevo que no "
                    "encaje en ninguna de las 10 originales, entra aquí en "
                    "vez de bloquear el alta; revisar periódicamente el "
                    "volumen de esta familia -- una acumulación real de un "
                    "mismo tipo dentro de 'Otros documentos' es la señal para "
                    "decidir en sesión, explícitamente, una familia nueva de "
                    "verdad (nunca creación libre por un supervisor)."
                ),
            ),
        ),
    ]
