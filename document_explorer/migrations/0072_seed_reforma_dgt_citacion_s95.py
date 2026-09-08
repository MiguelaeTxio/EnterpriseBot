# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0072_seed_reforma_dgt_citacion_s95.py
"""
H31 (S95). Tres tipos nuevos en DocumentTypeCatalog, confirmados
contra el contenido real de los documentos (descarga real del blob
via com-gcs-download, nunca por heuristica de nombre) tras la
auditoria de domain del Punto 4 -- 3 de las 17 excepciones que no
encajaban en ningun codigo existente.

1. REFORMA_VEHICULO (domain=MACHINE) -- documentos reales:
   "CERTIFICADO FINAL DE OBRA" (ingeniero tecnico industrial
   certificando la reforma) e "INFORME DE CONFORMIDAD" (ISVA-LABITV,
   organismo oficial de reformas de vehiculos) del mismo expediente
   de instalacion de cesta/grua sobre chasis (Z-34, ids 12538/12539).

2. INFORME_VEHICULO_DGT (domain=MACHINE) -- "INFORME DEL VEHICULO"
   real de la Direccion General de Trafico (historico de ITV, seguro,
   titularidad), id 12517. Nombre de archivo original ("Informe
   trafico") inducia a error -- no es un incidente, es una consulta
   administrativa del Registro General de Vehiculos.

3. CITACION_JUDICIAL (domain=PERSONAL) -- "CEDULA DE CITACION" real
   de un procedimiento de familia (Juzgado de Primera Instancia
   Malaga), id 35380, verificado contra domain_object real
   (PersonIdentity pk=158, GARCIA LUQUE ALEJANDRO) -- confirma que
   Miguel Angel identifico correctamente de memoria a quien
   pertenecia antes de verificarlo. Dato personal sensible, tratado
   como cualquier otro documento de personal del catalogo cerrado.
"""
from django.db import migrations

NEW_TYPES = [
    {
        "code": "REFORMA_VEHICULO",
        "label": "Certificado/informe de reforma de vehículo",
        "domain": "MACHINE",
        "family": "CIRCULACION",
    },
    {
        "code": "INFORME_VEHICULO_DGT",
        "label": "Informe del vehículo (Registro General de Vehículos, DGT)",
        "domain": "MACHINE",
        "family": "CIRCULACION",
    },
    {
        "code": "CITACION_JUDICIAL",
        "label": "Citación judicial",
        "domain": "PERSONAL",
        "family": "OTROS_DOCUMENTOS",
    },
]


def seed_new_types(apps, schema_editor):
    DocumentTypeCatalog = apps.get_model(
        "document_explorer", "DocumentTypeCatalog",
    )
    for item in NEW_TYPES:
        DocumentTypeCatalog.objects.get_or_create(
            code=item["code"],
            defaults={
                "label": item["label"],
                "domain": item["domain"],
                "family": item["family"],
                "is_active": True,
                "tracks_expiry": False,
                "ocr_unreliable": False,
            },
        )


def unseed_new_types(apps, schema_editor):
    DocumentTypeCatalog = apps.get_model(
        "document_explorer", "DocumentTypeCatalog",
    )
    DocumentTypeCatalog.objects.filter(
        code__in=[item["code"] for item in NEW_TYPES]
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0071_corregir_domain_ficha_epi_solicitud_admin_s95"),
    ]

    operations = [
        migrations.RunPython(seed_new_types, unseed_new_types),
    ]
