# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0044_seed_cert_exencion_tacografo_s65.py
"""
H30 (S65). Alta de CERT_EXENCION_TACOGRAFO, confirmado con muestra
real: "Circular_Leave_Letter.doc", encontrado archivado por error
dentro de "DOC. PERSONAL/ENTREGA EPIS/EPIS VARIAS EMPRESAS" (no tiene
relacion real con EPI, es un fallo de archivado historico).

Contenido real: plantilla en blanco de "Leave Letter" -- certificado
segun el Reglamento (CE) 561/2006 / AETR para justificar ante
inspeccion la ausencia de discos de tacografo de un conductor (baja,
vacaciones, o conduccion de vehiculo excluido del reglamento, como
las gruas moviles). Distinto de TACOGRAFO (que es la tarjeta fisica
del conductor, con caducidad) -- este es un certificado/plantilla de
la empresa, sin caducidad propia.

Family CIRCULACION (mismo bucket que TACOGRAFO), domain PERSONAL
(va ligado al conductor, confirmado por Miguel Angel en S65),
tracks_expiry=False (plantilla/certificado puntual, no una tarjeta
con vigencia).
"""
from django.db import migrations

NEW_TYPE = {
    "code": "CERT_EXENCION_TACOGRAFO",
    "label": "Certificado de exención de tacógrafo (Leave Letter)",
    "domain": "PERSONAL",
    "family": "CIRCULACION",
    "tracks_expiry": False,
}


def seed_new_type(apps, schema_editor):
    DocumentTypeCatalog = apps.get_model(
        "document_explorer", "DocumentTypeCatalog",
    )
    DocumentTypeCatalog.objects.get_or_create(
        code=NEW_TYPE["code"],
        defaults={
            "label": NEW_TYPE["label"],
            "domain": NEW_TYPE["domain"],
            "family": NEW_TYPE["family"],
            "tracks_expiry": NEW_TYPE["tracks_expiry"],
            "is_active": True,
        },
    )


def unseed_new_type(apps, schema_editor):
    DocumentTypeCatalog = apps.get_model(
        "document_explorer", "DocumentTypeCatalog",
    )
    DocumentTypeCatalog.objects.filter(code=NEW_TYPE["code"]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0043_seed_s65_h30_folder_types"),
    ]

    operations = [
        migrations.RunPython(seed_new_type, unseed_new_type),
    ]
