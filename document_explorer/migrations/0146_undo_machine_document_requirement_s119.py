# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0146_undo_machine_document_requirement_s119.py
"""
H30 (S119). REVIERTE la 0145: borra el modelo
`MachineDocumentRequirement` -- diseño equivocado corregido en la
propia sesión antes de tener ninguna fila real ni ningún uso (0
máquinas con el campo relleno, verificado con consulta real). Ver
docstring completo de la migración fleet 0014, que quita el FK que
apuntaba a este modelo (debe aplicarse antes que esta, de ahí la
dependencia).

Un requisito de documentación es UNO SOLO (`JobPosition`, ya existente
desde S109) y sirve tanto para `PersonIdentity` como para
`MachineAsset` -- nunca dos catálogos separados por dominio.
"""
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0145_machine_document_requirement_s119"),
        ("fleet", "0014_undo_machine_document_requirement_s119"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="machinedocumentrequirement",
            name="created_by",
        ),
        migrations.RemoveField(
            model_name="machinedocumentrequirement",
            name="required_document_types",
        ),
        migrations.DeleteModel(
            name="MachineDocumentRequirement",
        ),
    ]
