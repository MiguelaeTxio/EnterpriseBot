# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0151_lifting_accessory_certificates_as_domain_links_s121.py
"""
H30 (S121). Los certificados de un accesorio de elevación se vinculan
como la ficha técnica de un EPI: por el mecanismo genérico
`DocumentIndexEntry.domain_content_type`/`domain_object_id`, nunca por
una FK propia (mismo error corregido en S76 con
`EpiItemCatalog.technical_sheet`). Se quita
`LiftingAccessory.certificate_entry`.

Sin pérdida de datos: verificado en producción antes de escribir esta
migración (consulta real S121) -- 0 accesorios, 0 con certificado.
"""
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0150_lifting_accessories_s121"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="liftingaccessory",
            name="certificate_entry",
        ),
    ]
