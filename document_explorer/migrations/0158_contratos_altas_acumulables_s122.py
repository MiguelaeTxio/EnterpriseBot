# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0158_contratos_altas_acumulables_s122.py
"""
H30 (S122). Contratos, altas e IDC dejan de sustituirse entre sí.

Miguel Ángel: "en esta empresa tengo dos contratos, tres contratos,
pero solamente está apareciendo el primero". Cada alta en la
Seguridad Social es una relación laboral distinta con su propio
contrato: no se sustituyen, coexisten. Hasta ahora estos tipos eran
no acumulables (un único vigente por persona) y la sustitución
automática dejaba obsoleto todo lo anterior -- en las personas
activas, 175 de 253 contratos, 98 de 157 altas, 94 de 158 IDC.

1. CONTRATO, ALTA, IDC, COMUNICACION_CONTRATO y BAJA_PERSONAL pasan a
   `is_cumulative=True` (la ficha ya pinta todos los no obsoletos de
   un tipo acumulable, S117, y desde S122 la subida no los sustituye).
2. Se quita `is_obsolete` a sus documentos del dominio PERSONAL, SALVO
   las marcas que son decisión humana: archivos dentro de una carpeta
   "obsolet*" (resolve_obsoleto_folder_flag, S50) y copias marcadas
   "_unlocked"/"copia" (resolve_variant_marker_duplicates, S50).

Reversión: vuelve a `is_cumulative=False`; las marcas de obsoleto no
se restauran (no hay forma fiable de saber cuáles eran).
"""
from django.db import migrations

CODES = (
    "CONTRATO", "ALTA", "IDC", "COMUNICACION_CONTRATO", "BAJA_PERSONAL",
)


def make_cumulative(apps, schema_editor):
    """Marca los tipos como acumulables y libera sus obsoletos."""
    catalog = apps.get_model("document_explorer", "DocumentTypeCatalog")
    entry_model = apps.get_model("document_explorer", "DocumentIndexEntry")
    content_type = apps.get_model("contenttypes", "ContentType")

    catalog.objects.filter(code__in=CODES).update(is_cumulative=True)

    person_ct = content_type.objects.filter(
        app_label="document_explorer", model="personidentity",
    ).first()
    if person_ct is None:
        return
    released = (
        entry_model.objects.filter(
            document_type__code__in=CODES,
            domain_content_type=person_ct,
            is_obsolete=True,
            deleted_at__isnull=True,
        )
        .exclude(parent_path__icontains="obsolet")
        .exclude(name__icontains="_unlocked")
        .exclude(name__icontains="copia")
        .update(is_obsolete=False)
    )
    print(
        "\n  [0158] tipos acumulables: %s; documentos liberados de "
        "obsoleto: %d" % (", ".join(CODES), released)
    )


def revert_cumulative(apps, schema_editor):
    """Vuelve a no acumulables (las marcas de obsoleto no se restauran)."""
    catalog = apps.get_model("document_explorer", "DocumentTypeCatalog")
    catalog.objects.filter(code__in=CODES).update(is_cumulative=False)


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0157_notice_recipient_scope_delivery_s122"),
        ("contenttypes", "0002_remove_content_type_name"),
    ]

    operations = [
        migrations.RunPython(make_cumulative, revert_cumulative),
    ]
