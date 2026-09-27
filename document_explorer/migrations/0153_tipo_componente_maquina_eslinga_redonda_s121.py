# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0153_tipo_componente_maquina_eslinga_redonda_s121.py
"""
H30 (S121). Dos altas de catálogo, decididas con Miguel Ángel al revisar
sobre su contenido real los certificados de accesorios del bucket:

- Tipo documental CERT_COMPONENTE_MAQUINA: certificado de un componente
  que forma parte de la propia máquina (cables de la grúa, gancho,
  cabrestante, corona de giro...). Estaban tipados como certificado de
  accesorio de elevación (A63: cables de la Liebherr MK 80; H08/H09:
  dossier de componentes Hoeflon) o sin tipo (cabrestante VIME).
  Miguel Ángel: "hay que tiparlos como integrantes de la propia grúa".
  Sin caducidad propia: su revisión es la de la grúa (OCA). Acumulable:
  una máquina tiene varios componentes certificados.
- Tipo de accesorio ESLINGA_POLIESTER_REDONDA: las eslingas redondas
  sinfín (SRS) no encajan en ninguno de los 6 tipos sembrados en 0150.

Reverse: cada alta se borra solo si no tiene documentos/accesorios.
"""
from django.db import migrations

DOC_TYPE_CODE = "CERT_COMPONENTE_MAQUINA"
ACCESSORY_TYPE_CODE = "ESLINGA_POLIESTER_REDONDA"


def forwards(apps, schema_editor):
    DocumentTypeCatalog = apps.get_model(
        "document_explorer", "DocumentTypeCatalog",
    )
    LiftingAccessoryType = apps.get_model(
        "document_explorer", "LiftingAccessoryType",
    )
    _doc_type, created = DocumentTypeCatalog.objects.get_or_create(
        code=DOC_TYPE_CODE,
        defaults={
            "label": (
                "Certificado de componente de la máquina (cables, gancho, "
                "cabrestante, corona...)"
            ),
            "domain": "MACHINE",
            "family": "TECNICA_SEGURIDAD",
            "tracks_expiry": False,
            "is_cumulative": True,
            "is_active": True,
        },
    )
    print("\n  [document_explorer 0153] Tipo %s %s"
          % (DOC_TYPE_CODE, "creado" if created else "ya existía"),
          flush=True)
    _acc_type, created = LiftingAccessoryType.objects.get_or_create(
        code=ACCESSORY_TYPE_CODE,
        defaults={
            "label": "Eslinga de poliéster redonda (sinfín)",
            "display_order": 3,
            "is_active": True,
        },
    )
    print("  [document_explorer 0153] Tipo de accesorio %s %s"
          % (ACCESSORY_TYPE_CODE, "creado" if created else "ya existía"),
          flush=True)


def backwards(apps, schema_editor):
    DocumentTypeCatalog = apps.get_model(
        "document_explorer", "DocumentTypeCatalog",
    )
    DocumentIndexEntry = apps.get_model(
        "document_explorer", "DocumentIndexEntry",
    )
    LiftingAccessoryType = apps.get_model(
        "document_explorer", "LiftingAccessoryType",
    )
    LiftingAccessory = apps.get_model(
        "document_explorer", "LiftingAccessory",
    )
    if not DocumentIndexEntry.objects.filter(
        document_type__code=DOC_TYPE_CODE,
    ).exists():
        DocumentTypeCatalog.objects.filter(code=DOC_TYPE_CODE).delete()
    if not LiftingAccessory.objects.filter(
        accessory_type__code=ACCESSORY_TYPE_CODE,
    ).exists():
        LiftingAccessoryType.objects.filter(
            code=ACCESSORY_TYPE_CODE,
        ).delete()


class Migration(migrations.Migration):

    dependencies = [
        (
            "document_explorer",
            "0152_lifting_assignment_cost_center_required_s121",
        ),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
