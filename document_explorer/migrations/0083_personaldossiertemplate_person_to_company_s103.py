# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0083_personaldossiertemplate_person_to_company_s103.py
"""
H31 (S103). Corrige un error real de diseño detectado por Miguel
Ángel apenas desplegada la migración 0082: `PersonalDossierTemplate`
ataba la plantilla a UNA persona, pero la intención real es que sea
reutilizable por CUALQUIER supervisor/administrador de la empresa
sobre CUALQUIER trabajador -- "documentos como el DNI o la tarjeta de
conducción estén en plantillas y luego se añadan los documentos que
son específicos de cada trabajador [...] las plantillas deben servir
tb para cualquier supervisor y administrador".

Primero borra las plantillas existentes (RunPython) -- en este punto
solo hay, como mucho, una fila de prueba real creada por Miguel Ángel
minutos antes mientras probaba el mecanismo anterior; no es un dato
de negocio que merezca preservarse bajo un diseño que ya no existe.
Con la tabla vacía, RemoveField(person) + AddField(company NOT NULL)
no necesita ningún valor de relleno.

Reversible solo a nivel de esquema (vuelve a dejar el campo `person`,
NULL por defecto) -- las plantillas borradas en el forward no se
recuperan en el reverse, igual que cualquier RunPython de borrado de
este proyecto.
"""
import django.db.models.deletion
from django.db import migrations, models


def delete_existing_templates(apps, schema_editor):
    PersonalDossierTemplate = apps.get_model(
        "document_explorer", "PersonalDossierTemplate",
    )
    PersonalDossierTemplate.objects.all().delete()


def noop_reverse(apps, schema_editor):
    # No hay nada que reconstruir: las plantillas borradas en el
    # forward eran datos de prueba, no un histórico a restaurar.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0082_personaldossiertemplate_s103"),
        ("ivr_config", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(delete_existing_templates, noop_reverse),
        migrations.RemoveField(
            model_name="personaldossiertemplate",
            name="person",
        ),
        migrations.AddField(
            model_name="personaldossiertemplate",
            name="company",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="dossier_templates",
                to="ivr_config.company",
                verbose_name="Empresa",
                help_text=(
                    "Compartida por todos los supervisores/"
                    "administradores de esta empresa -- nunca atada a "
                    "una persona concreta."
                ),
            ),
            preserve_default=False,
        ),
        migrations.AlterModelOptions(
            name="personaldossiertemplate",
            options={
                "ordering": ["company_id", "created_at"],
                "verbose_name": "Plantilla de dossier",
                "verbose_name_plural": "Plantillas de dossier",
            },
        ),
    ]
