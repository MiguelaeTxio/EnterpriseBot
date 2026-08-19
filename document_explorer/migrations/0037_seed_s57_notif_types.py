# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0037_seed_s57_notif_types.py
"""
H30 (S57). Alta de 2 tipos documentales nuevos, detectados al revisar
el contenido real de los 11 documentos NOTIFICACION/NOTIF que estaban
mal clasificados como FACTURA_VENTA (sospecha real ya anotada en S56,
confirmada aquí descargando y leyendo el texto real de 10 de los 11
-- ninguno resultó ser una factura de venta).

- AUTORIZACION_PROVISIONAL_CIRCULACION: formulario DGT de autorización
  provisional de circulación (matrícula, titular, marca, bastidor),
  distinto del permiso de circulación definitivo (PERMISO_CIRCULACION,
  ya existente). Casos reales que lo motivaron: "NOTIFICACIÓN DE VENTA
  7585KHG.pdf" (id 4580), "NOTIFICACION VENTA R-07.pdf" (id 16012),
  "Notification de Venta R2654BCD.pdf" (id 16524) -- los tres, pese al
  nombre de archivo, son el mismo formulario DGT de autorización
  provisional, no facturas. `tracks_expiry=False`: documenta un
  trámite puntual de una máquina ya vendida/de baja en la mayoría de
  los casos reales encontrados, mismo criterio ya usado en
  BAJA_DEFINITIVA/CAMBIO_TITULARIDAD (también False).

- AVISO_BAJA: aviso/notificación de baja de oficio, distinto de una
  baja ya ejecutada (BAJA_DEFINITIVA, ya existente). Caso real que lo
  motivó: "B-19 1467-CNL Notif.venta trafico 13-4-16.pdf" (id 7114) --
  el contenido real es "PROPUESTA BAJA DE OFICIO RD 2042/94", un aviso
  de la DGT proponiendo la baja, no la baja ya consumada.
  `tracks_expiry=False`: mismo criterio que BAJA_DEFINITIVA.

Ambos confirmados verbatim por Miguel Ángel en S57 tras presentarle el
desglose real de los 10 documentos descargados y leídos con
`extract_text()` (mismo motor OCR de Fase B1) -- código y label exactos
tal cual los confirmó, sin reinterpretación (directriz 4.8/Fidelidad
Absoluta).

La reasignación de `document_type` de los documentos concretos (ids
4580, 6127, 7114, 8221, 12376, 15907, 16012, 16524, 18580, 18583) NO
va en esta migración -- es una operación de datos puntual sobre
documentos ya existentes, mismo patrón que los 26 `CONTRATO_COMPRA-
VENTA` reasignados en S56 (ver anexo H30), no un cambio de esquema.
Se ejecuta aparte, vía Comando S, una vez esta migración esté
confirmada en producción.
"""
from django.db import migrations

NEW_TYPES = [
    {
        "code": "AUTORIZACION_PROVISIONAL_CIRCULACION",
        "label": "Autorización provisional de circulación",
        "domain": "MACHINE",
        "family": "CIRCULACION",
        "tracks_expiry": False,
    },
    {
        "code": "AVISO_BAJA",
        "label": "Aviso/notificación de baja",
        "domain": "MACHINE",
        "family": "CIRCULACION",
        "tracks_expiry": False,
    },
]


def seed_new_types(apps, schema_editor):
    DocumentTypeCatalog = apps.get_model("document_explorer", "DocumentTypeCatalog")
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
    DocumentTypeCatalog = apps.get_model("document_explorer", "DocumentTypeCatalog")
    DocumentTypeCatalog.objects.filter(
        code__in=[spec["code"] for spec in NEW_TYPES],
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0036_factura_venta_compra_s56"),
    ]

    operations = [
        migrations.RunPython(seed_new_types, unseed_new_types),
    ]
