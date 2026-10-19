# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0188_remove_jobposition_scope_s130.py
# S130: se retira el ámbito de los requisitos (0187). Miguel Ángel: "no
# era requisitos, me equivoqué, era dossieres y estaba bien" -- el
# catálogo de requisitos vuelve a ser único (decisión de S119).

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0187_jobposition_scope_s130"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="jobposition",
            name="scope",
        ),
    ]
