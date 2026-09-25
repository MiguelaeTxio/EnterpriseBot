# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/fleet/migrations/0014_undo_machine_document_requirement_s119.py
"""
H30 (S119). REVIERTE la 0013: quita
MachineAsset.document_requirement (FK a
document_explorer.MachineDocumentRequirement).

Diseño equivocado corregido en la propia sesión, antes de que nadie
llegara a usarlo (0 máquinas tenían el campo relleno, verificado con
consulta real): Miguel Ángel, verbatim, "los requisitos documentales
no son ni para personas ni para máquinas [...] la gestión de
requisitos documentales es global [...] no tenemos que tener un
arreglo para máquinas y un arreglo para personas". Un requisito de
documentación es UNO SOLO (`JobPosition`, sin filtro de dominio en su
selector de tipos) y se asigna tanto a `PersonIdentity` como a
`MachineAsset` -- ver la migración siguiente, que vuelve a añadir
`MachineAsset.document_requirement`, esta vez apuntando a
`document_explorer.JobPosition`.

Debe aplicarse ANTES de que `document_explorer` borre el modelo
`MachineDocumentRequirement` (0146) -- por eso esa migración depende
de esta.
"""
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("fleet", "0013_machineasset_document_requirement_s119"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="machineasset",
            name="document_requirement",
        ),
    ]
