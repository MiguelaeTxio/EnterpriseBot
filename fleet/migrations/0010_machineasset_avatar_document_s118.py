# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/fleet/migrations/0010_machineasset_avatar_document_s118.py
"""
H30 (S118). Añade MachineAsset.avatar_document -- FK opcional al
DocumentIndexEntry (imagen) elegido explícitamente como foto de la
máquina. Miguel Ángel: "tenemos muchas máquinas con fotos, pues una de
las fotos es elegirla como foto de perfil de la maquinaria".

Mismo mecanismo que PersonIdentity.avatar_document (document_explorer
0087, S105): nunca reasigna el tipo del documento elegido. Campo
nullable, sin valor que rellenar en las filas existentes.
"""
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("fleet", "0009_active_from_owner_pdf_s117"),
        ("document_explorer", "0137_tipos_maquinas_cierre_fase1_s117"),
    ]

    operations = [
        migrations.AddField(
            model_name="machineasset",
            name="avatar_document",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to="document_explorer.documentindexentry",
                verbose_name="Documento-imagen usado como foto de la máquina",
            ),
        ),
    ]
