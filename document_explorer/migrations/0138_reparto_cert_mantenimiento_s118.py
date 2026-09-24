# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0138_reparto_cert_mantenimiento_s118.py
"""
H30 (S118), punto 6 de la hoja de ruta -- reparto del cajón de sastre
CERT_MANTENIMIENTO, SOLO máquinas activas, con las decisiones de Miguel
Ángel tomadas sobre el contenido real de muestras de cada grupo:

1. Word (.docx) -> PAPELERA. Borrador editable del que sale cada PDF,
   sin texto legible y a veces copiado de otra máquina. Miguel Ángel:
   "Papelera. Quitamos ruido documental." Borrado blando (deleted_at),
   nunca se toca GCS (directriz 4.12).
2. "PLANTILLA REGISTRO MANTENIMIENTO" en PDF -> LIBRO_HISTORIAL. Por
   contenido es el registro real de mantenimiento de la máquina (cada
   revisión e ITV con fecha, kilometraje y resultado). "Al libro
   historial, correcto."
3. Lista de chequeo RD 1215 de la P-26 (id 4579) -> C_ADECUACION.
4. "Z-79 Cert.pdf" (id 14555) -> máquina Z80: por contenido certifica
   la plataforma Z-80 Genie, nº de serie GS6807-49516.

Se quedan como CERT_MANTENIMIENTO, por decisión: los certificados en
PDF (incluidos los llamados "CERT.REVISION", mismo certificado por
contenido) y los "INF. MANTENIMIENTO" ("De acuerdo"). Las órdenes de
taller "REVISION MANTENIMIENTO" (2024-2026) quedan PENDIENTES de
decisión y no se tocan aquí.

Reverse: no-op (no se deshace un reparto ya decidido).
"""
from django.db import migrations
from django.utils import timezone

BUCKET = "cgs_grupo_alvarez"


def _log(message):
    print("  [document_explorer 0138] %s" % message, flush=True)


def reparto_cert_mantenimiento(apps, schema_editor):
    """
    Split CERT_MANTENIMIENTO of active machines as decided.
    ---
    Reparte CERT_MANTENIMIENTO de máquinas activas según lo decidido.
    """
    DocumentIndexEntry = apps.get_model(
        "document_explorer", "DocumentIndexEntry",
    )
    DocumentTypeCatalog = apps.get_model(
        "document_explorer", "DocumentTypeCatalog",
    )
    MachineAsset = apps.get_model("fleet", "MachineAsset")
    ContentType = apps.get_model("contenttypes", "ContentType")

    print("", flush=True)
    machine_ct = ContentType.objects.filter(
        app_label="fleet", model="machineasset",
    ).first()
    types = {
        dt.code: dt for dt in DocumentTypeCatalog.objects.filter(
            code__in=["CERT_MANTENIMIENTO", "LIBRO_HISTORIAL", "C_ADECUACION"],
        )
    }
    if machine_ct is None or len(types) != 3:
        _log("Falta ContentType de máquina o algún tipo del catálogo: "
             "no se toca nada.")
        return

    active_pks = list(MachineAsset.objects.filter(
        is_active=True,
    ).values_list("pk", flat=True))
    scope = DocumentIndexEntry.objects.filter(
        bucket=BUCKET, entry_kind="FILE",
        domain_content_type=machine_ct, domain_object_id__in=active_pks,
        document_type=types["CERT_MANTENIMIENTO"],
        deleted_at__isnull=True, purged_at__isnull=True,
    )
    _log("En alcance (CERT_MANTENIMIENTO, máquinas activas): %d"
         % scope.count())

    # 1. Word -> papelera.
    trashed = scope.filter(name__iregex=r"\.docx?$").update(
        deleted_at=timezone.now(),
    )
    _log("1. Word a la papelera: %d" % trashed)

    # 2. Registro de mantenimiento firmado -> libro historial.
    to_libro = scope.filter(
        name__icontains="PLANTILLA REGISTRO MANTENIMIENTO",
        name__iendswith=".pdf",
    ).update(document_type=types["LIBRO_HISTORIAL"])
    _log("2. Registro de mantenimiento a Libro historial: %d" % to_libro)

    # 3. Lista de chequeo RD 1215 de la P-26 -> certificado de adecuación.
    to_adecuacion = scope.filter(pk=4579).update(
        document_type=types["C_ADECUACION"],
    )
    _log("3. Lista de chequeo RD 1215 (P-26) a Certificado de adecuación: %d"
         % to_adecuacion)

    # 4. "Z-79 Cert.pdf" es de la Z-80.
    z80 = MachineAsset.objects.filter(code="Z80").first()
    if z80 is None:
        _log("4. No existe la máquina Z80: 'Z-79 Cert.pdf' (id 14555) "
             "se queda donde está.")
    else:
        moved = scope.filter(pk=14555).update(domain_object_id=z80.pk)
        _log("4. 'Z-79 Cert.pdf' reasignado a la Z80 (pk=%d): %d"
             % (z80.pk, moved))

    _log("Quedan como CERT_MANTENIMIENTO: %d" % scope.filter(
        document_type=types["CERT_MANTENIMIENTO"],
    ).count())


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0137_tipos_maquinas_cierre_fase1_s117"),
        ("fleet", "0012_fix_default_machine_photo_s118"),
        ("contenttypes", "0002_remove_content_type_name"),
    ]

    operations = [
        migrations.RunPython(
            reparto_cert_mantenimiento, migrations.RunPython.noop,
        ),
    ]
