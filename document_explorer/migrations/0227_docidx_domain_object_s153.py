# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0227_docidx_domain_object_s153.py
"""
S153. Index to find the documents of one person or machine.
---
S153. Índice para encontrar los documentos de una persona o máquina.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("contenttypes", "0002_remove_content_type_name"),
        ("document_explorer", "0226_person_emergency_contact_s153"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="documentindexentry",
            index=models.Index(
                fields=["domain_content_type", "domain_object_id"],
                name="docidx_domain_object",
            ),
        ),
    ]
