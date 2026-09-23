# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0137_tipos_maquinas_cierre_fase1_s117.py
"""
H30 (S117). Cierre de la Fase 1 (tipado por nombre) de MÁQUINAS --
tipos del catálogo decididos explícitamente por Miguel Ángel tras ver
el contenido real de documentos sin tipo (texto extraído con el modo
gcs_text del relevo, S117):

- CERTIFICADO_SEGURO (nuevo, SEGUROS, con caducidad): acreditación de
  cobertura con periodo -- "Mapfre certifica que el vehículo está
  asegurado del 15/12/2012 al 15/12/2013", certificados de correduría
  (Meditres/Generali) y de Europ Assistance. No es la póliza ni un
  recibo; la fecha a vigilar es el fin del periodo.
- AUTORIZACION_COMPLEMENTARIA_CIRCULACION (nuevo, CIRCULACION, con
  caducidad): autorizaciones especiales de la DGT para exceder masas y
  dimensiones (transporte especial, conjunto de auxilio en carretera),
  con "VIGENCIA DE LA AUTORIZACIÓN: desde ... hasta ...".
- ESPECIFICACIONES_FABRICANTE (nuevo, TECNICA_SEGURIDAD, sin
  caducidad): hojas técnicas / folletos del fabricante (Liebherr LTM
  1230-5.1, Genie GTH-2506) -- nunca la ficha técnica oficial de ITV.
- IMAGEN (existente, MEDIA): pasa de PERSONAL a BOTH para acoger las
  fotos de máquinas ("sí, ya tenemos media en personal") y a
  acumulable -- varias fotos vigentes a la vez, nunca "solo la última"
  (aplica igual a las imágenes de Personal).

Reversible: la reversa borra los tres tipos nuevos (solo si no tienen
documentos asignados) y devuelve IMAGEN a PERSONAL, no acumulable.
"""
from django.db import migrations

NEW_TYPES = [
    {
        "code": "CERTIFICADO_SEGURO",
        "label": "Certificado de seguro (acreditación de cobertura)",
        "family": "SEGUROS",
        "tracks_expiry": True,
    },
    {
        "code": "AUTORIZACION_COMPLEMENTARIA_CIRCULACION",
        "label": "Autorización complementaria de circulación (DGT)",
        "family": "CIRCULACION",
        "tracks_expiry": True,
    },
    {
        "code": "ESPECIFICACIONES_FABRICANTE",
        "label": "Especificaciones técnicas del fabricante",
        "family": "TECNICA_SEGURIDAD",
        "tracks_expiry": False,
    },
]


def seed(apps, schema_editor):
    DocumentTypeCatalog = apps.get_model(
        "document_explorer", "DocumentTypeCatalog",
    )
    for spec in NEW_TYPES:
        DocumentTypeCatalog.objects.get_or_create(
            code=spec["code"],
            defaults={
                "label": spec["label"],
                "domain": "MACHINE",
                "family": spec["family"],
                "tracks_expiry": spec["tracks_expiry"],
                "is_cumulative": False,
                "is_active": True,
            },
        )
    DocumentTypeCatalog.objects.filter(code="IMAGEN").update(
        domain="BOTH", is_cumulative=True,
    )


def unseed(apps, schema_editor):
    DocumentTypeCatalog = apps.get_model(
        "document_explorer", "DocumentTypeCatalog",
    )
    DocumentIndexEntry = apps.get_model(
        "document_explorer", "DocumentIndexEntry",
    )
    for spec in NEW_TYPES:
        if not DocumentIndexEntry.objects.filter(
            document_type__code=spec["code"],
        ).exists():
            DocumentTypeCatalog.objects.filter(code=spec["code"]).delete()
    DocumentTypeCatalog.objects.filter(code="IMAGEN").update(
        domain="PERSONAL", is_cumulative=False,
    )


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0136_nomina_vacaciones_registro_jornada_acumulables_s117"),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
