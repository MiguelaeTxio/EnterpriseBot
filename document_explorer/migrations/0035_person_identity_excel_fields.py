# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0035_person_identity_excel_fields.py
"""
H30 (S54). Persistencia real del Excel de administración de
trabajadores (EXEL_TRABAJADORES.xlsx, subido por Miguel Angel en
S54), cerrando el pendiente abierto desde S043 (cruce puntual sin
persistir -- "70/70 personas... nunca se capturo como dato duradero").

is_active_employee es nullable a proposito: None = todavia sin
cruzar contra el Excel real, nunca se confunde con un False real.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0034_correct_estiba_plataformas_domain"),
    ]

    operations = [
        migrations.AddField(
            model_name="personidentity",
            name="is_active_employee",
            field=models.BooleanField(
                blank=True,
                default=None,
                help_text="None = todavia no cruzado contra el Excel real de plantilla. True/False = resultado real del ultimo import_worker_machine_excel por DNI.",
                null=True,
                verbose_name="Empleado activo (Excel de plantilla)",
            ),
        ),
        migrations.AddField(
            model_name="personidentity",
            name="employer_company",
            field=models.CharField(
                blank=True,
                help_text="Columna EMPRESA del Excel real (p.ej. GRUAS ADOLFO ALVAREZ SL, TRANSGRUAL SL) -- que hoja/empresa real lo recoge, no una etiqueta calculada.",
                max_length=100,
                verbose_name="Empresa (Excel)",
            ),
        ),
        migrations.AddField(
            model_name="personidentity",
            name="dni_expiry_date",
            field=models.DateField(
                blank=True, null=True, verbose_name="Caducidad DNI/NIE (Excel)",
            ),
        ),
        migrations.AddField(
            model_name="personidentity",
            name="driving_license_expiry_date",
            field=models.DateField(
                blank=True,
                null=True,
                verbose_name="Caducidad carnet de conducir (Excel)",
            ),
        ),
        migrations.AddField(
            model_name="personidentity",
            name="crane_operator_card_expiry_date",
            field=models.DateField(
                blank=True,
                null=True,
                verbose_name="Caducidad carnet de gruista (Excel)",
            ),
        ),
        migrations.AddField(
            model_name="personidentity",
            name="driver_qualification_card_expiry_date",
            field=models.DateField(
                blank=True,
                null=True,
                verbose_name="Caducidad tarjeta cualificación de conductor -- CAP (Excel)",
            ),
        ),
        migrations.AddField(
            model_name="personidentity",
            name="tachograph_card_expiry_date",
            field=models.DateField(
                blank=True,
                null=True,
                verbose_name="Caducidad tarjeta de tacógrafo (Excel)",
            ),
        ),
        migrations.AddField(
            model_name="personidentity",
            name="medical_exam_date",
            field=models.DateField(
                blank=True,
                null=True,
                verbose_name="Reconocimiento médico -- RM (Excel)",
            ),
        ),
        migrations.AddField(
            model_name="personidentity",
            name="ss_affiliation_number",
            field=models.CharField(
                blank=True,
                max_length=30,
                verbose_name="Número de afiliación SS (Excel)",
            ),
        ),
        migrations.AddField(
            model_name="personidentity",
            name="phone",
            field=models.CharField(
                blank=True, max_length=30, verbose_name="Teléfono (Excel)",
            ),
        ),
        migrations.AddField(
            model_name="personidentity",
            name="email",
            field=models.EmailField(
                blank=True,
                max_length=150,
                verbose_name="Correo electrónico (Excel)",
            ),
        ),
        migrations.AddField(
            model_name="personidentity",
            name="excel_imported_at",
            field=models.DateTimeField(
                blank=True,
                null=True,
                verbose_name="Última importación real del Excel",
            ),
        ),
    ]
