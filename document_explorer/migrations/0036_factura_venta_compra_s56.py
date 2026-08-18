# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0036_factura_venta_compra_s56.py
"""
H30 (S56). Dos operaciones sobre el catalogo de facturacion, decision
explicita de Miguel Angel:

1. Fusion FACTURA_TERCEROS -> FACTURA_COMPRA (mismo patron que
   0033_merge_duplicate_types_s51.py): el unico criterio real de
   distincion es quien emite la factura, no si el destinatario es la
   empresa o un socio (caso real "BARCA ALBERTO ALVAREZ"). Miguel
   Angel, verbatim: "cuando el emisor de la factura no sea Grúas
   Álvarez, son facturas de compra [...] no hay más [...] solamente
   hay dos tipos de facturas, las que se emiten y las que se pagan."
   FACTURA_TERCEROS se desactiva (is_active=False), nunca se borra.

2. Renombrado de DOC_VENTA -> code=FACTURA_VENTA,
   label="Factura de venta". No es una fusion (un solo tipo, mismo id
   de catalogo) -- Miguel Angel confirmo que "documentacion de venta"
   era conceptualmente una factura de venta desde el principio, nunca
   otra cosa. CONTRATO_COMPRAVENTA queda fuera de esta migracion,
   confirmado explicitamente como concepto distinto (un contrato, no
   una factura).

   Renombrado retroactivo incluido (4.12: escritura pura de
   DocumentIndexEntry.name, nunca toca GCS): de los 89 documentos
   DOC_VENTA vivos, solo 4 ya llevaban el codigo antiguo incrustado en
   el nombre generado por naming_service (verificado con datos reales
   en S56 antes de escribir esta migracion) -- se sustituye el token
   literal DOC_VENTA por FACTURA_VENTA en esos 4 nombres para no dejar
   nombres de archivo huerfanos con un codigo de catalogo que ya no
   existe. El resto (85 de 89) conserva su nombre original de subida,
   sin renombrar todavia por el motor de H29 -- no requieren accion
   aqui.
"""
from django.db import migrations


def apply_factura_changes(apps, schema_editor):
    DocumentTypeCatalog = apps.get_model("document_explorer", "DocumentTypeCatalog")
    DocumentIndexEntry = apps.get_model("document_explorer", "DocumentIndexEntry")

    # 1. Fusion FACTURA_TERCEROS -> FACTURA_COMPRA
    winner = DocumentTypeCatalog.objects.filter(code="FACTURA_COMPRA").first()
    loser = DocumentTypeCatalog.objects.filter(code="FACTURA_TERCEROS").first()
    if winner is not None and loser is not None:
        DocumentIndexEntry.objects.filter(document_type_id=loser.id).update(
            document_type_id=winner.id,
        )
        DocumentTypeCatalog.objects.filter(id=loser.id).update(is_active=False)

    # 2. Renombrado DOC_VENTA -> FACTURA_VENTA (mismo objeto de catalogo)
    doc_venta = DocumentTypeCatalog.objects.filter(code="DOC_VENTA").first()
    if doc_venta is not None:
        DocumentTypeCatalog.objects.filter(id=doc_venta.id).update(
            code="FACTURA_VENTA", label="Factura de venta",
        )

        # Renombrado retroactivo (4.12: solo name, nunca GCS) de los
        # archivos que ya llevaban el codigo antiguo incrustado.
        entries = DocumentIndexEntry.objects.filter(
            document_type_id=doc_venta.id, name__contains="DOC_VENTA",
        )
        for entry in entries:
            entry.name = entry.name.replace("DOC_VENTA", "FACTURA_VENTA")
            entry.save(update_fields=["name"])


def revert_factura_changes(apps, schema_editor):
    # Reversion best-effort, mismo criterio que 0033: no se puede
    # reconstruir con certeza que fila era FACTURA_TERCEROS original
    # -- se reactiva el tipo vacio, sin reasignar filas de vuelta. El
    # renombrado DOC_VENTA/FACTURA_VENTA si es reversible sin perdida
    # de informacion (mismo objeto de catalogo, mismo id).
    DocumentTypeCatalog = apps.get_model("document_explorer", "DocumentTypeCatalog")
    DocumentIndexEntry = apps.get_model("document_explorer", "DocumentIndexEntry")

    DocumentTypeCatalog.objects.filter(code="FACTURA_TERCEROS").update(
        is_active=True,
    )

    factura_venta = DocumentTypeCatalog.objects.filter(code="FACTURA_VENTA").first()
    if factura_venta is not None:
        DocumentTypeCatalog.objects.filter(id=factura_venta.id).update(
            code="DOC_VENTA", label="Documentación de venta",
        )
        entries = DocumentIndexEntry.objects.filter(
            document_type_id=factura_venta.id, name__contains="FACTURA_VENTA",
        )
        for entry in entries:
            entry.name = entry.name.replace("FACTURA_VENTA", "DOC_VENTA")
            entry.save(update_fields=["name"])


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0035_person_identity_excel_fields"),
    ]

    operations = [
        migrations.RunPython(apply_factura_changes, revert_factura_changes),
    ]
