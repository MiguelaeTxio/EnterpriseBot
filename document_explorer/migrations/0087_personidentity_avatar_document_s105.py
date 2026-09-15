# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0087_personidentity_avatar_document_s105.py
"""
H35 (S105). Añade PersonIdentity.avatar_document -- FK opcional al
DocumentIndexEntry (imagen) elegido explícitamente como foto de
perfil. Miguel Ángel, verbatim: "en los documentos que son imágenes
hay que añadir la posibilidad de usar como foto de perfil".

Campo dedicado, deliberadamente separado del mecanismo antiguo
(DocumentTypeCatalog "IMAGEN") para no reasignar el tipo real del
documento elegido -- ver comentario completo en models.py.
"""
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0086_seed_recurso_preventivo_s105"),
    ]

    operations = [
        migrations.AddField(
            model_name="personidentity",
            name="avatar_document",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to="document_explorer.documentindexentry",
                verbose_name="Documento-imagen usado como foto de perfil",
            ),
        ),
    ]
