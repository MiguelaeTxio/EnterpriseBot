# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0127_limpia_etiquetas_dominio_s114.py
"""
H31 (S114). Miguel Ángel, viendo el listado real de circulares: "las
cosas internas confunden a los usuarios" -- las choices de `domain`
("Empresa y obra (CompanyWorksite, H30 S58)", "EPI (EpiItemCatalog,
H31 S95)") llevaban colada una nota interna de desarrollo (modelo
relacionado + hito/sesión de origen) en una etiqueta que se muestra
tal cual en el panel (columna "Dominio" del listado de circulares).

Solo metadatos de choices -- ningún valor almacenado cambia (siguen
siendo "COMPANY"/"EPI" en BD), solo el texto legible que Django
muestra para cada opción.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0126_is_notification_template_y_circulares_nuevas_s114"),
    ]

    operations = [
        migrations.AlterField(
            model_name="documenttypecatalog",
            name="domain",
            field=models.CharField(
                choices=[
                    ("MACHINE", "Maquinaria"),
                    ("PERSONAL", "Personal"),
                    ("BOTH", "Ambos"),
                    ("COMPANY", "Empresa y obra"),
                    ("EPI", "EPI"),
                ],
                default="BOTH",
                max_length=8,
                verbose_name="Dominio",
                help_text="A qué tipo de entidad aplica este tipo documental.",
            ),
        ),
    ]
