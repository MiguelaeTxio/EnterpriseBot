# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0185_remove_dossiertemplate_is_active_s128.py
"""
H30 (S128). Retira PersonalDossierTemplate.is_active ("Plantilla
activa", S106). Miguel Ángel: "quiero eliminar lo de plantilla activa
[...] pero sí quiero poder seleccionar [...] el dossier y que nos diga".
El gestor carga la plantilla al pulsarla; la marca solo servía para
eso y no se usaba en ningún otro sitio. Se pierde únicamente qué
plantilla estaba marcada, no ninguna plantilla ni sus tipos.
"""
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0184_jobposition_is_active_s128"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="personaldossiertemplate",
            name="is_active",
        ),
    ]
