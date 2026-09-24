# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0139_orden_trabajo_mantenimiento_s118.py
"""
H30 (S118), punto 6 de la hoja de ruta. Tipo nuevo
ORDEN_TRABAJO_MANTENIMIENTO y retipado de las órdenes de reparación de
Prologic que estaban como CERT_MANTENIMIENTO.

Miguel Ángel: "Hay un programa alternativo que se está usando en la
empresa que es Prologic [...] son reparaciones que se han hecho mientras
estaba la máquina alquilada [...] a modo como de factura para los
clientes [...] creas el tipo de orden de trabajo de mantenimiento y los
vamos a guardar ahí para que formen parte del libro de mantenimiento de
la máquina."

Tipo ACUMULABLE (is_cumulative): cada orden es una intervención distinta
y todas cuentan a la vez, como las hojas de un libro -- nunca "solo la
última". Sin caducidad. Familia Técnica y seguridad, junto al Libro
historial.

Se retipan las 21 órdenes comprobadas por contenido (cabecera "ORDEN DE
TRABAJO Nº", taller de Camino de Cantos, 2024-2026). NO entran las
"REVISION ANUAL" de la Z-42 (2019-2020, ids 14078-14080) ni la de la
Z-57 (id 14347): por contenido son listas de revisión preventiva
firmadas por el técnico, no órdenes de Prologic -- pendientes de
decisión aparte.

Reverse: borra el tipo solo si ya no tiene documentos (devuelve antes
las 21 a CERT_MANTENIMIENTO).
"""
from django.db import migrations

PROLOGIC_ORDER_IDS = [
    7470, 7632, 7787, 13128, 13291, 13302, 13348, 13380, 13411, 13515,
    13537, 13984, 13992, 14063, 14232, 14524, 14539, 14564, 14636, 14780,
    14796,
]


def forwards(apps, schema_editor):
    """
    Create the type and retype the 21 Prologic work orders.
    ---
    Crea el tipo y retipa las 21 órdenes de trabajo de Prologic.
    """
    DocumentTypeCatalog = apps.get_model(
        "document_explorer", "DocumentTypeCatalog",
    )
    DocumentIndexEntry = apps.get_model(
        "document_explorer", "DocumentIndexEntry",
    )
    new_type, created = DocumentTypeCatalog.objects.get_or_create(
        code="ORDEN_TRABAJO_MANTENIMIENTO",
        defaults={
            "label": "Orden de trabajo de mantenimiento (libro de "
                     "mantenimiento)",
            "domain": "MACHINE",
            "family": "TECNICA_SEGURIDAD",
            "tracks_expiry": False,
            "is_cumulative": True,
            "is_active": True,
        },
    )
    print("\n  [document_explorer 0139] Tipo ORDEN_TRABAJO_MANTENIMIENTO %s"
          % ("creado" if created else "ya existía"), flush=True)
    retyped = DocumentIndexEntry.objects.filter(
        pk__in=PROLOGIC_ORDER_IDS,
        document_type__code="CERT_MANTENIMIENTO",
        deleted_at__isnull=True,
    ).update(document_type=new_type)
    print("  [document_explorer 0139] Órdenes de Prologic retipadas: %d de %d"
          % (retyped, len(PROLOGIC_ORDER_IDS)), flush=True)


def backwards(apps, schema_editor):
    """
    Return the orders to CERT_MANTENIMIENTO and drop the type if empty.
    ---
    Devuelve las órdenes a CERT_MANTENIMIENTO y borra el tipo si queda
    vacío.
    """
    DocumentTypeCatalog = apps.get_model(
        "document_explorer", "DocumentTypeCatalog",
    )
    DocumentIndexEntry = apps.get_model(
        "document_explorer", "DocumentIndexEntry",
    )
    cert = DocumentTypeCatalog.objects.filter(
        code="CERT_MANTENIMIENTO",
    ).first()
    if cert:
        DocumentIndexEntry.objects.filter(
            pk__in=PROLOGIC_ORDER_IDS,
            document_type__code="ORDEN_TRABAJO_MANTENIMIENTO",
        ).update(document_type=cert)
    if not DocumentIndexEntry.objects.filter(
        document_type__code="ORDEN_TRABAJO_MANTENIMIENTO",
    ).exists():
        DocumentTypeCatalog.objects.filter(
            code="ORDEN_TRABAJO_MANTENIMIENTO",
        ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0138_reparto_cert_mantenimiento_s118"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
