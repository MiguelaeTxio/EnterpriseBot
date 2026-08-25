# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0050_seed_media_types_s67.py
"""
H30 (S67). Familia nueva MEDIA + tres tipos documentales nuevos:
IMAGEN, VIDEO, AUDIO.

---

H30 (S67). New family MEDIA + three new document types: IMAGEN,
VIDEO, AUDIO.

Origen real: al revisar a mano el residuo de 459 archivos sin tipo de
`DOC. PERSONAL/PERSONAL/` (S67), Miguel Angel identifico por nombre
de archivo un patron real ya visible en el propio listado -- 132 de
los 459 son fotos/videos/audios (WhatsApp Image, IMG-..., .jpeg/.png/
.mp4/...), nunca van a tener un tipo del catalogo cerrado documental
(no son ITV, no son DNI, no son ningun documento oficial), pero si
tienen que quedar vinculados a su PersonIdentity para verse en un
apartado "Media" de la ficha del trabajador.

Decision explicita de Miguel Angel (S67), verbatim (transcrito):
"Creadlo ya de media con subtipos, imagen, video y audio, para que no
haya problemas si encontramos despues videos o audios, aunque ahora
solamente tengamos imagenes."

- Familia nueva `MEDIA` en vez de reutilizar el catch-all
  `OTROS_DOCUMENTOS` (S51): Miguel Angel quiere una seccion propia y
  diferenciada en la interfaz (imagen/video/audio), no mezclada con
  el resto de "otros documentos".
- Tres tipos, no uno generico, para poder filtrar en el panel desde
  el primer momento aunque hoy solo haya archivos IMAGEN reales.
- domain=PERSONAL: el residuo real que motiva este alta vive en
  DOC. PERSONAL. No se abre a MACHINE en esta migracion -- si aparece
  el mismo patron real en DOC. MAQUINAS, se decide entonces si se
  amplia el domain a BOTH (nunca se asume aqui).
- tracks_expiry=False: no hay fecha de caducidad ni sustitucion
  automatica aplicable a una foto o un video.
"""
from django.db import migrations, models

NEW_TYPES = [
    {
        "code": "IMAGEN",
        "label": "Imagen (foto, WhatsApp Image, captura)",
        "domain": "PERSONAL",
        "family": "MEDIA",
        "tracks_expiry": False,
    },
    {
        "code": "VIDEO",
        "label": "Vídeo",
        "domain": "PERSONAL",
        "family": "MEDIA",
        "tracks_expiry": False,
    },
    {
        "code": "AUDIO",
        "label": "Audio",
        "domain": "PERSONAL",
        "family": "MEDIA",
        "tracks_expiry": False,
    },
]


def seed_new_types(apps, schema_editor):
    DocumentTypeCatalog = apps.get_model(
        "document_explorer", "DocumentTypeCatalog",
    )
    for spec in NEW_TYPES:
        DocumentTypeCatalog.objects.get_or_create(
            code=spec["code"],
            defaults={
                "label": spec["label"],
                "domain": spec["domain"],
                "family": spec["family"],
                "tracks_expiry": spec["tracks_expiry"],
                "is_active": True,
            },
        )


def unseed_new_types(apps, schema_editor):
    DocumentTypeCatalog = apps.get_model(
        "document_explorer", "DocumentTypeCatalog",
    )
    DocumentTypeCatalog.objects.filter(
        code__in=[spec["code"] for spec in NEW_TYPES],
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0049_seed_convenio_fct_s66"),
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
                    ("MEDIA", "Media (imagen, vídeo, audio) — H30 S67"),
                ],
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
                max_length=32,
                verbose_name="Familia de documento",
            ),
        ),
        migrations.RunPython(seed_new_types, unseed_new_types),
    ]
