# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0155_bigautofield_ids_s121.py
"""
H30 (S121, punto 3 de la hoja de ruta). Los 11 modelos de
document_explorer creados cuando la app aún generaba AutoField pasan a
BigAutoField, como ya espera el código (DEFAULT_AUTO_FIELD y
DocumentExplorerConfig.default_auto_field = BigAutoField). Desde que
cambió ese valor por defecto, makemigrations --check detectaba estos
11 cambios en cada verificación.

No es una reparación de tablas (com-migrations §3): la BD y el
historial de migraciones coincidían (int); lo que divergía era el
código. Migración normal con cambio de esquema.

Medido en producción antes de escribirla (consulta real S121): las 11
columnas id son int, y las 13 columnas FK que las apuntan también --
incluidas document_explorer_personidentity.job_position_id y
fleet_machineasset.document_requirement_id. Django las pasa todas a
bigint en esta misma migración (suelta y vuelve a crear las 13
restricciones FK). Tablas pequeñas (la mayor, epidelivery, ~2.875
filas).

Verificado en MySQL 8 local con datos enlazados: los enlaces
(persona -> puesto, entrega -> EPI, máquina -> requisito documental) se
conservan, las 13 FK se recrean, la vuelta atrás funciona y
makemigrations --check queda sin cambios.
"""
from django.db import migrations, models

MODELS = (
    "companyfiscalprofile",
    "documentacknowledgment",
    "documenttag",
    "epidelivery",
    "epideliverybatchtemplate",
    "epiitemcatalog",
    "epireview",
    "jobposition",
    "personaldossiertemplate",
    "persongrouptemplate",
    "subjectdocumentreference",
)


class Migration(migrations.Migration):

    dependencies = [
        (
            "document_explorer",
            "0154_lifting_accessory_models_traceability_s121",
        ),
    ]

    operations = [
        migrations.AlterField(
            model_name=model_name,
            name="id",
            field=models.BigAutoField(
                auto_created=True,
                primary_key=True,
                serialize=False,
                verbose_name="ID",
            ),
        )
        for model_name in MODELS
    ]
