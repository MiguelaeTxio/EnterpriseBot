# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/fleet/migrations/0006_machineasset_excel_fields.py
"""
H30 (S54). Persistencia real de la hoja MAQUINARIA del Excel de
administración (EXEL_TRABAJADORES.xlsx, subido por Miguel Angel en
S54). insurance_info se guarda como texto libre porque el Excel real
mezcla aseguradora+fecha en una sola celda (p.ej. "AXA 31/12/2026").
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("fleet", "0005_add_first_repair_to_machineasset"),
    ]

    operations = [
        migrations.AddField(
            model_name="machineasset",
            name="itv_date",
            field=models.DateField(
                blank=True, null=True, verbose_name="Última ITV (Excel)",
            ),
        ),
        migrations.AddField(
            model_name="machineasset",
            name="itv_next_appointment",
            field=models.DateField(
                blank=True, null=True, verbose_name="Próxima cita ITV (Excel)",
            ),
        ),
        migrations.AddField(
            model_name="machineasset",
            name="insurance_info",
            field=models.CharField(
                blank=True,
                help_text="Texto libre tal como viene en el Excel real (aseguradora + fecha en la misma celda, p.ej. 'AXA 31/12/2026').",
                max_length=100,
                verbose_name="Seguro (Excel)",
            ),
        ),
        migrations.AddField(
            model_name="machineasset",
            name="oca_date",
            field=models.DateField(
                blank=True, null=True, verbose_name="Inspección OCA (Excel)",
            ),
        ),
        migrations.AddField(
            model_name="machineasset",
            name="excel_imported_at",
            field=models.DateTimeField(
                blank=True,
                null=True,
                verbose_name="Última importación real del Excel",
            ),
        ),
    ]
