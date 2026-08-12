# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0025_poliza_poderes_factura_terceros.py
"""
H30 (S48). Alta de 3 tipos documentales nuevos, confirmados por
Miguel Ángel tras auditoría real del blob de B-38 (ver anexo H30,
sección "COMPLETADAS EN S48" -- "esto hay que hacerlo muy bien...
coge tres o cuatro máquinas, mira qué documentos son los que
tienen").

- `POLIZA_SEGURO`: distinto de `SEGURO` ("Recibo del seguro") --
  Miguel Ángel, verbatim: "una cosa es la póliza y otra cosa es el
  recibo del seguro". `tracks_expiry=True` -- se renueva
  periódicamente, igual que el recibo (muestras reales: "POLIZA
  HELVETIA 15-11-21 A 31-12-21", "POLIZA GENERALI 31-12-22").
- `CERTIFICADO_PODERES`: "cuando se da a una persona poder para
  realizar un trámite de una empresa o de otra persona jurídica o
  física" -- distinto de `MANDATO` (ya existente), confirmado porque
  conviven como archivos separados en la misma carpeta real de B-38.
  `tracks_expiry=False` -- mismo criterio que `MANDATO`, sin
  evidencia de renovación periódica en las muestras.
- `FACTURA_TERCEROS`: "una factura aparte de un cargo que tenga algún
  vehículo o maquinaria de un tercero" -- distinto de
  `FACTURA_COMPRA` (esa es de compra del propio vehículo).
  `tracks_expiry=False` -- registro financiero puntual, sin vigencia.
"""
from django.db import migrations


def seed_new_types(apps, schema_editor):
    DocumentTypeCatalog = apps.get_model("document_explorer", "DocumentTypeCatalog")
    entries = [
        {
            "code": "POLIZA_SEGURO", "label": "Póliza de seguro",
            "domain": "BOTH", "tracks_expiry": True,
        },
        {
            "code": "CERTIFICADO_PODERES", "label": "Certificado de poderes",
            "domain": "BOTH", "tracks_expiry": False,
        },
        {
            "code": "FACTURA_TERCEROS",
            "label": "Factura a terceros (cargo de un tercero a la máquina)",
            "domain": "MACHINE", "tracks_expiry": False,
        },
    ]
    for entry in entries:
        DocumentTypeCatalog.objects.get_or_create(
            code=entry["code"],
            defaults={
                "label": entry["label"], "domain": entry["domain"],
                "tracks_expiry": entry["tracks_expiry"], "is_active": True,
            },
        )


def unseed_new_types(apps, schema_editor):
    DocumentTypeCatalog = apps.get_model("document_explorer", "DocumentTypeCatalog")
    DocumentTypeCatalog.objects.filter(
        code__in=["POLIZA_SEGURO", "CERTIFICADO_PODERES", "FACTURA_TERCEROS"],
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0024_ocr_unreliable_and_obsolete_marker"),
    ]

    operations = [
        migrations.RunPython(seed_new_types, unseed_new_types),
    ]
