# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/ivr_config/migrations/0059_companyuser_payslip_uploader_s153.py
# S153 (H24, nóminas): `CompanyUser.payslip_uploader` -- solo quien lo
# tiene sube entregas de nóminas. Miguel Ángel: "Sólo cargan Jerónimo y
# Alejandro. Yo para pruebas." Se marca a jeronimo, alejandro_sergio y
# alvarez_admin.

from django.db import migrations, models

UPLOADER_USERNAMES = ("jeronimo", "alejandro_sergio", "alvarez_admin")


def mark_uploaders(apps, schema_editor):
    """
    Jerónimo, Alejandro and Miguel Ángel (tests) upload payslips.
    ---
    Cargan nóminas Jerónimo, Alejandro y Miguel Ángel (pruebas).
    """
    company_user = apps.get_model("ivr_config", "CompanyUser")
    company_user.objects.filter(
        user__username__in=UPLOADER_USERNAMES,
    ).update(payslip_uploader=True)


def noop(apps, schema_editor):
    """
    Nothing to undo: the column goes away with the field.
    ---
    Nada que deshacer: la columna desaparece con el campo.
    """


class Migration(migrations.Migration):

    dependencies = [
        ("ivr_config", "0058_companyuser_payslip_full_access_s153"),
    ]

    operations = [
        migrations.AddField(
            model_name="companyuser",
            name="payslip_uploader",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "Puede subir entregas de nóminas y dar acceso a cada "
                    "una a los supervisores que deban enviarlas."
                ),
                verbose_name="Carga nóminas",
            ),
        ),
        migrations.RunPython(mark_uploaders, noop),
    ]
