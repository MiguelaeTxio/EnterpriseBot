# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0125_rename_job_position_a_requisitos_documentacion_s113.py
"""
H31 (S113). Miguel Ángel: "el nombre tiene a confusión, porque en el
puesto lo que tenemos es [...] la documentación obligatoria por
puestos [...] habría que darle otro nombre". Confirmado el nuevo
nombre de cara al usuario: "Requisitos de documentación".

Solo metadatos (verbose_name/verbose_name_plural) -- ni la clase
JobPosition ni el campo job_position cambian de nombre en código,
ningún cambio real de columna ni de tabla.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0124_grualdi_fiscal_profile_y_fix_alias_transgrual_s113"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="jobposition",
            options={
                "ordering": ["name"],
                "verbose_name": "Requisito de documentación",
                "verbose_name_plural": "Requisitos de documentación",
            },
        ),
        migrations.AlterField(
            model_name="jobposition",
            name="name",
            field=models.CharField(max_length=150, unique=True, verbose_name="Nombre"),
        ),
        migrations.AlterField(
            model_name="jobposition",
            name="required_document_types",
            field=models.ManyToManyField(
                blank=True,
                related_name="job_positions",
                to="document_explorer.documenttypecatalog",
                verbose_name="Documentos obligatorios para este requisito",
            ),
        ),
        migrations.AlterField(
            model_name="personidentity",
            name="job_position",
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=models.SET_NULL,
                related_name="people",
                to="document_explorer.jobposition",
                verbose_name="Requisitos de documentación",
            ),
        ),
    ]
