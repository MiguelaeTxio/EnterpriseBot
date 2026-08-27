# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0063_personidentity_address_dates_s76.py
"""
H31 (S76). Dirección postal (calle/código postal/población/provincia)
+ fecha de alta/baja en la empresa en PersonIdentity -- Miguel Ángel,
verbatim: "echo en falta la dirección [...] no tenemos dirección,
población, código postal, provincia [...] fecha de alta, fecha de
baja." A diferencia de los campos "(Excel)" ya existentes (phone,
email, employer_company...), estos NO vienen del Excel de plantilla
-- se editan directamente desde el panel (ver PersonalUpdateView.
EDITABLE_FIELDS). Todos en blanco por defecto -- sin backfill, sin
inventar fechas retroactivas para el histórico ya existente.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0062_person_identity_audit_fixes_s74"),
    ]

    operations = [
        migrations.AddField(
            model_name="personidentity",
            name="address_street",
            field=models.CharField(
                max_length=200, blank=True, verbose_name="Dirección",
            ),
        ),
        migrations.AddField(
            model_name="personidentity",
            name="postal_code",
            field=models.CharField(
                max_length=10, blank=True, verbose_name="Código postal",
            ),
        ),
        migrations.AddField(
            model_name="personidentity",
            name="city",
            field=models.CharField(
                max_length=100, blank=True, verbose_name="Población",
            ),
        ),
        migrations.AddField(
            model_name="personidentity",
            name="province",
            field=models.CharField(
                max_length=100, blank=True, verbose_name="Provincia",
            ),
        ),
        migrations.AddField(
            model_name="personidentity",
            name="hire_date",
            field=models.DateField(
                null=True, blank=True,
                verbose_name="Fecha de alta en la empresa",
            ),
        ),
        migrations.AddField(
            model_name="personidentity",
            name="termination_date",
            field=models.DateField(
                null=True, blank=True,
                verbose_name="Fecha de baja en la empresa",
            ),
        ),
    ]
