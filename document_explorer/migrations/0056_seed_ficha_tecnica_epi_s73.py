# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0056_seed_ficha_tecnica_epi_s73.py
"""
H30 (S73). Alta de FICHA_TECNICA_EPI, confirmado con contenido real:
13 PDFs bajo DOC. PERSONAL/ENTREGA EPIS venian con tipo=EPIS mal
aplicado (heredado del heuristico de carpeta, S71/S72) pese a no ser
registros de entrega por persona -- son documentacion de referencia
del propio EPI (ficha tecnica, declaracion de conformidad, guia
tecnica, certificado, folleto informativo, consulta INSHT).

Decision explicita de Miguel Angel (S73): tipo nuevo, no reutilizar
EPIS. Confirmado en la misma sesion que el T501.pdf ya en papelera
(id 23042, borrado 2026-07-31, antes de esta sesion) queda cubierto
por el CERTIFICADO T501(CLASE 2)+T180 (CLASE 2)-CLASE 3.pdf activo
(id 22915) -- no se restaura.

Family TECNICA_SEGURIDAD (documentacion tecnica de un equipo, mismo
criterio que ITV/FICHA_TECNICA de maquinaria), domain PERSONAL (vive
bajo DOC. PERSONAL, aunque el enlace real -- pendiente de ejecutar --
sera domain_content_type/domain_object_id apuntando a
EpiItemCatalog, no a PersonIdentity). tracks_expiry False (sin fecha
de caducidad real) y ocr_unreliable False (PDFs nativos, no
manuscritos) -- ambos por defecto, sin motivo real para desviarse.
"""
from django.db import migrations

NEW_TYPE = {
    "code": "FICHA_TECNICA_EPI",
    "label": "Ficha técnica / declaración de conformidad de EPI",
    "domain": "PERSONAL",
    "family": "TECNICA_SEGURIDAD",
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
        ("document_explorer", "0055_seed_botiquin_catalog_item_s72"),
    ]

    operations = [
        migrations.RunPython(seed_new_type, unseed_new_type),
    ]
